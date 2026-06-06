import unittest
from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import Skill, SkillMechanics, SkillFormula, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, StatusEffect, Equipment
from core.skill_processor import SkillProcessor

class TestTriggerHooks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mock character
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_999",
            name="雷克斯",
            background="孤兒",
            primary_stats=PrimaryAttributes(STR=20, DEX=999, CON=15, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.char.total_stats = {"STR": 20, "DEX": 999, "CON": 15, "INT": 10, "WIS": 10, "CHA": 10}
        self.char.max_hp = 100
        self.char.combat_stats = {
            "p_def": 10, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
            "accuracy": 1.0, "skill_power": 1.0, "tenacity": 100, "luck": 1
        }
        
        # Mock save and update_vitality methods
        def mock_save():
            pass
        self.char.save = MagicMock(side_effect=mock_save)
        
        def mock_update_vitality(hp=None, mp=None, sanity=None, stamina=None, temp_hp=None):
            v = self.char.data.vitality
            if hp is not None: v.hp = max(0, min(int(hp), 100))
            if mp is not None: v.mp = max(0, min(int(mp), 100))
            if temp_hp is not None: v.temp_hp = max(0, int(temp_hp))
        self.char.update_vitality = MagicMock(side_effect=mock_update_vitality)
        
        self.monsters = [
            {
                "name": "幽靈",
                "base_name": "幽靈",
                "level": 5,
                "hp": 100,
                "max_hp": 100,
                "attack": 15,
                "defense": 10,
                "m_defense": 10,
                "speed": 15,
                "evasion_rate": 1.0, # 100% 迴避率，普通攻擊正常打不中
                "source_id": "ghost",
                "status_effects": [],
                "executable_triggers": []
            }
        ]

    async def test_absolute_hit_trigger(self):
        # 1. 裝備一把帶有「絕對命中」觸發器的武器
        weapon = Equipment(
            name="必中之弓",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1",
            scaling_stat="DEX",
            damage_type="physical"
        )
        weapon.executable_triggers = [
            {
                "event": "on_prepare",
                "actions": [
                    {
                        "action_type": "set_flag",
                        "param": "is_absolute_hit",
                        "param_value": True
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        
        cm = CombatManager(self.char, self.monsters)
        # 即使怪物的 evasion_rate = 1.0，因為絕對命中，攻擊必定打中
        res = await cm.player_attack(0)
        self.assertTrue(res["success"])
        self.assertIn("必中之弓", cm.character.data.equipment_slots.main_hand.name)
        self.assertIn("造成了", res["msg"])

    async def test_dice_floor_trigger(self):
        # 2. 裝備一個帶有「擲骰地板值=15」觸發器的戒指
        ring = Equipment(
            name="幸運指環",
            item_type="equipment",
            slot_type="ring_1",
            tier="T1"
        )
        ring.executable_triggers = [
            {
                "event": "on_dice",
                "actions": [
                    {
                        "action_type": "modify_dice",
                        "param": "floor_value",
                        "param_value": 15
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.ring_1 = ring
        
        # 將怪物迴避率降為 0 確保擊中
        self.monsters[0]["evasion_rate"] = 0.0
        
        cm = CombatManager(self.char, self.monsters)
        
        # 模擬 random.randint 返回 1 (最差情況)
        with patch("random.randint", return_value=1):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # 普通攻擊公式: STR * (dmg_roll / divisor) + weapon_power
            # divisor = 20 (無主手 ATK 武器). STR = 20.
            # 如果地板值起效，dmg_roll 會從 1 被拉高到 15。
            # 傷害 = 20 * (15 / 20.0) - target_defense (10) = 15 - 10 = 5.
            # 驗證得到的傷害是不是由地板值 15 計算出來的 5 點傷害
            self.assertEqual(res["damage"], 5)

    async def test_defense_ignore_trigger(self):
        # 3. 裝備一個「無視 50% 防禦」的胸甲
        chest = Equipment(
            name="破甲重鎧",
            item_type="equipment",
            slot_type="chest",
            tier="T1"
        )
        chest.executable_triggers = [
            {
                "event": "on_calculate_damage",
                "actions": [
                    {
                        "action_type": "set_value",
                        "param": "defense_ignore_ratio",
                        "param_value": 0.5
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.chest = chest
        
        # 將怪物迴避率降為 0 確保擊中，防禦力設為 20
        self.monsters[0]["evasion_rate"] = 0.0
        self.monsters[0]["defense"] = 20
        
        cm = CombatManager(self.char, self.monsters)
        
        # 模擬擲骰為 20 (最高點數)
        with patch("random.randint", return_value=20):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # STR = 20. dmg_roll = 20. divisor = 20. base_power = 20.
            # 敵防 = 20. 無視 50% 後 = 10.
            # 最終傷害 = 20 - 10 = 10.
            # 若無無視防禦，最終傷害為 20 - 20 = 1.0.
            self.assertEqual(res["damage"], 10)

    async def test_gain_shield_on_damaged_trigger(self):
        # 4. 當角色受傷時，獲得 20 點護盾 (temp_hp)
        shield_effect = StatusEffect(
            name="棘甲盾",
            description="受傷時獲得護盾",
            duration=3
        )
        shield_effect.executable_triggers = [
            {
                "event": "on_health_below", # 受傷扣減血量後觸發
                "actions": [
                    {
                        "action_type": "gain_shield",
                        "target": "caster", # 施法者自身獲得
                        "flat_value": 20.0
                    }
                ]
            }
        ]
        self.char.data.status_effects.append(shield_effect)
        
        # 怪物必定擊中玩家，為了解決先攻，把怪物速度設為極低
        self.monsters[0]["speed"] = 1
        self.char.combat_stats["evasion_rate"] = 0.0
        cm = CombatManager(self.char, self.monsters)
        
        # 執行怪物回合攻擊玩家 (手動調整回合為怪物)
        cm.turn_order = [{"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        with patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
        
        # 玩家的 temp_hp 應該增加了 20 點，且身上有護盾狀態
        self.assertEqual(self.char.data.vitality.temp_hp, 20)
        self.assertTrue(any(e.name == "Shield" for e in self.char.data.status_effects))

    async def test_inflict_damage_on_hit_trigger(self):
        # 5. 當玩家命中目標時，對目標追加 15 點額外真實傷害
        bonus_dmg_effect = StatusEffect(
            name="雷神之力",
            description="命中追加雷擊傷害",
            duration=3
        )
        bonus_dmg_effect.executable_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 15.0,
                        "damage_type": "true_damage"
                    }
                ]
            }
        ]
        self.char.data.status_effects.append(bonus_dmg_effect)
        
        # 怪物必定被擊中
        self.monsters[0]["evasion_rate"] = 0.0
        self.monsters[0]["hp"] = 100
        
        cm = CombatManager(self.char, self.monsters)
        
        # 模擬擲骰為 10
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # 普通傷害 = STR(20) * (10/20) - target_def(10) = 10 - 8 (80% 限制) = 2.
            # 追加傷害 = 15.
            # 怪物剩餘生命應該為 100 - 2 - 15 = 83
            self.assertEqual(self.monsters[0]["hp"], 83)
            self.assertIn("觸發效果", "".join(cm.battle_logs))

    async def test_target_health_below_trigger(self):
        # 測試 target_health_below 觸發過濾：擊中血量低於 30% 的敵人時額外造成 50 點傷害
        weapon = Equipment(
            name="斬殺巨劍",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "target_health_below": 30.0,
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 50.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.monsters[0]["evasion_rate"] = 0.0
        
        # 情況 A：怪 HP = 100 (普通擊中後為 83%) -> 不觸發追加傷害
        self.monsters[0]["hp"] = 100
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 83)

        # 情況 B：怪 HP = 25 (普通擊中後為 23%，低於 30%) -> 觸發追加 50 點傷害直接擊殺
        self.monsters[0]["hp"] = 25
        cm2 = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm2.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 0)

    async def test_target_health_above_trigger(self):
        # 測試 target_health_above 觸發過濾：擊中血量高於 70% 的敵人時額外造成 10 點傷害
        weapon = Equipment(
            name="壓制法杖",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_hit",
                "target_health_above": 70.0,
                "actions": [
                    {
                        "action_type": "inflict_damage",
                        "target": "target",
                        "flat_value": 10.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.monsters[0]["evasion_rate"] = 0.0
        
        # 情況 A：怪 HP = 100 (普通擊中後為 83%，大於 70%) -> 觸發追加 10 點傷害
        self.monsters[0]["hp"] = 100
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # 普通傷害 17 + 額外傷害 10 = 27 傷害。HP 變為 73
            self.assertEqual(self.monsters[0]["hp"], 73)

        # 情況 B：怪 HP = 50 (普通擊中後為 33%，小於 70%) -> 不觸發追加傷害
        self.monsters[0]["hp"] = 50
        cm2 = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm2.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 33)

    async def test_on_health_up_trigger(self):
        # 測試獲得治療 on_health_up 事件：受到治療時獲得 15 點護盾 (temp_hp)
        heal_buff = StatusEffect(
            name="神聖回響",
            duration=3
        )
        heal_buff.executable_triggers = [
            {
                "event": "on_health_up",
                "actions": [
                    {
                        "action_type": "gain_shield",
                        "target": "caster",
                        "flat_value": 15.0
                    }
                ]
            }
        ]
        self.char.data.status_effects.append(heal_buff)
        
        # 治療技能
        heal_skill = Skill(
            name="快速治療",
            description="恢復生命",
            tier="T5",
            mechanics=SkillMechanics(
                action_type="heal",
                target_type="self",
                cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="1d10", divisor=5.0)
            )
        )
        
        cm = CombatManager(self.char, self.monsters)
        self.char.data.vitality.hp = 50
        self.char.data.vitality.mp = 100
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=5):
            res = await cm.cast_skill(heal_skill)
            self.assertTrue(res["success"])
            
        # 治療應該增加 10 點生命且觸發護盾套上 15 點 temp_hp
        self.assertEqual(self.char.data.vitality.hp, 60)
        self.assertEqual(self.char.data.vitality.temp_hp, 15)
        self.assertTrue(any(e.name == "Shield" for e in self.char.data.status_effects))

    async def test_skill_passive_trigger(self):
        # 測試技能附帶的被動觸發器：當角色擊中目標時，額外造成 10 點真實傷害
        passive_skill = Skill(
            name="雷霆被動",
            description="被動傷害",
            tier="T1",
            mechanics=SkillMechanics(
                action_type="damage",
                target_type="single",
                cost={"MP": 0}
            ),
            executable_triggers=[
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "inflict_damage",
                            "target": "target",
                            "flat_value": 10.0
                        }
                    ]
                }
            ]
        )
        self.char.data.abilities.append(passive_skill)
        self.monsters[0]["evasion_rate"] = 0.0
        self.monsters[0]["hp"] = 100
        
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # 普通擊中傷害為 2 (無武器，STR=20, divisor=20, roll=10 => power=10, target_def=10 => mit=8 => dmg=2)
            # 被動技能觸發追加 10 傷害
            # 怪物剩餘生命 = 100 - 2 - 10 = 88
            self.assertEqual(self.monsters[0]["hp"], 88)

    async def test_brand_vulnerability_trigger(self):
        # 測試「烙印下一次受到傷害增加 15% 且消耗」
        brand_effect = StatusEffect(
            name="魔神烙印",
            description="下一次受到的傷害提高 15%，受到傷害後消失",
            duration=2
        )
        brand_effect.executable_triggers = [
            {
                "event": "on_calculate_damage",
                "actions": [
                    {
                        "action_type": "set_value",
                        "param": "damage_multiplier",
                        "param_value": 1.15
                    }
                ]
            },
            {
                "event": "on_damaged",
                "actions": [
                    {
                        "action_type": "remove_status",
                        "target": "caster",
                        "status_name": "魔神烙印"
                    }
                ]
            }
        ]
        
        # 2. 將狀態施加給怪物
        self.monsters[0]["status_effects"].append(brand_effect)
        self.monsters[0]["evasion_rate"] = 0.0
        self.monsters[0]["hp"] = 100
        
        # 提高角色力量，以便測出明顯的加成數值
        self.char.total_stats["STR"] = 100
        
        cm = CombatManager(self.char, self.monsters)
        
        # 3. 第一次攻擊：觸發傷害增加 15%（傷害變為 47）並清除烙印
        with patch("random.randint", return_value=10):
            # 無烙印時傷害為 40 (STR 100 * 0.5 - 10 = 40)
            # 有烙印加成 1.15 倍：total_power 變為 57.5，防禦減免後為 47.5 -> 實際傷害 47
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            self.assertEqual(self.monsters[0]["hp"], 53) # 100 - 47 = 53
            
        # 驗證第一次受傷後「魔神烙印」已經被消耗並移除
        self.assertFalse(any(e.name == "魔神烙印" for e in self.monsters[0]["status_effects"]))
        
        # 4. 第二次攻擊：因為烙印已移除，傷害恢復為正常值 40
        # 重置回合回玩家以進行第二次攻擊
        for idx, ent in enumerate(cm.turn_order):
            if ent["type"] == "player":
                cm.current_turn_idx = idx
                break
        cm._current_turn_ticked = False
        
        with patch("random.randint", return_value=10):
            res2 = await cm.player_attack(0)
            self.assertTrue(res2["success"])
            self.assertEqual(self.monsters[0]["hp"], 13) # 53 - 40 = 13

    async def test_heavenly_protection_trigger(self):
        # 測試天降之護與聖潔庇護：
        # 當角色 HP 低於 30% 時釋放天降之護，恢復 50% HP，並施加 2 回合「聖潔庇護」；
        # 受到傷害降低 20% (即 damage_multiplier 設為 0.8)；
        # 回合結束時移除「聖潔庇護」。
        # 觸發後進入 3 回合冷卻。
        
        self.char.data.vitality.max_hp = 100
        self.char.data.vitality.hp = 100
        self.char.data.vitality.temp_hp = 0
        self.char.total_stats["CON"] = 100 # 使 heal (CON * 0.5) 剛好等於 50
        
        # 1. 裝備一個帶有天降之護觸發器的盾牌
        shield = Equipment(
            name="天降之盾",
            item_type="equipment",
            slot_type="off_hand",
            tier="T1"
        )
        shield.executable_triggers = [
          {
            "event": "on_health_below",
            "health_threshold": 30.0,
            "cooldown": 3,
            "actions": [
              {
                "action_type": "heal",
                "target": "caster",
                "scaling_stat": "CON",
                "value_multiplier": 0.5,
                "chance": 1.0
              },
              {
                "action_type": "apply_status",
                "target": "caster",
                "status_name": "聖潔庇護",
                "duration": 2,
                "chance": 1.0
              }
            ]
          },
          {
            "event": "on_calculate_damage",
            "actions": [
              {
                "action_type": "set_value",
                "param": "damage_multiplier",
                "param_value": 0.8
              }
            ],
            "condition": "has_status('聖潔庇護')"
          },
          {
            "event": "on_turn_end",
            "actions": [
              {
                "action_type": "remove_status",
                "target": "caster",
                "status_name": "聖潔庇護"
              }
            ],
            "condition": "has_status('聖潔庇護')"
          }
        ]
        self.char.data.equipment_slots.off_hand = shield
        
        # 怪物打玩家
        self.monsters[0]["speed"] = 1
        self.char.combat_stats["evasion_rate"] = 0.0
        cm = CombatManager(self.char, self.monsters)
        
        # 手動調整為怪物回合，攻擊玩家
        cm.turn_order = [{"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 將玩家生命值調到 35%，怪物打玩家 10 點傷害，使玩家生命值變為 25% (低於 30%)
        self.char.data.vitality.hp = 35
        
        # 攻擊力設為 10 點，防禦設為 0
        self.monsters[0]["attack"] = 10
        self.char.combat_stats["p_def"] = 0
        
        with patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        # 驗證血量恢復到 80% (35 - 5 + 50 = 80)
        self.assertEqual(self.char.data.vitality.hp, 80)
        # 驗證自身獲得了「聖潔庇護」狀態
        self.assertTrue(any(e.name == "聖潔庇護" for e in self.char.data.status_effects))
        
        # 驗證天降之護觸發器 cooldown_left 設為 3
        health_below_trigger = next(t for t in shield.executable_triggers if t["event"] == "on_health_below")
        self.assertEqual(health_below_trigger.get("cooldown_left"), 3)
        
        # 3. 測試 20% 減傷 (damage_multiplier = 0.8)
        # 重新讓怪物攻擊玩家 (手動重置怪物回合)
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        self.monsters[0]["attack"] = 20 # 傷害 20 點，防禦 0 -> 20 * 0.55 * 0.9 = 9.9 傷害。
        # 由於聖潔庇護 status 作用，damage_multiplier 攔截器將其變為 9.9 * 0.8 = 7.92 -> 實際傷害 7 (因為轉 int 截斷)
        with patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        # 玩家受傷前 hp=80，受到 7 傷害 -> hp=73
        self.assertEqual(self.char.data.vitality.hp, 73)
        
        # 4. 測試 on_turn_end 移除狀態
        # 玩家的回合結束時，聖潔庇護狀態應該會被 on_turn_end 移除
        cm.turn_order = [
            {"type": "player", "speed": 10, "ref": self.char},
            {"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 調用 next_turn 切換到下一個行動者 (會觸發玩家的 on_turn_end)
        cm.next_turn()
        
        # 驗證「聖潔庇護」狀態已被清除
        self.assertFalse(any(e.name == "聖潔庇護" for e in self.char.data.status_effects))
        
        # 驗證 cooldown 遞減：第一回合結束後 cooldown 變為 2
        self.assertEqual(health_below_trigger.get("cooldown_left"), 2)
        
        # 切換到玩家回合再次結束，cooldown 變為 1
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        cm.next_turn()
        self.assertEqual(health_below_trigger.get("cooldown_left"), 1)
        
        # 再結束一次，cooldown 變為 0
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        cm.next_turn()
        self.assertEqual(health_below_trigger.get("cooldown_left"), 0)

    async def test_crust_counterattack_trigger(self):
        # 測試護頭反擊與硬殼狀態
        self.char.data.vitality.max_hp = 100
        self.char.data.vitality.hp = 100
        self.char.total_stats["CON"] = 30 # 反擊傷害 30
        
        armor = Equipment(
            name="硬殼鎧甲",
            item_type="equipment",
            slot_type="chest",
            tier="T1"
        )
        armor.executable_triggers = [
          {
            "event": "on_damaged",
            "actions": [
              {
                "action_type": "inflict_damage",
                "target": "random_enemy",
                "scaling_stat": "CON",
                "value_multiplier": 1.0,
                "damage_type": "true_damage"
              },
              {
                "action_type": "apply_status",
                "target": "random_enemy",
                "status_name": "硬殼",
                "duration": 2,
                "chance": 0.25,
                "executable_triggers": [
                  {
                    "event": "on_dice",
                    "actions": [
                      {
                        "action_type": "modify_dice",
                        "param": "roll_modifier",
                        "param_value": -15
                      }
                    ]
                  },
                  {
                    "event": "on_damaged",
                    "actions": [
                      {
                        "action_type": "remove_status",
                        "target": "caster",
                        "status_name": "硬殼"
                      }
                    ]
                  }
                ]
              }
            ],
            "chance": 0.25
          }
        ]
        self.char.data.equipment_slots.chest = armor
        
        self.monsters[0]["hp"] = 100
        self.monsters[0]["speed"] = 1
        self.monsters[0]["attack"] = 10
        self.char.combat_stats["p_def"] = 0
        self.char.combat_stats["evasion_rate"] = 0.0
        
        cm = CombatManager(self.char, self.monsters)
        
        # 情況 A：Trigger 機率失敗 (random.random 返回 0.3)
        cm.turn_order = [{"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        self.char.data.vitality.hp = 100
        self.monsters[0]["hp"] = 100
        
        with patch("random.random", return_value=0.3), patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        # 怪物打玩家 (5 damage)。玩家 hp=95。沒有觸發反擊，怪物 hp 仍為 100。
        self.assertEqual(self.char.data.vitality.hp, 95)
        self.assertEqual(self.monsters[0]["hp"], 100)
        
        # 情況 B：Trigger 成功，但 apply_status 失敗 (random.random 依次返回 0.1, 0.5)
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        self.char.data.vitality.hp = 100
        self.monsters[0]["hp"] = 100
        
        with patch("random.random", side_effect=[0.1, 0.5, 0.5]), patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        # 玩家受傷後 hp=95。觸發反擊造成 30 傷害 -> 怪物 hp=70。但 status 沒有上。
        self.assertEqual(self.char.data.vitality.hp, 95)
        self.assertEqual(self.monsters[0]["hp"], 70)
        self.assertFalse(any(e.name == "硬殼" if hasattr(e, "name") else e.get("name") == "硬殼" for e in self.monsters[0]["status_effects"]))
        
        # 情況 C：Trigger 成功且 apply_status 成功 (random.random 依次返回 0.1, 0.1)
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        self.char.data.vitality.hp = 100
        self.monsters[0]["hp"] = 100
        
        with patch("random.random", side_effect=[0.1, 0.1, 0.5]), patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        # 玩家受傷後 hp=95。觸發反擊造成 30 傷害 -> 怪物 hp=70。且施加「硬殼」狀態！
        self.assertEqual(self.char.data.vitality.hp, 95)
        self.assertEqual(self.monsters[0]["hp"], 70)
        self.assertTrue(any(e.name == "硬殼" if hasattr(e, "name") else e.get("name") == "硬殼" for e in self.monsters[0]["status_effects"]))
        
        # 情況 D：驗證「硬殼」下的減骰子點數效果 (on_dice 使 roll_modifier 為 -15)
        # 手動調整為怪物回合，攻擊玩家
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 正常 m_roll = 10。由於「硬殼」狀態在怪物身上，怪物的 on_dice 將 roll_modifier 設為 -15
        # 10 - 15 = -5 點。
        # m_roll_mult = 0.5 + (-5 * 0.05) = 0.25。
        # 威力 = 10 * 0.25 = 2.5。
        # 減傷前 2.5 * 1.0 = 2.5。韌性 0.9 -> 2.25。傷害 int 截斷後為 2。
        with patch("random.randint", return_value=10):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
        # 驗證傷害是 2，所以玩家 hp 變為 95 - 2 = 93。
        self.assertEqual(self.char.data.vitality.hp, 93)
        
        # 情況 E：怪物在「硬殼」下受傷時，應該觸發 on_damaged 移除「硬殼」狀態
        # 玩家進行攻擊，怪物受傷
        # 重置回合為玩家回合
        self.monsters[0]["evasion_rate"] = 0.0
        cm.turn_order = [
            {"type": "player", "speed": 10, "ref": self.char},
            {"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}
        ]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = False
        
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
        # 驗證「硬殼」狀態在受到傷害後被清除
        self.assertFalse(any(e.name == "硬殼" if hasattr(e, "name") else e.get("name") == "硬殼" for e in self.monsters[0]["status_effects"]))

    async def test_health_above_below_condition_evaluation(self):
        # 測試 evaluate_condition 中自訂的 health_above 和 health_below 解析
        chest = Equipment(
            name="養生棉襖",
            item_type="equipment",
            slot_type="chest",
            tier="T1"
        )
        chest.executable_triggers = [
            {
                "event": "on_turn_end",
                "condition": "health_above(50)",
                "actions": [
                    {
                        "action_type": "heal",
                        "target": "caster",
                        "flat_value": 10.0,
                        "target_resource": "hp"
                    }
                ]
            },
            {
                "event": "on_turn_end",
                "condition": "health_below(30)",
                "actions": [
                    {
                        "action_type": "gain_shield",
                        "target": "caster",
                        "flat_value": 20.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.chest = chest
        self.char.data.vitality.max_hp = 100
        
        # 情況 A: 玩家 HP = 60 (高於 50%) ➜ 觸發治療，但不觸發護盾
        self.char.data.vitality.hp = 60
        self.char.data.vitality.temp_hp = 0
        self.char.data.status_effects = []
        cm = CombatManager(self.char, self.monsters)
        cm.turn_order = [{"type": "player", "speed": 10, "ref": self.char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        cm.next_turn()  # 觸發 on_turn_end
        
        self.assertEqual(self.char.data.vitality.hp, 70)
        self.assertEqual(self.char.data.vitality.temp_hp, 0)
        
        # 情況 B: 玩家 HP = 20 (低於 30%) ➜ 觸發護盾，但不觸發治療
        self.char.data.vitality.hp = 20
        self.char.data.vitality.temp_hp = 0
        self.char.data.status_effects = []
        cm2 = CombatManager(self.char, self.monsters)
        cm2.turn_order = [{"type": "player", "speed": 10, "ref": self.char}]
        cm2.current_turn_idx = 0
        cm2._current_turn_ticked = True
        cm2.next_turn()  # 觸發 on_turn_end
        
        self.assertEqual(self.char.data.vitality.hp, 20)  # 沒有治療
        self.assertEqual(self.char.data.vitality.temp_hp, 20)  # 獲得護盾

    async def test_interceptor_target_health_above_below(self):
        # 測試攔截器 (on_calculate_damage) 中 target_health_above 和 target_health_below 的過濾判定
        weapon = Equipment(
            name="獵魔巨劍",
            item_type="equipment",
            slot_type="main_hand",
            tier="T1"
        )
        weapon.executable_triggers = [
            {
                "event": "on_calculate_damage",
                "target_health_above": 70.0,
                "actions": [
                    {
                        "action_type": "set_value",
                        "param": "damage_multiplier",
                        "param_value": 2.0
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.main_hand = weapon
        self.monsters[0]["evasion_rate"] = 0.0
        self.char.total_stats["STR"] = 20
        
        # 情況 A: 怪物 HP = 100 (100% 高於 70%) ➜ 觸發 2.0x 傷害倍率
        self.monsters[0]["hp"] = 100
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            # 正常威力: STR 20 * (10/15) + 14.3 = 27.63.
            # 2.0x 倍率 ➜ 55.26. 減免 10 ➜ 最終傷害 45.
            self.assertEqual(res["damage"], 45)
            
        # 情況 B: 怪物 HP = 50 (50% 低於 70%) ➜ 不觸發 2.0x 傷害倍率
        self.monsters[0]["hp"] = 50
        cm2 = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res2 = await cm2.player_attack(0)
            self.assertTrue(res2["success"])
            # 正常威力: STR 20 * (10/15) + 14.3 = 27.63.
            # 無倍率 ➜ 27.63. 減免 10 ➜ 最終傷害 17.
            self.assertEqual(res2["damage"], 17)

    async def test_apply_status_with_attribute_bonuses(self):
        # 測試觸發器 apply_status 動作可正確夾帶並套用屬性加成 (bonuses)
        ring = Equipment(
            name="暴怒之戒",
            item_type="equipment",
            slot_type="ring_1",
            tier="T1"
        )
        ring.executable_triggers = [
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "target": "caster",
                        "status_name": "狂暴之力",
                        "duration": 2,
                        "bonuses": {
                            "STR": 10.0,
                            "crit_rate": 0.10
                        }
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.ring_1 = ring
        self.monsters[0]["evasion_rate"] = 0.0
        self.char.data.status_effects = []
        
        cm = CombatManager(self.char, self.monsters)
        with patch("random.randint", return_value=10):
            res = await cm.player_attack(0)
            self.assertTrue(res["success"])
            
        # 檢查玩家身上是否有「狂暴之力」狀態且夾帶屬性加成
        berserk_status = next((e for e in self.char.data.status_effects if e.name == "狂暴之力"), None)
        self.assertIsNotNone(berserk_status)
        self.assertEqual(berserk_status.bonuses.get("STR"), 10.0)
        self.assertEqual(berserk_status.bonuses.get("crit_rate"), 0.10)

    async def test_combat_stats_incorporates_status_bonuses(self):
        # 測試 character.py 的 combat_stats 正確採計狀態的效果屬性加成
        from core.character import Character
        char_obj = Character(self.char.data, "test_char_999")
        char_obj.data.status_effects = []
        c_stats_before = char_obj.combat_stats
        
        # 施加一個狀態，加成 p_def=15, crit_rate=0.08, luck=3
        char_obj.data.status_effects.append(StatusEffect(
            name="戰神附體",
            duration=3,
            bonuses={
                "p_def": 15.0,
                "crit_rate": 0.08,
                "luck": 3.0
            }
        ))
        
        c_stats_after = char_obj.combat_stats
        # 驗證前後數值差異
        self.assertEqual(c_stats_after["p_def"] - c_stats_before["p_def"], 15)
        self.assertEqual(c_stats_after["luck"] - c_stats_before["luck"], 3)
        # 由於 crit_rate 經過雙曲遞減公式計算，這裡驗證大於原先數值
        self.assertGreater(c_stats_after["crit_rate"], c_stats_before["crit_rate"])

    async def test_stamina_below_condition_trigger(self):
        # 測試觸發器在 stamina_below 條件下的過濾判定
        chest = Equipment(
            name="沉重板甲",
            item_type="equipment",
            slot_type="chest",
            tier="T1"
        )
        chest.executable_triggers = [
            {
                "event": "on_turn_end",
                "condition": "stamina_below(30)",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "target": "caster",
                        "status_name": "疲憊",
                        "duration": 2
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.chest = chest
        self.char.data.vitality.max_stamina = 100
        
        # 情況 A: 精力 = 90 (90/175 = 51% 高於 30%) ➜ 不觸發疲憊
        self.char.data.vitality.stamina = 90
        self.char.data.status_effects = []
        cm = CombatManager(self.char, self.monsters)
        cm.turn_order = [{"type": "player", "speed": 10, "ref": self.char}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        cm.next_turn()  # 觸發 on_turn_end
        self.assertFalse(any(e.name == "疲憊" for e in self.char.data.status_effects))
        
        # 情況 B: 精力 = 20 (20/175 = 11% 低於 30%) ➜ 觸發疲憊
        self.char.data.vitality.stamina = 20
        self.char.data.status_effects = []
        cm2 = CombatManager(self.char, self.monsters)
        cm2.turn_order = [{"type": "player", "speed": 10, "ref": self.char}]
        cm2.current_turn_idx = 0
        cm2._current_turn_ticked = True
        cm2.next_turn()  # 觸發 on_turn_end
    async def test_damage_taken_to_healing(self):
        # 測試傷害等量轉化為治療：受到傷害時，100% 轉為治療
        cotton_pants = Equipment(
            name="阿罵的棉褲",
            item_type="equipment",
            slot_type="legs",
            tier="T1"
        )
        cotton_pants.executable_triggers = [
            {
                "event": "on_damaged",
                "actions": [
                    {
                        "action_type": "heal",
                        "target": "caster",
                        "flat_value": 0.0,
                        "scaling_stat": "DAMAGE_TAKEN",
                        "value_multiplier": 1.0,
                        "target_resource": "hp"
                    }
                ]
            }
        ]
        self.char.data.equipment_slots.legs = cotton_pants
        self.char.data.vitality.max_hp = 100
        self.char.data.vitality.hp = 80  # 初始生命 80
        
        # 讓怪物攻擊玩家
        self.monsters[0]["speed"] = 1
        self.monsters[0]["attack"] = 20 # 造成一定傷害
        self.char.combat_stats["p_def"] = 0
        self.char.combat_stats["evasion_rate"] = 0.0
        
        cm = CombatManager(self.char, self.monsters)
        cm.turn_order = [{"type": "monster", "speed": 1, "ref": self.monsters[0], "index": 0}]
        cm.current_turn_idx = 0
        cm._current_turn_ticked = True
        
        # 模擬怪物攻擊
        # 正常傷害 = attack 20 * roll_mult (0.55 if roll=1) = 11 傷害。
        # 扣減傷害後玩家 hp 變為 80 - 11 = 69 點。
        # 然後觸發 on_damaged，治療 11 * 1.0 = 11 點。
        # 最終玩家生命值應恢復回 69 + 11 = 80 點。
        with patch("random.randint", return_value=1):
            res = await cm.monster_action()
            self.assertTrue(res["success"])
            
        self.assertEqual(self.char.data.vitality.hp, 80)

if __name__ == "__main__":
    unittest.main()
