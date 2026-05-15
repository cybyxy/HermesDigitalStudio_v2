"""SubprocessGateway — 管理单个 Hermes agent 子进程的 JSON-RPC 网关。

每个 SubprocessGateway 实例负责：
- 启动/停止一个 hermes 子进程
- 通过 stdin/stdout 的 JSON-RPC 协议通信
- 将子进程事件分发给注册的处理器（SSE 客户端等）
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.gateway._config import (
    _BACKEND_ROOT,
    _HERMES_ENTRY,
    _HERMES_PROJECT_ROOT,
    _HERMES_VENDOR_ROOT,
    _SUBPROCESS_TIMEOUT_S,
)
from backend.gateway._utils import (
    ensure_hermes_image_path,
    generate_session_key,
    inject_model_credentials_into_env,
)

_log = logging.getLogger(__name__)

# 支持的图片扩展名
_IMAGE_EXTENSIONS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.tif', '.svg', '.ico'})


@dataclass
class SubprocessGateway:
    """Manages one hermes subprocess as a JSON-RPC gateway over stdio.

    Thread-safe: all public methods acquire _lock.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    hermes_home: str | None = field(default=None)
    model: str | None = field(default=None)
    model_provider: str | None = field(default=None)
    _proc: subprocess.Popen[str] | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _stdout_reader: threading.Thread | None = field(default=None, init=False)
    _stderr_reader: threading.Thread | None = field(default=None, init=False)
    _pending: dict[str, tuple[threading.Event, dict | None]] = field(default_factory=dict)
    _seq: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)
    _event_handlers: list[Callable[[dict], None]] = field(default_factory=list)
    _stdout_queue: queue.Queue[str | None] = field(default_factory=queue.Queue)
    _ready_event: threading.Event = field(default_factory=threading.Event, init=False)
    _startup_done: bool = field(default=False, init=False)
    _on_session_switch: Callable[[str, str], None] | None = field(default=None, init=False)

    # ── 子进程管理 ──────────────────────────────────────────────────────

    def _start_process(self) -> None:
        _hw_path = self.hermes_home or os.environ.get(
            "HERMES_HOME", str(Path.home() / ".hermes")
        )
        _hw_expanded = str(Path(_hw_path).expanduser())
        try:
            from hermes_cli.env_loader import load_hermes_dotenv

            load_hermes_dotenv(
                hermes_home=_hw_expanded,
                project_env=_HERMES_VENDOR_ROOT / ".env",
            )
        except Exception as e:
            _log.warning("load_hermes_dotenv failed (keys may be missing): %s", e)

        # 加载 ~/.hermes/.env 中的环境变量
        file_env: dict[str, str] = {}
        prev_hermes = os.environ.get("HERMES_HOME")
        try:
            os.environ["HERMES_HOME"] = _hw_expanded
            from hermes_cli.config import load_env as _hermes_file_env

            file_env = _hermes_file_env()
        except Exception as e:
            _log.warning("Hermes load_env() for gateway subprocess failed: %s", e)
        finally:
            if prev_hermes is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = prev_hermes

        # 将根 Hermes 目录 .env 中有用的键补进 file_env
        try:
            from hermes_cli.auth import has_usable_secret
            from hermes_constants import get_default_hermes_root

            root_home = get_default_hermes_root()
            prof = Path(_hw_expanded).expanduser().resolve()
            root_res = root_home.expanduser().resolve()
            if root_res.is_dir() and prof != root_res:
                prev_r = os.environ.get("HERMES_HOME")
                root_fe: dict[str, str] = {}
                try:
                    os.environ["HERMES_HOME"] = str(root_home.expanduser())
                    from hermes_cli.config import load_env as _hermes_root_env

                    root_fe = _hermes_root_env()
                finally:
                    if prev_r is None:
                        os.environ.pop("HERMES_HOME", None)
                    else:
                        os.environ["HERMES_HOME"] = prev_r
                for _rk, _rv in root_fe.items():
                    if not _rv or not str(_rv).strip():
                        continue
                    cur = str(file_env.get(_rk, "") or "").strip()
                    if not has_usable_secret(cur) and has_usable_secret(_rv):
                        file_env[_rk] = _rv
        except Exception as e:
            _log.debug("merge root Hermes .env for profile gateway skipped: %s", e)

        # 构建子进程环境
        env = dict(os.environ)
        for _k, _v in file_env.items():
            if _v:
                env[_k] = _v
        env["HERMES_HOME"] = _hw_expanded
        inject_model_credentials_into_env(env, _hw_expanded)

        # 传递 MEMOS 目录路径，使子进程可读取 bootstrap 缓存
        try:
            from backend.services.mem_os_service import _get_memos_dir
            env["HERMES_STUDIO_MEMOS_DIR"] = _get_memos_dir()
        except Exception:
            _log.warning("[%s] failed to resolve MEMOS directory", self.session_id, exc_info=True)

        if self.model:
            env["HERMES_MODEL"] = self.model
        if self.model_provider:
            env["HERMES_TUI_PROVIDER"] = self.model_provider

        env["HERMES_GATEWAY_NATIVE_IMAGES"] = "1"
        env["TERMINAL_CWD"] = env["HERMES_HOME"]
        _src_root = str((_BACKEND_ROOT / "src").resolve())
        _vendor_root = str(_HERMES_VENDOR_ROOT.resolve())
        _pp = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            os.pathsep.join([_src_root, _vendor_root, _pp]) if _pp else os.pathsep.join([_src_root, _vendor_root])
        )

        _bootstrap = (
            "import runpy,sys;"
            f"sys.path.insert(0,{_src_root!r});"
            "from backend.hermes_subagent_ext import apply_runtime_patches;"
            "apply_runtime_patches();"
            "runpy.run_module('tui_gateway.entry', run_name='__main__')"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", _bootstrap],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(_HERMES_PROJECT_ROOT),
        )
        self._proc = proc
        self._seq = 0
        self._closed = False

        t = threading.Thread(target=self._drain_stdout, daemon=True, name=f"hgw-{self.session_id}")
        t.start()
        self._stdout_reader = t

        t2 = threading.Thread(target=self._drain_stderr, daemon=True, name=f"hgw-{self.session_id}-err")
        t2.start()
        self._stderr_reader = t2

        if not self._ready_event.wait(timeout=5.0):
            _log.warning("[%s] gateway.ready timeout", self.session_id)

    def _drain_stdout(self) -> None:
        """后台线程：持续读取子进程 stdout，解析 JSON-RPC 消息并分发给事件处理器。"""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    _log.warning("[%s] malformed stdout: %s", self.session_id, line[:100])
                    continue
                self._dispatch_inbound(obj)
        except Exception:
            _log.warning("[%s] stdout drain failed", self.session_id, exc_info=True)

    def _drain_stderr(self) -> None:
        """后台线程：持续读取子进程 stderr 并写入日志。"""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for raw_line in proc.stderr:
                line = raw_line.rstrip("\n")
                if line:
                    _log.debug("[%s] %s", self.session_id, line)
        except Exception:
            _log.warning("[%s] stderr drain failed", self.session_id, exc_info=True)

    def _dispatch_inbound(self, obj: dict) -> None:
        """Handle inbound JSON-RPC from subprocess.

        Two cases:
        - method="event"  → SSE/notification, no id: route to _event_handlers
        - id is present   → response to a pending call: wake the waiter
        """
        method = obj.get("method")
        if method == "event" and "params" in obj:
            raw_params = obj["params"]
            if raw_params.get("type") == "gateway.ready":
                self._ready_event.set()
                return
            if raw_params.get("type") == "session.switch":
                payload = raw_params.get("payload", {})
                old_sid = payload.get("old_session_id", "")
                new_sid = payload.get("new_session_id", "")
                if old_sid and new_sid and self._on_session_switch:
                    self._on_session_switch(old_sid, new_sid)
            event_dict: dict[str, Any] = {
                "type": raw_params.get("type", ""),
                "session_id": raw_params.get("session_id"),
            }
            if "payload" in raw_params:
                event_dict["payload"] = raw_params["payload"]
            for handler in list(self._event_handlers):
                try:
                    handler(event_dict)
                except Exception:
                    _log.warning("[%s] event handler failed for event=%s", self.session_id, event_dict.get("event", "?"), exc_info=True)
            return

        rid = obj.get("id")
        if rid is not None:
            entry = self._pending.get(rid)
            if entry is not None:
                entry[1] = obj
                entry[0].set()

    # ── public API ──────────────────────────────────────────────────────

    def start(self) -> None:
        """启动子进程（若尚未运行则初始化）。"""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._start_process()

    def close(self) -> None:
        """安全关闭子进程：先尝试优雅终止，超时后强制 kill。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            proc = self._proc
            if proc is None:
                return
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=3.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    _log.warning("[%s] failed to kill subprocess after terminate+wait", self.session_id, exc_info=True)
            self._proc = None

    def is_alive(self) -> bool:
        """返回子进程是否仍在运行。"""
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def on_event(self, handler: Callable[[dict], None]) -> None:
        """注册事件处理器，接收子进程推送的 SSE 事件。"""
        self._event_handlers.append(handler)

    def remove_event(self, handler: Callable[[dict], None]) -> None:
        try:
            self._event_handlers.remove(handler)
        except ValueError:
            pass

    def dispatch_synthetic_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """向所有 ``on_event`` 监听者推送与 Hermes 子进程同形的事件（供 Studio 规划链等）。"""
        event_dict: dict[str, Any] = {
            "type": event_type,
            "session_id": session_id,
        }
        if payload is not None:
            event_dict["payload"] = payload
        for handler in list(self._event_handlers):
            try:
                handler(event_dict)
            except Exception:
                _log.warning("[%s] synthetic event handler failed for event=%s", self.session_id, event_dict.get("event", "?"), exc_info=True)

    def call(self, method: str, params: dict | None = None, timeout: float = _SUBPROCESS_TIMEOUT_S) -> dict | None:
        """向子进程发送 JSON-RPC 请求并等待响应，线程安全。"""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                _log.warning("[%s] call %s on dead process", self.session_id, method)
                return None
            rid = uuid.uuid4().hex[:8]
            evt = threading.Event()
            self._pending[rid] = [evt, None]

        req = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        line = json.dumps(req, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except Exception as e:
            _log.warning("[%s] stdin error on %s: %s", self.session_id, method, e)
            self._pending.pop(rid, None)
            return None

        if not evt.wait(timeout=timeout):
            _log.warning("[%s] call %s timed out id=%s", self.session_id, method, rid)
            self._pending.pop(rid, None)
            return None

        _, result = self._pending.pop(rid, (None, None))
        return result

    # ── RPC 方法 ────────────────────────────────────────────────────────

    def create_session(self, cols: int = 120) -> str | None:
        resp = self.call("session.create", {"cols": cols})
        if resp is None:
            return None
        return resp.get("result", {}).get("session_id")

    def create_session_with_key(self, cols: int = 120) -> tuple[str | None, str | None]:
        session_key = generate_session_key()
        resp = self.call("session.create", {"cols": cols, "session_key": session_key})
        if resp is None:
            return (None, None)
        result = resp.get("result", {})
        return (result.get("session_id"), result.get("session_key"))

    def submit_prompt(self, session_id: str, text: str, attachments: list[str] | None = None) -> bool:
        file_refs: list[str] = []
        if attachments:
            for att in attachments:
                att_path = Path(att)
                use_path = ensure_hermes_image_path(att_path, _IMAGE_EXTENSIONS)
                if use_path is not None:
                    result = self.call(
                        "image.attach",
                        {"session_id": session_id, "path": str(use_path.resolve())},
                    )
                    res = result.get("result") if result else None
                    ok = bool(result) and "error" not in result and isinstance(res, dict) and res.get("attached") is True
                    if ok:
                        _log.info("image.attach(%s) -> ok", use_path.name)
                    else:
                        _log.warning("image.attach(%s) failed: %s", use_path.name, result)
                        file_refs.append(str(att_path))
                else:
                    file_refs.append(str(att_path))

        final_text = text
        if file_refs:
            file_ref_text = "\n" + "\n".join(f"[User attached file: {f}]" for f in file_refs)
            final_text = (final_text or "") + file_ref_text

        resp = self.call("prompt.submit", {"session_id": session_id, "text": final_text})
        if resp is None:
            return False
        if resp.get("error"):
            _log.warning("[%s] prompt.submit error: %s", self.session_id, resp.get("error"))
            return False
        ok = resp.get("result", {}).get("status") == "streaming"
        if not ok:
            _log.warning("[%s] prompt.submit unexpected: %s", self.session_id, resp)
        return ok

    def interrupt(self, session_id: str) -> bool:
        resp = self.call("session.interrupt", {"session_id": session_id})
        return resp is not None

    def close_session(self, session_id: str) -> bool:
        resp = self.call("session.close", {"session_id": session_id})
        return resp is not None

    def session_history(self, session_id: str) -> list[dict]:
        resp = self.call("session.history", {"session_id": session_id})
        if resp is None:
            return []
        return resp.get("result", {}).get("messages", [])

    def session_history_by_key(self, session_key: str) -> list[dict]:
        resp = self.call("session.history_by_key", {"session_key": session_key})
        if resp is None:
            return []
        return resp.get("result", {}).get("messages", [])

    def session_list(self) -> list[dict]:
        resp = self.call("session.list", {})
        if resp is None:
            return []
        return resp.get("result", {}).get("sessions", [])

    def delete_session_by_key(self, session_key: str) -> bool:
        resp = self.call("session.delete", {"session_id": session_key})
        if resp is None:
            return False
        if resp.get("error"):
            code = resp.get("error", {}).get("code", 0)
            if code in (4007,):
                return True
            _log.warning("[%s] session.delete for key=%s: %s", self.session_id, session_key, resp.get("error"))
            return False
        return resp.get("result", {}).get("deleted") == session_key

    def resume_session(self, session_key: str, session_id: str = "", cols: int = 120) -> tuple[str | None, str | None]:
        params: dict = {"cols": cols, "session_key": session_key}
        if session_id:
            params["session_id"] = session_id
        resp = self.call("session.create", params)
        if resp is None:
            return (None, None)
        result = resp.get("result", {})
        return (result.get("session_id"), result.get("session_key"))

    def respond_approval(self, session_id: str, choice: str, all: bool = False) -> bool:
        resp = self.call("approval.respond", {"session_id": session_id, "choice": choice, "all": all})
        return resp is not None

    def respond_clarify(self, session_id: str, request_id: str, answer: str) -> bool:
        resp = self.call("clarify.respond", {"session_id": session_id, "request_id": request_id, "answer": answer})
        return resp is not None

    def evict_agent(self, session_id: str) -> bool:
        resp = self.call("agent.evict", {"session_id": session_id})
        return resp is not None

    def set_env(self, key: str, value: str) -> bool:
        resp = self.call("agent.set_env", {"key": key, "value": value})
        return resp is not None
