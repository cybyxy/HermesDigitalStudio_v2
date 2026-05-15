#!/usr/bin/env python3
"""诊断：可选文本冒烟 → 截图 + prompt.submit → 流式与最终回复。

用法（在 backend 目录下）:
  .venv/bin/python scripts/diagnose_vision_turn.py
  .venv/bin/python scripts/diagnose_vision_turn.py /path/to/image.png
  .venv/bin/python scripts/diagnose_vision_turn.py --no-smoke          # 跳过文本冒烟，只测图
  .venv/bin/python scripts/diagnose_vision_turn.py --skip-gateway      # 只解析 config + native parts

默认：先在同一 session 发一条极短文本（验证 API Key / 模型可用），再发带附件的图片推理。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
VENDOR_HERMES = BACKEND_ROOT.parent / "vendor" / "hermes-agent"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(VENDOR_HERMES))

_print_lock = threading.Lock()


def _safe_print(*args, **kwargs) -> None:
    with _print_lock:
        print(*args, **kwargs)
        sys.stdout.flush()
        sys.stderr.flush()


def _credential_hint() -> None:
    keys = (
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "HERMES_API_KEY",
        "MINIMAX_API_KEY",
    )
    _safe_print("\n=== 环境里的 API 相关变量（是否已设置，不显示值）===", file=sys.stderr)
    for k in keys:
        v = os.environ.get(k, "").strip()
        _safe_print(f"  {k}: {'yes' if v else 'no'}", file=sys.stderr)


def _print_model_env_overrides() -> None:
    """子进程里 tui_gateway 会优先读这些环境变量，覆盖 config.yaml 的 default。"""
    keys = ("HERMES_MODEL", "HERMES_INFERENCE_MODEL", "HERMES_TUI_PROVIDER", "HERMES_INFERENCE_PROVIDER")
    _safe_print("\n=== 会覆盖 config 模型/提供商的环境变量（有值则优先生效）===", file=sys.stderr)
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            _safe_print(f"  {k}={v!r}", file=sys.stderr)
        else:
            _safe_print(f"  {k}: (未设置)", file=sys.stderr)


def _simulate_tui_gateway_resolve_model() -> tuple[str, str]:
    """复刻 vendor/hermes-agent/tui_gateway/server.py::_resolve_model() 的逻辑。"""
    env_m = (os.environ.get("HERMES_MODEL", "") or os.environ.get("HERMES_INFERENCE_MODEL", "")).strip()
    if env_m:
        return env_m, "环境变量 HERMES_MODEL 或 HERMES_INFERENCE_MODEL"
    try:
        import yaml
        from hermes_constants import get_config_path

        p = get_config_path()
        if p.exists():
            with p.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        m = data.get("model", "")
        if isinstance(m, dict):
            d = str(m.get("default", "") or "").strip()
            if d:
                return d, f"config.yaml model.default（文件: {p}）"
        if isinstance(m, str) and m.strip():
            return m.strip(), f"config.yaml model 标量（文件: {p}）"
    except Exception as e:
        return "anthropic/claude-sonnet-4", f"解析 config 失败 → hermes 硬编码默认（{e}）"
    return "anthropic/claude-sonnet-4", "config 中无 model.default / 无有效 model → hermes 硬编码默认 anthropic/claude-sonnet-4"


def _extract_model_block_lines(text: str) -> tuple[list[str] | None, str]:
    """按缩进取「看起来像」的 model: 块（纯文本，不解析 YAML）。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("model:") or line.strip() == "model:":
            start = i
            break
    if start is None:
        return None, ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j] and not lines[j][0].isspace():
            end = j
            break
    block_lines = lines[start:end]
    return block_lines, "\n".join(block_lines)


