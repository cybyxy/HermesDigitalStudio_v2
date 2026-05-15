"""向量感知服务 (Vector Perception Service) — 3区记忆分区 + 直觉过滤器

复用现有 MemOS (Qdrant) 基础设施，通过 session_id 字段实现逻辑分区。

Per-agent Qdrant collections: {agent_id}_memory
Logical partitions via session_id: "A" (Likes/Values), "B" (Style/Corpus), "C" (Shared Experience)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)


# ═══════════════ 数据模型 ═══════════════


@dataclass
class MemoryHit:
    """向量搜索结果"""

    text: str
    partition: str  # "A" / "B" / "C"
    relevance: float  # 0.0 ~ 1.0 (近似)


@dataclass
class IntuitionResult:
    """直觉过滤结果"""

    hits: list[MemoryHit] = field(default_factory=list)
    activation: dict[str, float] = field(
        default_factory=lambda: {"A": 0.0, "B": 0.0, "C": 0.0}
    )
    combined_relevance: float = 0.0
    filtered: bool = False  # combined_relevance < 0.15 时过滤


@dataclass
class PartitionStats:
    """分区统计"""

    partition: str
    doc_count: int
    avg_strength: float
    oldest_ts: float = 0.0
    newest_ts: float = 0.0


@dataclass
class MemoryEntry:
    """待写入的记忆条目"""

    text: str
    partition: str  # "A" / "B" / "C"
    label: str = ""
    source: str = "conversation"


# ═══════════════ 服务类 ═══════════════


class VectorPerceptionService:
    """向量感知服务（单例）。

    复用现有 MemOS (Qdrant)，实现 3 区逻辑分区。
    """

    _instance: VectorPerceptionService | None = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    # ── 直觉过滤器 (感知层核心) ──

    def intuition_filter(
        self, agent_id: str, query: str, top_k: int = 5
    ) -> IntuitionResult:
        """对查询执行多分区搜索 + 组合相关性评估。

        1. 搜索各分区 top_k 记忆
        2. 按分区分组
        3. 计算组合相关性
        4. 如果 combined_relevance < 0.15，打上 filtered=True

        Args:
            agent_id: Agent ID
            query: 查询文本
            top_k: 每个分区搜索数量

        Returns:
            IntuitionResult
        """
        try:
            from backend.services.mem_os_service import mos_search

            all_hits: list[MemoryHit] = []

            for partition in ("A", "B", "C"):
                results = mos_search(
                    agent_id=agent_id,
                    query=query,
                    top_k=top_k,
                    mode="fast",
                    session_id=partition,
                )
                for i, text in enumerate(results):
                    # 近似相关性: 排序越靠前，相关性越高
                    relevance = max(0.0, 1.0 - i / max(1, len(results)))
                    all_hits.append(
                        MemoryHit(text=text, partition=partition, relevance=relevance)
                    )

            if not all_hits:
                return IntuitionResult(filtered=True)

            # 按分区计算平均激活强度
            activation: dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0}
            counts: dict[str, int] = {"A": 0, "B": 0, "C": 0}

            for hit in all_hits:
                activation[hit.partition] += hit.relevance
                counts[hit.partition] += 1

            for p in ("A", "B", "C"):
                if counts[p] > 0:
                    activation[p] /= counts[p]

            # 组合相关性: 三区加权平均
            combined = (
                activation["A"] * 0.4 + activation["B"] * 0.3 + activation["C"] * 0.3
            )

            return IntuitionResult(
                hits=all_hits,
                activation=activation,
                combined_relevance=combined,
                filtered=combined < 0.15,
            )

        except Exception as e:
            _log.debug("vector_memory: intuition_filter failed: %s", e)
            return IntuitionResult(filtered=True)

    # ── 分区写入 ──

    def add_to_partition(
        self,
        agent_id: str,
        text: str,
        partition: str,
        label: str = "",
        source: str = "conversation",
    ) -> bool:
        """向指定分区写入记忆。

        Args:
            agent_id: Agent ID
            text: 记忆文本
            partition: 分区 "A" / "B" / "C"
            label: 可选的标签
            source: 记忆来源

        Returns:
            成功返回 True
        """
        try:
            from backend.services.mem_os_service import mos_add_text

            doc_path = f"partition:{partition}"
            if label:
                doc_path += f"|label:{label}"
            if source:
                doc_path += f"|source:{source}"

            return mos_add_text(
                agent_id=agent_id,
                content=text,
                session_id=partition,
                doc_path=doc_path,
            )
        except Exception as e:
            _log.debug("vector_memory: add_to_partition failed: %s", e)
            return False

    def batch_add(self, agent_id: str, entries: list[MemoryEntry]) -> int:
        """批量写入不同分区。

        Returns:
            成功写入的数量
        """
        count = 0
        for entry in entries:
            if self.add_to_partition(
                agent_id=agent_id,
                text=entry.text,
                partition=entry.partition,
                label=entry.label,
                source=entry.source,
            ):
                count += 1
        return count

    # ── 分区搜索 ──

    def search(
        self,
        agent_id: str,
        query: str,
        partition: str | None = None,
        top_k: int = 10,
    ) -> list[MemoryHit]:
        """按分区语义搜索。

        Args:
            agent_id: Agent ID
            query: 搜索查询
            partition: 分区过滤 (None = 全部分区)
            top_k: 返回结果数

        Returns:
            MemoryHit 列表
        """
        try:
            from backend.services.mem_os_service import mos_search

            if partition:
                partitions = [partition]
            else:
                partitions = ["A", "B", "C"]

            all_hits: list[MemoryHit] = []
            for p in partitions:
                results = mos_search(
                    agent_id=agent_id,
                    query=query,
                    top_k=top_k,
                    mode="fast",
                    session_id=p,
                )
                for i, text in enumerate(results):
                    relevance = max(0.0, 1.0 - i / max(1, len(results)))
                    all_hits.append(
                        MemoryHit(text=text, partition=p, relevance=relevance)
                    )

            # 按相关性排序
            all_hits.sort(key=lambda h: h.relevance, reverse=True)
            return all_hits[:top_k]

        except Exception as e:
            _log.debug("vector_memory: search failed: %s", e)
            return []

    # ── 分区统计 ──

    def get_partition_stats(self, agent_id: str) -> list[PartitionStats]:
        """获取各分区统计信息。

        Returns:
            PartitionStats 列表
        """
        try:
            from backend.services.mem_os_service import mos_search

            stats: list[PartitionStats] = []
            for p in ("A", "B", "C"):
                results = mos_search(
                    agent_id=agent_id,
                    query="*",
                    top_k=100,
                    mode="fast",
                    session_id=p,
                )
                count = len(results)
                avg = 0.0
                for i in range(count):
                    avg += max(0.0, 1.0 - i / max(1, count))
                if count > 0:
                    avg /= count

                stats.append(
                    PartitionStats(
                        partition=p,
                        doc_count=count,
                        avg_strength=avg,
                    )
                )
            return stats

        except Exception as e:
            _log.debug("vector_memory: get_partition_stats failed: %s", e)
            return [
                PartitionStats(partition=p, doc_count=0, avg_strength=0.0)
                for p in ("A", "B", "C")
            ]


# ═══════════════ 便捷访问 ═══════════════


def get_vector_perception_service() -> VectorPerceptionService:
    """获取向量感知服务单例。"""
    return VectorPerceptionService()
