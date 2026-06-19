import unittest
from unittest.mock import MagicMock, patch
import random

from core.combat import CombatManager
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character
from core.skill_processor import SkillProcessor
from core.combat_utils import add_entity_status_effect, get_entity_id, has_status, get_status_effect, remove_status
from core.skill_generator import _enforce_tier_constraints, _enforce_divisor_floor

class TestTierDifferentiation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Setup standard caster and target
        self.caster_schema = CharacterSchema(
            character_id="caster_777",
            name="Caster Hero",
            background="Hero",
            primary_stats=PrimaryAttributes(STR=30, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100, temp_hp=0),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.caster = MagicMock(spec=Character)
        self.caster.data = self.caster_schema
        self.caster.total_stats = {"STR": 30, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
        self.caster.max_hp = 100
        self.caster.max_mp = 50
        self.caster.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 1.0, "skill_power": 1.0
        }
        self.caster.save = MagicMock()
        def mock_update_vitality(hp=None, mp=None, sanity=None, stamina=None, temp_hp=None):
            v = self.caster_schema.vitality
            if hp is not None:
                val = int(hp)
                if val <= 0 and has_status(self.caster, "Phoenix_Rebirth"):
                    remove_status(self.caster, "Phoenix_Rebirth")
                    v.hp = int(self.caster.max_hp * 0.5)
                    v.mp = int(self.caster.max_mp * 0.5)
                else:
                    v.hp = max(0, min(val, self.caster.max_hp))
            if mp is not None:
                v.mp = max(0, min(int(mp), self.caster.max_mp))
            if sanity is not None:
                v.sanity = max(0, min(int(sanity), self.caster.max_sanity))
            if stamina is not None:
                v.stamina = max(0, min(int(stamina), self.caster.max_stamina))
            if temp_hp is not None:
                v.temp_hp = max(0, int(temp_hp))
        self.caster.update_vitality = MagicMock(side_effect=mock_update_vitality)

        self.monsters = [
            {
                "id": "monster_888",
                "name": "Monster A",
                "hp": 200,
                "max_hp": 200,
                "defense": 10,
                "m_defense": 10,
                "crit_rate": 0.0,
                "evasion_rate": 0.0,
                "accuracy": 1.0,
                "status_effects": [],
                "speed": 10
            }
        ]

    async def test_focus_guarantees_crit(self):
        """Focus guarantees crit, and is consumed after the attack."""
        skill = Skill(
            name="Test Focus Damage",
            description="Damage with focus",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0),
                actions=[]
            )
        )
        # Apply Focus to caster
        add_entity_status_effect(self.caster, "Focus", "Next hit crit", 1)
        self.assertTrue(has_status(self.caster, "Focus"))

        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill, self.caster, self.monsters[0])
            self.assertTrue(res["success"])
            # base = 30 * (10 / 10) = 30. Crit increases to 45. Defense reduces 10 = 35 damage.
            self.assertEqual(res["final_value"], 35.0)
            self.assertFalse(has_status(self.caster, "Focus"))

    async def test_siphon_stat_transfer(self):
        """Siphon transfers target's stat to caster for duration."""
        skill = Skill(
            name="Test Siphon",
            description="Siphons target STR",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0),
                actions=[{
                    "action_type": "call_special_mechanic",
                    "keyword_name": "Siphon",
                    "target": "target",
                    "stat": "STR",
                    "steal_percent": 0.20,
                    "duration": 3
                }]
            )
        )
        # Target starts with 10 STR (monsters default attack 10 = 10 STR)
        target = self.monsters[0]
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill, self.caster, target)
            self.assertTrue(res["success"])
            # Stolen amount = 10 * 0.20 = 2.
            # Caster gains 2 STR. Target loses 2 STR.
            self.assertTrue(has_status(target, "Siphon_Debuff"))
            self.assertTrue(has_status(self.caster, "Siphon_Buff"))

    async def test_bleed_halves_healing_and_lifesteal(self):
        """Bleed halves healing on target and halves lifesteal on caster."""
        # 1. Test healing halved
        heal_skill = Skill(
            name="Test Heal",
            description="Heal",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="heal",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0)
            )
        )
        target = self.monsters[0]
        target["hp"] = 50
        add_entity_status_effect(target, "Bleed", "Bleed Dot", 3, dot_damage_flat=10.0)
        self.assertTrue(has_status(target, "Bleed"))

        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(heal_skill, self.caster, target)
            self.assertTrue(res["success"])
            # base = 30 * 1 = 30. Halved due to Bleed = 15.
            # target HP was 50 + 15 = 65.
            self.assertEqual(target["hp"], 65)

        # 2. Test lifesteal halved
        lifesteal_skill = Skill(
            name="Test Lifesteal",
            description="Lifesteal",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0),
                actions=[{"action_type": "call_special_mechanic", "keyword_name": "Lifesteal", "target": "caster"}]
            )
        )
        self.caster_schema.vitality.hp = 50
        add_entity_status_effect(self.caster, "Bleed", "Bleed dot", 3, dot_damage_flat=10.0)
        
        target["defense"] = 0
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(lifesteal_skill, self.caster, target)
            self.assertTrue(res["success"])
            # base damage = 30 * 1 = 30. Lifesteal = 30 * 0.3 = 9. Halved due to Bleed = 4.
            # Caster hp = 50 + 4 = 54.
            self.assertEqual(self.caster_schema.vitality.hp, 54)

    async def test_ward_blocks_negative_effect(self):
        """Ward blocks negative status effect and is consumed, but lets positive pass."""
        # Add Ward to caster
        add_entity_status_effect(self.caster, "Ward", "Block next debuff", 3)
        self.assertTrue(has_status(self.caster, "Ward"))

        # Try to apply a negative status (Stun)
        add_entity_status_effect(self.caster, "Stun", "Stunned", 1)
        self.assertFalse(has_status(self.caster, "Stun")) # Stun blocked
        self.assertFalse(has_status(self.caster, "Ward")) # Ward consumed

        # Add Ward back and apply positive status (Bless)
        add_entity_status_effect(self.caster, "Ward", "Block next debuff", 3)
        add_entity_status_effect(self.caster, "Bless", "Blessed", 3)
        self.assertTrue(has_status(self.caster, "Bless")) # Bless allowed
        self.assertTrue(has_status(self.caster, "Ward")) # Ward not consumed

    async def test_desperation_activation(self):
        """Desperation increases damage and grants lifesteal when caster HP <= 30%."""
        skill = Skill(
            name="Desperate strike",
            description="Strike",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0)
            )
        )
        
        # Add Desperation status to caster (threshold 30%, dmg bonus 50%, lifesteal 40%)
        add_entity_status_effect(self.caster, "Desperation", "Desperate", 3, extra_data={
            "hp_threshold": 30.0,
            "dmg_bonus": 50.0,
            "lifesteal_percent": 40.0
        })

        target = self.monsters[0]
        target["defense"] = 0

        # Case A: HP is 80% (above threshold) -> no bonus
        self.caster_schema.vitality.hp = 80
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill, self.caster, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 30.0)
            self.assertEqual(self.caster_schema.vitality.hp, 80) # No lifesteal

        # Case B: HP is 20% (below threshold) -> +50% damage & 40% lifesteal
        self.caster_schema.vitality.hp = 20
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill, self.caster, target)
            self.assertTrue(res["success"])
            # base = 30 * 1.5 = 45.0 damage.
            self.assertEqual(res["final_value"], 45.0)
            # Lifesteal = 45 * 0.40 = 18.
            # Caster HP goes from 20 to 38.
            self.assertEqual(self.caster_schema.vitality.hp, 38)

    async def test_phoenix_rebirth_on_death(self):
        """Phoenix Rebirth revives caster/monster on fatal damage to 50% HP/MP."""
        add_entity_status_effect(self.caster, "Phoenix_Rebirth", "Revive", 3)
        self.caster_schema.vitality.hp = 10
        self.caster_schema.vitality.mp = 5

        # Kill character (hp <= 0)
        self.caster.update_vitality(hp=0)
        # Should trigger Rebirth
        self.assertEqual(self.caster_schema.vitality.hp, 50)
        self.assertEqual(self.caster_schema.vitality.mp, 25)
        self.assertFalse(has_status(self.caster, "Phoenix_Rebirth"))

    async def test_fate_swap_hp_percentage(self):
        """Fate Swap swaps HP percentages of caster and target."""
        skill = Skill(
            name="Fate Swap Skill",
            description="Swap hp",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=10.0),
                actions=[{"action_type": "call_special_mechanic", "keyword_name": "Fate_Swap", "target": "target"}]
            )
        )
        target = self.monsters[0]
        # Caster at 20% HP (20/100)
        self.caster_schema.vitality.hp = 20
        # Target at 80% HP (160/200)
        target["hp"] = 160

        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill, self.caster, target)
            self.assertTrue(res["success"])
            # After swap:
            # Caster should be at 80% HP -> 80 HP
            # Target should be at 20% HP -> 40 HP
            self.assertEqual(self.caster_schema.vitality.hp, 80)
            self.assertEqual(target["hp"], 40)

    async def test_tier_constraints_enforcement(self):
        """Test that tier generation rules are strictly enforced."""
        # 1. T5 constraints
        s_data = {
            "template_choices": [{"template_id": "active_stun"}],
            "targeting_modifier": "chain",
            "synergy_requirement": "requires_burn",
            "execution_mode": "delayed",
            "formula": {"divisor": 5.0},
            "target_type": "single"
        }
        res_t5 = _enforce_tier_constraints(s_data, "T5")
        res_t5 = _enforce_divisor_floor(res_t5, "T5")
        self.assertEqual(res_t5["template_choices"], [])
        self.assertIsNone(res_t5["targeting_modifier"])
        self.assertIsNone(res_t5["synergy_requirement"])
        self.assertEqual(res_t5["execution_mode"], "immediate")
        self.assertEqual(res_t5["formula"]["divisor"], 15.0)

        # 2. T3 constraints (max 2 templates, max 1 modifier, divisor 10.0)
        s_data_t3 = {
            "template_choices": [{"template_id": "active_stun"}, {"template_id": "active_silence"}, {"template_id": "active_root"}],
            "targeting_modifier": "chain",
            "synergy_requirement": "requires_burn",
            "execution_mode": "stance_switch",
            "formula": {"divisor": 5.0},
            "target_type": "single"
        }
        res_t3 = _enforce_tier_constraints(s_data_t3, "T3")
        res_t3 = _enforce_divisor_floor(res_t3, "T3")
        self.assertEqual(len(res_t3["template_choices"]), 2)
        # Modifiers reduced to 1 (only targeting_modifier kept)
        self.assertIsNone(res_t3["synergy_requirement"])
        self.assertEqual(res_t3["execution_mode"], "immediate") # stance_switch not allowed in T3
        self.assertEqual(res_t3["formula"]["divisor"], 10.0)

    def test_tier_constraints_target_types(self):
        """Test target type restrictions and action compatibility enforcement."""
        # 1. T5 AOE target type must be forced to single
        t5_aoe = {
            "target_type": "aoe",
            "action_type": "damage",
            "targeting_modifier": None
        }
        res = _enforce_tier_constraints(t5_aoe, "T5")
        self.assertEqual(res["target_type"], "single")

        # 2. Damage targeting allies must be corrected to AOE (hostile targets enemies)
        dmg_allies = {
            "target_type": "allies",
            "action_type": "damage",
            "targeting_modifier": None
        }
        res = _enforce_tier_constraints(dmg_allies, "T3")
        self.assertEqual(res["target_type"], "aoe")

        # 3. Heal targeting AOE must be corrected to allies (friendly targets allies)
        heal_aoe = {
            "target_type": "aoe",
            "action_type": "heal",
            "targeting_modifier": None
        }
        res = _enforce_tier_constraints(heal_aoe, "T3")
        self.assertEqual(res["target_type"], "allies")

        # 4. Invalid targeting modifier must be set to None
        invalid_mod = {
            "target_type": "single",
            "action_type": "damage",
            "targeting_modifier": "aoe"
        }
        res = _enforce_tier_constraints(invalid_mod, "T3")
        self.assertIsNone(res["targeting_modifier"])

        # 5. Valid targeting modifier "chain" must be preserved
        valid_mod = {
            "target_type": "single",
            "action_type": "damage",
            "targeting_modifier": "chain"
        }
        res = _enforce_tier_constraints(valid_mod, "T3")
        self.assertEqual(res["targeting_modifier"], "chain")

if __name__ == "__main__":
    unittest.main()
