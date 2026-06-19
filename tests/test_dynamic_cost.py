import unittest
from unittest.mock import MagicMock, patch
import random

from core.combat import CombatManager
from core.combat_utils import get_entity_combat_stat, has_status
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character
from core.skill_processor import SkillProcessor

class TestDynamicCostAndConversion(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 初始化玩家 Mock 數據
        self.char_schema = CharacterSchema(
            character_id="test_char_999",
            name="雷恩",
            background="戰士",
            primary_stats=PrimaryAttributes(STR=12, DEX=15, CON=12, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100, temp_hp=0),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots(),
            stat_points=5
        )
        self.mock_char = MagicMock(spec=Character)
        self.mock_char.data = self.char_schema
        self.mock_char.total_stats = {"STR": 12, "DEX": 15, "CON": 12, "INT": 10, "WIS": 10, "CHA": 10}
        self.mock_char.max_hp = 220
        self.mock_char.combat_stats = {
            "p_def": 12, "m_def": 6, "crit_rate": 0.1, "evasion_rate": 0.1,
            "accuracy": 0.95, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        def mock_save():
            self.char_schema.vitality.max_hp = self.mock_char.max_hp
            self.char_schema.vitality.hp = min(self.char_schema.vitality.hp, self.char_schema.vitality.max_hp)
        self.mock_char.save = MagicMock(side_effect=mock_save)
        
        def mock_update_vitality(hp=None, mp=None, sanity=None, stamina=None, temp_hp=None):
            v = self.char_schema.vitality
            if hp is not None: v.hp = max(0, min(int(hp), 220))
            if mp is not None: v.mp = max(0, min(int(mp), 100))
            if temp_hp is not None: v.temp_hp = max(0, int(temp_hp))
        self.mock_char.update_vitality = MagicMock(side_effect=mock_update_vitality)

        # 怪物與召喚物列表
        self.monsters = [
            {
                "name": "半人馬",
                "hp": 100,
                "max_hp": 100,
                "attack": 20,
                "defense": 10,
                "m_defense": 5,
                "speed": 10,
                "gold_reward": 50,
                "exp_reward": 30,
                "source_id": "horse",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    async def test_dynamic_cost_all_mp_burn_scaling(self):
        """測試消耗所有 MP 的技能扣減與威力加成效果"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        test_skill = Skill(
            name="魔力燃盡",
            description="消耗當前所有 MP 造成大額魔法傷害",
            tier="T4",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": "all"},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=10.0),
                execution_mode="immediate"
            )
        )
        
        # 1. 設置 MP 為 50
        self.char_schema.vitality.mp = 50
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 模擬 1d20 擲出 10
        # 基礎公式：INT 10 * (10/10) = 10 威力
        # 消耗 50 MP 的加成：1 + 50 * 0.02 = 2.0x 倍率 -> 威力變成 20
        # 怪物防禦 10 (最多折抵 80%，即折抵 20 * 0.8 = 16，但防禦僅 10，折抵 10) -> 傷害 20 - 10 = 10
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            res = await cm.cast_skill(test_skill, target_idx=0)
            self.assertTrue(res["success"])
            
        # 驗證 MP 已被全部消耗歸零
        self.assertEqual(self.char_schema.vitality.mp, 0)
        # 驗證怪物 HP 正確扣除 (100 - 10 = 90)
        self.assertEqual(self.monsters[0]["hp"], 90.0)
        self.assertTrue(any("消耗了所有 MP (50)" in log for log in cm.battle_logs))

    async def test_dynamic_cost_percentage_hp_deduction(self):
        """測試消耗 50% HP 的技能前置扣血與防致死保護"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        test_skill = Skill(
            name="血性狂怒",
            description="消耗當前 50% HP 造成的物理攻擊",
            tier="T4",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"HP": "50%"},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d20", divisor=10.0),
                execution_mode="immediate"
            )
        )
        
        self.char_schema.vitality.hp = 80
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            res = await cm.cast_skill(test_skill, target_idx=0)
            self.assertTrue(res["success"])
            
        # 驗證生命值已扣除 50% max_hp (max_hp = 220, 50% = 110. 但當前 hp=80, 80 - 110 <= 0 -> 觸發最低 1 點生命值保護)
        self.assertEqual(self.char_schema.vitality.hp, 1)
