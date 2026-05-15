"""
媒体文件服务 — 提供 /api/media 端点，供前端播放 Agent 生成的音频（MP3/OGG 等）。
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media", tags=["media"])

# 允许服务的媒体根目录（按优先级查找）
_MEDIA_ROOTS = [
    Path(__file__).resolve().parents[3] / "media",          # backend/media/
    Path.home() / "voice-memos",                             # ~/voice-memos/
    Path.home() / ".hermes" / "voice-memos",                # ~/.hermes/voice-memos/
]


@router.get("/{file_path:path}")
async def serve_media(file_path: str):
    """通过相对路径或绝对路径来提供 .mp3 / .ogg / .wav 文件。"""
    if not file_path or '..' in file_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # 1) 如果在 _MEDIA_ROOTS 中能找到文件，优先返回
    for root in _MEDIA_ROOTS:
        if root.is_dir():
            candidate = (root / file_path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                media_type = _guess_media_type(candidate.suffix)
                return FileResponse(str(candidate), media_type=media_type)

    # 2) 尝试直接解析为绝对路径（开发/调试用）
    abs_path = Path(file_path)
    if abs_path.is_absolute() and abs_path.is_file():
        media_type = _guess_media_type(abs_path.suffix)
        return FileResponse(str(abs_path), media_type=media_type)

    raise HTTPException(status_code=404, detail=f"Media not found: {file_path}")


def _guess_media_type(suffix: str) -> str:
    mapping = {
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".opus": "audio/ogg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")
