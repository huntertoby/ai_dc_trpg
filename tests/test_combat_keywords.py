import unittest
from unittest.mock import MagicMock, patch
import random

from core.combat import CombatManager
from core.models import CharacterSchema, Equipment, Vitality, PrimaryAttributes, EquipmentSlots, Skill, SkillMechanics, SkillFormula, StatusEffect
from core.character import Character

class TestCombatKeywords(unittest.IsolatedAsyncioTestCase):
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
        
        # 設置 save 與 update_vitality 的模擬
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
                "name": "精英半人馬",
                "base_name": "半人馬",
                "level": 5,
                "hp": 100,
                "max_hp": 100,
                "attack": 20,
                "defense": 10,
                "m_defense": 5,
                "speed": 10,
                "gold_reward": 50,
                "exp_reward": 30,
                "source_id": "elite_horse",
                "status_effects": []
            },
            {
                "name": "地精弩手",
                "base_name": "地精",
                "level": 3,
                "hp": 40,
                "max_hp": 40,
                "attack": 12,
                "defense": 4,
                "m_defense": 2,
                "speed": 8,
                "gold_reward": 20,
                "exp_reward": 15,
                "source_id": "goblin_archer",
                "status_effects": []
            }
        ]

    async def test_sunder_defense_reduction(self):
        """驗證 Sunder 破甲狀態下，普攻防禦扣減是否生效"""
        cm = CombatManager(self.mock_char, self.monsters)
        monster = self.monsters[0]
        
        # 施加 Sunder 狀態：防禦降低 30% (-3 點防禦)
        monster["status_effects"].append(
            StatusEffect(name="Sunder", duration=3, bonuses={"p_def": -3})
        )
        
        # 測試 _get_entity_defense 取得防禦是否正確減少
        defense = cm._get_entity_defense(monster, "physical", is_player=False)
        self.assertEqual(defense, 7) # 10 - 3 = 7

        # 測試玩家普攻傷害是否隨之增加
        # 力量設為 50 以免防禦上限折抵，普攻公式：50 * (10 / 20.0) = 25.
        # 若原防禦 10，傷害為 25 - 10 = 15；降防後防禦 7，傷害應為 25 - 7 = 18
        self.mock_char.total_stats["STR"] = 50
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 18)

    async def test_burn_dot_damage(self):
        """驗證 Burn 灼燒傷害是否於回合開始時正確扣減生命值，且優先扣除 temp_hp 護盾"""
        cm = CombatManager(self.mock_char, self.monsters)
        player_schema = self.char_schema
        
        # 施加 Burn 狀態
        player_schema.status_effects.append(StatusEffect(name="Burn", duration=3))
        # 設置護盾與生命
        player_schema.vitality.temp_hp = 5
        player_schema.vitality.hp = 100
        
        # 行動開始前 Tick。Burn 傷害公式：10 + 等級 (1) = 11。
        # 預期扣減 5 點護盾，並扣除玩家 6 點 HP。
        cm._current_turn_ticked = False
        # 強制當前回合為玩家
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        
        cm._tick_current_entity_at_turn_start()
        
        self.assertEqual(player_schema.vitality.temp_hp, 0)
        self.assertEqual(player_schema.vitality.hp, 94)
        
        # 驗證狀態持續時間減少
        self.assertEqual(player_schema.status_effects[0].duration, 2)

    def test_stun_turn_skip(self):
        """驗證 Stun 暈眩狀態會被 next_turn() 自動跳過"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 強制戰鬥順序：玩家 (15) -> 怪物 0 (10) -> 怪物 1 (8)
        cm.turn_order = [
            {"type": "player", "speed": 15, "ref": self.mock_char},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0},
            {"type": "monster", "speed": 8, "ref": self.monsters[1], "index": 1}
        ]
        cm.current_turn_idx = 0
        
        # 施加 Stun 狀態給怪物 0
        self.monsters[0]["status_effects"].append(StatusEffect(name="Stun", duration=1))
        
        # 當前是玩家回合，呼叫 next_turn()。
        # 預期轉到怪物 0 時，觸發 Stun 狀態 Tick，將其跳過，最終輪到怪物 1！
        cm.next_turn()
        
        curr = cm.get_current_entity()
        self.assertEqual(curr["type"], "monster")
        self.assertEqual(curr["index"], 1) # 已跳過 0，轉到 1
        
        # 驗證怪物 0 的 Stun 回合已扣減並移除
        self.assertEqual(len(self.monsters[0]["status_effects"]), 0)

    def test_confusion_turn_skip(self):
        """驗證 Confusion 混亂有 50% 機率跳過回合"""
        # 情況 A：判定觸發混亂取消 (random < 0.5)
        with patch("random.random", return_value=0.3):
            cm = CombatManager(self.mock_char, self.monsters)
            cm.turn_order = [
                {"type": "player", "speed": 15, "ref": self.mock_char},
                {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
            ]
            cm.current_turn_idx = 0
            
            # 給怪物施加混亂
            self.monsters[0]["status_effects"].append(StatusEffect(name="Confusion", duration=1))
            
            # 玩家結束回合，切到怪物。怪物因混亂被跳過，回合又回到玩家！
            cm.next_turn()
            
            curr = cm.get_current_entity()
            self.assertEqual(curr["type"], "player")

        # 情況 B：判定未觸發混亂取消 (random >= 0.5)
        with patch("random.random", return_value=0.7):
            cm2 = CombatManager(self.mock_char, self.monsters)
            cm2.turn_order = [
                {"type": "player", "speed": 15, "ref": self.mock_char},
                {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
            ]
            cm2.current_turn_idx = 0
            
            # 重新清理與施加
            self.monsters[0]["status_effects"] = [StatusEffect(name="Confusion", duration=1)]
            
            cm2.next_turn()
            
            curr = cm2.get_current_entity()
            self.assertEqual(curr["type"], "monster") # 混亂未觸發，成功停留於怪物回合

    async def test_shield_and_reflect_normal_attack(self):
        """驗證普攻下 Shield 護盾與 Reflect 反射的運作"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 玩家擁有 Reflect 狀態與護盾
        self.char_schema.status_effects.append(StatusEffect(name="Reflect", duration=2))
        self.char_schema.vitality.temp_hp = 10
        self.char_schema.vitality.hp = 100
        
        # 怪物發動普通攻擊打玩家
        # 強制當前輪到怪物
        cm.turn_order = [{"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        
        # 傷害計算：攻擊力 20，m_roll = 10 -> 總威力 20 * 1.0 = 20
        # 玩家防禦為 12 -> 原始傷害為 20 - 12 = 8
        # 反射折半：傷害變為 4，並反彈 4 點傷害給怪物。
        # 玩家受傷 4 點，優先由 temp_hp (10) 吸收 -> temp_hp 變為 6
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 4)
            self.assertEqual(self.char_schema.vitality.temp_hp, 6)
            self.assertEqual(self.char_schema.vitality.hp, 100) # 血量無損
            self.assertEqual(self.monsters[0]["hp"], 96) # 怪物遭到 4 點反彈傷害
            
            # 驗證 Reflect 狀態被消耗移除
            self.assertFalse(cm._has_status(self.mock_char, is_player=True, status_name="Reflect"))

    async def test_invis_hit_rate_reduction(self):
        """驗證玩家 Invis 隱身狀態下，怪物普通攻擊命中率劇減"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 玩家隱身
        self.char_schema.status_effects.append(StatusEffect(name="Invis", duration=3))
        
        # 怪物普通攻擊。玩家 evasion_rate = 0.10.
        # hit_chance = 90 - 10 = 80%. 隱身後 hit_chance *= 0.3 = 24%.
        # 投擲 30 (> 24) 時應未命中。
        cm.turn_order = [{"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        
        with patch("random.randint", return_value=30):
            res = await cm.monster_action()
            self.assertFalse(res["success"])
            self.assertIn("躲過了", res["msg"])

    async def test_banish_attack_blocked(self):
        """驗證 Banish 放逐狀態下普通攻擊完全無法命中"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 怪物放逐
        self.monsters[0]["status_effects"].append(StatusEffect(name="Banish", duration=2))
        
        # 玩家普攻該怪物，應判定未命中
        res = await cm.player_attack(0)
        self.assertFalse(res["success"])
        self.assertIn("處於放逐狀態", res["msg"])
        
        # 怪物放逐狀態下，反過來攻擊玩家，亦判定無法命中（自己也被放逐了）
        cm.turn_order = [{"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        res2 = await cm.monster_action()
        self.assertFalse(res2["success"])
        self.assertIn("處於放逐狀態", res2["msg"])

    async def test_bless_padding(self):
        """驗證 Bless 祝福狀態下，普通攻擊的 1d20 小於 5 補底為 10"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 玩家獲得 Bless
        self.char_schema.status_effects.append(StatusEffect(name="Bless", duration=3))
        
        # dmg_roll 隨機投出 3，應補底拉升為 10
        # 基礎威力：12 (STR) * (10/20.0) = 6.0
        # 怪物防禦：4 (地精弩手) -> 最終傷害 6.0 - 4.0 = 2.0
        with patch("random.randint", return_value=3), patch("random.random", return_value=0.5):
            res = await cm.player_attack(1) # 攻擊地精弩手
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 2)
            self.assertIn("觸發【祝福】補底", res["msg"])

    async def test_charm_target_inversion(self):
        """驗證被魅惑的怪物普攻改為攻擊其他存活怪物"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 怪物 0 被魅惑
        self.monsters[0]["status_effects"].append(StatusEffect(name="Charm", duration=2))
        
        cm.turn_order = [{"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        
        # 怪物 0 普通攻擊。預期其攻擊對象改為存活的怪物 1（地精弩手）
        # 怪物 1 防禦為 4，m_roll = 10 (威力 20)，無韌性減傷 -> 實際傷害 20 - 4 = 16.
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 16)
            self.assertEqual(self.monsters[1]["hp"], 24) # 40 - 16 = 24
            self.assertIn("半人馬 攻擊了 地精弩手", res["msg"])

    async def test_taunt_and_summon_mechanics(self):
        """驗證召喚物攻擊與嘲諷判定"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 1. 注入召喚物至怪物列表
        summon_entity = {
            "name": "召喚火靈",
            "hp": 50,
            "max_hp": 50,
            "attack": 15,
            "defense": 2,
            "m_defense": 2,
            "speed": 8,
            "level": 1,
            "gold_reward": 0,
            "exp_reward": 0,
            "is_summon": True
        }
        cm.monsters.append(summon_entity)
        cm.turn_order.append({"type": "monster", "speed": 8, "ref": summon_entity, "index": 2})
        
        # 動態找出 summon 的 turn index
        summon_idx = next(i for i, ent in enumerate(cm.turn_order) if ent["ref"] is summon_entity)
        cm.current_turn_idx = summon_idx
        cm._current_turn_ticked = True # 防止狀態重覆 Tick
        
        # 召喚物威力：15，攻擊怪物 1 (防禦 4)。m_roll = 10 -> 總威力 15。
        # 傷害 15 - 4 = 11。
        with patch("random.randint", return_value=10), patch("random.choice", return_value=self.monsters[1]):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            self.assertEqual(res["damage"], 11)
            self.assertEqual(self.monsters[1]["hp"], 29) # 40 - 11 = 29
            self.assertIn("召喚火靈 攻擊了 地精弩手", res["msg"])
            
        # 3. 驗證嘲諷功能 (Taunt)
        # 怪物 0 (半人馬) 被嘲諷。若有召喚物且被嘲諷，怪物強迫打玩家，不打召喚物。
        self.monsters[0]["status_effects"].append(StatusEffect(name="Taunt", duration=2))
        cm.turn_order = [
            {"type": "player", "speed": 15, "ref": self.mock_char},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0},
            {"type": "monster", "speed": 8, "ref": summon_entity, "index": 2}
        ]
        cm.current_turn_idx = 1
        cm._current_turn_ticked = True
        
        # 強制隨機轉向隨從未觸發（因為嘲諷），攻擊目標鎖定為玩家。
        # 傷害計算：攻擊力 20. m_roll = 10 -> 威力 20. 玩家防禦 12 -> 最終傷害 8. 乘上韌性減傷 (90%) 為 7.2 -> 7.
        with patch("random.randint", return_value=10):
            res2 = await cm.monster_action()
            self.assertTrue(res2["success"])
            self.assertEqual(res2["damage"], 7)
            self.assertEqual(self.char_schema.vitality.hp, 93) # 100 - 7 = 93
            self.assertIn("半人馬 攻擊了 雷恩", res2["msg"])

    async def test_echo_delayed_casts(self):
        """驗證 Echo 殘響延遲法術的 50% 威力自動發動"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 建立一個測試技能
        test_skill = Skill(
            name="火球術",
            description="造成魔法傷害",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=15.0),
                keywords=["Echo"]
            )
        )
        
        # 在玩家回合施法，觸發殘響佇列
        # 設置玩家當前 turn，並使用 cast_skill 施法
        cm.turn_order = [
            {"type": "player", "speed": 20, "ref": self.mock_char},
            {"type": "monster", "speed": 10, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        
        self.char_schema.vitality.mp = 50
        with patch("random.randint", return_value=15), patch("random.random", return_value=0.5): # 1d20 擲骰 15
            res = await cm.cast_skill(test_skill, target_idx=0)
            self.assertTrue(res["success"])
            self.assertEqual(len(cm.delayed_actions), 1) # 殘響已加入延遲佇列
            
        # 下一回合輪到怪物，隨後切回玩家回合開始
        # 我們直接模擬 next_turn 回到玩家回合
        cm.current_turn_idx = 1
        cm.next_turn() # 會切換到玩家，並自動觸發殘響 tick！
        
        # 驗證殘響已執行，且 delayed_actions 佇列被排空
        self.assertEqual(len(cm.delayed_actions), 0)
        
        # 威力驗證：
        # 1d20 = 15 -> 玩家 INT = 10 -> (10 * (15/15)) = 10 點基礎威力
        # 第一發傷害：防禦 10，最多折抵 80% (10 * 0.8 = 8) -> 10 - 8 = 2.0 點真實傷害。
        # 殘響威力減半 (50% 威力) -> 5 點基礎威力
        # 殘響防禦最多折抵 80% (5 * 0.8 = 4) -> 5 - 4 = 1.0 點真實傷害。
        # 總共造成 3 點傷害 -> 怪物 HP 100 -> 97.0.
        self.assertEqual(self.monsters[0]["hp"], 97.0)

    async def test_berserk_force_attack(self):
        """驗證 Berserk 狂暴狀態下阻止技能施放並強制作普攻"""
        cm = CombatManager(self.mock_char, self.monsters)
        # 玩家獲得狂暴狀態
        self.char_schema.status_effects.append(StatusEffect(name="Berserk", duration=3))
        
        test_skill = Skill(
            name="療癒術",
            description="恢復生命值",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="heal",
                target_type="self",
                cost={"MP": 5},
                formula=SkillFormula(type="additive", base_stat="WIS", dice="1d6")
            )
        )
        
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 普攻公式：12 * (10/20.0) = 6.
        # 防禦最多折抵 80% (6 * 0.8 = 4.8) -> 最終傷害 6 - 4.8 = 1.2 -> 1.
        with patch("random.randint", return_value=10), patch("random.random", return_value=0.5), patch("random.choice", return_value=0):
            res = await cm.cast_skill(test_skill, target_idx=0)
            self.assertTrue(res["success"])
            self.assertIn("施法者正處於狂暴狀態！無法使用技能，強制發動普通攻擊", res["msg"])
            self.assertEqual(self.monsters[0]["hp"], 99) # 100 - 1 = 99

    async def test_greed_gold_multiplier(self):
        """驗證 Greed 貪婪擊殺怪物時金幣加倍"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 建立一個貪婪技能
        greed_skill = Skill(
            name="點金術",
            description="獲得貪婪效果",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d20", divisor=15.0),
                keywords=["Greed"]
            )
        )
        
        # 怪物 HP 設為極低，使技能足以將其擊殺
        self.monsters[0]["hp"] = 1
        
        cm.turn_order = [{"type": "player", "speed": 20, "ref": self.mock_char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 施放技能擊殺怪物
        # 怪物 0 原始金幣為 50G. 貪婪乘數隨機設為 3 倍 -> 金幣變為 150G.
        with patch("random.randint", return_value=3), patch("random.random", return_value=0.5): # 這裡 patch 了 Greed 的 multiplier 與 1d20 擲骰
            res = await cm.cast_skill(greed_skill, target_idx=0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["gold_reward"], 150)
            self.assertIn("觸發【貪婪】：擊殺目標，使其金幣掉落翻了", res["msg"])

    def test_slow_evasion_clamping(self):
        """驗證 Slow 減速狀態下，迴避率計算夾持防止為負數"""
        cm = CombatManager(self.mock_char, self.monsters)
        
        # 怪物獲得減速狀態
        self.monsters[0]["status_effects"].append(StatusEffect(name="Slow", duration=3, bonuses={"DEX": -99}))
        
        # 檢測怪物迴避率是否正確降為 0
        evasion = cm._get_entity_evasion(self.monsters[0], is_player=False)
        self.assertEqual(evasion, 0.0)
 
        # 玩家獲得減速狀態，使戰鬥面板中的 DEX 極低
        self.char_schema.status_effects.append(StatusEffect(name="Slow", duration=3, bonuses={"DEX": -99}))
        # 模擬戰鬥屬性。由於 character 的 combat_stats 沒有重新加載，我們直接驗證 _get_entity_evasion 對玩家的保護
        # 故意給玩家 combat_stats 塞一個負數迴避
        self.mock_char.combat_stats["evasion_rate"] = -0.5
        evasion_p = cm._get_entity_evasion(self.mock_char, is_player=True)
        self.assertEqual(evasion_p, 0.0) # 應夾持為 0.0 以上

if __name__ == "__main__":
    unittest.main()
