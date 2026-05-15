"""@-handoff / relay 解析 — 与 HermesBungalow ``handoff_parser.py`` 及前端 ``gameApi.ts`` 对齐。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

USER_RELAY_RE = re.compile(r"^/relay\s+(\S+)\s*\|\s*([\s\S]+)$", re.I)
USER_AT_PIPE_RE = re.compile(r"^@([^\s|@\n]+)\s*[|｜]\s*([\s\S]+)$")
# 中文键盘常见「：」与英文「:」
USER_AT_COLON_RE = re.compile(r"^@([^\s|@\n]+)\s*[：:]\s*([\s\S]+)$")
USER_AT_SPACE_RE = re.compile(r"^@([^\s|@\n]+)\s+([\s\S]+)$")


def is_broadcast_all_handoff_token(token: str) -> bool:
    t = (token or "").strip()
    return t == "所有人" or t.lower() == "all"


def normalize_handoff_input(text: str | None) -> str:
    """去掉 BOM / 零宽字符；全角 ``＠``→``@``；兼容空白；NFKC 消解常见「复制即变体」字符。"""
    t = text or ""
    t = t.replace("\ufeff", "")
    for ch in ("\u200b", "\u200c", "\u200d", "\u2060"):
        t = t.replace(ch, "")
    # 全角 COMMERCIAL AT（微信 / 部分输入法 / 文档里常见）
    t = t.replace("\uff20", "@")
    t = t.replace("\u202f", " ").replace("\u00a0", " ")
    # 其它 Unicode 空白 → 普通空格，便于 ``@token 正文`` 的 ``\s+`` 匹配
    t = re.sub(r"[\u2000-\u200a\u3000]+", " ", t)
    try:
        t = unicodedata.normalize("NFKC", t)
    except Exception:
        pass
    return t.strip()


def relay_payload_from_handoff(leading: str, message: str) -> str:
    """多 Agent 规范：招呼写在正文前，独立 ``@`` 行指向同事 — 目标应看到前文 + @ 行后的说明。"""
    lead = (leading or "").strip()
    body = (message or "").strip()
    if lead and body:
        return f"{lead}\n\n{body}"
    return body


def _try_parse_handoff_block(block: str) -> dict[str, Any] | None:
    """对单段字符串尝试解析 handoff（整段须匹配，无多余前后缀）。"""
    raw = normalize_handoff_input(block)
    if not raw:
        return None
    m = USER_RELAY_RE.match(raw)
    if m:
        token = str(m.group(1) or "").strip()
        message = str(m.group(2) or "").strip()
        if token and message:
            return {"token": token, "message": message, "was_legacy_relay": True}
        return None
    m = USER_AT_PIPE_RE.match(raw)
    if m:
        token = str(m.group(1) or "").strip()
        message = str(m.group(2) or "").strip()
        if token and message:
            return {"token": token, "message": message, "was_legacy_relay": False}
        return None
    m = USER_AT_COLON_RE.match(raw)
    if m:
        token = str(m.group(1) or "").strip()
        message = str(m.group(2) or "").strip()
        if token and message:
            return {"token": token, "message": message, "was_legacy_relay": False}
        return None
    m = USER_AT_SPACE_RE.match(raw)
    if m:
        token = str(m.group(1) or "").strip()
        message = str(m.group(2) or "").strip()
        if token and message:
            return {"token": token, "message": message, "was_legacy_relay": False}
        return None
    return None


def parse_user_handoff_prefix(text: str) -> dict[str, Any] | None:
    """解析用户转发：整段 trim 后匹配；若不中则自底向上找首行 ``@`` / ``/relay``（多行前文人后单独一行 @ 的常见写法）。"""
    raw = normalize_handoff_input(text)
    direct = _try_parse_handoff_block(raw)
    if direct:
        return {**direct, "leading": ""}
    parts = raw.splitlines()
    for i in range(len(parts) - 1, -1, -1):
        line = parts[i].strip()
        if not line:
            continue
        if not (line.startswith("@") or line.lower().startswith("/relay")):
            continue
        hit = _try_parse_handoff_block(line)
        if not hit:
            continue
        leading = "\n".join(parts[:i]).strip()
        return {**hit, "leading": leading}
    return None


# ── Assistant 正文中的 @ 行（与 HermesBungalow ``parse_at_handoff_lines`` / ``parse_hermes_bungalow_invokes`` 对齐）──

def _norm_fullwidth_pipe_line(line: str) -> str:
    """将全角竖线 "｜"（U+FF5C）转换为半角竖线 "|"，便于统一解析。"""
    return line.replace("\uff5c", "|")


# 行内 token 不含 ``|`` / ``@``；正文用 ``.+`` / ``[\s\S]+`` 与 Bungalow 一致
_ASSIST_AT_PIPE = re.compile(r"^\s*@([^\s|@]+)\s*[|｜]\s*(.+)$")
_ASSIST_AT_COLON = re.compile(r"^\s*@([^\s|@]+)\s*[：:]\s*(.+)$")
_ASSIST_AT_SPACE = re.compile(r"^\s*@([^\s|@]+)\s+([\s\S]+)$")


def parse_assistant_invoke_lines(text: str | None) -> list[tuple[str, str]]:
    """逐行解析 assistant 中的 ``@target | msg`` / ``@target：msg`` / ``@target msg``。"""
    out: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = normalize_handoff_input(_norm_fullwidth_pipe_line(raw)).strip()
        if not line.startswith("@"):
            continue
        mp = _ASSIST_AT_PIPE.match(line)
        if not mp:
            mp = _ASSIST_AT_COLON.match(line)
        if not mp:
            mp = _ASSIST_AT_SPACE.match(line)
        if not mp:
            continue
        target = str(mp.group(1) or "").strip()
        message = str(mp.group(2) or "").strip()
        if target and message:
            out.append((target, message))
    return out


def parse_assistant_invokes(text: str | None) -> list[tuple[str, str]]:
    """去重后的同伴 @ 行列表（与 Bungalow ``parse_hermes_bungalow_invokes`` 等价）。"""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for t, msg in parse_assistant_invoke_lines(text):
        key = (t, msg)
        if key in seen:
            continue
        seen.add(key)
        out.append((t, msg))
    return out


def strip_assistant_invoke_lines(text: str | None) -> str:
    """去掉符合 handoff 形状的 ``@…`` 行（供同伴 payload 剥离）。"""
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = normalize_handoff_input(_norm_fullwidth_pipe_line(raw_line)).strip()
        if line.startswith("@") and (
            _ASSIST_AT_PIPE.match(line) or _ASSIST_AT_COLON.match(line) or _ASSIST_AT_SPACE.match(line)
        ):
            continue
        lines.append(raw_line)
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def expand_broadcast_invokes_studio(
    source_agent_id: str,
    invokes: list[tuple[str, str]],
    agents: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """将 ``@所有人`` / ``@all`` 展开为各同伴 profile token（与 Bungalow ``expand_broadcast_invokes_for_sender`` 对齐）。"""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tt, msg in invokes:
        t = str(tt).strip()
        m = str(msg).strip()
        if not t or not m:
            continue
        if is_broadcast_all_handoff_token(t):
            for a in agents:
                aid = str(a.get("agentId") or "").strip()
                if not aid or aid == source_agent_id:
                    continue
                prof = str(a.get("profile") or "").strip() or aid
                key = (prof, m)
                if key in seen:
                    continue
                seen.add(key)
                out.append((prof, m))
        else:
            key = (t, m)
            if key not in seen:
                seen.add(key)
                out.append((t, m))
    return out
