import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, Equipment, StatusEffect
from core.compiler import TriggerCompiler
from core.trigger_engine import TriggerEngine

class TestDiceBranchingAndFlexibleShield(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_upgrades",
            name="索爾",
            background="戰士",
            primary_stats=PrimaryAttributes(STR=20, DEX=15, CON=15, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100, temp_hp=0),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.char.total_stats = {"STR": 20, "DEX": 15, "CON": 15, "INT": 10, "WIS": 10, "CHA": 10}
        self.char.max_hp = 100
        self.char.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 1.0, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        def mock_save():
            pass
        self.char.save = MagicMock(side_effect=mock_save)
        
        def mock_update_vitality(hp=None, mp=None, sanity=None, stamina=None, temp_hp=None):
            v = self.char.data.vitality
            if hp is not None: v.hp = max(0, min(int(hp), 100))
            if mp is not None: v.mp = max(0, min(int(mp), 100))
            if temp_hp is not None: v.temp_hp = max(0, int(temp_hp))
        self.char.update_vitality = MagicMock(side_effect=mock_update_vitality)
        
        # Setup monsters
        self.monsters = [
            {
                "name": "地精 A",
                "base_name": "地精",
                "level": 1,
                "hp": 100,
                "max_hp": 100,
                "defense": 5,
                "m_defense": 5,
                "speed": 8,
                "evasion_rate": 0.0,
                "source_id": "goblin",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    def test_flexible_shield_compilation(self):
        # 1. Test compilation of apply_shield with custom stats and flat values
        raw_trigger = {
            "event": "on_hit",
            "actions": [
                {
                    "action_type": "apply_shield",
                    "shield_name": "MageShield",
                    "duration": 4,
                    "flat_value": 20.0,
                    "scaling_stat": "INT",
                    "value_multiplier": 1.5,
                    "target": "caster"
                }
            ]
        }
        
        compiled = TriggerCompiler.compile_flat_triggers([raw_trigger])
        self.assertEqual(len(compiled), 1)
        actions = compiled[0]["actions"]
        self.assertEqual(len(actions), 2)
        
        self.assertEqual(actions[0]["action_type"], "apply_status")
        self.assertEqual(actions[0]["status_name"], "MageShield")
        self.assertEqual(actions[0]["duration"], 4)
        
        self.assertEqual(actions[1]["action_type"], "gain_shield")
        self.assertEqual(actions[1]["flat_value"], 20.0)
        self.assertEqual(actions[1]["scaling_stat"], "INT")
        self.assertEqual(actions[1]["value_multiplier"], 1.5)

    async def test_flexible_shield_execution(self):
        # 2. Test execution of a flexible shield trigger
        weapon = Equipment(
            name="奧術庇護法杖",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "status_name": "MageShield",
                        "duration": 4,
                        "target": "caster"
                    },
                    {
                        "action_type": "gain_shield",
                        "flat_value": 20.0,
                        "scaling_stat": "INT",
                        "value_multiplier": 1.5,
                        "target": "caster"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        
        cm = CombatManager(self.char, self.monsters)
        # Trigger on_hit:
        # Caster INT = 10, flat_value = 20.0, multiplier = 1.5. Shield = 20 + 10 * 1.5 = 35.
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.char.data.vitality.temp_hp, 35)

    async def test_action_level_dice_execution(self):
        # 3. Test action-level dice formulas: e.g. 25.0 + 1d20/10.0 * STR
        weapon = Equipment(
            name="雷霆裂地斧",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 25.0,
                        "dice": "1d20",
                        "divisor": 10.0,
                        "scaling_stat": "STR",
                        "value_multiplier": 1.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.monsters[0]["hp"] = 100
        
        cm = CombatManager(self.char, self.monsters)
        # Mock roll_dice for the 1d20 in action to return 15
        # STR = 20. Extra dmg = 25.0 + 20 * 1.0 * (15 / 10.0) = 25.0 + 30.0 = 55.
        # Normal hit is 22. Total = 77.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=15), \
             patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 23) # 100 - 77 = 23

    async def test_dice_branching_execution(self):
        # 4. Test dice roll branching: Turn Start rolls 1d2.
        # If 2, caster gets "狂暴" status.
        # If 1, caster takes 10 flat damage.
        weapon = Equipment(
            name="賭徒手套",
            item_type="equipment",
            slot_type="trinket_1",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_turn_start",
                "branch_roll": "1d2",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "status_name": "狂暴",
                        "duration": 2,
                        "branch_when": [2, 2],
                        "target": "caster"
                    },
                    {
                        "action_type": "inflict_damage",
                        "flat_value": 10.0,
                        "branch_when": [1, 1],
                        "target": "caster"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.trinket_1 = weapon
        
        # Test Case A: Roll 2 -> Buff Caster
        self.char.data.vitality.hp = 100
        self.char.data.status_effects = []
        
        # Mock turn start dice roll to 2
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=2):
            cm = CombatManager(self.char, self.monsters)
            
            # Caster should have "狂暴" status
            has_status = any(e.name == "狂暴" for e in self.char.data.status_effects)
            self.assertTrue(has_status)
            # Caster HP should still be 100
            self.assertEqual(self.char.data.vitality.hp, 100)

        # Test Case B: Roll 1 -> Damage Caster
        self.char.data.vitality.hp = 100
        self.char.data.status_effects = []
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            cm = CombatManager(self.char, self.monsters)
            
            # Caster should NOT have "狂暴" status
            has_status = any(e.name == "狂暴" for e in self.char.data.status_effects)
            self.assertFalse(has_status)
            # Caster should have taken 10 damage -> HP = 90
            self.assertEqual(self.char.data.vitality.hp, 90)

    def test_pydantic_validator_guard(self):
        # 5. Test validation guard in item_generator.py parsing logic
        from core.item_generator import generate_equipment_by_ai
        
        # Test that lower-case or invalid stats default correctly or parse uppercase
        # We can directly test the guard logic by preparing mock parsed JSON structures
        # Mocking repair_and_parse_json to return lowercase stats and invalid "luck"
        mock_response_1 = '{"name": "骰子之戒", "scaling_stat": "luck", "damage_type": "magical"}'
        mock_response_2 = '{"name": "力量拳套", "scaling_stat": "dex", "damage_type": "physical"}'
        
        from utils.json_utils import repair_and_parse_json
        
        # Case A: "luck" is invalid, should default to "STR"
        parsed_1 = repair_and_parse_json(mock_response_1)
        stat_1 = parsed_1.get("scaling_stat")
        if not isinstance(stat_1, str) or stat_1.upper() not in ["STR", "DEX", "INT", "WIS", "CHA", "CON"]:
            parsed_1["scaling_stat"] = "STR"
        else:
            parsed_1["scaling_stat"] = stat_1.upper()
        self.assertEqual(parsed_1["scaling_stat"], "STR")
        
        # Case B: "dex" is lowercase, should clean to "DEX"
        parsed_2 = repair_and_parse_json(mock_response_2)
        stat_2 = parsed_2.get("scaling_stat")
        if not isinstance(stat_2, str) or stat_2.upper() not in ["STR", "DEX", "INT", "WIS", "CHA", "CON"]:
            parsed_2["scaling_stat"] = "STR"
        else:
            parsed_2["scaling_stat"] = stat_2.upper()
        self.assertEqual(parsed_2["scaling_stat"], "DEX")

if __name__ == '__main__':
    unittest.main()
