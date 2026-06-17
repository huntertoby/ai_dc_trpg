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

    def test_validate_and_clamp_t2_clears_special_effect(self):
        """品質分層：T2 也應清除 special_effect"""
        eq = Equipment(
            name="史詩劍", slot_type="main_hand", tier="T2", item_level=15,
            special_effect="史詩效果", bonuses={"STR": 20.0},
            executable_triggers=[{"event": "on_hit", "actions": []}]
        )
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        # T2 不保留 special_effect（只有 T1 保留）
        self.assertEqual(clamped.special_effect, "")

    def test_validate_and_clamp_t3_clears_special_effect(self):
        """品質分層：T3 也應清除 special_effect"""
        eq = Equipment(
            name="稀有盔甲", slot_type="chest", tier="T3", item_level=12,
            special_effect="稀有效果", bonuses={"CON": 15.0},
            executable_triggers=[{"event": "on_damaged", "actions": []}]
        )
        clamped = EquipmentBalancer.validate_and_clamp(eq)
        # T3 不保留 special_effect
        self.assertEqual(clamped.special_effect, "")

    def test_validate_and_clamp_trigger_count_limits(self):
        """品質分層：觸發器數量限制"""
        # T1: 最多 2 個
        t1_eq = Equipment(
            name="傳說武器", slot_type="main_hand", tier="T1", item_level=20,
            executable_triggers=[
                {"event": "on_hit", "actions": []},
                {"event": "on_damaged", "actions": []},
                {"event": "on_turn_start", "actions": []}  # 第 3 個會被截斷
            ]
        )
        t1_clamped = EquipmentBalancer.validate_and_clamp(t1_eq)
        self.assertEqual(len(t1_clamped.executable_triggers), 2)

        # T2: 最多 1 個
        t2_eq = Equipment(
            name="史詩防具", slot_type="chest", tier="T2", item_level=15,
            executable_triggers=[
                {"event": "on_hit", "actions": []},
                {"event": "on_damaged", "actions": []}  # 第 2 個會被刪除
            ]
        )
        t2_clamped = EquipmentBalancer.validate_and_clamp(t2_eq)
        self.assertEqual(len(t2_clamped.executable_triggers), 1)

        # T3: 最多 1 個
        t3_eq = Equipment(
            name="稀有項鍊", slot_type="trinket_1", tier="T3", item_level=10,
            executable_triggers=[
                {"event": "on_turn_start", "actions": []},
                {"event": "on_turn_end", "actions": []}  # 第 2 個會被刪除
            ]
        )
        t3_clamped = EquipmentBalancer.validate_and_clamp(t3_eq)
        self.assertEqual(len(t3_clamped.executable_triggers), 1)

    def test_validate_and_clamp_adds_base_armor_defenses(self):
        """驗證防具部位會自動獲得對應等級與品質的基礎雙防"""
        # 1. T5 胸甲 (lv.10)
        chest = Equipment(
            name="粗糙皮甲", slot_type="chest", tier="T5", item_level=10,
            bonuses={}
        )
        clamped_chest = EquipmentBalancer.validate_and_clamp(chest)
        # p_def: (8.0 + 10 * 1.6) * 1.0 = 24.0
        # m_def: (4.0 + 10 * 0.8) * 1.0 = 12.0
        self.assertEqual(clamped_chest.bonuses.get("p_def"), 24.0)
        self.assertEqual(clamped_chest.bonuses.get("m_def"), 12.0)

        # 2. T1 頭盔 (lv.5)
        helm = Equipment(
            name="傳說聖冠", slot_type="head", tier="T1", item_level=5,
            bonuses={}
        )
        clamped_helm = EquipmentBalancer.validate_and_clamp(helm)
        # p_def: (3.0 + 5 * 0.6) * 2.2 = 13.2
        # m_def: (1.5 + 5 * 0.3) * 2.2 = 6.6
        self.assertEqual(clamped_helm.bonuses.get("p_def"), 13.2)
        self.assertEqual(clamped_helm.bonuses.get("m_def"), 6.6)

