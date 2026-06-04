import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots

class TestCombat(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up a mock Character
        self.mock_char = MagicMock()
        self.mock_char.data = CharacterSchema(
            character_id="test_char_123",
            name="卡爾",
            background="孤兒",
            primary_stats=PrimaryAttributes(STR=10, DEX=12, CON=10, INT=8, WIS=8, CHA=8),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots(),
            stat_points=5
        )
        self.mock_char.total_stats = {"STR": 10, "DEX": 12, "CON": 10, "INT": 8, "WIS": 8, "CHA": 8}
        self.mock_char.max_hp = 200
        self.mock_char.combat_stats = {
            "p_def": 10, "m_def": 5, "crit_rate": 0.1, "evasion_rate": 0.05,
            "accuracy": 0.9, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        self.monsters = [
            {
                "name": "野狼 A",
                "base_name": "野狼",
                "level": 1,
                "hp": 30,
                "max_hp": 30,
                "attack": 8,
                "defense": 2,
                "m_defense": 1,
                "speed": 8,
                "source_id": "common_species"
            },
            {
                "name": "野狼 B",
                "base_name": "野狼",
                "level": 1,
                "hp": 30,
                "max_hp": 30,
                "attack": 8,
                "defense": 2,
                "m_defense": 1,
                "speed": 6,
                "source_id": "common_species"
            }
        ]

    def test_initialize_battle(self):
        cm = CombatManager(self.mock_char, self.monsters)
        # Turn order should contain 3 entities (1 player, 2 monsters)
        self.assertEqual(len(cm.turn_order), 3)
        # Verify the fastest entity is at index 0
        self.assertGreaterEqual(cm.turn_order[0]["speed"], cm.turn_order[1]["speed"])
        self.assertGreaterEqual(cm.turn_order[1]["speed"], cm.turn_order[2]["speed"])

    def test_get_current_entity_and_next_turn(self):
        cm = CombatManager(self.mock_char, self.monsters)
        first_entity = cm.get_current_entity()
        self.assertIn(first_entity["type"], ["player", "monster"])
        
        cm.next_turn()
        second_entity = cm.get_current_entity()
        self.assertNotEqual(id(first_entity), id(second_entity))

    @patch("random.randint", return_value=10)
    @patch("random.random", return_value=0.5)
    async def test_player_attack(self, mock_random, mock_randint):
        cm = CombatManager(self.mock_char, self.monsters)
        # Let's perform an attack on target 0 ("野狼 A")
        # Target 0 HP is 30.
        res = await cm.player_attack(0)
        self.assertTrue(res["success"])
        # Target HP should have decreased
        self.assertLess(self.monsters[0]["hp"], 30)

    @patch("random.randint", return_value=10)
    async def test_monster_action_hit(self, mock_randint):
        cm = CombatManager(self.mock_char, self.monsters)
        # Force current turn to be a monster
        cm.turn_order = [{"type": "monster", "speed": 15, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        
        res = await cm.monster_action()
        self.assertTrue(res["success"])
        # Player HP should have decreased
        self.assertLess(self.mock_char.data.vitality.hp, 100)

    def test_check_battle_status_player_wins(self):
        cm = CombatManager(self.mock_char, self.monsters)
        self.assertFalse(cm.is_finished)
        # Kill all monsters
        for m in self.monsters:
            m["hp"] = 0
        cm._check_battle_status()
        self.assertTrue(cm.is_finished)
        self.assertEqual(cm.winner, "player")

    def test_check_battle_status_monster_wins(self):
        cm = CombatManager(self.mock_char, self.monsters)
        self.assertFalse(cm.is_finished)
        # Kill player
        self.mock_char.data.vitality.hp = 0
        cm._check_battle_status()
        self.assertTrue(cm.is_finished)
        self.assertEqual(cm.winner, "monster")

    def test_get_battle_summary(self):
        cm = CombatManager(self.mock_char, self.monsters)
        summary = cm.get_battle_summary()
        self.assertIn("卡爾", summary)
        self.assertIn("野狼 A", summary)
        self.assertIn("野狼 B", summary)

    @patch("random.randint", return_value=10)
    @patch("random.random", return_value=0.5)
    async def test_player_attack_default_target_and_turn_progression(self, mock_random, mock_randint):
        cm = CombatManager(self.mock_char, self.monsters)
        # Ensure it is player's turn initially for testing
        cm.turn_order = [
            {"type": "player", "speed": 10, "ref": self.mock_char},
            {"type": "monster", "speed": 5, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        
        # Test attack without passing target_idx (should target monster at index 0)
        res = await cm.player_attack()
        self.assertTrue(res["success"])
        self.assertLess(self.monsters[0]["hp"], 30)
        # Turn should have advanced to the monster
        self.assertEqual(cm.get_current_entity()["type"], "monster")

    @patch("core.skill_processor.SkillProcessor.execute_skill")
    async def test_cast_skill_default_target(self, mock_execute):
        from core.models import Skill, SkillMechanics, SkillFormula
        cm = CombatManager(self.mock_char, self.monsters)
        cm.turn_order = [
            {"type": "player", "speed": 10, "ref": self.mock_char},
            {"type": "monster", "speed": 5, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        
        mock_execute.return_value = {"success": True, "final_value": 10, "logs": [], "control_flags": {}}
        test_skill = Skill(
            name="火球術",
            description="射出火球",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", divisor=10.0, dice="1d20")
            )
        )
        
        res = await cm.cast_skill(test_skill)
        self.assertTrue(res["success"])
        # Should execute skill targeting first alive monster (index 0)
        mock_execute.assert_called_once()
        self.assertEqual(mock_execute.call_args[0][2], self.monsters[0])

    def test_get_valid_targets(self):
        cm = CombatManager(self.mock_char, self.monsters)
        # Initially both monsters are alive
        targets = cm.get_valid_targets()
        self.assertEqual(len(targets), 2)
        
        # Kill one monster
        self.monsters[0]["hp"] = 0
        targets = cm.get_valid_targets()
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["index"], 1)
        self.assertEqual(targets[0]["name"], "野狼 B")
