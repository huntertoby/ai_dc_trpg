import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import random

from core.combat import CombatManager
from core.combat_utils import get_entity_combat_stat, has_status, get_entity_attr
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character
from core.skill_processor import SkillProcessor

class TestDelayedChannelAndSummons(unittest.IsolatedAsyncioTestCase):
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

    async def test_delayed_cast_success_on_turns_zero(self):
        """測試延遲施法在 turns_left 歸零時正確施放"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        test_skill = Skill(
            name="隕石術",
            description="大範圍火焰魔法",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=10.0),
                execution_mode="delayed"
            )
        )
        
        cm.turn_order = [
            {"type": "player", "speed": 20, "ref": self.mock_char},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        self.char_schema.vitality.mp = 50
        
        # 施展延遲法術
        res = await cm.cast_skill(test_skill, target_idx=0)
        self.assertTrue(res["success"])
        
        # 驗證已加入 casting_queue，且 turns_left = 1
        self.assertEqual(len(cm.casting_queue), 1)
        self.assertEqual(cm.casting_queue[0]["turns_left"], 1)
        
        # 轉移回合：切換到怪物，再回到玩家回合開始
        cm.current_turn_idx = 1
        
        # 模擬擲骰與傷害解算，讓隕石術在玩家回合開始時爆發
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            cm.next_turn()  # 這會切換到玩家，觸發玩家 turn_start 的 tick_current_entity，進而扣減 turns_left 並執行
            
        # 驗證解算後已被移出隊列
        self.assertEqual(len(cm.casting_queue), 0)
        # 驗證對半人馬造成了傷害 (INT 10 * 1.0 = 10, 防禦折抵 8 點 -> 最終傷害 2)
        self.assertEqual(self.monsters[0]["hp"], 98.0)
        self.assertTrue(any("隕石術" in log for log in cm.battle_logs))

    async def test_delayed_cast_interrupted(self):
        """測試在延遲施法詠唱途中被眩暈 (Stun) 打斷"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        test_skill = Skill(
            name="雷霆暴擊",
            description="蓄力一擊",
            tier="T3",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d20", divisor=10.0),
                execution_mode="delayed"
            )
        )
        
        cm.turn_order = [
            {"type": "player", "speed": 20, "ref": self.mock_char},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        self.char_schema.vitality.mp = 50
        
        # 詠唱開始
        await cm.cast_skill(test_skill, target_idx=0)
        self.assertEqual(len(cm.casting_queue), 1)
        
        # 在回合切換前，施加 Stun 給玩家
        self.char_schema.status_effects.append(StatusEffect(name="Stun", duration=1))
        
        # 回合切回玩家，此時 Stun 會在 _process_entity_status_tick 觸發打斷
        cm.current_turn_idx = 1
        cm.next_turn()
        
        # 驗證詠唱隊列已清空，打斷日誌已輸出
        self.assertEqual(len(cm.casting_queue), 0)
        self.assertTrue(any("法術詠唱被打斷了" in log for log in cm.battle_logs))

    async def test_summon_commands_and_defend_redirection(self):
        """測試召喚物指令控制（Attack/Defend）與傷害重定向機制"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 生成一個帶有 master_id 的召喚物
        summon = {
            "name": "召喚小狼",
            "hp": 30,
            "max_hp": 30,
            "attack": 12,
            "defense": 2,
            "m_defense": 2,
            "speed": 12,
            "level": 1,
            "is_summon": True,
            "master_id": str(id(self.mock_char)),
            "status_effects": [],
            "executable_triggers": [],
            "abilities": [
                Skill(
                    name="狼嚎",
                    description="提升隊友士氣",
                    tier="T5",
                    mechanics=SkillMechanics(action_type="buff", target_type="self", cost={})
                )
            ]
        }
        
        cm.monsters.append(summon)
        # 設定行動順序：玩家 -> 召喚小狼 -> 怪物
        cm.turn_order = [
            {"type": "player", "speed": 20, "ref": self.mock_char},
            {"type": "monster", "speed": 12, "ref": summon, "index": 1},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
        ]
        
        # 1. 測試指令 Attack
        cm.current_turn_idx = 1
        cm._current_turn_ticked = True
        
        with patch("random.randint", return_value=10):  # 12 * 1.0 = 12 威力，怪物防禦 10 -> 2 傷害
            res = await cm.cast_summon_action(action_type="attack", target_idx=0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 98.0)
            self.assertIn("召喚小狼 攻擊了 半人馬", res["msg"])
            
        # 2. 測試指令 Defend (護衛主人)
        cm.current_turn_idx = 1
        cm._current_turn_ticked = True
        
        res = await cm.cast_summon_action(action_type="defend")
        self.assertTrue(res["success"])
        self.assertEqual(getattr(self.mock_char, "_defended_by"), summon)
        
        # 3. 測試傷害重定向：怪物攻擊主人，傷害應轉移給召喚小狼
        cm.current_turn_idx = 2
        cm._current_turn_ticked = True
        
        # 怪物攻擊力 20，1d20 = 10 -> 20 威力。小狼防禦 2 -> 18 傷害。
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.8):
            res_attack = await cm.monster_action()
            self.assertTrue(res_attack["success"])
            
        # 驗證主人生命未減少 (依舊是 100)
        self.assertEqual(self.char_schema.vitality.hp, 100)
        # 驗證召喚小狼承受了重定向傷害 (30 - 7 = 23 HP)
        self.assertEqual(summon["hp"], 23)
        # 驗證護衛標記已被清除
        self.assertIsNone(getattr(self.mock_char, "_defended_by"))

    async def test_summon_dissipation_on_master_defeated(self):
        """測試當主人（玩家）被擊倒時，召喚物自動消散"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        summon = {
            "name": "召喚火靈",
            "hp": 50,
            "max_hp": 50,
            "attack": 15,
            "speed": 8,
            "level": 1,
            "is_summon": True,
            "master_id": str(id(self.mock_char)),
            "status_effects": [],
            "executable_triggers": []
        }
        cm.monsters.append(summon)
        cm.turn_order = [
            {"type": "player", "speed": 20, "ref": self.mock_char},
            {"type": "monster", "speed": 8, "ref": summon, "index": 1}
        ]
        
        # 模擬主人死亡
        self.char_schema.vitality.hp = 0
        
        # 切換到召喚物的回合
        cm.current_turn_idx = 1
        cm._current_turn_ticked = False
        
        # 觸發回合開始，此時召喚物應發現主人死亡並消散
        cm._tick_current_entity_at_turn_start()
        
        # 驗證召喚物 HP 已被歸零消散
        self.assertEqual(summon["hp"], 0)
        self.assertTrue(any("自動消散" in log for log in cm.battle_logs))
