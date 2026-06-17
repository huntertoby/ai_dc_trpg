# tests/test_equipment_quality.py
"""
品質分層系統單元測試

驗證 AFFIX_QUALITY_TIERS 配置的正確性：
- T1: 2 個高貴/複合詞條，無限制
- T2: 1 個標準詞條，禁 AoE/複合，減益≤-15%
- T3: 1 個基礎詞條，【只能自增益】
- T4/T5: 無觸發器
"""

import pytest
from core.models import Equipment
from core.equipment import EquipmentBalancer


class TestAffixQualityTiers:
    """品質分層配置測試"""

    def test_affix_quality_tiers_config_exists(self):
        """驗證 AFFIX_QUALITY_TIERS 配置存在"""
        config = EquipmentBalancer.AFFIX_QUALITY_TIERS
        assert config is not None
        assert "T1" in config
        assert "T2" in config
        assert "T3" in config
        assert "T4" in config
        assert "T5" in config

    def test_t1_config(self):
        """T1 配置：2 個觸發器，無限制"""
        config = EquipmentBalancer.AFFIX_QUALITY_TIERS["T1"]
        assert config["max_triggers"] == 2
        assert config["can_have_aoe"] == True
        assert config["can_have_complex"] == True
        assert config["can_have_debuff"] == True

    def test_t2_config(self):
        """T2 配置：1 個觸發器，禁 AoE/複合，減益≤-15%"""
        config = EquipmentBalancer.AFFIX_QUALITY_TIERS["T2"]
        assert config["max_triggers"] == 1
        assert config["can_have_aoe"] == False
        assert config["can_have_complex"] == False
        assert config["can_have_debuff"] == True
        assert config["max_debuff_strength"] == -0.15

    def test_t3_config(self):
        """T3 配置：1 個觸發器，【禁減敵方】"""
        config = EquipmentBalancer.AFFIX_QUALITY_TIERS["T3"]
        assert config["max_triggers"] == 1
        assert config["can_have_aoe"] == False
        assert config["can_have_complex"] == False
        assert config["can_have_debuff"] == False  # ⚠️ 關鍵：禁減敵方

    def test_t4_t5_config(self):
        """T4/T5 配置：無觸發器"""
        assert EquipmentBalancer.AFFIX_QUALITY_TIERS["T4"]["max_triggers"] == 0
        assert EquipmentBalancer.AFFIX_QUALITY_TIERS["T5"]["max_triggers"] == 0


class TestIsComplexTrigger:
    """複合效果判定測試"""

    def test_single_action_is_not_complex(self):
        """單個 action 不是複合"""
        trigger = {
            "event": "on_hit",
            "actions": [
                {"action_type": "inflict_damage", "target": "target", "flat_value": 10.0}
            ]
        }
        assert EquipmentBalancer.is_complex_trigger(trigger) == False

    def test_multiple_actions_is_complex(self):
        """多個 action 是複合"""
        trigger = {
            "event": "on_hit",
            "actions": [
                {"action_type": "inflict_damage", "target": "target", "flat_value": 10.0},
                {"action_type": "apply_debuff", "debuff_name": "Burn", "duration": 3}
            ]
        }
        assert EquipmentBalancer.is_complex_trigger(trigger) == True

    def test_mixed_status_and_debuff_is_complex(self):
        """同時有 status_name 和 debuff_name 是複合"""
        trigger = {
            "event": "on_hit",
            "actions": [
                {
                    "action_type": "apply_status",
                    "status_name": "Fury",
                    "debuff_name": "Burn",  # 混合
                    "duration": 3
                }
            ]
        }
        assert EquipmentBalancer.is_complex_trigger(trigger) == True

    def test_empty_actions_is_not_complex(self):
        """空 action 列表不是複合"""
        trigger = {"event": "on_hit", "actions": []}
        assert EquipmentBalancer.is_complex_trigger(trigger) == False


