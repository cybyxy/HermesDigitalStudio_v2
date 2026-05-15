"""Skill Controller — 技能相关的 HTTP 路由。

对应 Spring Boot @RestController。
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException, Query

from backend.services import agent as agent_service
from backend.services import skill as skill_service

router = APIRouter(prefix="/chat", tags=["skills"])
_log = logging.getLogger(__name__)


@router.get("/skills")
async def list_skills() -> dict:
    """列出所有已配置的技能，按 Agent 分组。

    从各 Agent 的 hermes_home 目录及 settings 的 skills.external_dirs 读取技能目录。
    每个目录下必须有 SKILL.md 文件，返回技能 id（目录名）、name、description（均从 SKILL.md 解析）以及 path。
    每个 Agent tab 下显示：
    - 该 Agent profile 目录下以 skills/ 子目录存在的技能
    - 全局 external_dirs 中属于该 Agent 的技能（通过 skill 目录名匹配）
    """
    agents_data = agent_service.list_agents()
    agents = skill_service.list_skills_per_agent(agents_data, agent_service._get_manager)
    return {"ok": True, "agents": agents}


@router.get("/skills/read")
async def read_skill_md(skill_path: str = Query(..., alias="skill_path")) -> dict:
    """读取指定技能目录下的 SKILL.md（路径用查询参数，避免 URL 路径中的 / 被错误解析）。"""
    p = Path(skill_path).expanduser()
    skill_md = p / "SKILL.md"
    if not skill_md.is_file():
        raise HTTPException(status_code=404, detail=f"SKILL.md not found under {skill_path}")
    content = skill_md.read_text(encoding="utf-8")
    return {"ok": True, "content": content}


@router.put("/skills/content")
async def write_skill_md(body: dict) -> dict:
    """写入 SKILL.md。body: { \"skillPath\": str, \"content\": str }"""
    skill_path = body.get("skillPath") or body.get("skill_path")
    if not skill_path or not isinstance(skill_path, str):
        raise HTTPException(status_code=400, detail="skillPath is required")
    p = Path(skill_path).expanduser()
    skill_md = p / "SKILL.md"
    if not skill_md.is_file():
        raise HTTPException(status_code=404, detail=f"SKILL.md not found under {skill_path}")
    content = body.get("content", "")
    if not isinstance(content, str):
        content = ""
    skill_md.write_text(content, encoding="utf-8")
    return {"ok": True}


@router.delete("/skills")
async def delete_skill(skill_path: str = Query(..., alias="skill_path")) -> dict:
    """删除指定技能目录及其下的所有文件，并触发 Agent 技能热重载。"""
    p = Path(skill_path).expanduser()
    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill directory not found: {skill_path}")
    shutil.rmtree(p)
    _log.info("已删除技能目录: %s", p)

    # 触发 Hermes Agent 技能热重载，使运行中的 Agent 立即感知技能变更
    try:
        from agent.skill_commands import reload_skills
        result = reload_skills()
        _log.info("技能重载完成: added=%s, removed=%s, total=%s",
                  result.get("added", []), result.get("removed", []), result.get("total", 0))
    except Exception as e:
        _log.warning("技能重载失败（不影响目录删除）: %s", e)

    return {"ok": True}
