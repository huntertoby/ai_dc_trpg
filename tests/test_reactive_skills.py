import unittest
from unittest.mock import MagicMock, patch
import random

from core.combat import CombatManager
from core.combat_utils import get_entity_combat_stat, has_status
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character
from core.trigger_engine import TriggerEngine

class TestReactiveSkills(unittest.IsolatedAsyncioTestCase):
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

        # 怪物列表
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

    async def test_reactive_trigger_success_and_deduction(self):
        """測試反制技能在 MP 充足時成功觸發，並扣除相應資源"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 設置反制技能：受到傷害時獲得 20 點護盾，消耗 15 MP
        reactive_skill = Skill(
            name="反擊防護",
            description="受到傷害時獲得護盾",
            tier="T4",
            mechanics=SkillMechanics(
                action_type="buff",
                target_type="self",
                cost={"MP": 15},
                execution_mode="reactive"
            ),
            executable_triggers=[
                {
                    "event": "on_damaged",
                    "cooldown": 2,
                    "chance": 1.0,
                    "condition": None,
                    "actions": [
                        {
                            "action_type": "gain_shield",
                            "target": "caster",
                            "flat_value": 20.0
                        }
                    ]
                }
            ]
        )
        
        self.char_schema.abilities.append(reactive_skill)
        self.char_schema.vitality.mp = 30
        self.char_schema.vitality.temp_hp = 0
        
        # 模擬玩家受傷觸發 on_damaged 事件
        TriggerEngine.dispatch_event("on_damaged", self.mock_char, self.monsters[0], cm, damage=10)
        
        # 驗證護盾成功附加
        self.assertEqual(self.char_schema.vitality.temp_hp, 20)
        # 驗證 MP 正確扣除 (30 - 15 = 15)
        self.assertEqual(self.char_schema.vitality.mp, 15)
        
        # 驗證戰鬥日誌含有消耗與觸發訊息
        self.assertTrue(any("消耗 15 MP" in log for log in cm.battle_logs))
        self.assertTrue(any("獲得了 20 點臨時護盾" in log for log in cm.battle_logs))

    async def test_reactive_trigger_insufficient_resources(self):
        """測試反制技能在 MP 不足時不觸發，不扣資源且不產生效果"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 設置反制技能：受到傷害時獲得護盾，消耗 40 MP
        reactive_skill = Skill(
            name="反擊防護",
            description="受到傷害時獲得護盾",
            tier="T4",
            mechanics=SkillMechanics(
                action_type="buff",
                target_type="self",
                cost={"MP": 40},
                execution_mode="reactive"
            ),
            executable_triggers=[
                {
                    "event": "on_damaged",
                    "cooldown": 2,
                    "chance": 1.0,
                    "condition": None,
                    "actions": [
                        {
                            "action_type": "gain_shield",
                            "target": "caster",
                            "flat_value": 20.0
                        }
                    ]
                }
            ]
        )
        
        self.char_schema.abilities.append(reactive_skill)
        self.char_schema.vitality.mp = 10  # MP 不足 (需要 40)
        self.char_schema.vitality.temp_hp = 0
        
        # 模擬玩家受傷觸發
        TriggerEngine.dispatch_event("on_damaged", self.mock_char, self.monsters[0], cm, damage=10)
        
        # 驗證護盾未生成
        self.assertEqual(self.char_schema.vitality.temp_hp, 0)
        # 驗證 MP 未被扣除
        self.assertEqual(self.char_schema.vitality.mp, 10)
        
        # 驗證戰鬥日誌含有資源不足警告
        self.assertTrue(any("資源不足" in log for log in cm.battle_logs))
