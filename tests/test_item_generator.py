# tests/test_item_generator.py
import unittest
from unittest.mock import MagicMock, AsyncMock
from core.item_generator import generate_equipment_by_ai
from core.models import Equipment
from core.compiler import TriggerCompiler

class TestItemGenerator(unittest.IsolatedAsyncioTestCase):
    async def test_generate_equipment_by_ai_success(self):
        mock_llm = MagicMock()
        
        stage1_output = '''
        {
            "slot_type": "hands",
            "tier": "T4",
            "item_level": 5,
            "bonuses": {
                "CON": 15.0,
                "DEX": 5.0
            }
        }
        '''
        stage2_output = '''
        {
            "name": "灰燼之手",
            "description": "被火焰灼燒過的手套"
        }
        '''
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="火焰手套",
            item_level=5,
            tier="T4",
            slot_type="hands",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "灰燼之手")
        self.assertEqual(eq.slot_type, "hands")
        self.assertEqual(eq.tier, "T4")
        self.assertEqual(eq.item_level, 5)
        self.assertIsInstance(eq, Equipment)

    async def test_generate_weapon_defaults_type(self):
        mock_llm = MagicMock()
        
        stage1_output = '''
        {
            "slot_type": "main_hand",
            "tier": "T3",
            "item_level": 10,
            "bonuses": {
                "INT": 15.0
            }
        }
        '''
        stage2_output = '''
        {
            "name": "神秘法劍",
            "description": "蘊含奧術力量的單手劍"
        }
        '''
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="法術劍",
            item_level=10,
            tier="T3",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "神秘法劍")
        # Since INT is higher than STR, weapon_type should fall back/default to "法杖"
        self.assertEqual(eq.weapon_type, "法杖")

    async def test_generate_t1_equipment_with_triggers(self):
        mock_llm = MagicMock()
        
        stage1_output = '''
        {
            "slot_type": "main_hand",
            "tier": "T1",
            "item_level": 10,
            "bonuses": {
                "STR": 20.0,
                "crit_rate": 0.05
            },
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "chance": 0.3,
                    "actions": [
                        {
                            "action_type": "inflict_damage",
                            "flat_value": 15.0,
                            "multiplier": 1.0,
                            "scaling_stat": "STR"
                        }
                    ]
                }
            ]
        }
        '''
        stage2_output = '''
        {
            "name": "天罰神諭",
            "description": "召喚雷霆",
            "special_effect": "神聖裁決：擊中敵人時有 30% 機率額外造成 15 點無視防禦力的真實傷害。"
        }
        '''
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])

        eq = await generate_equipment_by_ai(
            description="天罰神諭",
            item_level=10,
            tier="T1",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "天罰神諭")
        self.assertEqual(eq.tier, "T1")
        self.assertEqual(len(eq.executable_triggers), 1)
        self.assertEqual(eq.executable_triggers[0]["event"], "on_hit")
        self.assertEqual(eq.executable_triggers[0]["actions"][0]["action_type"], "inflict_damage")
        self.assertEqual(eq.executable_triggers[0]["actions"][0]["flat_value"], 15.0)
        self.assertEqual(eq.executable_triggers[0]["actions"][0]["damage_type"], "true_damage")

    async def test_generate_t1_equipment_two_stage(self):
        mock_llm = MagicMock()
        
        stage1_output = '''
        {
            "slot_type": "legs",
            "tier": "T1",
            "item_level": 100,
            "bonuses": {
                "CON": 100.0,
                "evasion_rate": 0.05
            },
            "executable_triggers": [
                {
                    "event": "on_turn_end",
                    "hp_above": 50,
                    "cooldown": 2,
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "target": "caster",
                            "status_name": "棉絮庇護",
                            "duration": 2,
                            "stat_bonuses": {
                                "evasion_rate": 0.20
                            }
                        }
                    ]
                }
            ]
        }
        '''
        stage2_output = '''
        {
            "name": "阿媽的棉褲",
            "description": "暖和的棉褲",
            "special_effect": "每回合結束時，若自身血量高於 50%，則獲得「棉絮庇護」狀態，持續至下回合結束；冷卻 2 回合。"
        }
        '''
        mock_llm.call = AsyncMock(side_effect=[stage1_output, stage2_output])
        
        eq = await generate_equipment_by_ai(
            description="保暖棉質長褲",
            item_level=100,
            tier="T1",
            slot_type="legs",
            llm_client=mock_llm
        )
        
        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "阿媽的棉褲")
        self.assertEqual(eq.tier, "T1")
        self.assertEqual(len(eq.executable_triggers), 1)
        self.assertEqual(eq.executable_triggers[0]["event"], "on_turn_end")
        self.assertEqual(eq.executable_triggers[0]["condition"], "health_above(50)")
        self.assertEqual(eq.executable_triggers[0]["cooldown"], 2)
        self.assertEqual(eq.executable_triggers[0]["actions"][0]["action_type"], "apply_status")
        self.assertEqual(eq.executable_triggers[0]["actions"][0]["bonuses"]["evasion_rate"], 0.20)

    # --- TriggerCompiler 獨立單元測試 ---
    def test_trigger_compiler_coercion(self):
        flat_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "flat_value": "15.5x",
                        "multiplier": "20%",
                        "scaling_stat": "int_stat" # 非法，應變為 None
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        self.assertEqual(len(compiled), 1)
        act = compiled[0]["actions"][0]
        self.assertEqual(act["flat_value"], 15.5)
        self.assertEqual(act["value_multiplier"], 0.2)
        self.assertIsNone(act["scaling_stat"])

    def test_trigger_compiler_purge_debuffs(self):
        flat_triggers = [
            {
                "event": "on_turn_start",
                "actions": [
                    {
                        "action_type": "purge_debuffs",
                        "target": "caster"
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(len(compiled[0]["actions"]), 1)
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "purge_debuffs")
        self.assertEqual(compiled[0]["actions"][0]["target"], "caster")

    def test_trigger_compiler_apply_shield(self):
        flat_triggers = [
            {
                "event": "on_damaged",
                "actions": [
                    {
                        "action_type": "apply_shield",
                        "shield_name": "棉絮庇護",
                        "con_multiplier": "1.5x",
                        "duration": 2
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(len(compiled[0]["actions"]), 2)
        
        # 1. apply_status
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "apply_status")
        self.assertEqual(compiled[0]["actions"][0]["status_name"], "棉絮庇護")
        self.assertEqual(compiled[0]["actions"][0]["duration"], 2)
        
        # 2. gain_shield
        self.assertEqual(compiled[0]["actions"][1]["action_type"], "gain_shield")
        self.assertEqual(compiled[0]["actions"][1]["scaling_stat"], "CON")
        self.assertEqual(compiled[0]["actions"][1]["value_multiplier"], 1.5)

    def test_trigger_compiler_auto_split(self):
        # 包含一個攔截器行為(set_value)與一個普通戰鬥行為(inflict_damage)
        flat_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "set_value",
                        "param": "damage_multiplier",
                        "param_value": 1.25
                    },
                    {
                        "action_type": "inflict_damage",
                        "flat_value": 10
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        # 應自動拆分為 2 個 Triggers
        self.assertEqual(len(compiled), 2)
        
        # Trigger 1: on_calculate_damage
        self.assertEqual(compiled[0]["event"], "on_calculate_damage")
        self.assertEqual(len(compiled[0]["actions"]), 2)
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "set_value")
        self.assertEqual(compiled[0]["actions"][1]["action_type"], "set_flag")
        flag_name = compiled[0]["actions"][1]["param"]
        self.assertTrue(flag_name.startswith("_auto_flag_"))
        
        # Trigger 2: on_hit
        self.assertEqual(compiled[1]["event"], "on_hit")
        self.assertEqual(compiled[1]["condition"], f"context_flag('{flag_name}')")
        self.assertEqual(len(compiled[1]["actions"]), 1)
        self.assertEqual(compiled[1]["actions"][0]["action_type"], "inflict_damage")

    def test_trigger_compiler_percent_scaling(self):
        # 測試 hp_below 浮點數/百分比格式轉成 1-100 的整數
        flat_triggers = [
            {
                "event": "on_health_below",
                "hp_below": 0.4,
                "actions": [
                    {
                        "action_type": "heal",
                        "flat_value": 50
                    }
                ]
            },
            {
                "event": "on_health_below",
                "hp_below": "30%",
                "actions": [
                    {
                        "action_type": "heal",
                        "flat_value": 50
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        self.assertEqual(len(compiled), 2)
        
        # 第一個 trigger 應轉為 health_below(40) 且 health_threshold 補齊為 40.0
        self.assertEqual(compiled[0]["condition"], "health_below(40)")
        self.assertEqual(compiled[0]["health_threshold"], 40.0)
        
        # 第二個 trigger 應轉為 health_below(30) 且 health_threshold 補齊為 30.0
        self.assertEqual(compiled[1]["condition"], "health_below(30)")
        self.assertEqual(compiled[1]["health_threshold"], 30.0)

    def test_trigger_compiler_mismatched_event_actions(self):
        # 測試在攔截器事件 (on_cast / on_prepare) 中放入普通戰鬥行動，能自動重新路由到 on_hit
        flat_triggers = [
            {
                "event": "on_cast",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "status_name": "真理洞察",
                        "duration": 1
                    }
                ]
            }
        ]
        compiled = TriggerCompiler.compile_flat_triggers(flat_triggers)
        # 應將 event 從 on_prepare (on_cast) 改寫為 on_hit
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_hit")
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "apply_status")
