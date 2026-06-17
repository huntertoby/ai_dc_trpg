# tests/test_item_generator.py
"""
裝備生成器測試（模板驅動架構版）

測試 Stage 1A（LLM 選模板）→ Stage 1B（程式組裝）→ Stage 2（故事包裝）流程。
"""
import unittest
from unittest.mock import MagicMock, AsyncMock
from core.item_generator import (
    generate_equipment_by_ai,
    _build_stage1_example,
    _assemble_triggers_from_choices,
)
from core.models import Equipment
from core.compiler import TriggerCompiler
from core.equipment import EquipmentBalancer
from core.trigger_templates import TEMPLATE_REGISTRY, assemble_trigger, get_templates_for_tier
import json


class TestItemGenerator(unittest.IsolatedAsyncioTestCase):
    """整合測試：完整的模板驅動生成流程"""

    async def test_generate_t4_equipment_no_triggers(self):
        """T4 裝備：無觸發器，只有屬性"""
        mock_llm = MagicMock()

        stage1_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": None,
            "damage_type": "physical",
            "scaling_stat": "CON",
            "bonuses": {"CON": 20.0, "p_def": 5.0},
            "trigger_choices": []
        })
        stage2_output = json.dumps({
            "name": "鐵甲之護",
            "description": "堅固的護手甲冑",
            "special_effect": ""
        })
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="護手甲",
            item_level=5,
            tier="T4",
            slot_type="hands",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "鐵甲之護")
        self.assertEqual(eq.slot_type, "hands")
        self.assertEqual(eq.tier, "T4")
        self.assertEqual(eq.item_level, 5)
        self.assertEqual(len(eq.executable_triggers), 0)
        self.assertIsInstance(eq, Equipment)

    async def test_generate_weapon_defaults_type(self):
        """武器部位：weapon_type 防呆（INT 最高 → 法杖）"""
        mock_llm = MagicMock()

        stage1_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": None,
            "damage_type": "magical",
            "scaling_stat": "INT",
            "bonuses": {"INT": 20.0},
            "trigger_choices": []
        })
        stage2_output = json.dumps({
            "name": "神秘法劍",
            "description": "蘊含奧術力量的法器",
            "special_effect": ""
        })
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="法術劍",
            item_level=10,
            tier="T4",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "神秘法劍")
        # INT 最高 → 法杖
        self.assertEqual(eq.weapon_type, "法杖")

    async def test_generate_t3_equipment_with_template_trigger(self):
        """T3 裝備：使用模板觸發器"""
        mock_llm = MagicMock()

        stage1_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": None,
            "damage_type": "physical",
            "scaling_stat": "CON",
            "bonuses": {"CON": 25.0, "p_def": 8.0},
            "trigger_choices": [
                {
                    "template_id": "on_damaged_buff",
                    "status_name": "不屈之志",
                    "duration": 2,
                    "stat_bonuses": {"p_def": 25, "tenacity": 20},
                    "cooldown": 3
                }
            ]
        })
        stage2_output = json.dumps({
            "name": "鋼鐵意志護臂",
            "description": "傳說中曾在百戰中沉默守護主人的護臂。",
            "special_effect": "受傷激發：受到傷害時，獲得不屈之志狀態，持續2回合（冷卻3回合）。"
        })
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="防禦護臂",
            item_level=10,
            tier="T3",
            slot_type="hands",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "鋼鐵意志護臂")
        self.assertEqual(eq.tier, "T3")
        self.assertGreaterEqual(len(eq.executable_triggers), 1)
        # T3 觸發器必須是自身增益
        for trigger in eq.executable_triggers:
            for action in trigger.get("actions", []):
                target = action.get("target", "caster")
                self.assertIn(target, ["caster", "self"], f"T3 不應有敵方目標: {target}")

    async def test_generate_t1_equipment_with_template_triggers(self):
        """T1 裝備：兩個模板觸發器"""
        mock_llm = MagicMock()

        stage1_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": "長劍",
            "damage_type": "physical",
            "scaling_stat": "STR",
            "bonuses": {"STR": 30.0, "crit_rate": 0.08},
            "trigger_choices": [
                {
                    "template_id": "on_hit_damage_dot",
                    "flat_value": 20.0,
                    "scaling_stat": "STR",
                    "value_mult": 1.0,
                    "debuff_name": "Burn",
                    "dot_flat": 15.0,
                    "dot_stat": "STR",
                    "dot_mult": 0.4,
                    "dot_type": "true_damage",
                    "duration": 3,
                    "chance": 0.35,
                    "cooldown": 2
                },
                {
                    "template_id": "on_kill_buff",
                    "status_name": "嗜血狂戰",
                    "duration": 2,
                    "stat_bonuses": {"STR": 20, "crit_rate": 0.20}
                }
            ]
        })
        stage2_output = json.dumps({
            "name": "天罰神諭",
            "description": "由隕星鍛造的傳說武器",
            "special_effect": "灼燒裁決：擊中目標時有35%機率造成額外傷害並附加灼燒。嗜血：擊殺目標後大幅強化。"
        })
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="傳說長劍",
            item_level=15,
            tier="T1",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "天罰神諭")
        self.assertEqual(eq.tier, "T1")
        # T1 應有 2 個觸發器
        self.assertEqual(len(eq.executable_triggers), 2)
        # 第一個觸發器應是 on_hit
        self.assertEqual(eq.executable_triggers[0]["event"], "on_hit")

    async def test_generate_retry_on_missing_triggers(self):
        """若產生的觸發器數量不足，應進行重試，並在重試成功後返回正確結果"""
        mock_llm = MagicMock()

        # 第一次嘗試：只回傳 1 個觸發器（但 T1 需要 2 個，這會觸發重試）
        bad_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": "長劍",
            "damage_type": "physical",
            "scaling_stat": "STR",
            "bonuses": {"STR": 30.0},
            "trigger_choices": [
                {
                    "template_id": "on_hit_damage_dot",
                    "flat_value": 20.0,
                    "scaling_stat": "STR",
                    "value_mult": 1.0,
                    "debuff_name": "Burn",
                    "dot_flat": 15.0,
                    "dot_stat": "STR",
                    "dot_mult": 0.4,
                    "dot_type": "true_damage",
                    "duration": 3,
                    "chance": 0.35,
                    "cooldown": 2
                }
            ]
        })

        # 第二次嘗試：回傳 2 個觸發器（成功）
        good_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": "長劍",
            "damage_type": "physical",
            "scaling_stat": "STR",
            "bonuses": {"STR": 30.0},
            "trigger_choices": [
                {
                    "template_id": "on_hit_damage_dot",
                    "flat_value": 20.0,
                    "scaling_stat": "STR",
                    "value_mult": 1.0,
                    "debuff_name": "Burn",
                    "dot_flat": 15.0,
                    "dot_stat": "STR",
                    "dot_mult": 0.4,
                    "dot_type": "true_damage",
                    "duration": 3,
                    "chance": 0.35,
                    "cooldown": 2
                },
                {
                    "template_id": "on_kill_buff",
                    "status_name": "嗜血狂戰",
                    "duration": 2,
                    "stat_bonuses": {"STR": 20, "crit_rate": 0.20}
                }
            ]
        })

        stage2_output = json.dumps({
            "name": "天罰神諭",
            "description": "由隕星鍛造的傳說武器",
            "special_effect": "效果描述"
        })

        # 模擬呼叫順序：bad_output (第1次 Stage1) -> good_output (第2次 Stage1) -> stage2_output (Stage 2)
        mock_llm.call = AsyncMock(side_effect=[bad_output, good_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="傳說長劍",
            item_level=15,
            tier="T1",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "天罰神諭")
        self.assertEqual(len(eq.executable_triggers), 2)
        self.assertEqual(mock_llm.call.call_count, 3) # 2 次 Stage1 + 1 次 Stage2

    async def test_generate_failure_returns_none_after_retry(self):
        """所有重試都失敗時應返回 None"""
        mock_llm = MagicMock()

        # 每次都回傳空的 trigger_choices（對 T1 來說不夠）
        bad_output = json.dumps({
            "is_two_handed": False,
            "weapon_type": None,
            "damage_type": "physical",
            "scaling_stat": "STR",
            "bonuses": {"STR": 20.0},
            "trigger_choices": []  # T1 需要 2 個，但這裡是空的
        })
        # 3 次 Stage1A 嘗試 + 不會到 Stage2（因為失敗）
        mock_llm.call = AsyncMock(return_value=bad_output)

        eq = await generate_equipment_by_ai(
            description="失敗的裝備",
            item_level=10,
            tier="T1",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        # 應該返回 None（生成失敗）
        self.assertIsNone(eq)
        # LLM 應被呼叫 3 次（3 次重試）
        self.assertEqual(mock_llm.call.call_count, 3)


class TestTemplateAssembly(unittest.TestCase):
    """Stage 1B 模板組裝測試"""

    def test_assemble_on_hit_damage_dot(self):
        """on_hit_damage_dot 模板組裝：應包含傷害和 DoT"""
        choices = [{
            "template_id": "on_hit_damage_dot",
            "flat_value": 20.0,
            "scaling_stat": "STR",
            "value_mult": 1.0,
            "debuff_name": "Burn",
            "dot_flat": 15.0,
            "dot_stat": "STR",
            "dot_mult": 0.5,
            "dot_type": "true_damage",
            "duration": 3,
            "chance": 0.35,
            "cooldown": 2
        }]
        flat = _assemble_triggers_from_choices(choices, "T1", 2)
        self.assertEqual(len(flat), 1)
        trigger = flat[0]
        self.assertEqual(trigger["event"], "on_hit")
        self.assertAlmostEqual(trigger["chance"], 0.35)
        self.assertEqual(trigger["cooldown"], 2)
        # 應有 2 個 action: inflict_damage + apply_debuff
        self.assertEqual(len(trigger["actions"]), 2)
        damage_action = trigger["actions"][0]
        self.assertEqual(damage_action["action_type"], "inflict_damage")
        dot_action = trigger["actions"][1]
        self.assertEqual(dot_action["action_type"], "apply_debuff")
        self.assertEqual(dot_action["debuff_name"], "Burn")
        self.assertEqual(dot_action["dot_damage_flat"], 15.0)

    def test_assemble_invalid_template_id_skipped(self):
        """非法 template_id 應被跳過"""
        choices = [
            {"template_id": "non_existent_template", "flat_value": 10.0},
            {"template_id": "on_battle_start_buff", "status_name": "測試增益",
             "duration": 2, "stat_bonuses": {"STR": 10}}
        ]
        flat = _assemble_triggers_from_choices(choices, "T1", 2)
        # 非法的跳過，只有 1 個有效
        self.assertEqual(len(flat), 1)
        self.assertEqual(flat[0]["event"], "on_battle_start")

    def test_t3_only_allows_shared_templates(self):
        """T3 不應使用 T1 限定模板"""
        from core.trigger_templates import get_templates_for_tier
        t3_templates = get_templates_for_tier("T3")
        t1_only = [t for t, entry in TEMPLATE_REGISTRY.items() if entry[1] == {"T1"}]
        for t in t1_only:
            self.assertNotIn(t, t3_templates)

    def test_stat_bonuses_sanitize_buff(self):
        """增益 stat_bonuses 不應包含負值"""
        choices = [{
            "template_id": "on_damaged_buff",
            "status_name": "測試",
            "duration": 2,
            "stat_bonuses": {"STR": 10, "p_def": -5},  # -5 應被過濾
            "cooldown": 3
        }]
        flat = _assemble_triggers_from_choices(choices, "T3", 1)
        self.assertEqual(len(flat), 1)
        action = flat[0]["actions"][0]
        bonuses = action.get("stat_bonuses", {})
        # 負值應被過濾
        self.assertNotIn("p_def", bonuses)
        self.assertIn("STR", bonuses)


class TestTriggerCompilerCompatibility(unittest.TestCase):
    """確認模板輸出的 trigger 能通過 TriggerCompiler"""

    def test_battle_start_buff_compiles(self):
        flat = [assemble_trigger("on_battle_start_buff", {
            "status_name": "戰前激勵", "duration": 3,
            "stat_bonuses": {"STR": 15, "crit_rate": 0.10}
        })]
        compiled = TriggerCompiler.compile_flat_triggers(flat)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_battle_start")

    def test_on_hit_drain_compiles(self):
        flat = [assemble_trigger("on_hit_drain", {
            "dmg_flat": 20.0, "dmg_stat": "STR", "dmg_mult": 0.8,
            "heal_flat": 10.0, "chance": 0.30, "cooldown": 2
        })]
        compiled = TriggerCompiler.compile_flat_triggers(flat)
        self.assertEqual(len(compiled), 1)
        actions = compiled[0]["actions"]
        action_types = [a["action_type"] for a in actions]
        self.assertIn("inflict_damage", action_types)
        self.assertIn("heal", action_types)

    def test_on_turn_end_heal_compiles(self):
        flat = [assemble_trigger("on_turn_end_heal", {
            "flat_value": 15.0, "target_resource": "mp", "cooldown": 3
        })]
        compiled = TriggerCompiler.compile_flat_triggers(flat)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_turn_end")
        self.assertEqual(compiled[0]["cooldown"], 3)
        action = compiled[0]["actions"][0]
        self.assertEqual(action["action_type"], "heal")

    def test_on_fatal_damage_buff_compiles(self):
        flat = [assemble_trigger("on_fatal_damage_buff", {
            "status_name": "死而復生", "duration": 2,
            "stat_bonuses": {"STR": 30, "crit_rate": 0.25}
        })]
        compiled = TriggerCompiler.compile_flat_triggers(flat)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_fatal_damage")

    def test_on_dodge_buff_compiles(self):
        flat = [assemble_trigger("on_dodge_buff", {
            "status_name": "幻影步伐", "duration": 1,
            "stat_bonuses": {"DEX": 20, "evasion_rate": 0.15},
            "cooldown": 2
        })]
        compiled = TriggerCompiler.compile_flat_triggers(flat)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_dodge")
