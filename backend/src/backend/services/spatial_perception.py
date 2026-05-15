"""空间感知引擎 (Spatial Perception) — Tiled 地图物品解析 + 环境感知文本生成

纯计算模块 + Neo4j 查询接口（try/except 降级）。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field


# ═══════════════ 数据模型 ═══════════════


@dataclass
class InteractiveItem:
    """Tiled 地图中的可交互物品"""

    id: int
    name: str  # e.g. "朝南的窗户" / "旧书架"
    x: int  # Tiled pixel coordinate X
    y: int  # Tiled pixel coordinate Y
    description: str = ""  # 环境描述文本
    mood_tags: list[str] = field(default_factory=list)  # e.g. ["bright", "warm"]
    interact_actions: list[str] = field(default_factory=list)  # e.g. ["打开窗户"]
    category: str = "furniture"

    @property
    def tile_x(self) -> int:
        """像素坐标 → 瓦片坐标 (假设 32px tile)"""
        return self.x // 32

    @property
    def tile_y(self) -> int:
        return self.y // 32


@dataclass
class MapContext:
    """地图上下文"""

    name: str
    items: list[InteractiveItem]


# ═══════════════ 常量 ═══════════════

# 情绪标签 → PAD 增量映射
MOOD_TAG_PAD_MAP: dict[str, tuple[float, float, float]] = {
    "bright": (0.2, 0.1, 0.0),
    "warm": (0.3, -0.1, 0.0),
    "relaxing": (0.2, -0.2, 0.0),
    "quiet": (0.1, -0.1, 0.0),
    "intellectual": (0.1, 0.2, 0.05),
    "nostalgic": (0.1, -0.1, -0.05),
    "dark": (-0.1, 0.1, -0.05),
    "cold": (-0.1, 0.0, -0.1),
    "cozy": (0.25, -0.15, 0.05),
    "refreshing": (0.15, 0.3, 0.0),
}

# 默认地图文件映射
DEFAULT_MAP_FILES: dict[str, str] = {
    "office": "office_layer.json",
    "cafe": "cafe_layer.json",
    "library": "library_layer.json",
}

# 默认感知距离阈值 (像素)
DEFAULT_PERCEPTION_THRESHOLD = 150


# ═══════════════ Tiled 地图解析 ═══════════════


def parse_tiled_interactive_objects(map_json: dict) -> list[InteractiveItem]:
    """解析 Tiled JSON 中的所有可交互物体。

    从 objectgroup 图层中提取有 properties.description 的物体。

    Args:
        map_json: Tiled map JSON 数据

    Returns:
        InteractiveItem 列表
    """
    items: list[InteractiveItem] = []

    for layer in map_json.get("layers", []):
        if layer.get("type") != "objectgroup":
            continue

        for obj in layer.get("objects", []):
            props = {
                p["name"]: p["value"] for p in obj.get("properties", [])
            }
            description = props.get("description", "")
            if not description:
                continue

            name = obj.get("name", f"item_{obj.get('id', 0)}")

            # 解析 JSON 格式的标签和动作
            mood_tags: list[str] = []
            raw_tags = props.get("mood_tags", "")
            if raw_tags:
                try:
                    tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                    if isinstance(tags, list):
                        mood_tags = [t for t in tags if isinstance(t, str)]
                except (json.JSONDecodeError, TypeError):
                    mood_tags = [raw_tags] if isinstance(raw_tags, str) else []

            interact_actions: list[str] = []
            raw_actions = props.get("interact_actions", "")
            if raw_actions:
                try:
                    actions = json.loads(raw_actions) if isinstance(raw_actions, str) else raw_actions
                    if isinstance(actions, list):
                        interact_actions = [a for a in actions if isinstance(a, str)]
                except (json.JSONDecodeError, TypeError):
                    pass

            category = props.get("category", "furniture")

            items.append(
                InteractiveItem(
                    id=obj.get("id", 0),
                    name=name,
                    x=int(obj.get("x", 0)),
                    y=int(obj.get("y", 0)),
                    description=description,
                    mood_tags=mood_tags,
                    interact_actions=interact_actions,
                    category=category,
                )
            )

    return items


# ═══════════════ 空间计算 ═══════════════


def calculate_tile_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """计算两点欧氏距离 (像素)"""
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def get_direction_description(
    agent_x: float, agent_y: float, item_x: float, item_y: float
) -> str:
    """基于相对位置生成方向描述。

    Returns:
        "右前方" / "左前方" / "前方" / "右侧" / "左侧" / "后方"
    """
    dx = item_x - agent_x
    dy = agent_y - item_y  # Tiled Y 轴向下为正

    angle = math.degrees(math.atan2(dx, dy))  # 以"向上"为前
    # angle: 0=前方, 90=右侧, -90=左侧, ±180=后方

    distance = math.sqrt(dx**2 + dy**2)

    if distance < 1:
        return "正前方"

    if -22.5 <= angle <= 22.5:
        return "前方"
    elif 22.5 < angle <= 67.5:
        return "右前方"
    elif 67.5 < angle <= 112.5:
        return "右侧"
    elif 112.5 < angle <= 157.5:
        return "右后方"
    elif -67.5 <= angle < -22.5:
        return "左前方"
    elif -112.5 <= angle < -67.5:
        return "左侧"
    elif -157.5 <= angle < -112.5:
        return "左后方"
    else:
        return "后方"


def filter_nearby_items(
    agent_x: float,
    agent_y: float,
    items: list[InteractiveItem],
    threshold: float = DEFAULT_PERCEPTION_THRESHOLD,
) -> list[tuple[InteractiveItem, float]]:
    """筛选附近物品，按距离排序。

    Returns:
        [(item, distance), ...] 按距离升序
    """
    nearby: list[tuple[InteractiveItem, float]] = []
    for item in items:
        d = calculate_tile_distance(agent_x, agent_y, item.x, item.y)
        if d <= threshold:
            nearby.append((item, d))
    return sorted(nearby, key=lambda x: x[1])


def compute_environment_perception(
    agent_x: float,
    agent_y: float,
    items: list[InteractiveItem],
    threshold: float = DEFAULT_PERCEPTION_THRESHOLD,
) -> str:
    """生成自然语言环境感知文本。

    Args:
        agent_x, agent_y: Agent 当前像素坐标
        items: 可交互物品列表
        threshold: 感知距离阈值

    Returns:
        环境感知文本
    """
    nearby = filter_nearby_items(agent_x, agent_y, items, threshold)

    if not nearby:
        return "【当前环境感知】周围空荡荡的，没有特别值得注意的东西。"

    lines = ["【当前环境感知】你正身处一个小屋里。"]

    for item, distance in nearby:
        direction = get_direction_description(agent_x, agent_y, item.x, item.y)
        proximity = "不远处" if distance > 80 else "近处"
        lines.append(f"在你的{direction}{proximity}，有一个{item.name}。{item.description}")

    return "\n".join(lines)


# ═══════════════ 环境→情绪闭环 ═══════════════


def compute_environment_mood_deltas(
    nearby_items: list[tuple[InteractiveItem, float]],
    threshold: float = DEFAULT_PERCEPTION_THRESHOLD,
) -> tuple[float, float, float]:
    """根据附近物品的情绪标签计算 PAD 增量。

    Args:
        nearby_items: [(item, distance), ...]
        threshold: 感知距离阈值

    Returns:
        (v_delta, a_delta, d_delta)
    """
    total_v = total_a = total_d = 0.0

    for item, distance in nearby_items:
        intensity = max(0.0, 1.0 - distance / threshold)  # 越近越强

        for tag in item.mood_tags:
            delta = MOOD_TAG_PAD_MAP.get(tag)
            if delta:
                total_v += delta[0] * intensity * 0.05
                total_a += delta[1] * intensity * 0.05
                total_d += delta[2] * intensity * 0.03

    return (total_v, total_a, total_d)


# ═══════════════ 多世界支持 ═══════════════


def load_map_context(
    map_name: str = "office",
    map_json: dict | None = None,
) -> MapContext:
    """加载地图上下文。

    Args:
        map_name: 地图名称
        map_json: 已加载的 Tiled JSON (如果已有)

    Returns:
        MapContext
    """
    if map_json is None:
        return MapContext(name=map_name, items=[])

    items = parse_tiled_interactive_objects(map_json)
    return MapContext(name=map_name, items=items)
