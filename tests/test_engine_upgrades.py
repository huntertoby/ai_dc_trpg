import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, StatusEffect, Equipment
from core.skill_processor import add_entity_status_effect

class TestEngineUpgrades(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_999",
            name="雷克斯",
            background="孤兒",
            primary_stats=PrimaryAttributes(STR=20, DEX=999, CON=15, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.char.total_stats = {"STR": 20, "DEX": 999, "CON": 15, "INT": 10, "WIS": 10, "CHA": 10}
        self.char.max_hp = 100
        self.char.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 0.95, "skill_power": 1.0, "tenacity": 100, "luck": 1
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
        
        self.monsters = [
            {
                "name": "幽靈",
                "base_name": "幽靈",
                "level": 5,
                "hp": 100,
                "max_hp": 100,
                "attack": 15,
                "defense": 10,
                "m_defense": 10,
                "speed": 15,
                "evasion_rate": 0.0,
                "source_id": "ghost",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    def test_status_stacking_refreshes_duration(self):
        # Apply the same status twice to test stacking and duration refresh
        add_entity_status_effect(self.char, "TestStack", "Test Stack Effect", 3, max_stacks=3)
        self.assertEqual(len(self.char.data.status_effects), 1)
        self.assertEqual(self.char.data.status_effects[0].stacks, 1)
        self.assertEqual(self.char.data.status_effects[0].duration, 3)

        # Apply again: stacks should increase to 2, duration refreshes to 5
        add_entity_status_effect(self.char, "TestStack", "Test Stack Effect", 5, max_stacks=3)
        self.assertEqual(len(self.char.data.status_effects), 1)
        self.assertEqual(self.char.data.status_effects[0].stacks, 2)
        self.assertEqual(self.char.data.status_effects[0].duration, 5)

        # Apply to max_stacks
        add_entity_status_effect(self.char, "TestStack", "Test Stack Effect", 2, max_stacks=3)
        self.assertEqual(self.char.data.status_effects[0].stacks, 3)
        self.assertEqual(self.char.data.status_effects[0].duration, 2)

        # Apply beyond max_stacks: should clamp to 3 and refresh duration to 4
        add_entity_status_effect(self.char, "TestStack", "Test Stack Effect", 4, max_stacks=3)
        self.assertEqual(self.char.data.status_effects[0].stacks, 3)
        self.assertEqual(self.char.data.status_effects[0].duration, 4)

    async def test_context_flag_sharing(self):
        # 1. Equip an item that sets a flag on calculate damage interceptor phase
        weapon = Equipment(
            name="魂之刃",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1",
            scaling_stat="STR",
            damage_type="physical"
        )
        weapon.executable_triggers = [
            {
                "event": "on_calculate_damage",
                "actions": [
                    {
                        "action_type": "set_flag",
                        "param": "soul_blade_active",
                        "param_value": True
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon

        # 2. Add a status effect that heals 15 HP on hit ONLY if the combat flag is active
        heal_on_hit_effect = StatusEffect(
            name="魂之回饋",
            description="擊中時若有魂之刃標記則治療自身",
            duration=3,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "condition": "context_flag('soul_blade_active')",
                    "actions": [
                        {
                            "action_type": "heal",
                            "target": "caster",
                            "flat_value": 15.0
                        }
                    ]
                }
            ]
        )
        self.char.data.status_effects.append(heal_on_hit_effect)

        # Initialize character health at 50 to see the heal
        self.char.data.vitality.hp = 50

        # Run attack
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
            # Since the flag was shared from calculate damage to on_hit, the character should heal
            # Initial hp = 50. Heal amount = 15. Total = 65.
            self.assertEqual(self.char.data.vitality.hp, 65)

    async def test_status_auto_consume(self):
        # Add a status effect with trigger_limit=1
        consumable_effect = StatusEffect(
            name="一次性力量",
            description="下一擊造成額外 10 點傷害，隨後消失",
            duration=3,
            trigger_limit=1,
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "inflict_damage",
                            "target": "target",
                            "flat_value": 10.0
                        }
                    ]
                }
            ]
        )
        self.char.data.status_effects.append(consumable_effect)

        # Initialize combat manager
        cm = CombatManager(self.char, self.monsters)
        
        # Verify status is active initially
        self.assertEqual(len(self.char.data.status_effects), 1)
        self.assertEqual(self.char.data.status_effects[0].name, "一次性力量")

        # Perform attack
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
            # Status should have fired and then been automatically removed because of trigger_limit = 1
            self.assertEqual(len(self.char.data.status_effects), 0)
