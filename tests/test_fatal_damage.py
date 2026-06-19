import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, StatusEffect
from core.combat_utils import add_entity_status_effect

class TestFatalDamage(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_999",
            name="雷克斯",
            background="孤兒",
            primary_stats=PrimaryAttributes(STR=20, DEX=999, CON=15, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=50, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.char.total_stats = {"STR": 20, "DEX": 999, "CON": 15, "INT": 10, "WIS": 10, "CHA": 10}
        self.char.max_hp = 100
        self.char.combat_stats = {
            "p_def": 0, "m_def": 0, "crit_rate": 0.0, "evasion_rate": 0.0,
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
                "attack": 60,
                "defense": 10,
                "m_defense": 10,
                "speed": 999,
                "evasion_rate": 0.0,
                "source_id": "ghost",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    async def test_fatal_damage_prevention(self):
        # 1. Give character the consumable fatal damage prevention status effect
        unyielding_effect = StatusEffect(
            name="棉絮纏繞",
            description="受到下一次致命傷害時強制保留 1 點生命值",
            duration=3,
            trigger_limit=1,
            executable_triggers=[
                {
                    "event": "on_fatal_damage",
                    "actions": [
                        {
                            "action_type": "call_special_mechanic",
                            "target": "caster",
                            "keyword_name": "Prevent_Death"
                        }
                    ]
                }
            ]
        )
        self.char.data.status_effects.append(unyielding_effect)

        cm = CombatManager(self.char, self.monsters)
        cm.turn_order = [{"type": "monster", "speed": 999, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True

        # Initial HP is 50. Monster attacks with 60 damage (with mock randint = 10, roll_mult = 1.0, damage = 60, which is lethal)
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])

        # Health should be clamped to exactly 1 HP!
        self.assertEqual(self.char.data.vitality.hp, 1)

        # The status effect should have been consumed/removed
        self.assertEqual(len(self.char.data.status_effects), 0)

        # Monster attacks again. Since character only has 1 HP and no unyielding status, character dies.
        cm.turn_order = [{"type": "monster", "speed": 999, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        self.assertEqual(self.char.data.vitality.hp, 0)
        self.assertTrue(cm.is_finished)
        self.assertEqual(cm.winner, "monster")
