import unittest
from unittest.mock import MagicMock, patch
from core.skill_processor import SkillProcessor
from core.models import Skill, SkillMechanics, SkillFormula, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots

class TestSkillProcessor(unittest.TestCase):
    def test_roll_dice_simple(self):
        # 1d20 -> returns value between 1 and 20
        with patch("random.randint", return_value=12):
            val = SkillProcessor.roll_dice("1d20")
            self.assertEqual(val, 12)

    def test_roll_dice_with_modifier(self):
        # 2d6+3 -> random.randint will be called twice. Let's return 4 each time.
        with patch("random.randint", return_value=4):
            val = SkillProcessor.roll_dice("2d6+3")
            # 4 + 4 + 3 = 11
            self.assertEqual(val, 11)

        # 1d10-2 -> returns 5 - 2 = 3
        with patch("random.randint", return_value=5):
            val = SkillProcessor.roll_dice("1d10-2")
            self.assertEqual(val, 3)

    def test_roll_dice_invalid(self):
        self.assertEqual(SkillProcessor.roll_dice("invalid"), 0)

    def test_validate_and_clamp_skill_single_hand(self):
        # Tier T5: min divisor = 15.0
        # If original divisor is 10.0, it should be clamped to 15.0
        skill = Skill(
            name="火球", description="召喚小火球", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=10.0)
            )
        )
        clamped = SkillProcessor.validate_and_clamp_skill(skill)
        self.assertEqual(clamped.mechanics.formula.divisor, 15.0)

    def test_validate_and_clamp_skill_aoe_tax(self):
        # Tier T4: min divisor = 12.0
        # If target_type is aoe, it gets 1.5x tax -> min divisor becomes 18.0
        skill = Skill(
            name="烈焰雨", description="火焰降臨", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="aoe", cost={"MP": 15},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=12.0)
            )
        )
        clamped = SkillProcessor.validate_and_clamp_skill(skill)
        self.assertEqual(clamped.mechanics.formula.divisor, 18.0)

    def test_calculate_base_value_multiplier(self):
        # Stat * (Dice / Divisor)
        skill = Skill(
            name="冰箭", description="射出冰箭", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=10.0)
            )
        )
        total_stats = {"INT": 20}
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=5):
            val, dice_roll = SkillProcessor.calculate_base_value(skill, total_stats)
            # 20 * (5 / 10.0) = 10.0
            self.assertEqual(val, 10.0)
            self.assertEqual(dice_roll, 5)

    def test_execute_skill_mana_check_and_deduction(self):
        skill = Skill(
            name="治療術", description="恢復生命值", tier="T5",
            mechanics=SkillMechanics(
                action_type="heal", target_type="single", cost={"MP": 10, "SAN": 5},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1d10", divisor=10.0)
            )
        )
        
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=5, WIS=15, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        char.total_stats = {"WIS": 15}
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10), \
             patch("random.random", return_value=0.5):
            res = SkillProcessor.execute_skill(skill, char)
            self.assertEqual(res["skill_name"], "治療術")
            # 15 * (10 / 10.0) = 15.0
            self.assertEqual(res["final_value"], 15.0)
            
            # Vitality should have decreased
            self.assertEqual(char.data.vitality.mp, 10)
            self.assertEqual(char.data.vitality.sanity, 95)

    def test_execute_skill_insufficient_mana(self):
        skill = Skill(
            name="高級治療術", description="恢復生命值", tier="T5",
            mechanics=SkillMechanics(
                action_type="heal", target_type="single", cost={"MP": 30},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1d10", divisor=10.0)
            )
        )
        
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=5, WIS=15, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=10, max_mp=10, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        
        with self.assertRaises(ValueError):
            SkillProcessor.execute_skill(skill, char)

    def test_execute_skill_detailed_math_breakdown(self):
        # Test damage skill log breakdown
        skill_dmg = Skill(
            name="火球術", description="召喚大火球", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=10.0)
            )
        )
        
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=15, WIS=5, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        char.total_stats = {"INT": 15}
        
        target = MagicMock()
        target.data = CharacterSchema(
            character_id="test_target_456", name="木人樁", background="無",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=5, WIS=5, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        target.combat_stats = {"p_def": 5, "m_def": 5, "crit_rate": 0.05, "evasion_rate": 0.0, "accuracy": 0.95, "skill_power": 1.0}
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10), \
             patch("random.random", return_value=0.5):
            res = SkillProcessor.execute_skill(skill_dmg, char, target)
            self.assertTrue(res["success"])
            
            # Find the log containing the math breakdown
            breakdown_log = [l for l in res["logs"] if "🎲 **判定**:" in l]
            self.assertEqual(len(breakdown_log), 1)
            log_text = breakdown_log[0]
            self.assertIn("10 (公式: 1d20)", log_text)
            self.assertIn("(智力:15 * (10/10.0))", log_text)
            self.assertIn("有效減免: 5.0，上限 80%", log_text)

        # Test healing skill log breakdown
        skill_heal = Skill(
            name="治療術", description="恢復生命值", tier="T5",
            mechanics=SkillMechanics(
                action_type="heal", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1d20", divisor=10.0)
            )
        )
        char.total_stats = {"WIS": 15}
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10), \
             patch("random.random", return_value=0.5):
            res_heal = SkillProcessor.execute_skill(skill_heal, char, target)
            self.assertTrue(res_heal["success"])
            
            # Find the log containing the math breakdown
            breakdown_log_heal = [l for l in res_heal["logs"] if "🎲 **判定**:" in l]
            self.assertEqual(len(breakdown_log_heal), 1)
            log_text_heal = breakdown_log_heal[0]
            self.assertIn("10 (公式: 1d20)", log_text_heal)
            self.assertIn("(感知:15 * (10/10.0)) = 15.0", log_text_heal)

    def test_execute_skill_detonate(self):
        from core.models import StatusEffect
        skill_detonate = Skill(
            name="引爆擊", description="引爆目標狀態", tier="T2",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=10.0),
                actions=[
                    {"action_type": "call_special_mechanic", "keyword_name": "Detonate", "target": "target", "status_name": "Burn", "flat_value": 30.0}
                ]
            )
        )
        
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=15, WIS=5, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        char.total_stats = {"INT": 15}
        
        target = MagicMock()
        burn_effect = StatusEffect(name="Burn", duration=3, dot_damage_flat=15.0)
        target.data = CharacterSchema(
            character_id="test_target_456", name="木人樁", background="無",
            primary_stats=PrimaryAttributes(STR=5, DEX=5, CON=5, INT=5, WIS=5, CHA=5),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[burn_effect], equipment_slots=EquipmentSlots()
        )
        target.combat_stats = {"p_def": 0, "m_def": 0, "crit_rate": 0.0, "evasion_rate": 0.0, "accuracy": 1.0, "skill_power": 1.0}
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10), \
             patch("random.random", return_value=0.5):
            # Verify the target initially has Burn
            self.assertEqual(len(target.data.status_effects), 1)
            self.assertEqual(target.data.status_effects[0].name, "Burn")
            
            res = SkillProcessor.execute_skill(skill_detonate, char, target)
            self.assertTrue(res["success"])
            
            # The burn status should be consumed (removed)
            self.assertEqual(len(target.data.status_effects), 0)
            
            # Damage calculation:
            # Base damage = 15 * (10 / 10.0) = 15.0
            # Min defense is 1.0, so base dmg after def = 14.0
            # Detonate bonus = 30.0
            # Total damage = 14.0 + 30.0 = 44.0
            self.assertEqual(res["final_value"], 44.0)
            self.assertTrue(any("觸發【引爆】" in l for l in res["logs"]))
