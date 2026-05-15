"""测试 SelfModel 文件 I/O 服务。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.services.self_model import (
    FIELD_MAX_CHARS,
    HISTORY_MAX_ENTRIES,
    _DEFAULT_SELF_MODEL,
    _prune_field,
    _prune_history,
    read_self_model,
    write_self_model,
    delete_self_model,
)


class TestReadSelfModel:
    """read_self_model 测试。"""

    def test_file_not_exists_returns_default(self, tmp_path: Path):
        result = read_self_model(str(tmp_path))
        assert result["version"] == _DEFAULT_SELF_MODEL["version"]
        assert result["preferences"] == ""

    def test_read_empty_json(self, tmp_path: Path):
        target = tmp_path / "self_model.json"
        target.write_text("{}", encoding="utf-8")
        result = read_self_model(str(tmp_path))
        # 缺失字段应补充默认值
        assert result["version"] == _DEFAULT_SELF_MODEL["version"]
        assert result["reflection_history"] == []

    def test_read_valid(self, tmp_path: Path):
        data = {
            "version": 1,
            "updated_at": time.time(),
            "preferences": "- 喜欢简洁的回答",
            "capabilities": "- 擅长 Python",
            "behavioral_patterns": "",
            "derived_traits": "",
            "reflection_history": [],
        }
        target = tmp_path / "self_model.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        result = read_self_model(str(tmp_path))
        assert result["preferences"] == "- 喜欢简洁的回答"
        assert result["capabilities"] == "- 擅长 Python"

    def test_corrupted_falls_back_to_backup(self, tmp_path: Path):
        # 主文件损坏，备份有效
        target = tmp_path / "self_model.json"
        target.write_text("不是json{", encoding="utf-8")
        backup = tmp_path / "self_model.json.bak"
        backup.write_text(json.dumps({"preferences": "- 来自备份"}), encoding="utf-8")
        result = read_self_model(str(tmp_path))
        assert result["preferences"] == "- 来自备份"

    def test_both_corrupted_returns_default(self, tmp_path: Path):
        target = tmp_path / "self_model.json"
        target.write_text("坏json", encoding="utf-8")
        backup = tmp_path / "self_model.json.bak"
        backup.write_text("也坏了", encoding="utf-8")
        result = read_self_model(str(tmp_path))
        assert result["version"] == _DEFAULT_SELF_MODEL["version"]


class TestWriteSelfModel:
    """write_self_model / delete_self_model 测试。"""

    def test_write_creates_file(self, tmp_path: Path):
        data = {"preferences": "- 测试偏好", "capabilities": "", "behavioral_patterns": "", "derived_traits": "", "reflection_history": []}
        write_self_model(str(tmp_path), data)
        target = tmp_path / "self_model.json"
        assert target.is_file()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["preferences"] == "- 测试偏好"
        assert loaded["version"] == 1

    def test_write_creates_backup(self, tmp_path: Path):
        data = {"preferences": "v1", "capabilities": "", "behavioral_patterns": "", "derived_traits": "", "reflection_history": []}
        write_self_model(str(tmp_path), data)
        data2 = {"preferences": "v2", "capabilities": "", "behavioral_patterns": "", "derived_traits": "", "reflection_history": []}
        write_self_model(str(tmp_path), data2)
        backup = tmp_path / "self_model.json.bak"
        assert backup.is_file()
        bak = json.loads(backup.read_text(encoding="utf-8"))
        assert bak["preferences"] == "v1"  # 备份保留上次内容

    def test_delete_removes_files(self, tmp_path: Path):
        target = tmp_path / "self_model.json"
        backup = tmp_path / "self_model.json.bak"
        target.write_text("{}", encoding="utf-8")
        backup.write_text("{}", encoding="utf-8")
        assert target.is_file()
        assert backup.is_file()
        target.unlink()
        backup.unlink()
        assert not target.exists()
        assert not backup.exists()


class TestFieldPruning:
    """字段裁剪测试。"""

    def test_prune_field_short(self):
        text = "short text"
        assert _prune_field(text) == text

    def test_prune_field_exceeds(self):
        long = "a\n" * (FIELD_MAX_CHARS // 2 + 10)
        result = _prune_field(long)
        assert len(result) <= FIELD_MAX_CHARS

    def test_prune_history_count(self):
        now = time.time()
        history = []
        for i in range(HISTORY_MAX_ENTRIES + 20):
            history.append({"timestamp": now - i * 100, "lesson": f"lesson {i}", "confidence": "medium"})
        pruned = _prune_history(history)
        assert len(pruned) <= HISTORY_MAX_ENTRIES

    def test_prune_history_age(self):
        old = time.time() - 100 * 86400  # 100 天前
        new = time.time()
        history = [
            {"timestamp": old, "lesson": "old", "confidence": "low"},
            {"timestamp": new, "lesson": "new", "confidence": "high"},
        ]
        pruned = _prune_history(history)
        assert len(pruned) == 1
        assert pruned[0]["lesson"] == "new"


class TestDeleteSelfModel:
    """delete_self_model 路径解析测试。"""

    def test_delete_nonexistent(self):
        # 不应抛异常
        delete_self_model("__nonexistent_agent__")
