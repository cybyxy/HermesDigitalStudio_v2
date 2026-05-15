"""空间感知引擎单元测试"""
from __future__ import annotations

from backend.services.spatial_perception import (
    InteractiveItem,
    MapContext,
    parse_tiled_interactive_objects,
    calculate_tile_distance,
    get_direction_description,
    filter_nearby_items,
    compute_environment_perception,
    compute_environment_mood_deltas,
    load_map_context,
    MOOD_TAG_PAD_MAP,
)


SAMPLE_MAP = {
    "layers": [
        {
            "name": "background",
            "type": "tilelayer",
            "objects": [],
        },
        {
            "name": "interactive",
            "type": "objectgroup",
            "objects": [
                {
                    "id": 1,
                    "name": "朝南的窗户",
                    "x": 300,
                    "y": 100,
                    "width": 64,
                    "height": 32,
                    "properties": [
                        {"name": "description", "type": "string", "value": "午后的阳光透过玻璃洒在地板上。"},
                        {"name": "mood_tags", "type": "string", "value": '["bright", "warm"]'},
                        {"name": "interact_actions", "type": "string", "value": '["打开窗户", "看风景"]'},
                        {"name": "category", "type": "string", "value": "decoration"},
                    ],
                },
                {
                    "id": 2,
                    "name": "旧书架",
                    "x": 150,
                    "y": 200,
                    "width": 96,
                    "height": 128,
                    "properties": [
                        {"name": "description", "type": "string", "value": "散发着淡淡的旧书纸张味道。"},
                        {"name": "mood_tags", "type": "string", "value": '["nostalgic", "intellectual"]'},
                        {"name": "category", "type": "string", "value": "furniture"},
                    ],
                },
            ],
        },
    ]
}


class TestParseTiled:
    def test_parse_items(self):
        items = parse_tiled_interactive_objects(SAMPLE_MAP)
        assert len(items) == 2
        assert items[0].name == "朝南的窗户"
        assert items[1].name == "旧书架"

    def test_mood_tags_parsed(self):
        items = parse_tiled_interactive_objects(SAMPLE_MAP)
        assert "bright" in items[0].mood_tags
        assert "warm" in items[0].mood_tags
        assert "nostalgic" in items[1].mood_tags

    def test_interact_actions(self):
        items = parse_tiled_interactive_objects(SAMPLE_MAP)
        assert "打开窗户" in items[0].interact_actions

    def test_category(self):
        items = parse_tiled_interactive_objects(SAMPLE_MAP)
        assert items[0].category == "decoration"
        assert items[1].category == "furniture"

    def test_no_description_skip(self):
        m = {"layers": [{"type": "objectgroup", "objects": [
            {"id": 1, "properties": [{"name": "x", "value": 1}]}
        ]}]}
        items = parse_tiled_interactive_objects(m)
        assert len(items) == 0


class TestDistance:
    def test_same_point(self):
        assert calculate_tile_distance(0, 0, 0, 0) == 0.0

    def test_pythagoras(self):
        d = calculate_tile_distance(0, 0, 30, 40)
        assert d == 50.0


class TestDirection:
    def test_front(self):
        d = get_direction_description(0, 0, 0, -50)
        assert d == "前方"

    def test_right(self):
        d = get_direction_description(0, 0, 50, 0)
        assert d == "右侧"

    def test_left(self):
        d = get_direction_description(0, 0, -50, 0)
        assert d == "左侧"

    def test_behind(self):
        d = get_direction_description(0, 0, 0, 50)
        assert d == "后方"


class TestFilterNearby:
    def test_filter_within_threshold(self):
        items = [
            InteractiveItem(id=1, name="near", x=50, y=0),
            InteractiveItem(id=2, name="far", x=500, y=0),
        ]
        nearby = filter_nearby_items(0, 0, items, threshold=100)
        assert len(nearby) == 1
        assert nearby[0][0].name == "near"

    def test_sort_by_distance(self):
        items = [
            InteractiveItem(id=2, name="far", x=80, y=0),
            InteractiveItem(id=1, name="near", x=20, y=0),
        ]
        nearby = filter_nearby_items(0, 0, items, threshold=200)
        assert nearby[0][0].name == "near"
        assert nearby[1][0].name == "far"


class TestEnvironmentPerception:
    def test_generates_text(self):
        items = [
            InteractiveItem(id=1, name="窗户", x=50, y=0, description="阳光明媚。")
        ]
        text = compute_environment_perception(0, 0, items)
        assert "窗户" in text
        assert "阳光明媚" in text

    def test_empty_perception(self):
        text = compute_environment_perception(0, 0, [], threshold=100)
        assert "空荡荡" in text


class TestMoodDeltas:
    def test_bright_tag(self):
        item = InteractiveItem(id=1, name="窗", x=50, y=0, mood_tags=["bright"])
        v, a, d = compute_environment_mood_deltas([(item, 50)], threshold=150)
        assert v > 0  # bright → positive valence

    def test_intensity_by_distance(self):
        item = InteractiveItem(id=1, name="窗", x=50, y=0, mood_tags=["bright"])
        v_close, _, _ = compute_environment_mood_deltas([(item, 50)], threshold=150)
        v_far, _, _ = compute_environment_mood_deltas([(item, 140)], threshold=150)
        assert v_close > v_far  # 越近越强

    def test_no_tags(self):
        item = InteractiveItem(id=1, name="空", x=50, y=0)
        v, a, d = compute_environment_mood_deltas([(item, 50)])
        assert v == 0.0 and a == 0.0 and d == 0.0


class TestMapContext:
    def test_load_with_json(self):
        ctx = load_map_context("office", SAMPLE_MAP)
        assert ctx.name == "office"
        assert len(ctx.items) == 2

    def test_load_without_json(self):
        ctx = load_map_context("office", None)
        assert ctx.name == "office"
        assert ctx.items == []
