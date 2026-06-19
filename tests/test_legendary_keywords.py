import unittest
from unittest.mock import MagicMock, patch
import random

from core.combat import CombatManager, find_entity_by_id
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character
from core.skill_processor import SkillProcessor
from core.combat_utils import add_entity_status_effect, get_entity_id

class TestLegendaryKeywords(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Setup standard caster and target for keyword validation
        self.caster_schema = CharacterSchema(
            character_id="caster_123",
            name="Caster",
            background="Isolated",
            primary_stats=PrimaryAttributes(STR=50, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100, temp_hp=0),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.mock_char = MagicMock(spec=Character)
        self.mock_char.data = self.caster_schema
        self.mock_char.total_stats = {"STR": 50, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
        self.mock_char.max_hp = 100
        self.mock_char.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 1.0, "skill_power": 1.0
        }
        self.mock_char.save = MagicMock()
        self.mock_char.update_vitality = MagicMock(side_effect=lambda hp=None, mp=None, sanity=None, stamina=None, temp_hp=None: None)

        self.monsters = [
            {
                "id": "monster_456",
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
            },
            {
                "id": "monster_789",
                "name": "Monster B",
                "hp": 100,
                "max_hp": 100,
                "defense": 0,
                "m_defense": 0,
                "crit_rate": 0.0,
                "evasion_rate": 0.0,
                "accuracy": 1.0,
                "status_effects": [],
                "speed": 10
            }
        ]

    def _get_status_name(self, status):
        return status.name if hasattr(status, "name") else status.get("name")

    def _get_status_extra_data(self, status):
        return status.extra_data if hasattr(status, "extra_data") else status.get("extra_data", {})

    async def test_keyword_annihilate(self):
        """1. Annihilate: target's temp_hp becomes 0 and 80% maximum defense mitigation limit is bypassed."""
        skill = Skill(
            name="Annihilate Skill",
            description="Bypasses defense cap",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Annihilate"
            )
        )
        
        target = self.monsters[0]
        target["temp_hp"] = 50
        target["defense"] = 45  # High defense relative to base damage 50
        
        # Base val = 50. Without Annihilate, max mitigation caps at 80% of 50 = 40. Effective def = 40. Damage = 10.
        # With Annihilate, temp_hp -> 0, and effective def = 45. Damage = 50 - 45 = 5.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 5.0)
            self.assertEqual(target["temp_hp"], 0)

    async def test_keyword_soul_drain(self):
        """2. Soul_Drain: absorb 20% of damage as MP, transfer to caster HP. If target MP reaches 0, apply Soul_Exhaustion."""
        skill = Skill(
            name="Soul Drain Skill",
            description="Drain MP to HP",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Soul_Drain"
            )
        )
        
        self.mock_char.data.vitality.hp = 50  # Needs healing
        target = self.monsters[0]
        target["defense"] = 0
        target["mp"] = 8  # Low MP
        
        # Base damage = 50. Target def = 0. Final value = 50.
        # 20% of 50 = 10 MP drain. Since target only has 8, actual drain = 8.
        # Target MP becomes 0, triggering Soul_Exhaustion. Caster HP goes from 50 to 58.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(target["mp"], 0)
            self.assertEqual(self.mock_char.data.vitality.hp, 58)
            
            # Check Soul_Exhaustion status
            has_se = any(self._get_status_name(s) == "Soul_Exhaustion" for s in target["status_effects"])
            self.assertTrue(has_se)

    async def test_soul_exhaustion_effect(self):
        """Verify that Soul_Exhaustion doubles skill MP, SAN, and Stamina costs."""
        skill = Skill(
            name="Exhaust Test Skill",
            description="Test skill cost",
            tier="T2",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10, "SAN": 5, "STAMINA": 15},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[]
            )
        )
        # Apply Soul_Exhaustion to caster
        self.mock_char.data.status_effects.append(StatusEffect(name="Soul_Exhaustion", duration=1))
        
        # Cast should succeed but deduct double cost
        # Required: MP 20, SAN 10, STAMINA 30.
        # Caster currently has MP 50, SAN 100, STAMINA 100.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, self.monsters[0])
            self.assertTrue(res["success"])
            self.assertEqual(self.mock_char.data.vitality.mp, 30)       # 50 - (10 * 2) = 30
            self.assertEqual(self.mock_char.data.vitality.sanity, 90)   # 100 - (5 * 2) = 90
            self.assertEqual(self.mock_char.data.vitality.stamina, 70)  # 100 - (15 * 2) = 70

    async def test_keyword_doom_seal_and_purge(self):
        """3. Doom_Seal: apply unpurgeable Doom_Seal. Expire triggers instant death."""
        skill = Skill(
            name="Doom Seal Skill",
            description="Unpurgeable doom",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Doom_Seal"
            )
        )
        
        target = self.monsters[0]
        target["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            
            # Check Doom_Seal applied
            ds_status = next(s for s in target["status_effects"] if self._get_status_name(s) == "Doom_Seal")
            self.assertEqual(ds_status["duration"], 2)
            self.assertIn("no_purge", ds_status["tags"])

            # Add standard Doom for comparison (should be purgeable)
            target["status_effects"].append({
                "name": "Doom",
                "description": "Standard doom",
                "duration": 3,
                "tags": []
            })
            
            # Test Purge
            purge_skill = Skill(
                name="Purge Skill",
                description="Cleanses debuffs",
                tier="T3",
                mechanics=SkillMechanics(
                    action_type="buff",
                    target_type="single",
                    cost={"MP": 5},
                    formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                    keywords=["Purge"]
                )
            )
            
            res_purge = SkillProcessor.execute_skill(purge_skill, self.mock_char, target)
            self.assertTrue(res_purge["success"])
            
            # Doom should be gone, Doom_Seal should remain
            names = [self._get_status_name(s) for s in target["status_effects"]]
            self.assertNotIn("Doom", names)
            self.assertIn("Doom_Seal", names)

            # Test Doom_Seal combat-level instant death tick when duration == 1
            cm = CombatManager(self.mock_char, self.monsters)
            # Find Doom_Seal status in target status effects list
            ds_status = next(s for s in target["status_effects"] if self._get_status_name(s) == "Doom_Seal")
            ds_status["duration"] = 1
            
            # Setup turn context
            cm.turn_order = [{"type": "monster", "speed": 10, "ref": target, "index": 0}]
            cm.current_turn_idx = 0
            
            cm._process_entity_status_tick(target, is_player=False)
            
            # Target HP should become 0
            self.assertEqual(target["hp"], 0)

    async def test_keyword_blood_pact(self):
        """4. Blood_Pact: deduct 20% caster HP, increase damage based on missing HP ratio."""
        skill = Skill(
            name="Blood Pact Skill",
            description="Sacrifice HP for damage boost",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Blood_Pact"
            )
        )
        
        # HP=100. Cost = 20. Remaining = 80. Missing ratio = 20% = 0.2.
        # Multiplier = 1.0 + 0.2 * 1.5 = 1.3x.
        # Base damage = 50. Target def = 0. Final value = 50 * 1.3 = 65.
        target = self.monsters[0]
        target["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(self.mock_char.data.vitality.hp, 80)
            self.assertEqual(res["final_value"], 65.0)

    async def test_keyword_epoch_break(self):
        """5. Epoch_Break: strip target's buff status effects and reset temp_hp."""
        skill = Skill(
            name="Epoch Break Skill",
            description="Clear target buffs",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Epoch_Break"
            )
        )
        
        target = self.monsters[0]
        target["temp_hp"] = 100
        target["defense"] = 0
        target["status_effects"] = [
            StatusEffect(name="Bless", duration=3),
            StatusEffect(name="Shield", duration=3),
            StatusEffect(name="Immune", duration=3),
            StatusEffect(name="Reflect", duration=3),
            StatusEffect(name="Invis", duration=3),
            StatusEffect(name="Burn", duration=3)  # Debuff, shouldn't be stripped
        ]
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(target["temp_hp"], 0)
            names = [self._get_status_name(s) for s in target["status_effects"]]
            self.assertNotIn("Bless", names)
            self.assertNotIn("Shield", names)
            self.assertNotIn("Immune", names)
            self.assertNotIn("Reflect", names)
            self.assertNotIn("Invis", names)
            self.assertIn("Burn", names)

    async def test_keyword_void_rift_recoil(self):
        """6. Void_Rift: target damage recoil on caster."""
        skill = Skill(
            name="Void Rift Skill",
            description="Apply recoil connection",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Void_Rift"
            )
        )
        
        cm = CombatManager(self.mock_char, self.monsters)
        target = self.monsters[0]
        target["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target, cm)
            self.assertTrue(res["success"])
            
            # Verify Void_Rift status applied with caster's ID
            vr_status = next(s for s in target["status_effects"] if self._get_status_name(s) == "Void_Rift")
            extra_data = self._get_status_extra_data(vr_status)
            self.assertEqual(extra_data.get("rift_caster_id"), get_entity_id(self.mock_char))
            
            # Deal 100 damage to target. Recoil should be 25. Caster HP 100 -> 75.
            applied_dmg, logs = cm._apply_damage(target, is_target_player=False, damage=100, source_entity=self.mock_char, is_source_player=True)
            self.assertEqual(applied_dmg, 100)
            self.assertEqual(self.mock_char.data.vitality.hp, 75)

    async def test_keyword_last_rites(self):
        """7. Last_Rites: 2x damage if target HP >= 50%. Else, spread Doom to all other enemies."""
        skill = Skill(
            name="Last Rites Skill",
            description="Execute/spread doom",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Last_Rites"
            )
        )
        
        # Target HP >= 50%
        target_a = self.monsters[0]
        target_a["hp"] = 150
        target_a["max_hp"] = 200
        target_a["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target_a)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 100.0)  # Base 50 * 2 = 100
            self.assertFalse(res["control_flags"].get("last_rites_doom_spread", False))

        # Target HP < 50%
        target_a["hp"] = 50
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target_a)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 50.0)
            self.assertTrue(res["control_flags"].get("last_rites_doom_spread"))
            
        # Verify combat spread
        cm = CombatManager(self.mock_char, self.monsters)
        cm.turn_order = [{"type": "player", "speed": 15, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        
        # Reset monsters
        self.monsters[0]["hp"] = 50
        self.monsters[1]["hp"] = 100
        self.monsters[1]["status_effects"] = []
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res_cast = await cm._cast_skill_raw(skill, target_idx=0)
            self.assertTrue(res_cast["success"])
            
            # Monster B should receive Doom status
            has_doom = any(self._get_status_name(s) == "Doom" for s in self.monsters[1]["status_effects"])
            self.assertTrue(has_doom)

    async def test_keyword_paradox(self):
        """8. Paradox: target defense is added to damage as flat bonus."""
        skill = Skill(
            name="Paradox Skill",
            description="Reverse defense",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Paradox"
            )
        )
        
        target = self.monsters[0]
        target["defense"] = 30
        
        # Base val = 50. Effective def = min(30, 40) = 30.
        # Val after def = 50 - 30 = 20.
        # Paradox bonus adds 30. Final damage = 20 + 30 = 50.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 50.0)

    async def test_keyword_eternal_wound(self):
        """9. Eternal_Wound: blocks target heals and lifesteal."""
        skill = Skill(
            name="Eternal Wound Skill",
            description="Inflicts eternal wound",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Eternal_Wound"
            )
        )
        
        target = self.monsters[0]
        target["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertTrue(any(self._get_status_name(s) == "Eternal_Wound" for s in target["status_effects"]))
            
        # Test healing block
        heal_skill = Skill(
            name="Heal Skill",
            description="Heal",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="heal",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[]
            )
        )
        
        # Make target have Eternal_Wound status object
        target["status_effects"] = [StatusEffect(name="Eternal_Wound", duration=3)]
        target["hp"] = 50
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res_heal = SkillProcessor.execute_skill(heal_skill, self.mock_char, target)
            self.assertTrue(res_heal["success"])
            self.assertEqual(res_heal["final_value"], 0.0)
            self.assertEqual(target["hp"], 50)  # HP remains unchanged

    async def test_keyword_abyssal_mark(self):
        """10. Abyssal_Mark: target takes 40% increased damage from all sources in combat."""
        target = self.monsters[0]
        target["defense"] = 0
        target["status_effects"] = [StatusEffect(name="Abyssal_Mark", duration=2)]
        
        cm = CombatManager(self.mock_char, self.monsters)
        applied_dmg, logs = cm._apply_damage(target, is_target_player=False, damage=100, source_entity=self.mock_char, is_source_player=True)
        self.assertEqual(applied_dmg, 140)

    async def test_keyword_resonance_break(self):
        """11. Resonance_Break: damage multiplied by 1.0 + status_count * 0.15."""
        skill = Skill(
            name="Resonance Break Skill",
            description="Explode status effects",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Resonance_Break"
            )
        )
        
        target = self.monsters[0]
        target["defense"] = 0
        target["status_effects"] = [
            StatusEffect(name="A", duration=2),
            StatusEffect(name="B", duration=2),
            StatusEffect(name="C", duration=2)
        ]
        
        # Base damage = 50. 3 statuses -> 1.0 + 3 * 0.15 = 1.45x multiplier.
        # Final value = 50 * 1.45 = 72.5.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 72.5)

    async def test_keyword_soul_shatter(self):
        """12. Soul_Shatter: kills target, gives 50 SAN to caster, stuns all other alive enemies."""
        skill = Skill(
            name="Soul Shatter Skill",
            description="Shatter soul on death",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Soul_Shatter"
            )
        )
        
        self.mock_char.data.vitality.sanity = 40
        self.monsters[0]["hp"] = 10  # Low HP to trigger kill
        self.monsters[0]["defense"] = 0
        self.monsters[1]["hp"] = 100
        self.monsters[1]["status_effects"] = []
        
        cm = CombatManager(self.mock_char, self.monsters)
        cm.turn_order = [{"type": "player", "speed": 15, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = await cm._cast_skill_raw(skill, target_idx=0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 0)
            self.assertEqual(self.mock_char.data.vitality.sanity, 90)  # 40 + 50 = 90
            self.assertTrue(any(self._get_status_name(s) == "Stun" for s in self.monsters[1]["status_effects"]))

    async def test_keyword_fate_seal(self):
        """13. Fate_Seal: record target's HP, revert to it after 3 turns."""
        skill = Skill(
            name="Fate Seal Skill",
            description="Freeze HP state",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Fate_Seal"
            )
        )
        
        target = self.monsters[0]
        target["hp"] = 120
        target["defense"] = 0
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            
            # Check Fate_Seal state recording
            fs_status = next(s for s in target["status_effects"] if self._get_status_name(s) == "Fate_Seal")
            extra_data = self._get_status_extra_data(fs_status)
            self.assertEqual(extra_data.get("sealed_hp"), 70)
            
            # Heal target to full
            target["hp"] = 200
            # Set duration = 1 to trigger decay/expiry logic
            if isinstance(fs_status, dict):
                fs_status["duration"] = 1
            else:
                fs_status.duration = 1
            
            cm = CombatManager(self.mock_char, self.monsters)
            cm.turn_order = [{"type": "monster", "speed": 10, "ref": target, "index": 0}]
            cm.current_turn_idx = 0
            
            cm._process_entity_status_tick(target, is_player=False)
            
            # HP should be reverted to 70
            self.assertEqual(target["hp"], 70)

    async def test_keyword_devils_roll(self):
        """14. Devil's_Roll: rolls 1d6 for different battle outcomes."""
        skill = Skill(
            name="Devils Roll Skill",
            description="Roll of fate",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d10", divisor=1.0),
                keywords=[],
                legendary_keyword="Devil's_Roll"
            )
        )
        
        target = self.monsters[0]
        target["defense"] = 0
        
        # Case A: Roll 1 -> Fail, backlash 50% base damage
        self.mock_char.data.vitality.hp = 100
        with patch("random.randint", return_value=1), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 0.0)
            self.assertEqual(self.mock_char.data.vitality.hp, 75)  # 100 - 25 = 75
            self.assertTrue(res["control_flags"].get("devil_roll_failed"))

        # Case B: Roll 3 -> Normal damage
        self.mock_char.data.vitality.hp = 100
        with patch("random.randint", return_value=3), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 50.0)

        # Case C: Roll 5 -> 1.5x damage + random debuff
        with patch("random.randint", return_value=5), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 75.0)
            self.assertIn(res["control_flags"].get("devil_roll_debuff"), ["Stun", "Burn", "Doom"])

        # Case D: Roll 6 -> 3.0x damage + AoE flag
        with patch("random.randint", return_value=6), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=1):
            res = SkillProcessor.execute_skill(skill, self.mock_char, target)
            self.assertTrue(res["success"])
            self.assertEqual(res["final_value"], 150.0)
            self.assertTrue(res["control_flags"].get("devil_roll_aoe"))