def _print_config_yaml_diagnostic(hermes_home: str) -> bool:
    """先展示 model 文本截取，再整文件 yaml.safe_load；失败则 hermes 不会用你写的 model。

    返回 True 表示整份 config.yaml 可被解析（与 hermes load_config 合并逻辑一致的前提）。
    """
    cfg_path = Path(hermes_home).expanduser() / "config.yaml"
    if not cfg_path.is_file():
        _safe_print(f"\n=== config.yaml 未找到: {cfg_path} ===", file=sys.stderr)
        return False
    try:
        text = cfg_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        _safe_print(f"\n=== 无法读取 config.yaml: {e} ===", file=sys.stderr)
        return False

    _safe_print(
        "\n【重要】下面「model 段」是把文件当纯文本按行截出来的，"
        "只有整份 YAML 能被解析时，hermes 才会真正采用其中的 provider/model/base_url。",
        file=sys.stderr,
    )
    block_lines, block = _extract_model_block_lines(text)
    if block_lines:
        redacted: list[str] = []
        for ln in block_lines:
            stripped = ln.strip()
            if stripped.startswith("api_key:") or stripped.startswith("api:"):
                redacted.append(ln.split(":")[0] + ": <redacted>")
            else:
                redacted.append(ln)
        _safe_print("\n=== ~/.hermes/config.yaml — model 段文本截取（api_key 已脱敏）===")
        _safe_print("\n".join(redacted))
    else:
        _safe_print("\n=== 文件中未找到顶层 model: 块 ===", file=sys.stderr)

    try:
        import yaml

        with cfg_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        _safe_print("\n" + "!" * 80, file=sys.stderr)
        _safe_print("✗ 整份 config.yaml YAML 解析失败 — hermes 会忽略该文件，回退到内置默认配置。", file=sys.stderr)
        _safe_print(f"  解析错误: {e}", file=sys.stderr)
        _safe_print(
            "  因此上面截取的 minimax / model 等**不会**生效；"
            "load_config() 里 model 为空 → resolve_runtime_provider 走默认（常见为 openrouter）。",
            file=sys.stderr,
        )
        _safe_print(
            "  请用编辑器打开 config.yaml，重点检查报错行附近的缩进、重复的键、未闭合的引号。",
            file=sys.stderr,
        )
        _safe_print("!" * 80 + "\n", file=sys.stderr)
        return False

    if not isinstance(data, dict):
        data = {}
    mc = data.get("model")
    _safe_print("\n=== YAML 解析成功 — 从解析结果读到的 model（hermes 会采用）===")
    if isinstance(mc, dict):
        _safe_print("  provider:", mc.get("provider"))
        _safe_print("  default:", mc.get("default") or mc.get("model"))
        _safe_print("  base_url:", mc.get("base_url"))
    elif isinstance(mc, str) and mc.strip():
        _safe_print("  model (scalar):", mc.strip())
    else:
        _safe_print("  (解析结果中无 model 键或为空)")
    return True


def _print_image_routing_hint() -> None:
    """打印本 turn 在 auto 下会走 native 还是 text（与 tui_gateway 一致）。"""
    try:
        from agent.auxiliary_client import _read_main_model, _read_main_provider
        from agent.image_routing import decide_image_input_mode
        from hermes_cli.config import load_config

        cfg = load_config()
        mode = decide_image_input_mode(_read_main_provider(), _read_main_model(), cfg)
        img_cfg = ((cfg.get("agent") or {}) if isinstance(cfg, dict) else {}).get("image_input_mode", "auto")
        _safe_print("\n=== 用户附件图片路由（image_routing）===")
        _safe_print("  config agent.image_input_mode:", img_cfg)
        _safe_print("  本 turn 将使用:", mode, "(native=主模型直接看图; text=先 vision_analyze)")
        if os.environ.get("HERMES_GATEWAY_NATIVE_IMAGES", "").strip().lower() in ("1", "true", "yes"):
            _safe_print("  注意: 子进程若设置 HERMES_GATEWAY_NATIVE_IMAGES=1，gateway 会强制 native。")
    except Exception as ex:
        _safe_print(f"\n=== image_routing 提示（解析失败: {ex}）===", file=sys.stderr)


