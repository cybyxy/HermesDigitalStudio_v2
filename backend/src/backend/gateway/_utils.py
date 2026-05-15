"""Gateway 工具函数：环境变量展开、session key 生成、图片处理、凭证注入。"""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from backend.gateway._config import _ENV_REF_PATTERN

if TYPE_CHECKING:
    pass

_log = logging.getLogger("backend.gateway")


def expand_hermes_env_refs(value: str, lookup: dict[str, str]) -> str:
    """展开字符串中的 ${VAR_NAME} 环境变量占位符。

    用于在将 config.yaml 中的凭证传给子进程前，用实际环境变量值替换占位符。
    """
    if not value or "${" not in value:
        return value

    def _repl(m: re.Match[str]) -> str:
        return str(lookup.get(m.group(1), "") or "").strip()

    return _ENV_REF_PATTERN.sub(_repl, value)


def generate_session_key() -> str:
    """生成 date-based session_key，格式与 vendor _new_session_key() 一致。

    session_key 用作 state.db sessions 表的主键和磁盘 session 文件名，
    格式：YYYYMMDD_HHMMSS_6位hex，例如 20260511_143022_f9e8d7。
    这是本项目直接引用的 session ID 生成方式。
    """
    from datetime import datetime
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def sniff_image_suffix(path: Path) -> str | None:
    """通过读取文件头部魔数识别图片真实格式，返回标准扩展名。

    支持 PNG、JPEG、GIF、WebP、BMP，与 hermes image.attach 按扩展名校验配合使用。
    """
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"BM"):
        return ".bmp"
    return None


def ensure_hermes_image_path(path: Path, image_extensions: frozenset[str]) -> Path | None:
    """确保图片文件具有 hermes 认可的扩展名。

    若文件扩展名不正确但内容为图片，则复制一份带正确扩展名的副本供 image.attach 使用。
    """
    if not path.is_file():
        return None
    if path.suffix.lower() in image_extensions:
        return path
    ext = sniff_image_suffix(path)
    if ext is None:
        return None
    corrected = path.with_suffix(ext)
    if corrected.resolve() == path.resolve():
        return path
    if corrected.is_file():
        return corrected

    shutil.copy2(path, corrected)
    return corrected


def inject_model_credentials_into_env(env: dict[str, str], hermes_home: str) -> None:
    """将 config.yaml 中的 model.api_key / base_url 写入子进程 env（补全仅配在 YAML、未进 .env 的情况）。

    Hermes 的 runtime 会从 YAML 读 api_key，但部分 HTTP 路径仍依赖 os.environ；
    Web 启动的 uvicorn 子进程若只有 YAML 密钥，可能出现上游 401 Missing Authentication header。
    """
    # 含已从 ~/.hermes/.env 合并的项，供展开 YAML 中的 ${VAR}（勿只保留非空，否则占位键无法参与替换链）
    lookup: dict[str, str] = {str(k): "" if v is None else str(v) for k, v in env.items()}

    prev = os.environ.get("HERMES_HOME")
    try:
        os.environ["HERMES_HOME"] = hermes_home
        from hermes_cli.auth import has_usable_secret
        from hermes_cli.config import read_raw_config
        from utils import base_url_host_matches

        cfg = read_raw_config()
    except Exception as exc:
        _log.debug("model credential inject skipped: %s", exc)
        return
    finally:
        if prev is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = prev

    raw_model = cfg.get("model")
    if isinstance(raw_model, str):
        return
    if not isinstance(raw_model, dict):
        return

    base_url = expand_hermes_env_refs(str(raw_model.get("base_url") or "").strip(), lookup)
    inline = expand_hermes_env_refs(
        str(raw_model.get("api_key") or raw_model.get("api") or "").strip(),
        lookup,
    )
    prov = expand_hermes_env_refs(str(raw_model.get("provider", "")).strip(), lookup).lower()

    def _ensure_env(name: str, val: str) -> None:
        if not val or not has_usable_secret(val):
            return
        cur = str(env.get(name, "") or "").strip()
        if not cur or not has_usable_secret(cur):
            env[name] = val

    if base_url:
        if base_url_host_matches(base_url, "openrouter.ai"):
            _ensure_env("OPENROUTER_BASE_URL", base_url.rstrip("/"))
        else:
            _ensure_env("OPENAI_BASE_URL", base_url.rstrip("/"))

    if not inline or not has_usable_secret(inline):
        return

    from hermes_cli.auth import PROVIDER_REGISTRY

    if prov in PROVIDER_REGISTRY:
        pcfg = PROVIDER_REGISTRY[prov]
        if getattr(pcfg, "auth_type", "") == "api_key":
            for ev in pcfg.api_key_env_vars:
                _ensure_env(ev, inline)
        return

    is_openrouter = (not base_url) or base_url_host_matches(base_url, "openrouter.ai")
    if prov in ("", "auto") or (prov == "custom" and is_openrouter):
        _ensure_env("OPENROUTER_API_KEY", inline)
        _ensure_env("OPENAI_API_KEY", inline)
    elif prov == "custom":
        _ensure_env("OPENAI_API_KEY", inline)
    else:
        key_name = f"{prov.upper().replace('-', '_')}_API_KEY"
        _ensure_env(key_name, inline)
