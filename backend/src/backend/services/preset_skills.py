"""胎教技能包 — 预置 Agent 技能定义。

提供可直接注入到 Agent 子进程的预设技能模板，
每种技能定义包含 SKILL.md 路径和默认 personality 配置。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

_PRESET_DIR = Path(__file__).parent / "preset_skills"


@dataclass
class SkillPreset:
    """预置技能定义。"""
    id: str
    name: str
    description: str
    skill_md_path: str          # SKILL.md 文件路径
    default_personality: str = ""
    default_catchphrases: str = ""
    recommended_model: str = "gpt-4o-mini"
    icon: str = "🤖"

    def read_skill_md(self) -> str:
        """读取 SKILL.md 内容。"""
        p = Path(self.skill_md_path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""


# ── 预置技能定义 ───────────────────────────────────────────────────────

PRESETS: list[SkillPreset] = [
    SkillPreset(
        id="code-reviewer",
        name="代码审查专家",
        description="精通代码审查，能识别安全漏洞、性能瓶颈和代码异味",
        skill_md_path=str(_PRESET_DIR / "code-reviewer" / "SKILL.md"),
        default_personality="严谨、细致、注重代码质量和安全性",
        default_catchphrases="这里有一个潜在的空指针风险\n建议改为...\n测试覆盖率不足",
        recommended_model="gpt-4o",
        icon="🔍",
    ),
    SkillPreset(
        id="content-writer",
        name="内容写作专家",
        description="擅长各类文案创作，从技术文档到营销文案",
        skill_md_path=str(_PRESET_DIR / "content-writer" / "SKILL.md"),
        default_personality="文字细腻、善于共情、注重逻辑与美感",
        default_catchphrases="让我帮你梳理一下结构\n这个表述可以更有感染力\n读者会喜欢这个角度",
        recommended_model="gpt-4o-mini",
        icon="✍️",
    ),
    SkillPreset(
        id="data-analyst",
        name="数据分析专家",
        description="数据分析、统计推断、可视化建议",
        skill_md_path=str(_PRESET_DIR / "data-analyst" / "SKILL.md"),
        default_personality="理性、数据驱动、善于从数字中发现洞察",
        default_catchphrases="从数据来看...\n相关性不等于因果\n让我画张图来说明",
        recommended_model="gpt-4o",
        icon="📊",
    ),
]


def list_presets() -> list[dict]:
    """列出所有预置技能（不含 SKILL.md 全文）。"""
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "defaultPersonality": p.default_personality,
            "defaultCatchphrases": p.default_catchphrases,
            "recommendedModel": p.recommended_model,
            "icon": p.icon,
        }
        for p in PRESETS
    ]


def get_preset(preset_id: str) -> dict | None:
    """获取指定预置技能的完整定义。"""
    for p in PRESETS:
        if p.id == preset_id:
            return {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "skillMd": p.read_skill_md(),
                "defaultPersonality": p.default_personality,
                "defaultCatchphrases": p.default_catchphrases,
                "recommendedModel": p.recommended_model,
                "icon": p.icon,
            }
    return None