def _print_inference_model_and_url() -> None:
    try:
        from hermes_cli.config import load_config
        from hermes_cli.runtime_provider import resolve_runtime_provider

        cfg = load_config()
        mc = cfg.get("model")
        model_default = ""
        provider_rq: str | None = None
        if isinstance(mc, str) and mc.strip():
            model_default = mc.strip()
        elif isinstance(mc, dict):
            model_default = (mc.get("default") or mc.get("model") or "").strip()
            provider_rq = (mc.get("provider") or "").strip() or None

        rt = resolve_runtime_provider(
            requested=provider_rq,
            target_model=model_default or None,
        )
        _safe_print("\n=== 推理模型与 API URL（config + env 解析）===")
        _safe_print("model（config）:", model_default or "(未设置)")
        _safe_print("provider（解析后）:", rt.get("provider"))
        _safe_print("API base_url:", rt.get("base_url") or "(空)")
        _safe_print("api_mode:", rt.get("api_mode"))
        _safe_print("credential source:", rt.get("source"))
        key = str(rt.get("api_key") or "")
        if key and key not in ("no-key-required", "dummy-key"):
            _safe_print("api_key 已解析: yes (masked)", f"{key[:6]}…{key[-4:]}" if len(key) > 10 else "(短)")
        else:
            _safe_print("api_key 已解析: no 或 placeholder — 易出现 401")
    except Exception as ex:
        _safe_print(f"\n=== 推理模型与 API URL（解析失败: {ex}）===", file=sys.stderr)


def _find_desktop_image(filename: str) -> Path | None:
    home = Path.home()
    for folder in ("Desktop", "桌面"):
        p = home / folder / filename
        if p.is_file():
            return p
    return None


def _print_native_parts(image: Path) -> None:
    from agent.image_routing import build_native_content_parts

    text = "（测试）请描述图片。"
    parts, skipped = build_native_content_parts(text, [str(image.resolve())])
    _safe_print("\n=== build_native_content_parts (hermes) ===")
    _safe_print("skipped paths:", skipped)
    for i, part in enumerate(parts):
        t = part.get("type")
        if t == "image_url":
            url = (part.get("image_url") or {}).get("url") or ""
            preview = url[:72] + "…" if len(url) > 72 else url
            _safe_print(f"  [{i}] image_url url_len={len(url)} preview={preview!r}")
        else:
            tx = str(part.get("text", ""))[:200]
            _safe_print(f"  [{i}] {t}: {tx!r}")


