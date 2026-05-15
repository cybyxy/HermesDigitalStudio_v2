"""技能（Skill）管理：扫描、解析、分类。

从各 Agent 的 hermes_home 目录及 settings 的 skills.external_dirs 读取技能目录。
每个目录下必须有 SKILL.md 文件，返回技能 id（目录名）、name、description（均从 SKILL.md 解析）以及 path。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _load_skill_meta(skill_path: Path) -> dict[str, Any]:
    """解析 SKILL.md 的 frontmatter，返回完整元数据。"""
    skill_md = skill_path / "SKILL.md"
    name = skill_path.name
    description = ""
    version = ""
    author = ""
    license_ = ""
    platforms: list[str] = []
    commands: list[str] = []
    tags: list[str] = []

    if skill_md.is_file():
        try:
            text = skill_md.read_text(encoding="utf-8")
            header_re = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
            m = header_re.match(text)
            if m:
                import yaml
                data = yaml.safe_load(m.group(1)) or {}
                name = data.get("name", name) or name
                description = data.get("description", "") or ""
                version = data.get("version", "") or ""
                author = data.get("author", "") or ""
                license_ = data.get("license", "") or ""
                platforms = data.get("platforms", []) or []
                prerequisites = data.get("prerequisites", {}) or {}
                commands = prerequisites.get("commands", []) if isinstance(prerequisites, dict) else []
                metadata = data.get("metadata", {}) or {}
                if isinstance(metadata, dict):
                    hermes_meta = metadata.get("hermes", {}) or {}
                    if isinstance(hermes_meta, dict):
                        tags = hermes_meta.get("tags", []) or []
            else:
                lines = text.strip().splitlines()
                if lines:
                    first = lines[0].strip()
                    if first.startswith("#"):
                        first = first.lstrip("#").strip()
                    if first:
                        name = first
        except Exception:
            pass

    return {
        "name": name,
        "description": description,
        "version": version,
        "author": author,
        "license": license_,
        "platforms": platforms,
        "commands": commands,
        "tags": tags,
    }


def _find_skills_in_dir(base_path: Path) -> list[dict[str, Any]]:
    """递归扫描 base_path 下所有包含 SKILL.md 的目录。

    category 取 SKILL.md 所在目录的直接父目录名（便于前端按分类展示）。
    如果 SKILL.md 就在 base_path 的直接子目录下，则 category 为该子目录名。
    """
    if not base_path.is_dir():
        return []

    skills: list[dict[str, Any]] = []

    def scan_recursive(current: Path) -> None:
        if current.name.startswith('.'):
            return
        skill_md = current / "SKILL.md"
        if skill_md.is_file():
            # 找到技能：category 为 current 的父目录名
            category = current.parent.name
            meta = _load_skill_meta(current)
            skills.append({
                "id": current.name,
                "name": meta["name"],
                "description": meta["description"],
                "path": str(current),
                "category": category,
                "version": meta.get("version", ""),
                "author": meta.get("author", ""),
                "license": meta.get("license", ""),
                "platforms": meta.get("platforms", []),
                "commands": meta.get("commands", []),
                "tags": meta.get("tags", []),
            })
            return
        # 还没找到 SKILL.md，继续递归子目录
        try:
            for entry in sorted(current.iterdir()):
                if entry.is_dir() and not entry.name.startswith('.'):
                    scan_recursive(entry)
        except PermissionError:
            pass

    scan_recursive(base_path)
    return skills


def _scan_skills_in_dir(base_path: Path) -> list[dict[str, Any]]:
    """扫描 base_path/skills/ 目录下的所有技能（兼容旧调用）。"""
    skills_dir = base_path / "skills"
    return _find_skills_in_dir(skills_dir)


def list_skills_per_agent(
    agents_data: list[dict[str, Any]],
    get_manager,
) -> list[dict[str, Any]]:
    """列出所有已配置的技能，按 Agent 分组。

    每个 Agent tab 下显示：
    - 该 Agent profile 目录下以 skills/ 子目录存在的技能
    - 全局 external_dirs 中属于该 Agent 的技能（通过 skill 目录名匹配）
    """
    external_dirs: list[str] = []
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        external_dirs = cfg.get("skills", {}).get("external_dirs", [])
    except Exception:
        pass

    all_skill_paths: dict[str, str] = {}  # path -> agent_id

    result: list[dict[str, Any]] = []

    for agent_info in agents_data:
        agent_id = str(agent_info.get("agentId") or "")
        profile = str(agent_info.get("profile") or "default")
        display_name = str(agent_info.get("displayName") or profile)

        gw_home = None
        try:
            info = get_manager().get_agent(agent_id)
            if info is not None:
                gw_home = getattr(info.gateway, "hermes_home", None)
        except Exception:
            pass

        if gw_home:
            hermes_home = str(Path(gw_home).expanduser())
        else:
            hermes_home = str(Path("~/.hermes").expanduser() / ("profiles/" + profile if profile != "default" else ""))

        agent_skills = _scan_skills_in_dir(Path(hermes_home))
        all_skill_paths.update({s["path"]: agent_id for s in agent_skills})

        for dir_path in external_dirs:
            p = Path(dir_path).expanduser().resolve()
            if not p.is_dir():
                continue
            if p.name.startswith('.'):
                continue
            if p.name not in all_skill_paths:
                is_associated = (
                    profile in p.name or
                    agent_id in p.name or
                    any(aid in p.name for aid in [agent_id, profile, display_name])
                )
                if is_associated:
                    meta = _load_skill_meta(p)
                    agent_skills.append({
                        "id": p.name,
                        "name": meta["name"],
                        "description": meta["description"],
                        "path": str(p),
                        "version": meta.get("version", ""),
                        "author": meta.get("author", ""),
                        "license": meta.get("license", ""),
                        "platforms": meta.get("platforms", []),
                        "commands": meta.get("commands", []),
                        "tags": meta.get("tags", []),
                    })
                    all_skill_paths[str(p)] = agent_id

        result.append({
            "agentId": agent_id,
            "agentName": display_name,
            "profile": profile,
            "skills": agent_skills,
        })

    return result
