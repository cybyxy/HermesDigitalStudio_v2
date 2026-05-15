"""Backward-compatible re-export shim for backend.gateway.gateway.

All classes are now defined in separate modules under the gateway/ package:
- SubprocessGateway → gateway.subprocess_gateway
- GatewayManager, AgentInfo → gateway.gateway_manager

This file exists purely for backward compatibility with existing import paths.
New code should import from::

    from backend.gateway import SubprocessGateway, GatewayManager, AgentInfo

or directly from the sub-modules.
"""

from backend.gateway.subprocess_gateway import SubprocessGateway
from backend.gateway.gateway_manager import GatewayManager, AgentInfo

__all__ = [
    "SubprocessGateway",
    "GatewayManager",
    "AgentInfo",
]
