import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import Skill, SkillMechanics, SkillFormula, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, StatusEffect, Equipment
from core.trigger_engine import TriggerEngine

class TestAoeAndTargetConditions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_aoe",
            name="索爾",
            background="戰士",
            primary_stats=PrimaryAttributes(STR=20, DEX=15, CON=15, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
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
        
        # Mock save and update_vitality methods
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
            },
            {
                "name": "地精 B",
                "base_name": "地精",
                "level": 1,
                "hp": 100,
                "max_hp": 100,
                "defense": 5,
                "m_defense": 5,
                "speed": 6,
                "evasion_rate": 0.0,
                "source_id": "goblin",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    async def test_target_status_condition(self):
        # Verify that a trigger with target_has_status condition only fires when the target possesses the status.
        weapon = Equipment(
            name="獵巫邪劍",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "condition": "target_has_status('Stun')",
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 30.0,
                        "damage_type": "true_damage"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        
        # Case A: Attack target without 'Stun' status -> no extra damage
        self.monsters[0]["hp"] = 100
        cm = CombatManager(self.char, self.monsters)
        
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # Normal attack with weapon results in 22 damage.
            self.assertEqual(self.monsters[0]["hp"], 78)
            
        # Case B: Attack target with 'Stun' status -> triggers 30 extra true damage
        self.monsters[0]["hp"] = 100
        self.monsters[0]["status_effects"].append(StatusEffect(name="Stun", description="眩暈", duration=3))
        
        # Reset turn order so player can attack again
        for idx, ent in enumerate(cm.turn_order):
            if ent["type"] == "player":
                cm.current_turn_idx = idx
                break
        cm._current_turn_ticked = False
        
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # Normal attack = 22. Extra true damage = 30. Total damage = 52.
            # HP = 100 - 52 = 48.
            self.assertEqual(self.monsters[0]["hp"], 48)

    async def test_all_enemies_aoe_damage(self):
        # Verify that a trigger targeting all_enemies correctly inflicts damage on all active monsters in combat.
        weapon = Equipment(
            name="雷神震擊之錘",
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
                        "target": "all_enemies",
                        "flat_value": 20.0,
                        "damage_type": "true_damage"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.monsters[0]["hp"] = 100
        self.monsters[1]["hp"] = 100
        
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
            # Normal hit on monster 0: 22 damage.
            # Thunder shock trigger on all_enemies: 20 true damage to both monsters.
            # Monster 0 HP: 100 - 22 - 20 = 58.
            # Monster 1 HP: 100 - 20 = 80.
            self.assertEqual(self.monsters[0]["hp"], 58)
            self.assertEqual(self.monsters[1]["hp"], 80)

    async def test_all_allies_aoe_shield(self):
        # Verify that a trigger targeting all_allies applies shield/effects to both the character and summons.
        weapon = Equipment(
            name="聖光誓言",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "gain_shield",
                        "target": "all_allies",
                        "flat_value": 15.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.char.data.vitality.temp_hp = 0
        
        # Setup summon monster on player side
        # Summons are stored in combat_manager.monsters with is_summon = True
        summon = {
            "name": "召喚小鬼",
            "base_name": "召喚小鬼",
            "level": 1,
            "hp": 50,
            "max_hp": 50,
            "speed": 5,
            "is_summon": True,
            "temp_hp": 0,
            "status_effects": []
        }
        self.monsters.append(summon)
        
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
            # Both character and summon should receive 15 shield (temp_hp)
            self.assertEqual(self.char.data.vitality.temp_hp, 15)
            self.assertEqual(summon["temp_hp"], 15)

    async def test_damage_type_condition(self):
        # Setup a trigger on the player with condition: damage_type('magical')
        weapon = Equipment(
            name="魔能法典",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "condition": "damage_type('magical')",
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 50.0,
                        "damage_type": "true_damage"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        
        # Case A: Attack using physical attack -> triggers should NOT fire
        self.monsters[0]["hp"] = 100
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # Normal attack (physical) damage = 22. Target HP = 100 - 22 = 78.
            self.assertEqual(self.monsters[0]["hp"], 78)
            
        # Case B: Cast a magical skill (INT-based) -> trigger should fire
        magic_skill = Skill(
            name="奧術衝擊",
            description="造成魔法傷害",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=5.0)
            )
        )
        
        # Reset monsters HP
        self.monsters[0]["hp"] = 100
        self.char.data.vitality.mp = 100
        
        # Reset turn order
        for idx, ent in enumerate(cm.turn_order):
            if ent["type"] == "player":
                cm.current_turn_idx = idx
                break
        cm._current_turn_ticked = False
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=5):
            # Base dmg = INT(10) * (5/5.0) = 10.
            # Edef = 5. Skill dmg = 10 - 5 = 5.
            # Trigger magic dmg = 50. Total dmg = 55.
            # HP = 100 - 55 = 45.
            res = await cm.cast_skill(magic_skill, 0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 45)
