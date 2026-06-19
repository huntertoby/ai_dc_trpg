import unittest
from unittest.mock import MagicMock, patch
import random
from core.combat import CombatManager
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula
from core.skill_processor import SkillProcessor

class TestDepthUpgrade(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up a mock Character
        self.mock_char = MagicMock()
        self.mock_char.data = CharacterSchema(
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
        self.mock_char.total_stats = {"STR": 10, "DEX": 12, "CON": 10, "INT": 8, "WIS": 8, "CHA": 8}
        self.mock_char.max_hp = 200
        self.mock_char.combat_stats = {
            "p_def": 10, "m_def": 5, "crit_rate": 0.1, "evasion_rate": 0.05,
            "accuracy": 0.9, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        self.monsters = [
            {
                "name": "前排野狼 A",
                "base_name": "野狼",
                "level": 1,
                "hp": 50,
                "max_hp": 50,
                "attack": 10,
                "defense": 5,
                "m_defense": 5,
                "speed": 8,
                "row": "front",
                "source_id": "common_species"
            },
            {
                "name": "後排祭司 B",
                "base_name": "祭司",
                "level": 1,
                "hp": 30,
                "max_hp": 30,
                "attack": 8,
                "defense": 2,
                "m_defense": 2,
                "speed": 6,
                "row": "back",
                "source_id": "common_species"
            }
        ]

    async def test_tag_set_resonance(self):
        # 裝備 3 件火屬性裝備，應自動獲得 Fire_Resonance
        head_item = Equipment(name="火焰頭盔", slot_type="head", tags=["Fire"])
        chest_item = Equipment(name="熔岩鎧甲", slot_type="chest", tags=["Fire"])
        main_hand_item = Equipment(name="赤炎劍", slot_type="main_hand", tags=["Fire"])
        
        self.mock_char.data.equipment_slots.head = head_item
        self.mock_char.data.equipment_slots.chest = chest_item
        self.mock_char.data.equipment_slots.main_hand = main_hand_item
        
        cm = CombatManager(self.mock_char, self.monsters)
        # Verify the status effect is applied
        from core.trigger_engine import has_status
        self.assertTrue(has_status(self.mock_char, "Fire_Resonance"))
        
        # Verify resonance buff emoji and translation
        res_effect = next(e for e in self.mock_char.data.status_effects if e.name == "Fire_Resonance")
        self.assertGreaterEqual(res_effect.duration, 90)

    async def test_melee_row_blocking_player(self):
        # 測試玩家近戰武器無法攻擊後排 (在前排野狼 A 存活的情況下)
        melee_weapon = Equipment(name="鋼劍", slot_type="main_hand", tags=["Melee"])
        self.mock_char.data.equipment_slots.main_hand = melee_weapon
        
        cm = CombatManager(self.mock_char, self.monsters)
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        
        # 嘗試攻擊後排祭司 (index 1)
        res = await cm.player_attack(1)
        self.assertFalse(res["success"])
        self.assertIn("無法攻擊後排", res["msg"])
        
        # 嘗試攻擊前排野狼 (index 0) - 應成功 (Patch 命中判定)
        with patch("random.randint", return_value=10):
            res_front = await cm.player_attack(0)
            self.assertTrue(res_front["success"])

    async def test_melee_row_blocking_skills(self):
        # 測試近戰技能無法攻擊後排 (在前排存活的情況下)
        melee_skill = Skill(
            name="重擊",
            description="近戰重擊",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                tags=["Melee"],
                cost={},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d20", divisor=10.0)
            )
        )
        
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 嘗試對後排祭司 (index 1) 施放近戰技能
        res = await cm.cast_skill(melee_skill, 1)
        self.assertFalse(res["success"])
        self.assertIn("無法對後排施展近戰技能", res["msg"])
        
        # 遠程或 Spell 技能應不受限制
        spell_skill = Skill(
            name="火球術",
            description="遠端火球",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                tags=["Fire", "Spell"],
                cost={},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=10.0)
            )
        )
        with patch("random.randint", return_value=10):
            res_spell = await cm.cast_skill(spell_skill, 1)
            self.assertTrue(res_spell["success"])

    async def test_monster_melee_redirection(self):
        # 測試怪物近戰攻擊後排玩家時，若有前排召喚物存活，會自動重定向至召喚物
        summon = {
            "name": "召喚精靈",
            "hp": 50,
            "max_hp": 50,
            "attack": 5,
            "defense": 5,
            "m_defense": 5,
            "speed": 10,
            "row": "front", # 前排召喚物
            "is_summon": True,
            "master_id": str(id(self.mock_char)),
            "status_effects": [],
            "executable_triggers": []
        }
        self.mock_char.data.row = "back" # 玩家位於後排
        
        cm = CombatManager(self.mock_char, self.monsters)
        cm.monsters.append(summon) # 加入召喚物 (index 2)
        
        # 讓怪物 A (近戰單位，無 Ranged/Spell 標籤) 行動
        cm.turn_order = [{"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        
        # 攻擊判定 - 應將目標重定向至前排召喚物
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            # 驗證召喚物 HP 減少
            self.assertLess(summon["hp"], 50)
            # 驗證玩家 HP 沒有減少
            self.assertEqual(self.mock_char.data.vitality.hp, 100)

    async def test_marginal_returns_defense_and_resistance(self):
        # 1. 測試防禦邊際效應減免公式
        # formula: Reduction Ratio = min(0.80, Stat / (Stat + 50 + Level * 5))
        # Target level 1: Stat / (Stat + 55)
        # For Stat = 55, Reduction Ratio = 55 / 110 = 50%
        target_monster = {
            "name": "防禦測試怪",
            "level": 1,
            "hp": 100,
            "max_hp": 100,
            "attack": 10,
            "defense": 55, # 55 防禦力
            "m_defense": 55,
            "speed": 8,
            "row": "front"
        }
        
        # 玩家赤手空拳 (無 melee 限制)，STR=10, 攻擊防禦為 55 的怪物，擲骰為 10，威力 = 10 * (10 / 20) = 5
        # 減免比率 = 55 / (55 + 55) = 50%
        # 預期傷害 = 5 * (1 - 0.5) = 2.5 -> 2 (因為 int(2.5) 為 2)
        cm = CombatManager(self.mock_char, [target_monster])
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 2) # 5 * 0.5 = 2.5 -> 2
            
        # 2. 測試元素抗性減免
        # 給怪物設置 fire 抗性值為 55
        target_monster["hp"] = 100
        target_monster["resistances"] = {"Fire": 55.0}
        
        # 施放一個火屬性技能，基礎威力 10，怪物無防禦
        # 減免前伤害 10，抗性減免 50%，預期傷害 = 5
        fire_skill = Skill(
            name="火球",
            description="火焰傷害",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                tags=["Fire"],
                cost={},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=20.0)
            )
        )
        self.mock_char.total_stats["INT"] = 20 # 威力 = 20 * (10 / 20) = 10
        target_monster["defense"] = 0 # 無防禦力
        target_monster["m_defense"] = 0
        
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            res_skill = await cm.cast_skill(fire_skill, 0)
            self.assertTrue(res_skill["success"])
            # 10 點基礎威力，抗性減免 50% -> 5 點傷害
            self.assertEqual(res_skill["final_value"], 5)
