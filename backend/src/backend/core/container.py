"""轻量级 DI 容器 — 替代散落的 _get_manager() 单例和服务局部导入。

设计目标：
- 集中管理所有服务/组件的生命周期
- 支持 singleton（进程级）和 transient（每次调用创建新实例）
- 利用 FastAPI lifespan 进行启动初始化
- 零外部依赖，纯 Python 实现
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_registry: Dict[str, _Registration] = {}


class _Registration:
    __slots__ = ("factory", "lifetime", "instance")
    factory: Callable[[], Any]
    lifetime: str          # "singleton" | "transient"
    instance: Any | None   # 仅 singleton 使用

    def __init__(self, factory: Callable[[], Any], lifetime: str) -> None:
        self.factory = factory
        self.lifetime = lifetime
        self.instance = None


class ContainerError(Exception):
    """DI 容器相关错误。"""


def register_singleton(name: str, factory: Callable[[], Any]) -> None:
    """注册进程级单例（惰性初始化）。

    ``factory`` 仅在首次 ``resolve(name)`` 时调用一次，之后缓存返回。
    """
    _registry[name] = _Registration(factory, "singleton")


def register_transient(name: str, factory: Callable[[], Any]) -> None:
    """注册瞬时服务（每次 resolve 调用 factory 创建新实例）。"""
    _registry[name] = _Registration(factory, "transient")


def resolve(name: str) -> Any:
    """从容器解析已注册的服务。

    - singleton: 首次调用 factory，之后返回缓存实例
    - transient: 每次调用 factory 返回新实例
    """
    reg = _registry.get(name)
    if reg is None:
        raise ContainerError(f"未注册的服务: {name!r}")
    if reg.lifetime == "singleton":
        if reg.instance is None:
            reg.instance = reg.factory()
        return reg.instance
    # transient
    return reg.factory()


def is_registered(name: str) -> bool:
    """检查服务是否已注册。"""
    return name in _registry


def clear() -> None:
    """清空所有注册（主要用于测试）。"""
    global _registry
    _registry = {}


# ── 便捷函数：从容器获取常用依赖 ──────────────────────────────────────────────

def db() -> Any:
    """获取 Database 连接池管理实例。"""
    return resolve("db")


def gateway_manager() -> Any:
    """获取 GatewayManager 单例。"""
    return resolve("gateway_manager")


def config() -> Any:
    """获取 StudioConfig 单例。"""
    return resolve("config")
