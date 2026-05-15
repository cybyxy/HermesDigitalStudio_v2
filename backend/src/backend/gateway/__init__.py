"""Gateway 模块：子进程管理（SubprocessGateway / GatewayManager / AgentInfo）。

模块结构：
- _config.py             — 常量与路径解析
- _utils.py              — 工具函数（环境展开、session key、图片处理、凭证注入）
- subprocess_gateway.py  — SubprocessGateway（单个 agent 子进程 JSON-RPC 网关）
- gateway_manager.py     — GatewayManager（多 agent 进程池与 session 路由）+ AgentInfo
"""

from backend.gateway.subprocess_gateway import SubprocessGateway
from backend.gateway.gateway_manager import GatewayManager, AgentInfo

__all__ = [
    "SubprocessGateway",
    "GatewayManager",
    "AgentInfo",
]
