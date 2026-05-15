"""测试 SOUL.md 解析。"""
from __future__ import annotations

from backend.services.soul_md import parse_soul_md


class TestParseSoulMd:
    """SOUL.md 解析测试。"""

    def test_parse_basic(self):
        text = """---
name: Tester
---

我叫**测试员**

## Identity

我是一个测试工程师。

## Style

简洁、直接。

### Defaults

默认使用中文回复。

### Avoid

避免使用过于技术化的术语。

### Core Truths

质量第一。
"""
        result = parse_soul_md(text)
        assert result["displayName"] == "测试员"  # 优先使用「我叫」中的名称
        assert "测试工程师" in result["identity"]
        assert "简洁" in result["style"]
        assert "中文回复" in result["defaults"]
        assert "技术化" in result["avoid"]
        assert "质量第一" in result["coreTruths"]

    def test_display_name_from_body_priority(self):
        """正文「我叫」优先于 YAML name。"""
        text = """---
name: EnglishName
---

我叫**中文名**
"""
        result = parse_soul_md(text)
        assert result["displayName"] == "中文名"

    def test_display_name_from_yaml_fallback(self):
        """无正文「我叫」时使用 YAML name。"""
        text = """---
name: FallbackName
---

## Identity

Test content.
"""
        result = parse_soul_md(text)
        assert result["displayName"] == "FallbackName"

    def test_empty_fields(self):
        text = """---
name: test
---
"""
        result = parse_soul_md(text)
        assert result["identity"] == ""
        assert result["style"] == ""
        assert result["defaults"] == ""
        assert result["avoid"] == ""
        assert result["coreTruths"] == ""

    def test_no_frontmatter(self):
        text = "我叫**无名**\n\n## Identity\n\nTesting"
        result = parse_soul_md(text)
        assert result["displayName"] == "无名"
        assert "Testing" in result["identity"]

    def test_partial_sections(self):
        """只提供部分 section。"""
        text = """---
name: x
---

## Identity

Who I am.

### Defaults

Default behavior.
"""
        result = parse_soul_md(text)
        assert result["identity"] == "Who I am."
        assert result["style"] == ""
        assert result["defaults"] == "Default behavior."
        assert result["avoid"] == ""
        assert result["coreTruths"] == ""

    def test_intro_name_stops_at_heading(self):
        """「我叫」必须出现在第一个 ## 标题之前才会被识别。"""
        text = """---
name: yaml
---

## Identity

我叫**被忽略的名称**
"""
        result = parse_soul_md(text)
        assert result["displayName"] == "yaml"  # body 中的「我叫」出现在 ## 之后，被忽略
