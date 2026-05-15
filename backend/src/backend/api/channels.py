"""Channel Controller — 对应 Spring Boot @RestController.

通道 CRUD：读写 ~/.hermes/config.yaml 中的 platforms.<platform>.home_channel。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.exceptions import DatabaseError, GatewayError, ValidationError
from backend.services import channel as channel_service
from backend.services.channel import ChannelPersistError, HermesConfigManagedError

router = APIRouter(prefix="/channels", tags=["channels"])
_log = logging.getLogger(__name__)


# ── Request/Response Models ───────────────────────────────────────────────────


class HomeChannelBody(BaseModel):
    """home_channel 子对象 — POST / PUT 请求体"""
    platform: str = Field(..., description="平台枚举值，如 telegram、discord")
    chat_id: str = Field(..., description="目标 chat ID")
    name: str = Field(..., description="通道显示名称")


class UpsertChannelRequest(BaseModel):
    """POST /channels — 新建或全量更新通道"""
    platform: str = Field(..., description="平台枚举值，如 telegram、discord")
    name: str = Field("", description="通道显示名称")
    chat_id: str = Field("", description="目标 chat ID")
    token: str = Field("", description="Bot Token / Bot Secret")
    api_key: str = Field("", description="备用认证 Key")
    enabled: bool = Field(True, description="是否启用")
    reply_to_mode: str = Field("first", description="回复模式: off | first | all")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="平台额外配置")
    agent_id: Optional[str] = Field(default=None, description="绑定的 Agent ID（前端保留字段）")


class PatchChannelRequest(BaseModel):
    """PATCH /channels/{platform} — 部分更新通道"""
    name: Optional[str] = Field(default=None, description="通道显示名称")
    chat_id: Optional[str] = Field(default=None, description="目标 chat ID")
    token: Optional[str] = Field(default=None, description="Bot Token")
    api_key: Optional[str] = Field(default=None, description="备用认证 Key")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    reply_to_mode: Optional[str] = Field(default=None, description="回复模式")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="平台额外配置")
    agent_id: Optional[str] = Field(default=None, description="绑定的 Agent ID（前端保留字段）")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=List[dict])
async def list_channels() -> List[dict]:
    """返回所有已配置的通道列表（只含已设置 home_channel 的平台）。"""
    return channel_service.list_channels()


@router.get("/{platform}", response_model=dict)
async def get_channel(platform: str) -> dict:
    """返回指定平台的通道信息。"""
    ch = channel_service.get_channel(platform)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 尚未配置通道")
    return ch


@router.post("", response_model=dict)
async def create_channel(body: UpsertChannelRequest) -> dict:
    """新建通道（按 platform 作为唯一键，已存在则覆盖）。"""
    try:
        return channel_service.upsert_channel(
            platform=body.platform,
            name=body.name,
            chat_id=body.chat_id,
            token=body.token,
            api_key=body.api_key,
            enabled=body.enabled,
            reply_to_mode=body.reply_to_mode,
            extra=body.extra,
            agent_id=body.agent_id,
        )
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except HermesConfigManagedError as e:
        raise GatewayError(str(e)) from e
    except ChannelPersistError as e:
        raise DatabaseError(str(e)) from e


@router.put("/{platform}", response_model=dict)
async def update_channel(platform: str, body: UpsertChannelRequest) -> dict:
    """全量更新通道配置（传入全部字段）。"""
    ch = channel_service.get_channel(platform)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 尚未配置通道，无法更新")

    try:
        return channel_service.upsert_channel(
            platform=body.platform or platform,
            name=body.name,
            chat_id=body.chat_id,
            token=body.token,
            api_key=body.api_key,
            enabled=body.enabled,
            reply_to_mode=body.reply_to_mode,
            extra=body.extra,
            agent_id=body.agent_id,
        )
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except HermesConfigManagedError as e:
        raise GatewayError(str(e)) from e
    except ChannelPersistError as e:
        raise DatabaseError(str(e)) from e


@router.patch("/{platform}", response_model=dict)
async def patch_channel(platform: str, body: PatchChannelRequest) -> dict:
    """部分更新通道配置（只更新传入的字段）。"""
    ch = channel_service.get_channel(platform)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 尚未配置通道，无法部分更新")

    patch: Dict[str, Any] = body.model_dump(exclude_unset=True)

    try:
        updated = channel_service.patch_channel(platform, patch)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except HermesConfigManagedError as e:
        raise GatewayError(str(e)) from e
    except ChannelPersistError as e:
        raise DatabaseError(str(e)) from e

    if updated is None:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 通道不存在")
    return updated


@router.delete("/{platform}", response_model=dict)
async def delete_channel(platform: str) -> dict:
    """删除指定平台的 home_channel 配置。"""
    existed = channel_service.delete_channel(platform)
    if not existed:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 不存在或尚未配置通道")
    return {"ok": True}
