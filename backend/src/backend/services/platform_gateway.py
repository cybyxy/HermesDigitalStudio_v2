"""Hermes 消息网关（GatewayRunner）与 Studio 的集成。

Studio 内每个 Agent 由 ``SubprocessGateway`` + ``tui_gateway`` 子进程承载；
Telegram/飞书等平台收发由 vendor 里的 ``gateway.run:GatewayRunner`` 负责。
二者共享 ``HERMES_HOME`` / ``~/.hermes/config.yaml``（主 Agent / default profile 即根目录）。

**默认**：FastAPI lifespan 会尝试拉起嵌入式 ``gateway.run``，使主环境 ``platforms.*`` 生效。
**跳过**：已存在 ``gateway.pid``（独立 ``hermes gateway``）或设置 ``HERMES_STUDIO_NO_EMBEDDED_GATEWAY=1``。

嵌入式子进程默认优先使用 ``backend/.venv/bin/python``（与 ``uv sync`` 一致），避免用系统
``python3`` 启动 Studio 时子进程缺 ``lark-oapi``。可用 ``HERMES_STUDIO_GATEWAY_PYTHON`` 覆盖。

分终端调试：``HERMES_STUDIO_NO_EMBEDDED_GATEWAY=1`` 启动 Studio，另开终端运行
``backend/scripts/run_messaging_gateway.py`` 或 ``scripts/dev-messaging-gateway.sh``。

仍支持显式仅环境变量开启的旧行为：``HERMES_STUDIO_EMBEDDED_GATEWAY=1`` + lifespan 里 ``require_env=True``（当前默认已改为自动启，一般不必再设）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.config import get_config

_log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_DIR.parent
_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"

_proc: Optional[subprocess.Popen[bytes]] = None


def _backend_venv_python() -> Optional[Path]:
    """``backend/.venv`` 下的解释器（与 ``uv sync`` 安装依赖的环境一致）。"""
    if sys.platform == "win32":
        p = _BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        p = _BACKEND_DIR / ".venv" / "bin" / "python"
    return p if p.is_file() else None


def _resolved_gateway_python() -> str:
    """用于启动嵌入式消息网关的解释器。

    若用系统 ``python3 main.py`` 启动 Studio，``sys.executable`` 往往没有 ``lark-oapi``；
    此时只要仓库里已有 ``backend/.venv``（``uv sync`` 过），则强制用该 venv，与
    ``hermes-agent[feishu]`` 依赖对齐。

    覆盖：环境变量 ``HERMES_STUDIO_GATEWAY_PYTHON`` 指向可执行文件时优先使用。
    """
    override = get_config().gateway_python
    if override:
        o = Path(override)
        if o.is_file():
            return str(o)
        _log.warning("HERMES_STUDIO_GATEWAY_PYTHON 无效（不是文件），忽略: %s", override)
    venv_py = _backend_venv_python()
    if venv_py is not None:
        cur = Path(sys.executable).resolve()
        if cur != venv_py.resolve():
            _log.info(
                "嵌入式消息网关改用 backend/.venv 解释器（与 uv sync 依赖一致），"
                "而非当前 Studio 进程: %s",
                venv_py,
            )
        return str(venv_py)
    return sys.executable


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _embedded_gateway_enabled() -> bool:
    return _truthy_env("HERMES_STUDIO_EMBEDDED_GATEWAY")


def _embedded_gateway_opt_out() -> bool:
    """为真时 lifespan 不自动启动嵌入式网关（用户自行跑 ``hermes gateway`` 时用）。"""
    return get_config().no_embedded_gateway


def _ensure_vendor_on_path() -> None:
    v = str(_VENDOR_ROOT)
    if v not in sys.path:
        sys.path.insert(0, v)


def _running_pid_from_hermes() -> Optional[int]:
    """读取 ~/.hermes/gateway.pid（与 vendor gateway 一致）。"""
    try:
        _ensure_vendor_on_path()
        from gateway.status import get_running_pid

        return get_running_pid()
    except Exception as e:
        _log.debug("get_running_pid unavailable: %s", e)
        return None


def _build_gateway_subprocess_code() -> str:
    """在子进程内插入 vendor 路径并 ``asyncio.run(start_gateway())``。

    ``verbosity=1``：网关会向 stderr 安装 INFO 级 ``StreamHandler``；默认 ``0`` 只有
    WARNING+，而 ``Connecting to feishu...`` 等关键行是 INFO，否则 Studio 终端里
    看不到任何 ``[hermes-gateway]`` 前缀日志。
    """
    root = str(_REPO_ROOT)
    return f"""import asyncio, sys
