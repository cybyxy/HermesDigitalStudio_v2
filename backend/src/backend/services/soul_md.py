"""SOUL.md 读写模块。

对应 Spring Boot Service 层 — 纯文件 I/O，无 agent 生命周期或数据库依赖。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

__all__ = [
    "write_soul_md",
    "parse_soul_md",
    "update_soul_md_field",
]

_log = logging.getLogger(__name__)


def write_soul_md(
    hermes_home: str,
    display_name: str,
    identity: str = "",
    style: str = "",
    defaults: str = "",
    avoid: str = "",
    core_truths: str = "",
) -> None:
    """将角色设定写入对应 profile 目录的 SOUL.md。

    SOUL.md 结构（无 ## 二节 / ## 三节 标记）：
    - 首行："我叫**{显示名称}**"
    - ## Identity / ## Style / ### Defaults / ### Avoid / ### Core Truths

    若文件已存在则整体覆盖（displayName 取 frontmatter name，body 合并各节）。"""
    import yaml

    soul_path = Path(hermes_home) / "SOUL.md"
    # 匹配 YAML frontmatter: ---...---
    header_re = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

    parts = [f"我叫**{display_name}**"]
    if identity.strip():
        parts.append(f"## Identity\n\n{identity.strip()}\n")
    if style.strip():
        parts.append(f"## Style\n\n{style.strip()}\n")
    if defaults.strip():
        parts.append(f"### Defaults\n\n{defaults.strip()}\n")
    if avoid.strip():
        parts.append(f"### Avoid\n\n{avoid.strip()}\n")
    if core_truths.strip():
        parts.append(f"### Core Truths\n\n{core_truths.strip()}\n")
    body = "\n\n".join(parts) + "\n"

    if soul_path.is_file():
        text = soul_path.read_text(encoding="utf-8")
        m = header_re.match(text)
        if m:
            # 已有 frontmatter — 只更新 name 字段，保留原有内容（body 部分）
            data = yaml.safe_load(m.group(1)) or {}
            data["name"] = display_name
            frontmatter = "---\n" + yaml.dump(data, allow_unicode=True, default_flow_style=False) + "---\n"
            soul_path.write_text(frontmatter + body, encoding="utf-8")
            return
        # 无 frontmatter — 原地添加，保留原有内容
        frontmatter = "---\n" + yaml.dump({"name": display_name}, allow_unicode=True, default_flow_style=False) + "---\n"
        soul_path.write_text(frontmatter + body, encoding="utf-8")
    else:
        # 文件不存在 — 创建新文件
        frontmatter = "---\n" + yaml.dump({"name": display_name}, allow_unicode=True, default_flow_style=False) + "---\n"
        soul_path.write_text(frontmatter + body, encoding="utf-8")


def parse_soul_md(text: str) -> dict[str, str]:
    """从 SOUL.md 文本解析出各字段。

    同时兼容：
    - 新格式（无 ## 二节 / ## 三节）：直接解析 ## Identity / ## Style / ### Defaults 等
    - 旧格式（有 ## 二节）：在二节/三节内部解析子节

    显示名称：正文「我叫**…**」优先于 YAML ``name``（后者常为 profile 英文名，会盖住用户显示名）。
    """
    identity = ""
    style = ""
    defaults = ""
    avoid = ""
    core_truths = ""

    header_re = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
    m = header_re.match(text)
    yaml_name = ""
    if m:
        import yaml
        data = yaml.safe_load(m.group(1)) or {}
        yaml_name = str(data.get("name", "") or "").strip()

    # 去掉 frontmatter，剩下的全部内容用状态机解析
    body = header_re.sub("", text).strip()

    intro_name = ""
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("我叫"):
            intro_name = line.replace("我叫", "").replace("**", "").strip()
            break
        # 正文里若先出现二级标题再出现「我叫」极少见；遇 ## 则停止扫 intro
        if re.match(r"^##\s+", line):
            break

    display_name = (intro_name or yaml_name).strip()

    # _KNOWN_FIELDS: 既可以是 level-2 (## Identity) 也可以是 level-3 (### Defaults)
    _KNOWN = frozenset(("Identity", "Style", "Defaults", "Avoid", "Core Truths"))
    sub_section: str | None = None
    buffer: list[str] = []

    def _flush():
        nonlocal identity, style, defaults, avoid, core_truths
        content = "\n".join(buffer).strip()
        if sub_section == "Identity":
            identity = content
        elif sub_section == "Style":
            style = content
        elif sub_section == "Defaults":
            defaults = content
        elif sub_section == "Avoid":
            avoid = content
        elif sub_section == "Core Truths":
            core_truths = content

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("我叫"):
            continue
        m2 = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m2:
            title = m2.group(2).strip()
            _flush()
            buffer = []
            if title in _KNOWN:
                # ## Identity / ## Style / ### Defaults — 全部按字段名直接识别
                sub_section = title
            else:
                # ## 二节 / ## 三节 等容器标题
                sub_section = None
        else:
            buffer.append(line)

    _flush()

    return {
        "displayName": display_name,
        "identity": identity,
        "style": style,
        "defaults": defaults,
        "avoid": avoid,
        "coreTruths": core_truths,
    }


def update_soul_md_field(hermes_home: str, field: str, content: str) -> bool:
    """向 SOUL.md 的指定字段追加内容（避免重复）。

    支持 SOUL.md 中的可写字段：
    - ``Identity``, ``Style``, ``Defaults``, ``Avoid``, ``CoreTruths``

    Args:
        hermes_home: Agent 的 hermes_home 目录路径。
        field: SOUL.md 字段名（首字母大写，如 ``Style``, ``CoreTruths``）。
        content: 要追加的内容。

    Returns:
        True 表示内容已追加，False 表示内容已存在或字段名无效。
    """
    VALID_FIELDS = frozenset({"Identity", "Style", "Defaults", "Avoid", "CoreTruths"})
    if field not in VALID_FIELDS:
        return False

    soul_path = Path(hermes_home) / "SOUL.md"
    if not soul_path.is_file():
        return False

    text = soul_path.read_text(encoding="utf-8")
    parsed = parse_soul_md(text)
    # map field name to parse_soul_md key: Identity→identity, CoreTruths→coreTruths
    section_key = field[0].lower() + field[1:]

    current = parsed.get(section_key, "")
    stripped_content = content.strip()
    if not stripped_content:
        return False

    if current and current.strip():
        if stripped_content in current:
            return False  # 已存在，跳过重复
        new_body = current.rstrip("\n") + "\n" + stripped_content
    else:
        new_body = stripped_content

    soul_path.write_text(_rebuild_soul_md(text, field, new_body), encoding="utf-8")
    _log.info("update_soul_md_field(%s): appended to %s", hermes_home, field)
    return True


def _rebuild_soul_md(original_text: str, target_field: str, new_value: str) -> str:
    """在现有 SOUL.md 文本中替换或新增指定字段的内容。"""
    import re as _re

    header_re = _re.compile(r"^---\n.*?\n---\n", re.DOTALL)
    body = header_re.sub("", original_text).strip()

    top_level = frozenset({"Identity", "Style"})
    if target_field in top_level:
        section_header = f"## {target_field}"
        next_pattern = r"\n(?:##|\Z)"
    else:
        section_header = f"### {target_field}"
        next_pattern = r"\n(?:##|###|\Z)"

    section_pattern = _re.compile(
        rf"({re.escape(section_header)}\n\n)(.*?)(?={next_pattern})",
        re.DOTALL,
    )
    match = section_pattern.search(body)
    if match:
        body = section_pattern.sub(rf"\1{new_value.strip()}\n\n", body, count=1)
    else:
        body = body.rstrip("\n") + f"\n\n{section_header}\n\n{new_value.strip()}\n"

    header_match = header_re.match(original_text)
    if header_match:
        return header_match.group(0) + body + "\n"
    return body + "\n"
