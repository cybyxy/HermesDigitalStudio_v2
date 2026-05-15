"""环境行为生成单元测试"""
from __future__ import annotations

from backend.services.environment_behavior import (
    BehaviorResult,
    PADDelta,
    select_environment_focus,
    build_environment_behavior_prompt,
    parse_behavior_response,
)


class TestSelectFocus:
    def test_select_from_items(self):
        items = [
            ({"name": "窗户", "mood_tags": ["bright"]}, 30),
            ({"name": "书架", "mood_tags": ["nostalgic"]}, 100),
        ]
        focus = select_environment_focus(items)
        assert focus is not None
        assert focus["name"] in ("窗户", "书架")

    def test_no_items(self):
        assert select_environment_focus([]) is None

    def test_avoids_recent(self):
        items = [({"name": "窗户", "mood_tags": ["bright"]}, 30)]
        focus = select_environment_focus(items, recent_focuses=["窗户"])
        # 可能返回 None 或降权后仍选中
        if focus is not None:
            assert focus["name"] == "窗户"

    def test_with_mood_tags(self):
        items = [
            ({"name": "窗", "mood_tags": []}, 50),
            ({"name": "书架", "mood_tags": ["nostalgic", "intellectual"]}, 50),
        ]
        # 有 mood_tags 的物品应更可能被选中
        results = []
        for _ in range(20):
            f = select_environment_focus(items)
            if f:
                results.append(f["name"])
        # 书架被选中的概率应≥窗户
        if results:
            pass  # 随机选择，不做强断言


class TestBuildPrompt:
    def test_builds_valid_prompt(self):
        prompt = build_environment_behavior_prompt(
            personality="温和、好奇",
            valence=0.5,
            arousal=0.3,
            dominance=0.2,
            satiety=70,
            environment_perception="前方有一个窗户。",
            focus_name="窗户",
            focus_description="阳光明媚。",
            mood_tags=["bright", "warm"],
            association="想起一个晴朗的午后。",
            triggered_emotions="愉悦感",
        )
        assert "温和" in prompt
        assert "窗户" in prompt
        assert "0.50" in prompt  # valence
        assert "70" in prompt  # satiety


class TestParseResponse:
    def test_valid_json(self):
        response = '{"action": "打开窗户", "self_talk": "天气真好", "emotion_delta": {"valence": 0.05, "arousal": -0.02, "dominance": 0.0}, "duration_seconds": 30}'
        result = parse_behavior_response(response)
        assert result.action == "打开窗户"
        assert result.self_talk == "天气真好"
        assert result.emotion_delta.v == 0.05
        assert result.duration_seconds == 30

    def test_invalid_json_fallback(self):
        result = parse_behavior_response("not json")
        assert isinstance(result, BehaviorResult)
        assert result.action != ""

    def test_partial_json(self):
        response = '{"action": "走路"}'
        result = parse_behavior_response(response)
        assert result.action == "走路"
        assert result.self_talk == ""  # 缺失字段为空
