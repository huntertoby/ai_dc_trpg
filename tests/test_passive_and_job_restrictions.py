import unittest
from unittest.mock import MagicMock, patch
from core.models import CharacterSchema, Equipment, PrimaryAttributes, Vitality, ActiveSkill, PassiveSkill, SkillMechanics, SkillFormula
from core.character import Character
from core.skill_processor import SkillProcessor, SkillExecutionPipeline
from core.trigger_engine import TriggerEngine

class TestPassiveAndJobRestrictions(unittest.TestCase):
    def setUp(self):
        # Create a mock character
        self.char_data = CharacterSchema(
            character_id="test_char_123",
            name="測試勇者",
            background="冒險起步",
            primary_stats=PrimaryAttributes(STR=10, DEX=12, CON=10, INT=8, WIS=8, CHA=8),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            base_jobs=["巫師", "術士"]
        )
        self.char = Character(self.char_data, "test_char_123")

    def test_equipment_job_restriction_mismatch_fails(self):
        # Equipment requires Warrior/Knight, character is Wizard/Warlock
        eq = Equipment(
            name="巨人之劍", slot_type="main_hand", tier="T4", item_level=5,
            allowed_jobs=["戰士", "騎士"], bonuses={"STR": 5}
        )
        self.char.data.inventory.append(eq)
        with self.assertRaises(ValueError) as ctx:
            self.char.equip_item("巨人之劍")
        self.assertIn("裝備限制", str(ctx.exception))

    def test_equipment_job_restriction_match_succeeds(self):
        # Equipment requires Wizard/Elementalist, character is Wizard/Warlock
        eq = Equipment(
            name="魔力法杖", slot_type="main_hand", tier="T4", item_level=5,
            allowed_jobs=["巫師", "元素使"], bonuses={"INT": 5}
        )
        self.char.data.inventory.append(eq)
        # Should succeed without raising error
        self.char.equip_item("魔力法杖")
        self.assertEqual(self.char.data.equipment_slots.main_hand.name, "魔力法杖")

    def test_equipment_job_restriction_empty_succeeds(self):
        # Equipment has no job restrictions
        eq = Equipment(
            name="生鏽鐵劍", slot_type="main_hand", tier="T5", item_level=1,
            allowed_jobs=[], bonuses={"STR": 1}
        )
        self.char.data.inventory.append(eq)
        # Should succeed
        self.char.equip_item("生鏽鐵劍")
        self.assertEqual(self.char.data.equipment_slots.main_hand.name, "生鏽鐵劍")

    def test_skill_job_restriction_mismatch_fails(self):
        # Skill requires Warrior, character is Wizard/Warlock
        skill = ActiveSkill(
            name="旋風斬", description="旋風斬擊", tier="T4",
            allowed_jobs=["戰士"],
            mechanics=SkillMechanics(
                action_type="damage", target_type="aoe",
                formula=SkillFormula(base_stat="STR", dice="1d10", divisor=15.0),
                cost={}
            )
        )
        # Execute skill should fail
        with self.assertRaises(ValueError) as ctx:
            SkillExecutionPipeline.execute(skill, self.char, self.char)
        self.assertIn("技能限制", str(ctx.exception))

    def test_skill_job_restriction_match_succeeds(self):
        # Skill requires Wizard, character is Wizard/Warlock
        skill = ActiveSkill(
            name="奧術飛彈", description="發射飛彈", tier="T4",
            allowed_jobs=["巫師"],
            mechanics=SkillMechanics(
                action_type="damage", target_type="single",
                formula=SkillFormula(base_stat="INT", dice="1d10", divisor=15.0),
                cost={}
            )
        )
        # Mock SkillExecutionPipeline to bypass actual execution results and check just allowed jobs check
        # Execute skill should not fail with job restrictions (it might fail with other combat logic, but not Job limit)
        # Since it has no cost, it should execute successfully
        with patch("random.random", return_value=0.0):
            res = SkillExecutionPipeline.execute(skill, self.char, self.char)
        self.assertTrue(res.get("success", True))

    def test_passive_skill_bonuses(self):
        # Base STR is 10
        self.assertEqual(self.char.total_stats["STR"], 10)
        
        # Add a passive skill giving +5 STR and +0.02 crit_rate
        passive = PassiveSkill(
            name="力量增幅", description="被動提升力量", tier="T5",
            bonuses={"STR": 5.0, "crit_rate": 0.02}
        )
        self.char.data.abilities.append(passive)
        
        # Verify STR increased to 15
        self.assertEqual(self.char.total_stats["STR"], 15)
        # Verify combat stats crit rate is increased (base DEX=12, main_off = max(12, 8, 8) = 12)
        # raw_crit = 12 * 0.005 + crit_rate_bonus(0.02) = 0.06 + 0.02 = 0.08
        # crit_rate = min(0.99, 0.05 + 0.94 * (raw_crit / (raw_crit + 0.35)))
        # For raw_crit = 0.08: 0.05 + 0.94 * (0.08 / 0.43) = 0.05 + 0.1748 = 0.2248
        self.assertGreater(self.char.combat_stats["crit_rate"], 0.20)

    def test_passive_skill_triggers_collected(self):
        # Create a passive skill with an executable trigger
        passive = PassiveSkill(
            name="絕處逢生", description="受擊時概率獲得護盾", tier="T4",
            executable_triggers=[{
                "event": "on_damaged",
                "chance": 1.0,
                "actions": [{"action_type": "gain_shield", "flat_value": 15}]
            }]
        )
        self.char.data.abilities.append(passive)
        
        # Check if TriggerEngine collects it
        triggers = TriggerEngine.get_active_triggers(self.char)
        # Should contain the trigger from the passive skill
        self.assertTrue(any(t.get("_owner_skill") is passive for t in triggers))
