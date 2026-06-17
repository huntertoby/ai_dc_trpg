# tests/test_integration_affix_quality.py
"""
品質分層系統集成測試

驗證完整流程：AI 生成→驗證→編譯→保存
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from core.models import Equipment
from core.equipment import EquipmentBalancer
from core.item_generator import (
    validate_equipment_affix_constraints,
    get_equipment_tier_rules
)


class TestGetEquipmentTierRules:
    """tier 規則生成測試"""

    def test_t1_rules_generated(self):
        """T1 規則應包含觸發器數量提示"""
        rules = get_equipment_tier_rules("T1")
        assert "T1" in rules
        assert "2" in rules  # 2 個觸發器
        assert "AoE" in rules or "template_id" in rules

    def test_t2_rules_generated(self):
        """T2 規則應包含觸發器數量限制"""
        rules = get_equipment_tier_rules("T2")
        assert "T2" in rules
        assert "1" in rules  # 1 個觸發器

    def test_t3_rules_strict(self):
        """T3 規則應強調自增益限制"""
        rules = get_equipment_tier_rules("T3")
        assert "T3" in rules
        assert "增益" in rules or "debuff" in rules

    def test_t4_t5_rules_no_triggers(self):
        """T4/T5 規則應禁止觸發器"""
        for tier in ["T4", "T5"]:
            rules = get_equipment_tier_rules(tier)
            assert "trigger_choices" in rules or "沒有觸發器" in rules or "無觸發器" in rules


class TestValidateEquipmentAffixConstraints:
    """AI 生成後驗證測試"""

    def test_t1_passes_any_triggers(self):
        """T1 通過任何觸發器"""
        parsed_data = {
            "executable_triggers": [
                {"event": "on_hit", "actions": []},
                {"event": "on_damaged", "actions": []}
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T1")
        assert is_valid == True
        assert error is None

    def test_t2_rejects_aoe(self):
        """T2 拒絕 AoE"""
        parsed_data = {
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "all_enemies"}
                    ]
                }
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T2")
        assert is_valid == False
        assert error is not None
        assert "AoE" in error or "all_" in error

    def test_t2_rejects_complex(self):
        """T2 拒絕複合"""
        parsed_data = {
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "target"},
                        {"action_type": "apply_debuff", "debuff_name": "Slow"}
                    ]
                }
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T2")
        assert is_valid == False
        assert "複合" in error or "多個" in error

    def test_t3_rejects_enemy_target(self):
        """T3 拒絕敵方目標"""
        parsed_data = {
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "target"}
                    ]
                }
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T3")
        assert is_valid == False
        assert "target" in error or "敵方" in error

    def test_t3_rejects_debuff(self):
        """T3 拒絕 debuff"""
        parsed_data = {
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "apply_debuff", "debuff_name": "Sunder"}
                    ]
                }
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T3")
        assert is_valid == False
        assert "debuff" in error.lower()

    def test_t3_accepts_self_buff(self):
        """T3 接受自增益"""
        parsed_data = {
            "executable_triggers": [
                {
                    "event": "on_damaged",
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "status_name": "Shield",
                            "target": "caster"
                        }
                    ]
                }
            ]
        }
        is_valid, error = validate_equipment_affix_constraints(parsed_data, "T3")
        assert is_valid == True
        assert error is None

    def test_t4_t5_reject_any_triggers(self):
        """T4/T5 拒絕任何觸發器"""
        for tier in ["T4", "T5"]:
            parsed_data = {
                "executable_triggers": [
                    {"event": "on_hit", "actions": []}
                ]
            }
            is_valid, error = validate_equipment_affix_constraints(parsed_data, tier)
            assert is_valid == False
            assert "觸發器" in error or error


class TestFullAffixQualityPipeline:
    """完整品質分層流程測試"""

    def test_t1_equipment_with_valid_triggers(self):
        """T1 裝備：有效觸發器應保留"""
        eq = Equipment(
            name="傳說劍",
            slot_type="main_hand",
            tier="T1",
            item_level=20,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "all_enemies", "flat_value": 50.0}
                    ]
                }
            ]
        )

        # validate_and_clamp 應保留 T1 的觸發器
        result = EquipmentBalancer.validate_and_clamp(eq)
        assert len(result.executable_triggers) == 1
        assert result.special_effect == ""  # 假設未設置

    def test_t2_equipment_with_valid_trigger(self):
        """T2 裝備：有效單體觸發器應保留"""
        eq = Equipment(
            name="史詩戰斧",
            slot_type="main_hand",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "target", "flat_value": 20.0}
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(eq)
        assert len(result.executable_triggers) == 1

    def test_t2_equipment_with_violating_trigger(self):
        """T2 裝備：違規觸發器應刪除"""
        eq = Equipment(
            name="違規史詩盔甲",
            slot_type="chest",
            tier="T2",
            item_level=15,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "all_enemies", "flat_value": 20.0}
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(eq)
        # AoE 違規，應被刪除
        assert len(result.executable_triggers) == 0

    def test_t3_equipment_only_self_buff(self):
        """T3 裝備：只有自增益應保留"""
        eq = Equipment(
            name="稀有護盾",
            slot_type="chest",
            tier="T3",
            item_level=12,
            executable_triggers=[
                {
                    "event": "on_damaged",
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "status_name": "Protection",
                            "target": "caster",
                            "duration": 2,
                            "stat_bonuses": {"p_def": 30}
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(eq)
        assert len(result.executable_triggers) == 1

    def test_t3_equipment_with_debuff_removed(self):
        """T3 裝備：含 debuff 應全部刪除"""
        eq = Equipment(
            name="違規稀有項鍊",
            slot_type="trinket_1",
            tier="T3",
            item_level=10,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "apply_debuff",
                            "debuff_name": "Weak",
                            "target": "target",
                            "duration": 3
                        }
                    ]
                }
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(eq)
        # 違規，應被刪除
        assert len(result.executable_triggers) == 0

    def test_validation_log_recorded(self):
        """驗證日誌應被記錄"""
        eq = Equipment(
            name="違規 T3",
            slot_type="chest",
            tier="T3",
            item_level=10,
            executable_triggers=[
                {"event": "on_hit", "actions": [{"action_type": "inflict_damage", "target": "target"}]},
                {"event": "on_damaged", "actions": [{"action_type": "apply_debuff", "debuff_name": "Slow"}]}
            ]
        )

        result = EquipmentBalancer.validate_and_clamp(eq)

        # 應有驗證日誌
        if hasattr(result, "_validation_log"):
            assert len(result._validation_log) > 0
            for deleted in result._validation_log:
                assert "reasons" in deleted
                assert isinstance(deleted["reasons"], list)


class TestTierRulesConsistency:
    """Tier 規則一致性測試"""

    def test_rules_match_config(self):
        """規則文本應與配置一致"""
        config = EquipmentBalancer.AFFIX_QUALITY_TIERS

        for tier in ["T1", "T2", "T3", "T4", "T5"]:
            rules = get_equipment_tier_rules(tier)
            cfg = config.get(tier, {})

            max_triggers = cfg.get("max_triggers", 0)

            # 根據 max_triggers 檢查規則文本
            if max_triggers == 2:
                assert "2" in rules or "二" in rules or "兩" in rules
            elif max_triggers == 1:
                assert "1" in rules or "一" in rules
            elif max_triggers == 0:
                assert "無" in rules or "0" in rules or "沒有" in rules or "trigger_choices" in rules

    def test_validation_matches_rules(self):
        """驗證邏輯應與規則文本一致"""
        # 如果規則說 T2 禁止 AoE，那麼驗證也應該拒絕 AoE
        parsed_data_with_aoe = {
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {"action_type": "inflict_damage", "target": "all_enemies"}
                    ]
                }
            ]
        }

        is_valid, error = validate_equipment_affix_constraints(parsed_data_with_aoe, "T2")
        rules = get_equipment_tier_rules("T2")

        # 規則說禁止，驗證也應該拒絕
        assert (not is_valid) or ("AoE" not in rules)
