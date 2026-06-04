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
        # Tier T5: min divisor = 12.0
        # If original divisor is 10.0, it should be clamped to 12.0
        skill = Skill(
            name="火球", description="召喚小火球", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=10.0)
            )
        )
        clamped = SkillProcessor.validate_and_clamp_skill(skill)
        self.assertEqual(clamped.mechanics.formula.divisor, 12.0)

    def test_validate_and_clamp_skill_aoe_tax(self):
        # Tier T4: min divisor = 10.0
        # If target_type is aoe, it gets 1.5x tax -> min divisor becomes 15.0
        skill = Skill(
            name="烈焰雨", description="火焰降臨", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="aoe", cost={"MP": 15},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=12.0)
            )
        )
        clamped = SkillProcessor.validate_and_clamp_skill(skill)
        self.assertEqual(clamped.mechanics.formula.divisor, 15.0)

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