class TestValidateAffixQuality:
    """詞條品質驗證測試"""

    def test_t3_forbids_enemy_target(self):
        """T3 禁止以敵人為目標"""
        equipment = Equipment(
            name="Test T3",
            slot_type="chest",
            tier="T3",
            item_level=10,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "inflict_damage",
                            "target": "target",  # ❌ 違規：指向敵人
                            "flat_value": 10.0
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T3")
        # 違規觸發器應被刪除
        assert len(result.executable_triggers) == 0

    def test_t3_allows_self_buff(self):
        """T3 允許自增益"""
        equipment = Equipment(
            name="Test T3 Buff",
            slot_type="chest",
            tier="T3",
            item_level=10,
            executable_triggers=[
                {
                    "event": "on_damaged",
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "status_name": "Shield",
                            "target": "caster",  # ✅ 允許：自身
                            "duration": 2,
                            "stat_bonuses": {"p_def": 20}
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T3")
        # 自增益應保留
        assert len(result.executable_triggers) == 1

    def test_t3_forbids_debuff(self):
        """T3 禁止 debuff"""
        equipment = Equipment(
            name="Test T3 Debuff",
            slot_type="chest",
            tier="T3",
            item_level=10,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "apply_debuff",
                            "debuff_name": "Sunder",  # ❌ 違規
                            "duration": 3
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T3")
        assert len(result.executable_triggers) == 0

    def test_t2_forbids_aoe(self):
        """T2 禁止 AoE"""
        equipment = Equipment(
            name="Test T2 AoE",
            slot_type="main_hand",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "inflict_damage",
                            "target": "all_enemies",  # ❌ 違規：AoE
                            "flat_value": 10.0
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T2")
        assert len(result.executable_triggers) == 0

    def test_t2_forbids_complex(self):
        """T2 禁止複合效果"""
        equipment = Equipment(
            name="Test T2 Complex",
            slot_type="main_hand",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "target", "flat_value": 10.0},
                        {"action_type": "apply_debuff", "debuff_name": "Slow", "duration": 2}
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T2")
        assert len(result.executable_triggers) == 0

    def test_t2_enforces_debuff_strength_limit(self):
        """T2 減益強度≤-15%"""
        # 違規例：-0.25（超過 -0.15）
        equipment_bad = Equipment(
            name="Test T2 Strong Debuff",
            slot_type="chest",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "apply_debuff",
                            "debuff_name": "WeakDef",
                            "duration": 3,
                            "stat_bonuses": {"p_def": -0.25}  # ❌ 超限
                        }
                    ]
                }
            ]
        )

        result_bad = EquipmentBalancer.validate_affix_quality(equipment_bad, "T2")
        assert len(result_bad.executable_triggers) == 0

        # 允許例：-0.10（在限制內）
        equipment_good = Equipment(
            name="Test T2 Weak Debuff",
            slot_type="chest",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "apply_debuff",
                            "debuff_name": "WeakDef",
                            "duration": 3,
                            "stat_bonuses": {"p_def": -0.10}  # ✅ 允許
                        }
                    ]
                }
            ]
        )

        result_good = EquipmentBalancer.validate_affix_quality(equipment_good, "T2")
        assert len(result_good.executable_triggers) == 1

    def test_t1_allows_anything(self):
        """T1 允許所有類型效果"""
        equipment = Equipment(
            name="Test T1 Legendary",
            slot_type="main_hand",
            tier="T1",
            item_level=20,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "all_enemies", "flat_value": 50.0},
                        {
                            "action_type": "apply_debuff",
                            "debuff_name": "Curse",
                            "duration": 5,
                            "stat_bonuses": {"p_def": -0.50}  # 極強減益
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_affix_quality(equipment, "T1")
        # T1 無任何限制
        assert len(result.executable_triggers) == 1

    def test_t4_t5_have_no_triggers(self):
        """T4/T5 應無觸發器"""
        for tier in ["T4", "T5"]:
            equipment = Equipment(
                name=f"Test {tier}",
                slot_type="chest",
                tier=tier,
                item_level=5,
                executable_triggers=[
                    {"event": "on_hit", "actions": []}
                ]
            )

            # validate_and_clamp 應清除所有觸發器
            result = EquipmentBalancer.validate_and_clamp(equipment)
            assert len(result.executable_triggers) == 0


class TestValidateAndClamp:
    """validate_and_clamp 整體驗證測試"""

    def test_validate_and_clamp_t1_preserves_special_effect(self):
        """T1 保留 special_effect"""
        equipment = Equipment(
            name="T1 Sword",
            slot_type="main_hand",
            tier="T1",
            item_level=20,
            special_effect="傳奇效果",
            executable_triggers=[{"event": "on_hit", "actions": []}]
        )

        result = EquipmentBalancer.validate_and_clamp(equipment)
        assert result.special_effect == "傳奇效果"

    def test_validate_and_clamp_non_t1_clears_special_effect(self):
        """非 T1 清除 special_effect"""
        for tier in ["T2", "T3", "T4", "T5"]:
            equipment = Equipment(
                name=f"{tier} Armor",
                slot_type="chest",
                tier=tier,
                item_level=10,
                special_effect="不應該有的效果",
                executable_triggers=[{"event": "on_hit", "actions": []}]
            )

            result = EquipmentBalancer.validate_and_clamp(equipment)
            assert result.special_effect == ""

    def test_validate_and_clamp_limits_trigger_count(self):
        """validate_and_clamp 按 tier 限制觸發器數量"""
        # T1: 最多 2 個
        equipment_t1 = Equipment(
            name="T1",
            slot_type="main_hand",
            tier="T1",
            item_level=20,
            executable_triggers=[
                {"event": "on_hit", "actions": []},
                {"event": "on_damaged", "actions": []},
                {"event": "on_turn_start", "actions": []}  # 第 3 個會被截斷
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(equipment_t1)
        assert len(result.executable_triggers) == 2

        # T2: 最多 1 個
        equipment_t2 = Equipment(
            name="T2",
            slot_type="chest",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {"event": "on_hit", "actions": []},
                {"event": "on_damaged", "actions": []}  # 第 2 個會被刪除
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(equipment_t2)
        assert len(result.executable_triggers) == 1
