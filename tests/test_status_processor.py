import unittest
from datetime import datetime, timedelta
from core.status_processor import StatusProcessor, DailyResetManager
from core.models import StatusEffect, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots

class TestStatusProcessor(unittest.TestCase):
    def setUp(self):
        self.char = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=50, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], equipment_slots=EquipmentSlots(),
            status_effects=[
                StatusEffect(name="強效護盾", duration_type="turns", duration=2),
                StatusEffect(name="詛咒", duration_type="days", duration=3),
                StatusEffect(name="短暫虛弱", duration_type="turns", duration=1)
            ]
        )

    def test_tick_turns(self):
        # Initial status effects: 2 turns, 3 days, 1 turn
        # After 1 tick:
        # - "強效護盾" becomes duration 1 (kept)
        # - "詛咒" is days (ignored, kept)
        # - "短暫虛弱" becomes duration 0 (removed)
        StatusProcessor.tick_turns(self.char)
        self.assertEqual(len(self.char.status_effects), 2)
        self.assertEqual(self.char.status_effects[0].name, "強效護盾")
        self.assertEqual(self.char.status_effects[0].duration, 1)
        self.assertEqual(self.char.status_effects[1].name, "詛咒")
        self.assertEqual(self.char.status_effects[1].duration, 3)

        # After another tick:
        # - "強效護盾" becomes duration 0 (removed)
        # - "詛咒" remains (kept)
        StatusProcessor.tick_turns(self.char)
        self.assertEqual(len(self.char.status_effects), 1)
        self.assertEqual(self.char.status_effects[0].name, "詛咒")
        self.assertEqual(self.char.status_effects[0].duration, 3)

    def test_update_days(self):
        # Initial status effects: 2 turns, 3 days, 1 turn
        # After update_days:
        # - "強效護盾" is turns (ignored, kept)
        # - "詛咒" becomes duration 2 (kept)
        # - "短暫虛弱" is turns (ignored, kept)
        StatusProcessor.update_days(self.char)
        self.assertEqual(len(self.char.status_effects), 3)
        self.assertEqual(self.char.status_effects[1].name, "詛咒")
        self.assertEqual(self.char.status_effects[1].duration, 2)

    def test_daily_reset_manager_same_day(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.char.last_daily_reset_date = today_str
        
        updated = DailyResetManager.check_and_reset(self.char)
        self.assertFalse(updated)

    def test_daily_reset_manager_first_time(self):
        self.char.last_daily_reset_date = None
        
        updated = DailyResetManager.check_and_reset(self.char)
        # Returns False on first registration
        self.assertFalse(updated)
        self.assertEqual(self.char.last_daily_reset_date, datetime.now().strftime("%Y-%m-%d"))

    def test_daily_reset_manager_cross_day(self):
        # Set last reset to yesterday
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.char.last_daily_reset_date = yesterday_str
        
        # Current stamina = 50, max_stamina = 100
        self.char.vitality.stamina = 50
        
        updated = DailyResetManager.check_and_reset(self.char)
        self.assertTrue(updated)
        
        # Stamina should be restored to max
        self.assertEqual(self.char.vitality.stamina, 100)
        # "詛咒" duration should have ticked down from 3 to 2
        self.assertEqual(self.char.status_effects[1].duration, 2)
        # Date updated to today
        self.assertEqual(self.char.last_daily_reset_date, datetime.now().strftime("%Y-%m-%d"))
        
    def test_daily_reset_manager_cross_multiple_days(self):
        # Set last reset to 3 days ago
        three_days_ago_str = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        self.char.last_daily_reset_date = three_days_ago_str
        
        updated = DailyResetManager.check_and_reset(self.char)
        self.assertTrue(updated)
        
        # "詛咒" duration should have ticked down by 3 (from 3 to 0, so it gets removed)
        # Verify "詛咒" is removed
        status_names = [e.name for e in self.char.status_effects]
        self.assertNotIn("詛咒", status_names)
