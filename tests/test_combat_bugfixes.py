import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import Skill, SkillMechanics, SkillFormula, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, StatusEffect
from core.skill_processor import SkillProcessor

class TestCombatBugfixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.mock_char = MagicMock()
        self.mock_char.data = CharacterSchema(
            character_id="test_char_123",
            name="卡爾",
            background="孤兒",
            primary_stats=PrimaryAttributes(STR=10, DEX=12, CON=10, INT=15, WIS=15, CHA=8),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.mock_char.total_stats = {"STR": 10, "DEX": 12, "CON": 10, "INT": 15, "WIS": 15, "CHA": 8}
        self.mock_char.max_hp = 100
        self.mock_char.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 1.0, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        self.monsters = [
            {
                "name": "野狼 A",
                "base_name": "野狼",
                "level": 1,
                "hp": 100,
                "max_hp": 100,
                "attack": 8,
                "defense": 5,
                "m_defense": 5,
                "speed": 8,
                "source_id": "common_species",
                "status_effects": []
            },
            {
                "name": "野狼 B",
                "base_name": "野狼",
                "level": 1,
                "hp": 100,
                "max_hp": 100,
                "attack": 8,
                "defense": 5,
                "m_defense": 5,
                "speed": 6,
                "source_id": "common_species",
                "status_effects": []
            }
        ]

    @patch("random.randint", return_value=10)
    @patch("random.random", return_value=0.5)
    async def test_status_tick_logs_prepending(self, mock_random, mock_randint):
        cm = CombatManager(self.mock_char, self.monsters)
        # Apply Burn status to player
        self.mock_char.data.status_effects.append(StatusEffect(name="Burn", description="灼燒", duration=3, dot_damage_flat=10.0))
        
        # Advance turn which should tick the player's status
        cm.turn_order = [
            {"type": "player", "speed": 10, "ref": self.mock_char},
            {"type": "monster", "speed": 5, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = False
        
        # Trigger player attack
        res = await cm.player_attack(0)
        self.assertTrue(res["success"])
        # Message should contain the Burn DoT log message prepended
        self.assertIn("🔥", res["msg"])
        self.assertIn("受到灼燒 DoT", res["msg"])

    def test_copy_skill_no_mutation(self):
        # 1. Cast a standard skill with Burn
        skill_burn = Skill(
            name="火焰球", description="火焰傷害", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="10", divisor=2.0),
                keywords=["Burn"]
            )
        )
        SkillProcessor.execute_skill(skill_burn, self.mock_char, self.monsters[0])
        
        # 2. Cast Copy skill
        skill_copy = Skill(
            name="鏡像術", description="複製技能", tier="T3",
            mechanics=SkillMechanics(
                action_type="buff", target_type="self", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1", divisor=1.0),
                keywords=["Copy"]
            )
        )
        res = SkillProcessor.execute_skill(skill_copy, self.mock_char, self.monsters[0])
        
        # The copy should have executed with copied keywords (Burn)
        self.assertIn("Burn", res["keywords"])
        # The original skill_copy passed in MUST NOT have been mutated in-place
        self.assertEqual(skill_copy.mechanics.formula.base_stat, "WIS")
        self.assertEqual(skill_copy.mechanics.keywords, ["Copy"])

    @patch("random.randint", return_value=4)  # Multi-hit triggers 4 hits
    @patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10)
    def test_multihit_logic(self, mock_roll, mock_randint):
        skill_multi = Skill(
            name="多重影斬", description="多重打擊", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=5.0),
                keywords=["Multi-hit"]
            )
        )
        # Base value = STR (10) * (10 / 5.0) = 20.
        # target defense is 5. Max mitigation 80% is 16. Effective defense = 5.
        # final damage = 20 - 5 = 15.
        # Split into 4 hits: 15 / 4 = 3.75 -> rounded to 3.8 per hit.
        
        # Target has 10 shield (temp_hp)
        self.monsters[0]["temp_hp"] = 10
        self.monsters[0]["hp"] = 100
        
        res = SkillProcessor.execute_skill(skill_multi, self.mock_char, self.monsters[0])
        self.assertTrue(res["success"])
        # Log should contain each of the 4 hits
        self.assertTrue(any("[第 1 擊] 護盾 (temp_hp) 抵擋了 3 點傷害" in l for l in res["logs"]))
        self.assertTrue(any("[第 4 擊] 護盾 (temp_hp) 被擊破" in l for l in res["logs"]))
        self.assertTrue(any("[第 4 擊] 對 野狼 A 造成了 2 點傷害" in l for l in res["logs"]))
        self.assertLess(self.monsters[0]["hp"], 100)

    async def test_chain_damage_pipeline(self):
        cm = CombatManager(self.mock_char, self.monsters)
        # Give monster B a shield of 50
        self.monsters[1]["temp_hp"] = 50
        self.monsters[1]["hp"] = 100
        
        skill_chain = Skill(
            name="閃電連鎖", description="連鎖攻擊", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="10", divisor=5.0),
                keywords=["Chain"]
            )
        )
        # Base damage = 30. Chained damage = 30 * 0.5 = 15.
        # Target 0 takes 30 - 5 = 25 final_value.
        # Chained damage = round(25 * 0.5, 1) = 12.5 -> int is 12.
        # Target 1 (wild wolf B) shield becomes 50 - 12 = 38.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = await cm.cast_skill(skill_chain, 0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[1]["hp"], 100)
            self.assertEqual(self.monsters[1]["temp_hp"], 38)

    def test_stamina_cost_checking(self):
        # Skill costs 50 stamina
        skill_stamina = Skill(
            name="重擊", description="消耗耐力", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"STAMINA": 50},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="5", divisor=10.0)
            )
        )
        # Set caster stamina to 10
        self.mock_char.data.vitality.stamina = 10
        
        with self.assertRaises(ValueError) as ctx:
            SkillProcessor.execute_skill(skill_stamina, self.mock_char, self.monsters[0])
        self.assertIn("精力值不足", str(ctx.exception))

    def test_banish_mechanics(self):
        # Case A: Caster is banished
        skill_dmg = Skill(
            name="火球術", description="傷害", tier="T5",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="5", divisor=10.0)
            )
        )
        self.mock_char.data.status_effects.append(StatusEffect(name="Banish", description="放逐", duration=2))
        with self.assertRaises(ValueError) as ctx:
            SkillProcessor.execute_skill(skill_dmg, self.mock_char, self.monsters[0])
        self.assertIn("自身處於放逐狀態", str(ctx.exception))
        
        # Case B: Skill applies Banish to target
        skill_banish = Skill(
            name="次元封鎖", description="放逐對手", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="5", divisor=10.0),
                keywords=["Banish"]
            )
        )
        self.mock_char.data.status_effects.clear() # remove banish from caster
        res = SkillProcessor.execute_skill(skill_banish, self.mock_char, self.monsters[0])
        self.assertTrue(res["success"])
        # Target should have Banish status applied
        self.assertTrue(any(e["name"] == "Banish" for e in self.monsters[0]["status_effects"]))
