"""测试 能量引擎 — 状态阈值、消耗逻辑、常量验证。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.services.energy import (
    SATIETY_MAX,
    SATIETY_MIN,
    SATIETY_DEFAULT,
    SATIETY_LOW_THRESHOLD,
    SATIETY_CRITICAL,
    BIO_CURRENT_MAX,
    BIO_CURRENT_MIN,
    BIO_CURRENT_DEFAULT,
    BIO_CURRENT_SURGE,
    BIO_CURRENT_FORCE_DISCHARGE,
    POSITIVE_INTERACTION_DELTA,
    TASK_BIO_CURRENT_DELTA,
    EnergyService,
    get_energy_service,
)


class TestEnergyConstants:
    """常量值域验证。"""

    def test_satiety_range(self):
        assert 0 <= SATIETY_MIN < SATIETY_LOW_THRESHOLD < SATIETY_DEFAULT <= SATIETY_MAX
        assert SATIETY_CRITICAL < SATIETY_LOW_THRESHOLD

    def test_bio_current_range(self):
        assert BIO_CURRENT_MIN < BIO_CURRENT_DEFAULT < BIO_CURRENT_SURGE <= BIO_CURRENT_MAX
        assert BIO_CURRENT_FORCE_DISCHARGE == BIO_CURRENT_MAX

    def test_positive_interaction_delta_values(self):
        assert POSITIVE_INTERACTION_DELTA["task_complete"] > 0
        assert POSITIVE_INTERACTION_DELTA["user_praise"] > 0
        assert POSITIVE_INTERACTION_DELTA["encourage"] > 0

    def test_task_bio_current_delta_values(self):
        assert TASK_BIO_CURRENT_DELTA["simple"] < TASK_BIO_CURRENT_DELTA["medium"] < TASK_BIO_CURRENT_DELTA["large"]


class TestEnergyServiceDefaultState:
    """_default_state 和单价函数单元测试。"""

    def test_default_state_structure(self):
        state = EnergyService._default_state("agent_1")
        assert state["agent_id"] == "agent_1"
        assert state["satiety"] == SATIETY_DEFAULT
        assert state["bio_current"] == BIO_CURRENT_DEFAULT
        assert state["mode"] == "normal"

    def test_get_current_multiplier_low(self):
        m = EnergyService._get_current_multiplier(2)
        assert m == 1.0

    def test_get_current_multiplier_medium(self):
        m = EnergyService._get_current_multiplier(5)
        assert m == 1.5

    def test_get_current_multiplier_high(self):
        m = EnergyService._get_current_multiplier(8)
        assert m == 2.0

    def test_get_current_multiplier_surge(self):
        m = EnergyService._get_current_multiplier(9)
        assert m == 3.0


class TestEnergyServiceSingleton:
    """单例工厂测试。"""

    def test_singleton_returns_same_instance(self):
        a = get_energy_service()
        b = get_energy_service()
        assert a is b