def _run_gateway_session(
    image: Path,
    image_prompt: str,
    hermes_home: str,
    *,
    quiet_stream: bool,
    run_smoke: bool,
    smoke_prompt: str,
    wait_timeout: float,
) -> int:
    from backend.gateway.gateway import SubprocessGateway

    gw = SubprocessGateway(hermes_home=hermes_home)
    gw.start()
    if not gw.is_alive():
        _safe_print("ERROR: gateway subprocess not alive after start", file=sys.stderr)
        return 2

    sid = gw.create_session(cols=120)
    _safe_print("\n=== session.create ===")
    _safe_print("session_id:", sid)
    if not sid:
        gw.close()
        return 3

    done = threading.Event()
    lock = threading.Lock()
    events: list[dict] = []
    session_info_printed = False

    # 当前 turn 的状态（每轮 submit 前重置）
    turn: dict[str, Any] = {
        "label": "",
        "streamed": "",
        "final": "",
        "reasoning": "",
        "err": "",
        "complete_status": "",
    }

    def on_event(ev: dict) -> None:
        nonlocal session_info_printed
        with lock:
            events.append(ev)
        et = ev.get("type") or ""
        payload = ev.get("payload") or {}
        if et == "session.info" and not session_info_printed:
            session_info_printed = True
            p = payload or {}
            u = p.get("usage") or {}
            _safe_print("\n=== 子进程 agent（session.info）===", file=sys.stderr)
            _safe_print("  model:", p.get("model"), file=sys.stderr)
            if isinstance(u, dict) and u.get("model"):
                _safe_print("  usage.model:", u.get("model"), file=sys.stderr)
        if et == "message.delta":
            chunk = str(payload.get("text", "") or "")
            turn["streamed"] += chunk
            if not quiet_stream and chunk:
                _safe_print(chunk, end="")
        elif et in ("thinking.delta", "reasoning.delta"):
            turn["reasoning"] += str(payload.get("text", "") or "")
        elif et == "message.complete":
            txt = payload.get("text")
            if txt is None:
                txt = turn["streamed"] or ""
            else:
                txt = str(txt)
            turn["final"] = txt
            turn["complete_status"] = str(payload.get("status") or "")
            done.set()
        elif et == "error":
            turn["err"] = str(payload.get("message", payload))
            done.set()

    gw.on_event(on_event)

    def _reset_turn(label: str) -> None:
        turn["label"] = label
        turn["streamed"] = ""
        turn["final"] = ""
        turn["reasoning"] = ""
        turn["err"] = ""
        turn["complete_status"] = ""
        done.clear()

    def _run_turn(label: str, prompt: str, attachments: list[str] | None, timeout: float) -> dict[str, Any]:
        _reset_turn(label)
        _safe_print(f"\n{'=' * 24} {label} {'=' * 24}")
        _safe_print("prompt:", prompt[:200] + ("…" if len(prompt) > 200 else ""))
        _safe_print("attachments:", attachments or "(无)")
        _safe_print("\n=== 流式输出 (message.delta) ===\n")

        t0 = time.monotonic()
        ok = gw.submit_prompt(sid, prompt, attachments=attachments)
        _safe_print(f"\n[submit streaming={ok}, 等待完成…]\n", file=sys.stderr)

        if not done.wait(timeout=timeout):
            return {
                "ok_wait": False,
                "label": label,
                "streamed": turn["streamed"],
                "final": turn["final"],
                "status": turn["complete_status"],
                "err": turn["err"] or "timeout",
                "wall": time.monotonic() - t0,
            }

        dt = time.monotonic() - t0
        st = turn["complete_status"]
        _safe_print("\n")
        _safe_print("-" * 80)
        _safe_print(f"[{label}] message.complete status={st!r} wall={dt:.2f}s")
        _safe_print("-" * 80)
        body = turn["final"] if str(turn["final"]).strip() else "(无正文)"
        _safe_print(body)
        _safe_print("-" * 80)
        return {
            "ok_wait": True,
            "label": label,
            "streamed": turn["streamed"],
            "final": turn["final"],
            "status": st,
            "err": turn["err"],
            "wall": dt,
        }

    last_rc = 0

    if run_smoke:
        r0 = _run_turn("文本冒烟（验证鉴权与模型）", smoke_prompt, None, min(wait_timeout, 120.0))
        if not r0["ok_wait"]:
            _safe_print("\n[文本冒烟超时]", file=sys.stderr)
            gw.close_session(sid)
            gw.close()
            return 4
        if r0["err"]:
            _safe_print("\n=== 文本冒烟 error 事件 ===", file=sys.stderr)
            _safe_print(r0["err"], file=sys.stderr)
            gw.close_session(sid)
            gw.close()
            return 5
        if r0["status"] != "complete" or not str(r0["final"]).strip():
            _safe_print("\n=== 文本冒烟未成功（status 或正文异常），请先修复鉴权/config ===", file=sys.stderr)
            gw.close_session(sid)
            gw.close()
            return 6
        _safe_print("\n>>> 文本链路正常，继续图片推理 <<<\n", file=sys.stderr)

    r1 = _run_turn("图片推理", image_prompt, [str(image.resolve())], wait_timeout)

    if not r1["ok_wait"]:
        gw.interrupt(sid)
        last_rc = 4
    elif r1["err"]:
        _safe_print("\n=== SSE error（图片阶段）===", file=sys.stderr)
        _safe_print(r1["err"], file=sys.stderr)
        last_rc = 5
    elif r1["status"] != "complete":
        last_rc = 6
    elif not str(r1["final"]).strip():
        last_rc = 7
    else:
        last_rc = 0

    _safe_print("\n=== message.complete 摘要（最后一轮）===", file=sys.stderr)
    for ev in reversed(events):
        if ev.get("type") == "message.complete":
            p = ev.get("payload") or {}
            _safe_print(
                json.dumps(
                    {k: p.get(k) for k in ("status", "error", "warning")},
                    ensure_ascii=False,
                    default=str,
                ),
                file=sys.stderr,
            )
            break

    _safe_print("\n=== session.history 最后一条 assistant ===", file=sys.stderr)
    hist = gw.session_history(sid) or []
    for row in reversed(hist):
        if row.get("role") == "assistant":
            content = row.get("content", "")
            preview = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)[:2000]
            _safe_print(preview, file=sys.stderr)
            break

    gw.close_session(sid)
    gw.close()
    return last_rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Text smoke (optional) + image vision turn via hermes gateway")
    parser.add_argument("image", nargs="?", default="截屏2026-05-07 15.43.30.png")
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    parser.add_argument(
        "--prompt",
        default="请用两到三句话描述这张截图里可见的主要内容。若图中有明显文字，请概括其主题。",
        help="图片阶段的用户提示",
    )
    parser.add_argument(
        "--smoke-prompt",
        default="只回复一个词：pong（不要其它任何字符或解释）。",
        help="文本冒烟阶段的提示（用于验证 API）",
    )
    parser.add_argument("--no-smoke", action="store_true", help="跳过文本冒烟，只提交图片")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--quiet-stream", action="store_true")
    parser.add_argument("--timeout", type=float, default=420.0, help="单次 submit 最长等待秒数")
    args = parser.parse_args()

    hh = str(Path(args.hermes_home).expanduser())
    os.environ["HERMES_HOME"] = hh

    from hermes_cli.env_loader import load_hermes_dotenv

    loaded = load_hermes_dotenv(hermes_home=hh, project_env=VENDOR_HERMES / ".env")
    _safe_print("已加载 dotenv 文件数:", len(loaded), file=sys.stderr)
    for p in loaded:
        _safe_print("  -", p, file=sys.stderr)
    _credential_hint()
    _print_model_env_overrides()
    yaml_ok = _print_config_yaml_diagnostic(hh)
    sim_model, sim_reason = _simulate_tui_gateway_resolve_model()
    _safe_print("\n=== 子进程 session.info 里的 model 从哪来（= tui_gateway._resolve_model）===")
    _safe_print("  解析结果 model:", sim_model)
    _safe_print("  原因:", sim_reason)
    if not yaml_ok and sim_model == "anthropic/claude-sonnet-4":
        _safe_print(
            "  提示: 若你期望 MiniMax 等，请先修好整份 config.yaml 的 YAML；"
            "并检查 shell 里是否 export 了 HERMES_MODEL=anthropic/claude-sonnet-4。",
            file=sys.stderr,
        )

    raw = Path(args.image).expanduser()
    if raw.is_file():
        image = raw.resolve()
    else:
        found = _find_desktop_image(args.image)
        if found is None:
            _safe_print(f"ERROR: 找不到图片: {args.image!r}", file=sys.stderr)
            return 1
        image = found.resolve()

    _safe_print("=== image ===")
    _safe_print(image)
    _safe_print("size_bytes:", image.stat().st_size)

    _print_inference_model_and_url()
    _print_image_routing_hint()
    _print_native_parts(image)

    if args.skip_gateway:
        _safe_print("\n(--skip-gateway)")
        return 0

    return _run_gateway_session(
        image,
        args.prompt,
        hh,
        quiet_stream=args.quiet_stream,
        run_smoke=not args.no_smoke,
        smoke_prompt=args.smoke_prompt,
        wait_timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
