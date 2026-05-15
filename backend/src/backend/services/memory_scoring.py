"""记忆评分引擎 — 四维度加权记忆重要性评估。

对 Agent 持久记忆条目进行评分，支持：
- 四维度加权：recency（时间衰减）、reinforcement（增强次数）、source（来源）、access_count（访问次数）
- 排名和淘汰建议
- 分数归一化到 [0, 1]

使用::

    from backend.services.memory_scoring import MemoryScoringEngine

    engine = MemoryScoringEngine()
    candidates = await engine.get_candidates_for_pruning("agent-alice", limit=10)
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone

_log = logging.getLogger(__name__)

# 来源权重映射
_SOURCE_SCORES: dict[str, float] = {
    "LLM抽取": 1.0,
    "用户显式": 0.9,
    "对话提取": 0.5,
    "启动恢复": 0.3,
}


class MemoryScoringEngine:
    """四维度加权记忆评分。

    权重默认值：
    - recency: 0.3（时间衰减）
    - reinforcement: 0.3（增强/重复次数）
    - source: 0.2（记忆来源可信度）
    - access_count: 0.2（被访问频率）
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "recency": 0.3,
            "reinforcement": 0.3,
            "source": 0.2,
            "access_count": 0.2,
        }
        self._max_days = 90.0  # 90 天后衰减到接近 0

    def calculate_score(self, memory_entry: dict) -> float:
        """计算单条记忆的重要性分数。

        各维度归一化到 [0, 1]：
        - recency: 基于 created_at 的指数衰减
        - reinforcement: min(reinforcement_count / 10, 1.0)
        - source: 来源映射
        - access_count: log(access_count + 1) / log(max_access + 2)

        Args:
            memory_entry: 包含 created_at, reinforcement_count, source, access_count 的 dict
        """
        w = self.weights

        # 1. Recency 维度：指数衰减
        recency_score = self._calc_recency(memory_entry.get("created_at", 0))

        # 2. Reinforcement 维度
        reinforcement = memory_entry.get("reinforcement_count", 0)
        reinforcement_score = min(float(reinforcement) / 10.0, 1.0)

        # 3. Source 维度
        source = memory_entry.get("source", "对话提取")
        source_score = _SOURCE_SCORES.get(source, 0.5)

        # 4. Access Count 维度
        access_count = memory_entry.get("access_count", 0)
        if access_count > 0:
            access_score = math.log(access_count + 1) / math.log(access_count + 2)
        else:
            access_score = 0.0

        score = (
            w["recency"] * recency_score
            + w["reinforcement"] * reinforcement_score
            + w["source"] * source_score
            + w["access_count"] * access_score
        )

        return round(score, 4)

    def _calc_recency(self, created_at: float | str | None) -> float:
        """计算基于时间的衰减分数。

        使用指数衰减：exp(-0.1 * days_ago)
        90 天后 ≈ 0.0001
        """
        if created_at is None:
            return 0.0

        try:
            if isinstance(created_at, str):
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                ts = dt.timestamp()
            else:
                ts = float(created_at)
        except (ValueError, TypeError):
            return 0.0

        days_ago = max(0.0, (time.time() - ts) / 86400.0)
        return math.exp(-0.1 * days_ago)

    async def rank_memories(self, agent_id: str) -> list[tuple[str, float]]:
        """返回按分数降序排列的记忆 (memory_id, score) 列表。"""
        from backend.db.memory_scoring import MemoryScoringDAO

        rows = MemoryScoringDAO.get_all_meta(agent_id)
        if not rows:
            return []

        scored: list[tuple[str, float]] = []
        for row in rows:
            score = self.calculate_score({
                "created_at": row["created_at"],
                "reinforcement_count": row["reinforcement_count"],
                "source": row["source"],
                "access_count": row["access_count"],
            })
            scored.append((row["id"], score))

        scored.sort(key=lambda x: -x[1])
        return scored

    async def get_candidates_for_pruning(
        self,
        agent_id: str,
        limit: int = 10,
        max_entries: int = 200,
    ) -> list[dict]:
        """获取建议淘汰的记忆列表（分数最低的 N 条）。

        Args:
            agent_id: Agent ID
            limit: 最多返回多少条候选
            max_entries: 记忆总数超过此值时才返回淘汰建议

        Returns:
            [{"memory_id": ..., "score": ..., "summary": ...}, ...]
        """
        from backend.db.memory_scoring import MemoryScoringDAO

        total = MemoryScoringDAO.get_count(agent_id)
        if total <= max_entries:
            return []

        rows = MemoryScoringDAO.get_lowest_scored(agent_id, limit)
        result: list[dict] = []
        for row in rows:
            score = self.calculate_score({
                "created_at": row["created_at"],
                "reinforcement_count": row["reinforcement_count"],
                "source": row["source"],
                "access_count": row["access_count"],
            })
            result.append({
                "memory_id": row["id"],
                "score": score,
                "summary": row["content_snippet"][:100],
                "source": row["source"],
            })

        return result

    async def update_scores_for_agent(self, agent_id: str) -> int:
        """重新计算并持久化 Agent 所有记忆的评分。

        Returns:
            更新的记忆数量。
        """
        from backend.db.memory_scoring import MemoryScoringDAO

        rows = MemoryScoringDAO.get_all_meta(agent_id)
        if not rows:
            return 0

        updated = 0
        for row in rows:
            score = self.calculate_score({
                "created_at": row["created_at"],
                "reinforcement_count": row["reinforcement_count"],
                "source": row["source"],
                "access_count": row["access_count"],
            })
            MemoryScoringDAO.update_score(row["id"], score)
            updated += 1

        return updated

    async def detect_conflicts(
        self,
        agent_id: str,
        min_confidence: float = 0.6,
        limit: int = 10,
    ) -> list[dict]:
        """检测 Agent 记忆中的事实冲突（矛盾对）。

        通过内容片段的关键词+否定词对比，找出可能互相矛盾的两条记忆。

        Args:
            agent_id: Agent ID
            min_confidence: 最低冲突置信度阈值
            limit: 最多返回的冲突对数量

        Returns:
            [{"mem_a": ..., "mem_b": ..., "conflict_type": ..., "confidence": ..., "detail": ...}, ...]
        """
        from backend.db.memory_scoring import MemoryScoringDAO

        rows = MemoryScoringDAO.get_all_meta(agent_id)
        if len(rows) < 2:
            return []

        conflicts: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a = rows[i]
                b = rows[j]
                snippet_a = a["content_snippet"] or ""
                snippet_b = b["content_snippet"] or ""
                if not snippet_a or not snippet_b:
                    continue

                pair_key = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                result = _CONFLICT_DETECTOR.detect_pair(
                    snippet_a, snippet_b,
                    mem_id_a=a["id"], mem_id_b=b["id"],
                )
                if result and result.get("confidence", 0) >= min_confidence:
                    conflicts.append(result)

        conflicts.sort(key=lambda c: -c["confidence"])
        if len(conflicts) > limit:
            conflicts = conflicts[:limit]

        return conflicts

    async def detect_conflicts_enhanced(
        self,
        agent_id: str,
        min_confidence: float = 0.5,
        limit: int = 10,
        use_vector_search: bool = True,
        use_llm_verdict: bool = False,
    ) -> list[dict]:
        """增强版冲突检测：关键词检测 + 向量相似度校验 + 可选 LLM 判定。

        检测流程（三级级联）：
        1. **一级（关键词）**：基于否定标记和实体重叠的传统检测
        2. **二级（向量）**：对置信度在 [0.3, 0.7) 的候选，通过 MemOS 向量搜索
           查找语义相似的记忆，若搜回另一条冲突记忆则置信度 +0.15
        3. **三级（LLM）**：对置信度仍偏低的候选，通过 MemOS Chat LLM 做最终裁决

        Args:
            agent_id: Agent ID
            min_confidence: 最低冲突置信度阈值
            limit: 最多返回的冲突对数量
            use_vector_search: 是否启用向量相似度校验（默认 True）
            use_llm_verdict: 是否启用 LLM 判定（默认 False，节省 token）

        Returns:
            增强后的冲突对列表，含 ``enhanced`` 和 ``llm_verified`` 标记。
        """
        # 一级：关键词检测
        conflicts = await self.detect_conflicts(
            agent_id=agent_id,
            min_confidence=0.3,  # 降低阈值，让更多候选进入后续阶段
            limit=limit * 3,     # 多取，后续再筛选
        )

        if not conflicts:
            return []

        enhanced: list[dict] = []

        for c in conflicts:
            entry = dict(c)
            entry["enhanced"] = False
            entry["llm_verified"] = False
            entry["vector_corroborated"] = False

            confidence = entry.get("confidence", 0)

            # 高置信度直接通过
            if confidence >= 0.7:
                enhanced.append(entry)
                continue

            # 二级：向量相似度校验
            if use_vector_search and confidence >= 0.3:
                try:
                    vector_boost = await self._vector_corroboration(
                        agent_id,
                        entry.get("snippet_a", ""),
                        entry.get("snippet_b", ""),
                    )
                    if vector_boost > 0:
                        entry["confidence"] = round(min(confidence + vector_boost, 1.0), 4)
                        entry["enhanced"] = True
                        entry["vector_corroborated"] = True
                        _log.debug(
                            "memory_scoring: vector boost +%.2f for pair %s↔%s",
                            vector_boost,
                            entry.get("mem_a", "")[:12],
                            entry.get("mem_b", "")[:12],
                        )
                except Exception as e:
                    _log.debug("memory_scoring: vector search failed: %s", e)

            # 三级：LLM 裁决
            if use_llm_verdict and entry["confidence"] < 0.7 and entry["confidence"] >= 0.35:
                try:
                    llm_result = await self._llm_conflict_verdict(
                        agent_id,
                        entry.get("snippet_a", ""),
                        entry.get("snippet_b", ""),
                    )
                    if llm_result.get("is_conflict"):
                        entry["confidence"] = max(entry["confidence"], 0.75)
                        entry["llm_verified"] = True
                        entry["llm_reason"] = llm_result.get("reason", "")
                        if not entry.get("conflict_type") or entry["conflict_type"] == "generic":
                            entry["conflict_type"] = "llm_verified"
                        _log.info(
                            "memory_scoring: LLM verified conflict pair %s↔%s",
                            entry.get("mem_a", "")[:12],
                            entry.get("mem_b", "")[:12],
                        )
                    elif llm_result.get("is_conflict") is False:
                        # LLM 认为不矛盾，降低置信度
                        entry["confidence"] = max(entry["confidence"] - 0.2, 0.0)
                        entry["llm_verified"] = False
                except Exception as e:
                    _log.debug("memory_scoring: LLM verdict failed: %s", e)

            if entry["confidence"] >= min_confidence:
                enhanced.append(entry)

        enhanced.sort(key=lambda c: -c["confidence"])
        return enhanced[:limit]

    async def _vector_corroboration(
        self,
        agent_id: str,
        snippet_a: str,
        snippet_b: str,
    ) -> float:
        """通过向量搜索验证冲突对。

        分别对 snippet_a 和 snippet_b 做语义搜索：
        - 若 snippet_a 搜回的记忆中包含 snippet_b 的关键词 → +0.10
        - 若 snippet_b 搜回的记忆中包含 snippet_a 的关键词 → +0.10
        - 若双向都互相搜回 → 额外 +0.05（强关联信号）

        Returns:
            附加置信度 boost（0 ~ 0.25）。
        """
        try:
            from backend.services.mem_os_service import mos_search
        except ImportError:
            return 0.0

        if not snippet_a or not snippet_b:
            return 0.0

        try:
            results_a = mos_search(agent_id, snippet_a[:200], top_k=3)
            results_b = mos_search(agent_id, snippet_b[:200], top_k=3)
        except Exception:
            return 0.0

        if not results_a or not results_b:
            return 0.0

        # 提取 snippet_b 的关键词（用于在搜索结果中匹配）
        terms_b = set(_CONFLICT_DETECTOR._extract_terms(snippet_b))
        terms_a = set(_CONFLICT_DETECTOR._extract_terms(snippet_a))

        boost = 0.0

        # 检查 snippet_a 的搜索结果是否包含 snippet_b 的实质内容
        for r in results_a:
            r_terms = set(_CONFLICT_DETECTOR._extract_terms(r))
            if r_terms & terms_b:
                boost += 0.10
                break

        # 检查 snippet_b 的搜索结果是否包含 snippet_a 的实质内容
        for r in results_b:
            r_terms = set(_CONFLICT_DETECTOR._extract_terms(r))
            if r_terms & terms_a:
                boost += 0.10
                break

        # 如果双向都互相搜回了相关记忆，额外加分
        if boost >= 0.15:
            boost += 0.05

        return min(boost, 0.25)

    async def _llm_conflict_verdict(
        self,
        agent_id: str,
        snippet_a: str,
        snippet_b: str,
    ) -> dict:
        """通过 MemOS Chat LLM 判断两条记忆是否存在事实矛盾。

        Returns:
            {"is_conflict": True/False, "reason": "..."}
        """
        prompt = (
            "你是记忆一致性检查器。请判断以下两条记忆是否互相矛盾：\n\n"
            f"记忆 A：{snippet_a}\n"
            f"记忆 B：{snippet_b}\n\n"
            "请仅以 JSON 格式回复：\n"
            '{"is_conflict": true/false, "reason": "简短说明"}'
        )

        try:
            from backend.services.mem_os_service import mos_chat
            reply = mos_chat(agent_id, prompt)
        except Exception:
            return {"is_conflict": False, "reason": "LLM 不可用"}

        if not reply:
            return {"is_conflict": False, "reason": "LLM 无回复"}

        # 解析 JSON 回复
        import json
        import re

        json_match = re.search(r"\{[^}]+\}", reply, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                if isinstance(result, dict) and "is_conflict" in result:
                    return result
            except json.JSONDecodeError:
                pass

        # fallback：检查文本中是否包含"矛盾"/"不一致"等词
        conflict_words = ("矛盾", "不一致", "冲突", "抵触", "不同")
        is_conflict = any(w in reply for w in conflict_words)
        return {"is_conflict": is_conflict, "reason": reply[:100]}

    async def check_write_conflict(
        self,
        agent_id: str,
        new_memory_text: str,
    ) -> list[dict]:
        """写入新记忆前检查是否与现有记忆矛盾。

        通过向量搜索找出与 new_memory_text 语义相似（≥0.85）的现有记忆，
        再用 LLM 判断是否存在矛盾。

        Args:
            agent_id: Agent ID
            new_memory_text: 即将写入的新记忆内容

        Returns:
            矛盾记忆列表 [{"existing_memory": ..., "conflict_type": ..., "confidence": ...}]
        """
        # 向量搜索相似记忆
        try:
            from backend.services.mem_os_service import mos_search
            similar = mos_search(agent_id, new_memory_text[:300], top_k=5)
        except Exception as e:
            _log.debug("memory_scoring: vector search for write check failed: %s", e)
            return []

        if not similar:
            return []

        # 检查关键词重叠，筛选有实质关联的
        from backend.db.memory_scoring import MemoryScoringDAO

        new_terms = _CONFLICT_DETECTOR._extract_terms(new_memory_text)
        if not new_terms:
            return []

        conflicts: list[dict] = []

        for existing_text in similar:
            # 使用检测器做基础冲突检查
            result = _CONFLICT_DETECTOR.detect_pair(
                new_memory_text, existing_text,
            )
            if result and result.get("confidence", 0) >= 0.3:
                # 用 LLM 做最终裁决
                try:
                    llm_result = await self._llm_conflict_verdict(
                        agent_id,
                        new_memory_text,
                        existing_text,
                    )
                    if llm_result.get("is_conflict"):
                        conflicts.append({
                            "existing_memory": existing_text[:200],
                            "new_memory": new_memory_text[:200],
                            "conflict_type": "semantic_contradiction",
                            "confidence": max(result.get("confidence", 0), 0.6),
                            "llm_reason": llm_result.get("reason", ""),
                        })
                except Exception as e:
                    _log.debug("memory_scoring: check_write LLM failed: %s", e)
                    # 即使 LLM 失败，若有较高关键词冲突也返回
                    if result.get("confidence", 0) >= 0.6:
                        conflicts.append({
                            "existing_memory": existing_text[:200],
                            "new_memory": new_memory_text[:200],
                            "conflict_type": result.get("conflict_type", "generic"),
                            "confidence": result.get("confidence", 0),
                        })

        conflicts.sort(key=lambda c: -c["confidence"])
        return conflicts[:3]


# ── 记忆冲突检测器 ─────────────────────────────────────────────────────


class _MemoryConflictDetector:
    """基于关键词和否定标记的记忆冲突检测。

    检测策略：
      1. 抽取两条记忆的共同实体词（重叠的名词/主题词）
      2. 检查否定标记：一条含「是/支持/能」而另一条含「不是/不支持/不能」
      3. 冲突置信度 = 实体重叠分 + 否定标记分
    """

    # 中文否定——肯定配对
    POS_NEG_PAIRS: tuple[tuple[str, str], ...] = (
        ("是", "不是"),
        ("能", "不能"),
        ("可以", "不可以"),
        ("支持", "不支持"),
        ("需要", "不需要"),
        ("允许", "不允许"),
        ("会", "不会"),
        ("应该", "不应该"),
        ("有", "没有"),
    )

    # 逻辑矛盾标记词
    CONFLICT_MARKERS: tuple[str, ...] = (
        "但是", "然而", "实际上", "恰恰相反", "反过来",
        "并非", "错误", "误解",
    )

    # 需要跳过的停用词
    STOP_WORDS: set[str] = {
        "的", "了", "在", "是", "我", "有", "和", "就",
        "不", "人", "都", "一", "一个", "上", "也", "很",
        "到", "说", "要", "去", "你", "会", "着", "没有",
        "看", "好", "自己", "这", "他", "她", "它", "们",
        "那", "什么", "怎么", "为什么", "因为", "所以",
    }

    def _extract_terms(self, text: str) -> list[str]:
        """从文本中提取有意义的词（简单切分）。"""
        import re
        tokens = re.findall(r"[\u4e00-\u9fff\w]{2,}", text)
        return [t for t in tokens if t.lower() not in self.STOP_WORDS]

    def detect_pair(
        self,
        snippet_a: str,
        snippet_b: str,
        mem_id_a: str = "",
        mem_id_b: str = "",
    ) -> dict | None:
        """检测两条记忆片段是否存在事实冲突。"""
        terms_a = self._extract_terms(snippet_a)
        terms_b = self._extract_terms(snippet_b)

        if not terms_a or not terms_b:
            return None

        # 1. 计算实体重叠度
        set_a = set(terms_a)
        set_b = set(terms_b)
        common = set_a & set_b
        if not common:
            return None

        overlap_ratio = len(common) / max(len(set_a | set_b), 1)

        # 2. 检测否定标记
        neg_score = 0.0
        conflict_type = "generic"
        for pos, neg in self.POS_NEG_PAIRS:
            has_pos_in_a = pos in snippet_a
            has_neg_in_a = neg in snippet_a
            has_pos_in_b = pos in snippet_b
            has_neg_in_b = neg in snippet_b

            if (has_pos_in_a and has_neg_in_b) or (has_pos_in_b and has_neg_in_a):
                neg_score += 1.0
                conflict_type = "factual_negation"
                break

        # 3. 检测冲突标记词
        marker_score = 0.0
        for marker in self.CONFLICT_MARKERS:
            if marker in snippet_a:
                marker_score += 0.3
            if marker in snippet_b:
                marker_score += 0.3
        marker_score = min(marker_score, 0.5)

        # 4. 综合置信度
        confidence = overlap_ratio * 0.4 + neg_score * 0.5 + marker_score * 0.1
        if confidence < 0.3:
            return None

        return {
            "mem_a": mem_id_a,
            "mem_b": mem_id_b,
            "snippet_a": snippet_a[:120],
            "snippet_b": snippet_b[:120],
            "conflict_type": conflict_type,
            "confidence": round(min(confidence, 1.0), 4),
            "shared_terms": sorted(common)[:10],
            "detail": (
                f"共同主题: {', '.join(sorted(common)[:5])}"
                f"{'; 发现否定矛盾' if neg_score > 0 else ''}"
                f"{'; 含矛盾标记词' if marker_score > 0 else ''}"
            ),
        }


_CONFLICT_DETECTOR = _MemoryConflictDetector()
