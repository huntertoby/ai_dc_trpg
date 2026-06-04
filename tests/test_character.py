import unittest
from unittest.mock import patch, MagicMock
from core.character import Character
from core.models import CharacterSchema, Item, Equipment, StatusEffect, Vitality, PrimaryAttributes, EquipmentSlots

class TestCharacter(unittest.TestCase):
    def setUp(self):
        # Create a dummy character schema
        self.schema = CharacterSchema(
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
        self.patcher = patch("core.character.CharacterRepository")
        self.mock_repo = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_init_and_save(self):
        char = Character(self.schema, "user_1")
        char.save()
        self.mock_repo.save.assert_called_with(self.schema, "user_1")
        # Check that max attributes got synced
        self.assertEqual(self.schema.vitality.max_hp, 100 + 10 * 10)  # CON=10 -> max_hp=200

    def test_add_log_limits_to_50(self):
        char = Character(self.schema, "user_1")
        for i in range(55):
            char.add_log("GRIND", f"Log event {i}")
        self.assertEqual(len(self.schema.adventure_logs), 50)
        self.assertEqual(self.schema.adventure_logs[-1].content, "Log event 54")

    def test_evolution_triggers(self):
        char = Character(self.schema, "user_1")
        # Default level = 1, total_trpg_events = 0
        self.assertFalse(char.check_evolution_triggers())
        
        # Trigger via level
        self.schema.level = 11
        self.assertTrue(char.check_evolution_triggers())
        
        char.mark_evolution_checked()
        self.assertEqual(self.schema.last_personality_check_level, 11)
        self.assertFalse(char.check_evolution_triggers())

        # Trigger via events
        self.schema.total_trpg_events = 20
        self.assertTrue(char.check_evolution_triggers())

    def test_reputation_title(self):
        char = Character(self.schema, "user_1")
        self.schema.level = 5
        self.assertEqual(char.reputation_title, "🌱 初出茅廬")
        self.schema.level = 26
        self.assertEqual(char.reputation_title, "🛡️ 嶄露頭角")
        self.schema.level = 100
        self.assertEqual(char.reputation_title, "👑 登峰造極")

    def test_rank_value(self):
        char = Character(self.schema, "user_1")
        self.schema.rank = "D"
        self.assertEqual(char.rank_value, 1)

    def test_total_stats_with_equipment_and_status(self):
        char = Character(self.schema, "user_1")
        # Base STR = 10
        # Equip a sword giving STR+3
        sword = Equipment(name="青銅劍", slot_type="main_hand", tier="T4", bonuses={"STR": 3.0})
        self.schema.equipment_slots.main_hand = sword
        
        # Add a status effect giving STR+2
        effect = StatusEffect(name="狂暴", duration=3, bonuses={"str": 2.0})
        self.schema.status_effects.append(effect)
        
        stats = char.total_stats
        self.assertEqual(stats["STR"], 15)  # 10 (base) + 3 (eq) + 2 (status)

    def test_add_item_stacking(self):
        char = Character(self.schema, "user_1")
        item1 = Item(name="狼牙", quantity=2, item_type="material")
        char.add_item(item1)
        self.assertEqual(len(self.schema.inventory), 1)
        self.assertEqual(self.schema.inventory[0].quantity, 2)
        
        # Stack same item
        item2 = Item(name="狼牙", quantity=3, item_type="material")
        char.add_item(item2)
        self.assertEqual(len(self.schema.inventory), 1)
        self.assertEqual(self.schema.inventory[0].quantity, 5)

    def test_equip_and_unequip_item(self):
        char = Character(self.schema, "user_1")
        sword = Equipment(name="鐵劍", slot_type="main_hand", tier="T4", bonuses={"STR": 4.0})
        self.schema.inventory.append(sword)
        
        char.equip_item("鐵劍")
        self.assertEqual(self.schema.equipment_slots.main_hand.name, "鐵劍")
        self.assertEqual(len(self.schema.inventory), 0)

        # Unequip
        char.unequip_item("main_hand")
        self.assertIsNone(self.schema.equipment_slots.main_hand)
        self.assertEqual(self.schema.inventory[0].name, "鐵劍")

    def test_equip_two_handed_weapon_un_equips_offhand(self):
        char = Character(self.schema, "user_1")
        shield = Equipment(name="小盾", slot_type="off_hand", tier="T4", bonuses={"CON": 2.0})
        self.schema.equipment_slots.off_hand = shield
        
        greatsword = Equipment(name="巨劍", slot_type="main_hand", tier="T4", is_two_handed=True, bonuses={"STR": 6.0})
        self.schema.inventory.append(greatsword)
        
        char.equip_item("巨劍")
        self.assertEqual(self.schema.equipment_slots.main_hand.name, "巨劍")
        self.assertIsNone(self.schema.equipment_slots.off_hand)
        self.assertEqual(self.schema.inventory[0].name, "小盾")

    def test_add_bonus_points(self):
        char = Character(self.schema, "user_1")
        self.assertEqual(self.schema.stat_points, 5)
        char.add_bonus_points({"STR": 3, "DEX": 2})
        self.assertEqual(self.schema.primary_stats.STR, 13)
        self.assertEqual(self.schema.primary_stats.DEX, 14)
        self.assertEqual(self.schema.stat_points, 0)

        # Spend too many points
        with self.assertRaises(ValueError):
            char.add_bonus_points({"STR": 1})

    def test_add_exp_and_level_up(self):
        char = Character(self.schema, "user_1")
        self.assertEqual(self.schema.level, 1)
        # xp_required = 100 * (1 ^ 1.5) = 100
        leveled_up = char.add_exp(120)
        self.assertTrue(leveled_up)
        self.assertEqual(self.schema.level, 2)
        self.assertEqual(self.schema.exp, 20)
        self.assertEqual(self.schema.stat_points, 10)  # 5 base + 5 level up

    def test_combat_stats(self):
        char = Character(self.schema, "user_1")
        c_stats = char.combat_stats
        self.assertIn("p_def", c_stats)
        self.assertIn("m_def", c_stats)
        self.assertIn("crit_rate", c_stats)
        self.assertIn("evasion_rate", c_stats)