from pathlib import Path
_root = Path({root!r})
sys.path.insert(0, str(_root / "vendor" / "hermes-agent"))
from gateway.run import start_gateway
ok = asyncio.run(start_gateway(verbosity=1))
raise SystemExit(0 if ok else 1)
"""


def _drain_gateway_subprocess_output(proc: subprocess.Popen[bytes]) -> None:
    """后台读取子进程合并输出（stdout+stderr），避免 PIPE 写满阻塞；打到 Studio logger。

    使用 INFO：与 uvicorn 默认 ``--log-level info`` 一致；网关子进程里既有 INFO 也有
    WARNING/ERROR，统一前缀便于检索 ``[hermes-gateway]``。
    """

    def _run() -> None:
        stream = proc.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, b""):
                if not line:
                    break
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    text = repr(line)
                if text:
                    _log.info("[hermes-gateway] %s", text)
        except Exception as e:
            _log.debug("gateway subprocess output drain ended: %s", e)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t = threading.Thread(target=_run, name="hermes-gateway-output", daemon=True)
    t.start()


def start_embedded_gateway(
    *,
    force: bool = False,
    require_env: bool = False,
    from_lifespan: bool = False,
) -> Dict[str, Any]:
    """启动嵌入式消息网关子进程（若已存在外部网关且未 force 则跳过）。

    :param require_env: 为 True 时仅当 ``HERMES_STUDIO_EMBEDDED_GATEWAY`` 为真才启动（旧式显式开关）。
    :param from_lifespan: 为 True 时表示 Studio 默认自启；尊重 ``HERMES_STUDIO_NO_EMBEDDED_GATEWAY``。
    """
    global _proc

    if require_env and not _embedded_gateway_enabled():
        return {"ok": True, "skipped": True, "reason": "env_not_enabled"}

    if from_lifespan and _embedded_gateway_opt_out():
        return {"ok": True, "skipped": True, "reason": "opt_out_no_embedded"}

    if _proc is not None and _proc.poll() is None:
        return {"ok": True, "skipped": True, "reason": "already_running_embedded", "pid": _proc.pid}

    ext = _running_pid_from_hermes()
    if ext is not None and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "external_gateway_pid_file",
            "pid": ext,
        }

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_VENDOR_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # 子进程 stderr 接管道时多为块缓冲；无缓冲便于尽快在 Studio 终端看到网关行
    env["PYTHONUNBUFFERED"] = "1"

    py = _resolved_gateway_python()
    if _backend_venv_python() is None and not get_config().gateway_python:
        _log.info(
            "未找到 backend/.venv，嵌入式网关使用当前解释器（飞书需 lark-oapi 时请在 backend 目录执行 uv sync 生成 .venv）"
        )

    code = _build_gateway_subprocess_code()
    _proc = subprocess.Popen(
        [py, "-u", "-c", code],
        cwd=str(_VENDOR_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _drain_gateway_subprocess_output(_proc)
    _log.info("Embedded Hermes messaging gateway started pid=%s", _proc.pid)
    return {"ok": True, "skipped": False, "pid": _proc.pid}


def stop_embedded_gateway() -> Dict[str, Any]:
    """仅终止由本模块启动的子进程，不杀用户手动起的独立 gateway。"""
    global _proc
    if _proc is None:
        return {"ok": True, "stopped": False, "reason": "not_started_by_studio"}

    if _proc.poll() is not None:
        _proc = None
        return {"ok": True, "stopped": False, "reason": "already_exited"}

    _proc.terminate()
    try:
        _proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _proc.kill()
        _proc.wait(timeout=5)
    pid = _proc.pid
    _proc = None
    _log.info("Embedded Hermes messaging gateway stopped (was pid=%s)", pid)
    return {"ok": True, "stopped": True, "pid": pid}


def gateway_runtime_status() -> Dict[str, Any]:
    """合并：Studio 托管子进程状态 + gateway.pid 文件状态。"""
    global _proc
    embedded_pid: Optional[int] = None
    embedded_alive = False
    if _proc is not None and _proc.poll() is None:
        embedded_pid = _proc.pid
        embedded_alive = True

    file_pid = _running_pid_from_hermes()
    return {
        "embeddedEnabled": _embedded_gateway_enabled(),
        "embeddedAutoStart": not _embedded_gateway_opt_out(),
        "embeddedStudioPid": embedded_pid,
        "embeddedAlive": embedded_alive,
        "hermesGatewayPidFile": file_pid,
    }


def restart_embedded_gateway_after_channel_change() -> Dict[str, Any]:
    """在 ~/.hermes/config.yaml 中 platforms.* 变更后，重启 Studio 嵌入式网关以重新执行各平台 connect()。

    - 若用户显式关闭嵌入式网关（HERMES_STUDIO_NO_EMBEDDED_GATEWAY），则不操作。
    - 若当前由独立 ``hermes gateway`` 占用（gateway.pid 指向存活外部进程），则只返回提示，不尝试再启嵌入式实例。
    """
    if _embedded_gateway_opt_out():
        return {
            "ok": True,
            "restarted": False,
            "reason": "opt_out_no_embedded",
            "hint": "已写入通道配置。请自行重启 Hermes 消息网关以加载 platforms。",
        }

    stop_embedded_gateway()
    ext = _running_pid_from_hermes()
    if ext is not None:
        return {
            "ok": True,
            "restarted": False,
            "reason": "external_gateway_running",
            "pid": ext,
            "hint": "已写入通道配置。检测到独立 Hermes 消息网关正在运行，请重启该进程以加载新配置。",
        }

    started = start_embedded_gateway(from_lifespan=True)
    restarted = not started.get("skipped")
    return {
        "ok": bool(started.get("ok", True)),
        "restarted": restarted,
        "gateway": started,
    }
