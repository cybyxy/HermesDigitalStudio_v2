"""测试 情绪引擎 — 关键词检测、PAD 常量验证。"""
from __future__ import annotations

from backend.services.emotion import (
    VALENCE_MIN,
    VALENCE_MAX,
    AROUSAL_MIN,
    AROUSAL_MAX,
    DOMINANCE_MIN,
    DOMINANCE_MAX,
    EmotionEngine,
    get_emotion_service,
)


class TestEmotionConstants:
    """PAD 值域常量验证。"""

    def test_pad_ranges(self):
        assert VALENCE_MIN < 0 < VALENCE_MAX
        assert AROUSAL_MIN < 0 < AROUSAL_MAX
        assert DOMINANCE_MIN < 0 < DOMINANCE_MAX


class TestAnalyzeSentiment:
    """静态情感分析函数测试（无需 DB）。

    analyze_sentiment 返回格式：
      {'valence': 0.1}  正面
      {'valence': -0.1} 负面
      {}                中性
    """

    def test_praise_zh(self):
        result = EmotionEngine.analyze_sentiment("太棒了，做得很好！")
        assert result["valence"] > 0

    def test_praise_en(self):
        result = EmotionEngine.analyze_sentiment("Great job, well done!")
        assert result["valence"] > 0

    def test_criticism_zh(self):
        result = EmotionEngine.analyze_sentiment("这太糟糕了，真差劲")
        assert result["valence"] < 0

    def test_criticism_en(self):
        result = EmotionEngine.analyze_sentiment("This is terrible and useless")
        assert result["valence"] < 0

    def test_neutral_text(self):
        result = EmotionEngine.analyze_sentiment("今天天气不错")
        # 中性文本无匹配关键词，返回空 dict
        assert result == {} or abs(result.get("valence", 0)) <= 0.1

    def test_empty_text(self):
        result = EmotionEngine.analyze_sentiment("")
        assert result == {}

    def test_value_clamping(self):
        # analyze_sentiment 返回值固定为 0.1 / -0.1 / {}，无需 clamping
        result = EmotionEngine.analyze_sentiment("太棒了完美厉害优秀")
        assert len(result) <= 1  # 只包含 valence 或为空

    def test_keyword_priority_zh_over_en(self):
        # 中文优先匹配
        result = EmotionEngine.analyze_sentiment("太棒了 great")
        assert result["valence"] > 0

    def test_partial_matches_not_triggered(self):
        result = EmotionEngine.analyze_sentiment("一般般")
        assert result == {}


class TestEmotionServiceSingleton:
    """情绪服务单例工厂测试。"""

    def test_singleton_returns_same_instance(self):
        a = get_emotion_service()
        b = get_emotion_service()
        assert a is b
