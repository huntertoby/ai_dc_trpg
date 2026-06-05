import unittest
from core.equipment import EquipmentBalancer
from core.models import Equipment

class TestEquipment(unittest.TestCase):
    def test_calculate_budgets(self):
        budgets = EquipmentBalancer.calculate_budgets(10, "T3")
        # primary: (10 + (10 * 2.5)) * 0.75 = 35 * 0.75 = 26.25
        # sub: (10 * 0.25) * 1.5 = 2.5 * 1.5 = 3.75
        self.assertAlmostEqual(budgets["primary"], 26.25)
        self.assertAlmostEqual(budgets["sub"], 3.75)

    def test_get_tier_color(self):
        self.assertEqual(EquipmentBalancer.get_tier_color("T1"), 0xf1c40f)
        self.assertEqual(EquipmentBalancer.get_tier_color("T5"), 0x95a5a6)
        self.assertEqual(EquipmentBalancer.get_tier_color("UNKNOWN"), 0xffffff)

    def test_validate_and_clamp_non_t1_clears_special_effect(self):
        eq = Equipment(
            name="鐵劍", slot_type="main_hand", tier="T4", item_level=5,
            special_effect="毀天滅地", bonuses={"STR": 100.0}
        )
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        self.assertEqual(clamped.special_effect, "")

    def test_validate_and_clamp_t1_keeps_special_effect(self):
        eq = Equipment(
            name="聖劍", slot_type="main_hand", tier="T1", item_level=5,
            special_effect="神聖光輝", bonuses={"STR": 10.0}
        )
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        self.assertEqual(clamped.special_effect, "神聖光輝")

    def test_validate_and_clamp_adjusts_stats(self):
        # Create an equipment with too many bonuses (over budget)
        eq = Equipment(
            name="超強戒指", slot_type="trinket_1", tier="T3", item_level=1,
            bonuses={"STR": 50.0, "DEX": 50.0, "crit_rate": 0.50}
        )
        
        # Budgets for level 1 T3:
        # primary = (10 + 2.5) * 0.75 = 9.375
        # sub = (1 * 0.25) * 1.5 = 0.375
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        
        # Primary stats should be scaled down to primary budget (9.375 -> around 9 total)
        total_primary = clamped.bonuses.get("STR", 0) + clamped.bonuses.get("DEX", 0)
        self.assertLessEqual(total_primary, 11)
        self.assertGreater(total_primary, 0)
        
        self.assertLessEqual(clamped.bonuses.get("crit_rate", 0), 0.02)

    def test_validate_and_clamp_filters_unauthorized_bonuses(self):
        # Create equipment with valid and invalid bonuses
        eq = Equipment(
            name="測試戒指", slot_type="trinket_1", tier="T3", item_level=10,
            bonuses={
                "STR": 10.0,            # Valid primary
                "crit_rate": 0.05,      # Valid sub
                "unauthorized_stat": 5.0 # Unauthorized, should be removed
            }
        )
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        self.assertIn("STR", clamped.bonuses)
        self.assertIn("crit_rate", clamped.bonuses)
        self.assertNotIn("unauthorized_stat", clamped.bonuses)
