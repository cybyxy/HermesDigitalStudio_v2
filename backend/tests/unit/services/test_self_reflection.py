"""测试自我反思引擎的独立功能（JSON 解析、频率控制、风格适配）。"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from backend.vendor_patches.self_reflection import (
    REFLECTION_COOLDOWN_SECONDS,
    _adapt_soul_md_style,
    _parse_reflection_result,
    check_reflection_eligibility,
)


class TestParseReflectionResult:
    """_parse_reflection_result JSON 解析测试。"""

    def test_parse_json_block(self):
        text = '```json\n{"preferences_updates": ["喜欢简洁"], "confidence": "high"}\n```'
        result = _parse_reflection_result(text)
        assert result is not None
        assert result["preferences_updates"] == ["喜欢简洁"]
        assert result["confidence"] == "high"

    def test_parse_json_block_no_label(self):
        text = '```\n{"preferences_updates": ["喜欢Python"]}\n```'
        result = _parse_reflection_result(text)
        assert result is not None
        assert "喜欢Python" in result["preferences_updates"]

    def test_parse_plain_json(self):
        text = '{"preferences_updates": [], "confidence": "low"}'
        result = _parse_reflection_result(text)
        assert result is not None
        assert result["confidence"] == "low"

    def test_parse_with_extra_text(self):
        text = '以下是反思结果：\n```json\n{"preferences_updates": ["a"], "capabilities_learned": ["b"]}\n```\n完毕。'
        result = _parse_reflection_result(text)
        assert result is not None
        assert result["preferences_updates"] == ["a"]

    def test_parse_empty_returns_none(self):
        assert _parse_reflection_result("") is None
        assert _parse_reflection_result("   ") is None

    def test_parse_extract_braces(self):
        text = "some text before { \"key\": \"value\" } and after"
        result = _parse_reflection_result(text)
        assert result is not None
        assert result["key"] == "value"

    def test_parse_invalid_returns_none(self):
        assert _parse_reflection_result("不是 JSON {{") is None


class TestCheckReflectionEligibility:
    """check_reflection_eligibility 频率控制测试。"""

    def test_cooldown_prevents_immediate_rerun(self):
        # 模拟刚做过反思
        import backend.vendor_patches.self_reflection as sr
        sr._LAST_REFLECTION["test_agent"] = time.time()
        assert not check_reflection_eligibility("test_agent", "test_session")
        del sr._LAST_REFLECTION["test_agent"]

    def test_busy_check(self):
        import backend.vendor_patches.self_reflection as sr
        with sr._run_lock:
            sr._reflection_running["busy_agent"] = True
        assert not check_reflection_eligibility("busy_agent", "test_session")
        with sr._run_lock:
            sr._reflection_running["busy_agent"] = False

    def test_message_count_below_minimum(self):
        import backend.vendor_patches.self_reflection as sr
        # 清除冷却
        sr._LAST_REFLECTION.pop("low_msg_agent", None)
        with patch.object(sr, "_get_session_message_count", return_value=5):
            assert not check_reflection_eligibility("low_msg_agent", "test_session")


class TestAdaptSoulMdStyle:
    """_adapt_soul_md_style 风格关键字识别测试。"""

    def test_style_keyword_does_nothing_without_match(self):
        # 没有风格关键词不应调用 update_soul_md_field
        with patch("backend.services.soul_md.update_soul_md_field") as mock_update:
            _adapt_soul_md_style("test_agent", ["学会了Python"], ["经常写测试"])
            mock_update.assert_not_called()

    def test_style_keyword_triggers_update(self):
        with patch("backend.services.soul_md.update_soul_md_field") as mock_update:
            with patch("backend.services.self_model._resolve_hermes_home", return_value="/tmp/test_home"):
                _adapt_soul_md_style("test_agent", ["偏好简洁的回答"], [])
                mock_update.assert_called_once()

    def test_behavior_style_keyword(self):
        with patch("backend.services.soul_md.update_soul_md_field") as mock_update:
            with patch("backend.services.self_model._resolve_hermes_home", return_value="/tmp/test_home"):
                _adapt_soul_md_style("test_agent", [], ["回复时倾向用正式的语言"])
                mock_update.assert_called_once()

    def test_no_hermes_home_skips(self):
        with patch("backend.services.soul_md.update_soul_md_field") as mock_update:
            with patch("backend.services.self_model._resolve_hermes_home", return_value=None):
                _adapt_soul_md_style("test_agent", ["偏好简洁的回答"], [])
                mock_update.assert_not_called()
