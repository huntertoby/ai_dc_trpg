import random
import math
from typing import List, Dict, Any, Optional, Union
from core.character import Character
from core.models import Skill, Equipment
from core.skill_processor import SkillProcessor
from core.constants import STAT_TRANSLATIONS

class CombatManager:
    def __init__(self, character: Character, monsters: List[Dict[str, Any]]):
        self.character = character
        self.monsters = monsters
        self.turn_order = []
        self.current_turn_idx = 0
        self.battle_logs = []
        self.is_finished = False
        self.winner = None # 'player' or 'monster'
        
        # 殘響延遲技能佇列
        self.delayed_actions = []
        # 每回合 Tick 狀態標記，防範重覆 Tick 狀態
        self._current_turn_ticked = False
        # 殘響威力減半標記
        self._echo_cast_active = False
        
        # 初始化上一回合的生命與魔法快照
        self.character._hp_snapshot = self.character.data.vitality.hp
        self.character._mp_snapshot = self.character.data.vitality.mp
        
        self._initialize_battle()

    def _initialize_battle(self):
        """初始化戰鬥：決定行動順序"""
        entities = []
        # 玩家加入順序 (速度 + 1d10 + 基礎先攻加成 10)
        p_speed = 10 + self.character.total_stats["DEX"] + random.randint(1, 10)
        entities.append({"type": "player", "speed": p_speed, "ref": self.character})
        
        # 怪物加入順序
        for i, m in enumerate(self.monsters):
            m_speed = m["speed"] + random.randint(1, 10)
            entities.append({"type": "monster", "speed": m_speed, "ref": m, "index": i})
            
        # 排序：速度高者先行動
        self.turn_order = sorted(entities, key=lambda x: x["speed"], reverse=True)
        self.battle_logs.append("⚔️ 戰鬥開始！行動順序已決定。")
        
        # 針對第一個行動者，進行狀態 Tick (處理可能已有的 Stun/Burn 等)
        self._tick_current_entity_at_turn_start()

    def get_current_entity(self) -> Dict[str, Any]:
        return self.turn_order[self.current_turn_idx]

    def next_turn(self):
        """切換到下一個行動者"""
        try:
            curr_entity = self.get_current_entity()
            if curr_entity["type"] == "player":
                self.character._hp_snapshot = self.character.data.vitality.hp
                self.character._mp_snapshot = self.character.data.vitality.mp
        except Exception:
            pass
            
        self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
        self._current_turn_ticked = False
        
        self._tick_current_entity_at_turn_start()

    def _has_status(self, entity, is_player: bool, status_name: str) -> bool:
        if is_player:
            return any(e.name == status_name for e in self.character.data.status_effects)
        else:
            effects = entity.get("status_effects", [])
            return any(
                (e.name == status_name if hasattr(e, "name") else e.get("name") == status_name)
                for e in effects
            )

    def _remove_status(self, entity, is_player: bool, status_name: str):
        if is_player:
            self.character.data.status_effects = [e for e in self.character.data.status_effects if e.name != status_name]
            self.character.save()
        else:
            if "status_effects" in entity:
                entity["status_effects"] = [
                    e for e in entity["status_effects"]
                    if (e.name != status_name if hasattr(e, "name") else e.get("name") != status_name)
                ]

    def _get_entity_defense(self, entity, damage_type: str, is_player: bool) -> int:
        if is_player:
            c_stats = self.character.combat_stats
            base_def = c_stats["p_def"] if damage_type == "physical" else c_stats["m_def"]
            status_def_bonus = 0
            stat_key = "p_def" if damage_type == "physical" else "m_def"
            for effect in self.character.data.status_effects:
                if stat_key in effect.bonuses:
                    status_def_bonus += effect.bonuses[stat_key]
            return max(0, int(base_def + status_def_bonus))
        else:
            base_def = entity.get("defense", 0) if damage_type == "physical" else entity.get("m_defense", 0)
            status_def_bonus = 0
            stat_key = "p_def" if damage_type == "physical" else "m_def"
            alt_key = "defense" if damage_type == "physical" else "m_defense"
            effects = entity.get("status_effects", [])
            for effect in effects:
                bonuses = effect.bonuses if hasattr(effect, "bonuses") else effect.get("bonuses", {})
                if stat_key in bonuses:
                    status_def_bonus += bonuses[stat_key]
                elif alt_key in bonuses:
                    status_def_bonus += bonuses[alt_key]
            return max(0, int(base_def + status_def_bonus))

    def _get_entity_evasion(self, entity, is_player: bool) -> float:
        if is_player:
            evasion = self.character.combat_stats.get("evasion_rate", 0.05)
            return max(0.0, min(1.0, evasion))
        else:
            if self._has_status(entity, is_player=False, status_name="Slow"):
                return 0.0
            return max(0.0, min(1.0, entity.get("evasion_rate", 0.05)))

    def _decay_status_effects(self, entity, is_player: bool) -> List[str]:
        expired = []
        if is_player:
            remaining = []
            for effect in self.character.data.status_effects:
                if effect.duration_type == "turns":
                    effect.duration -= 1
                    if effect.duration > 0:
                        remaining.append(effect)
                    else:
                        expired.append(effect.name)
                else:
                    remaining.append(effect)
            self.character.data.status_effects = remaining
            self.character.save()
        else:
            if "status_effects" in entity:
                remaining = []
                for effect in entity["status_effects"]:
                    name = effect.name if hasattr(effect, "name") else effect.get("name")
                    duration = effect.duration if hasattr(effect, "duration") else effect.get("duration", 0)
                    duration -= 1
                    if hasattr(effect, "duration"):
                        effect.duration = duration
                    else:
                        effect["duration"] = duration
                        
                    if duration > 0:
                        remaining.append(effect)
                    else:
                        expired.append(name)
                entity["status_effects"] = remaining
        return expired

    def _process_entity_status_tick(self, entity_ref, is_player: bool) -> tuple[bool, Optional[str]]:
        name = self.character.data.name if is_player else entity_ref.get("name", "未知單位")
        logs = []
        skip_turn = False
        
        # 1. 結算 Burn (灼燒) DoT 傷害
        if self._has_status(entity_ref, is_player, "Burn"):
            level = self.character.data.level if is_player else entity_ref.get("level", 1)
            burn_dmg = 10 + level
            
            if is_player:
                temp_hp = self.character.data.vitality.temp_hp
                if temp_hp > 0:
                    if temp_hp >= burn_dmg:
                        self.character.data.vitality.temp_hp -= burn_dmg
                        logs.append(f"🔥 {name} 受到灼燒 DoT {burn_dmg} 點傷害，被護盾完全吸收！")
                        burn_dmg = 0
                    else:
                        burn_dmg -= temp_hp
                        self.character.data.vitality.temp_hp = 0
                        logs.append(f"🔥 {name} 受到灼燒 DoT 傷害，護盾破裂吸收了 {temp_hp} 點！")
                
                if burn_dmg > 0:
                    self.character.data.vitality.hp = max(0, self.character.data.vitality.hp - burn_dmg)
                    logs.append(f"🔥 {name} 受到灼燒 DoT，扣除 {burn_dmg} 點生命值！")
                self.character.save()
            else:
                temp_hp = entity_ref.get("temp_hp", 0)
                if temp_hp > 0:
                    if temp_hp >= burn_dmg:
                        entity_ref["temp_hp"] -= burn_dmg
                        logs.append(f"🔥 {name} 受到灼燒 DoT {burn_dmg} 點傷害，被護盾完全吸收！")
                        burn_dmg = 0
                    else:
                        burn_dmg -= temp_hp
                        entity_ref["temp_hp"] = 0
                        logs.append(f"🔥 {name} 受到灼燒 DoT 傷害，護盾破裂吸收了 {temp_hp} 點！")
                
                if burn_dmg > 0:
                    entity_ref["hp"] = max(0, entity_ref["hp"] - burn_dmg)
                    logs.append(f"🔥 {name} 受到灼燒 DoT，扣除 {burn_dmg} 點生命值！")
            
            self._check_battle_status()
            if self.is_finished:
                return True, "\n".join(logs)
                
        # 2. 處理 Echo (殘響) 的延遲法術觸發 (僅在玩家回合開始時)
        if is_player and self.delayed_actions:
            player_actions = [a for a in self.delayed_actions if a.get("caster_type") == "player"]
            for action in player_actions:
                self.delayed_actions.remove(action)
                skill = action.get("skill")
                target_idx = action.get("target_idx")
                
                target = self.monsters[target_idx] if target_idx < len(self.monsters) else None
                if not target or target["hp"] <= 0:
                    alive_indices = [i for i, m in enumerate(self.monsters) if m["hp"] > 0]
                    if alive_indices:
                        target_idx = alive_indices[0]
                        target = self.monsters[target_idx]
                    else:
                        target = None
                
                if target:
                    logs.append(f"🔊 觸發【殘響】重播：準備以 50% 威力再次施放【{skill.name}】！")
                    self._echo_cast_active = True
                    try:
                        res = SkillProcessor.execute_skill(skill, self.character, target, self)
                        logs.extend(res.get("logs", []))
                    except Exception as e:
                        logs.append(f"❌ 殘響施法失敗：{str(e)}")
                    finally:
                        self._echo_cast_active = False
                    self._check_battle_status()
                    if self.is_finished:
                        return True, "\n".join(logs)

        # 3. 判定 Stun (暈眩) 是否需要跳過本回合
        if self._has_status(entity_ref, is_player, "Stun"):
            skip_turn = True
            logs.append(f"🌀 {name} 處於暈眩狀態，無法行動！")

        # 4. 判定 Confusion (混亂) 的 50% 取消行動檢定
        elif self._has_status(entity_ref, is_player, "Confusion"):
            if random.random() < 0.5:
                skip_turn = True
                logs.append(f"💫 {name} 處於混亂狀態，直接取消了本回合的行動！")
                
        # 5. 遞減 status_effects 的 duration
        expired = self._decay_status_effects(entity_ref, is_player)
        if expired:
            logs.append(f"⏳ {name} 的狀態效果結束：{', '.join(expired)}")
            
        return skip_turn, "\n".join(logs) if logs else None

    def _tick_current_entity_at_turn_start(self):
        if self.is_finished:
            return
            
        if self._current_turn_ticked:
            return
            
        curr = self.get_current_entity()
        if curr["type"] == "monster" and curr["ref"]["hp"] <= 0:
            self.next_turn()
            return
            
        self._current_turn_ticked = True
        is_player = (curr["type"] == "player")
        entity_ref = curr["ref"]
        
        skip_turn, log_msg = self._process_entity_status_tick(entity_ref, is_player)
        if log_msg:
            self.battle_logs.append(log_msg)
            
        if skip_turn:
            self.next_turn()

    def _apply_damage(self, target, is_target_player: bool, damage: int, source_entity, is_source_player: bool) -> tuple[int, List[str]]:
        logs = []
        final_dmg = damage
        
        # 1. 檢查 Reflect 反射
        if self._has_status(target, is_target_player, "Reflect"):
            reflected_dmg = max(1, round(final_dmg * 0.5))
            final_dmg = max(1, round(final_dmg * 0.5))
            
            if is_source_player:
                self.character.data.vitality.hp = max(0, self.character.data.vitality.hp - reflected_dmg)
                self.character.save()
                logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對 {self.character.data.name} 反彈了 {reflected_dmg} 點傷害！")
            else:
                source_entity["hp"] = max(0, source_entity["hp"] - reflected_dmg)
                logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對 {source_entity['name']} 反彈了 {reflected_dmg} 點傷害！")
                
            self._remove_status(target, is_target_player, "Reflect")
            
        # 記錄被護盾扣減之前的傷害，用於回傳與日誌顯示
        damage_before_shield = final_dmg
            
        # 2. 扣除 temp_hp
        if is_target_player:
            temp_hp = self.character.data.vitality.temp_hp
            if temp_hp > 0:
                if temp_hp >= final_dmg:
                    self.character.data.vitality.temp_hp -= final_dmg
                    logs.append(f"🛡️ 護盾 (temp_hp) 抵擋了所有傷害！剩餘護盾：{self.character.data.vitality.temp_hp}")
                    final_dmg = 0
                else:
                    final_dmg -= temp_hp
                    self.character.data.vitality.temp_hp = 0
                    logs.append(f"🛡️ 護盾 (temp_hp) 被擊破，抵擋了 {temp_hp} 點傷害！")
            self.character.save()
        else:
            temp_hp = target.get("temp_hp", 0)
            if temp_hp > 0:
                if temp_hp >= final_dmg:
                    target["temp_hp"] -= final_dmg
                    logs.append(f"🛡️ 護盾 (temp_hp) 抵擋了所有傷害！剩餘護盾：{target['temp_hp']}")
                    final_dmg = 0
                else:
                    final_dmg -= temp_hp
                    target["temp_hp"] = 0
                    logs.append(f"🛡️ 護盾 (temp_hp) 被擊破，抵擋了 {temp_hp} 點傷害！")
                    
        # 3. 扣除實際生命值
        if final_dmg > 0:
            if is_target_player:
                self.character.data.vitality.hp = max(0, self.character.data.vitality.hp - final_dmg)
                self.character.save()
            else:
                target["hp"] = max(0, target["hp"] - final_dmg)
                
        self._check_battle_status()
        return damage_before_shield, logs

    async def player_attack(self, target_idx: Optional[int] = None) -> Dict[str, Any]:
        """玩家進行普通攻擊 (TRPG 1d20 風格)"""
        curr_before = self.get_current_entity()
        if curr_before["type"] != "player": return {"success": False, "msg": "不是玩家的回合。"}
        
        # Ensure status tick is run for this turn
        self._tick_current_entity_at_turn_start()
        
        # Check if the turn changed or battle finished
        curr_after = self.get_current_entity()
        if self.is_finished:
            return {"success": False, "msg": "戰鬥已結束。"}
        if curr_after["type"] != "player":
            return {"success": False, "msg": f"👤 {self.character.data.name} 因暈眩/混亂跳過此回合。"}
            
        # 判定自身是否放逐 (Banish)
        if self._has_status(self.character, is_player=True, status_name="Banish"):
            return {"success": False, "msg": f"🌀 {self.character.data.name} 處於放逐狀態，自身無法進行普通攻擊！"}
            
        if target_idx is None:
            alive_indices = [i for i, m in enumerate(self.monsters) if m["hp"] > 0]
            if not alive_indices:
                return {"success": False, "msg": "戰場上沒有存活的目標！"}
            target_idx = alive_indices[0]

        target = self.monsters[target_idx]
        c_stats = self.character.combat_stats
        
        # 1. 取得屬性修正與武器加成
        main_hand = self.character.data.equipment_slots.main_hand
        scaling_stat = "STR"
        damage_type = "physical"
        divisor = 20.0  # 預設無裝備（赤手空拳）
        weapon_power = 0.0
        
        if main_hand and isinstance(main_hand, Equipment):
            scaling_stat = main_hand.scaling_stat
            damage_type = main_hand.damage_type
            divisor = 10.0 if main_hand.is_two_handed else 15.0
            
            # 優先讀取武器自帶的 ATK，若無 (舊武器) 則動態計算
            weapon_power = main_hand.bonuses.get("ATK", 0.0)
            if weapon_power == 0.0:
                ilvl = main_hand.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(main_hand.tier, 1.0)
                if main_hand.is_two_handed:
                    weapon_power = (15.0 + ilvl * 3.0) * mult
                else:
                    weapon_power = (5.0 + ilvl * 1.5) * mult
            
        stat_val = self.character.total_stats.get(scaling_stat, 10)
        
        # 2. 判定 Banish
        if self._has_status(target, is_player=False, status_name="Banish"):
            return {"success": False, "msg": f"🌀 目標 {target['name']} 處於放逐狀態，普通攻擊無法命中！"}
            
        # 3. 傷害計算 (1d20 乘法公式)
        dmg_roll = random.randint(1, 20)
        
        # 判定 Bless 補底
        has_bless = self._has_status(self.character, is_player=True, status_name="Bless")
        bless_msg = ""
        if has_bless and dmg_roll < 5:
            dmg_roll = 10
            bless_msg = "\n🌟 **觸發【祝福】補底**：擲骰小於 5，自動補底為 10！"
            
        roll_mult = dmg_roll / divisor
        
        # 基礎威力 = 屬性 * (1d20 / 武器分母) + 武器 ATK
        base_power = (stat_val * roll_mult) + weapon_power
        
        # 4. 判定爆擊 (1.5x)
        is_crit = random.random() < c_stats["crit_rate"]
        crit_mult = 1.5 if is_crit else 1.0
        
        # 5. 計算總威力 (基 * 爆)
        total_power = base_power * crit_mult
        
        # 6. 防禦力動態減免 (限制防禦力最大只能抵擋 80% 威力)
        defense = self._get_entity_defense(target, damage_type, is_player=False)
        max_mitigation = total_power * 0.80
        effective_def = min(defense, max_mitigation)
        
        final_dmg = max(1.0, round(total_power - effective_def, 1))
        
        # 7. 應用傷害
        actual_dmg, dmg_logs = self._apply_damage(target, is_target_player=False, damage=int(final_dmg), source_entity=self.character, is_source_player=True)
        
        crit_tag = "✨ **爆擊！** " if is_crit else ""
        crit_info = f" * 💥1.5x" if is_crit else ""
        
        stat_name = STAT_TRANSLATIONS.get(scaling_stat, scaling_stat)
        base_breakdown = f"{stat_name}:{stat_val} * ({dmg_roll}/{divisor}) + 攻:{weapon_power:.1f}"
        
        calc_info = (
            f"\n 🎲 **判定**: {dmg_roll} (分母 {divisor}){bless_msg}"
            f"\n 📊 **威力**: ({base_breakdown}){crit_info}"
            f"\n 🛡️ **減免**: - 敵方防禦 {defense:.1f} (有效減免: {effective_def:.1f}，上限 80%)"
        )
        
        log_suffix = "\n" + "\n".join(dmg_logs) if dmg_logs else ""
        msg = f"{crit_tag}💥 {self.character.data.name} 對 {target['name']} 造成了 {actual_dmg} 點傷害！{calc_info}{log_suffix}"
        
        if target["hp"] <= 0:
            msg += f"\n💀 {target['name']} 倒下了！"
            
        if not self.is_finished:
            self.next_turn()
            
        return {"success": True, "damage": actual_dmg, "is_crit": is_crit, "msg": msg}

    async def monster_action(self) -> Dict[str, Any]:
        """處理當前怪物的 AI 行動 (TRPG 風格)"""
        curr_before = self.get_current_entity()
        if curr_before["type"] != "monster": return {"success": False}
        monster = curr_before["ref"]
        c_stats = self.character.combat_stats
        
        # Ensure status tick is run for this turn
        self._tick_current_entity_at_turn_start()
        
        # Check if the turn changed or battle finished
        curr_after = self.get_current_entity()
        if self.is_finished:
            return {"success": False, "msg": "戰鬥已結束。"}
        if curr_after["type"] != "monster" or curr_after["ref"] is not monster:
            return {"success": False, "msg": f"👾 {monster['name']} 因暈眩/混難或已死亡跳過此回合。"}
            
        # 判定自身是否放逐 (Banish)
        if self._has_status(monster, is_player=False, status_name="Banish"):
            return {"success": False, "msg": f"🌀 {monster['name']} 處於放逐狀態，自身無法進行普通攻擊！"}
            
        # 檢查是否為召喚物
        is_summon = monster.get("is_summon", False)
        
        if is_summon:
            # 召喚物行動：攻擊敵方怪物
            alive_enemies = [m for m in self.monsters if m["hp"] > 0 and not m.get("is_summon")]
            if not alive_enemies:
                return {"success": False, "msg": f"🌀 {monster['name']} 四處張望，沒有發現敵人。"}
                
            target = random.choice(alive_enemies)
            # 1. 命中判定
            if random.randint(1, 100) > 90:
                return {"success": False, "msg": f"🛡️ {target['name']} 躲過了 {monster['name']} 的攻擊！"}
                
            # 2. 減傷計算
            defense = self._get_entity_defense(target, "physical", is_player=False)
            
            m_roll = random.randint(1, 20)
            m_roll_mult = 0.5 + (m_roll * 0.05)
            total_m_power = monster["attack"] * m_roll_mult
            
            final_dmg = max(1, round(total_m_power - defense))
            
            # 3. 應用傷害
            actual_dmg, dmg_logs = self._apply_damage(target, is_target_player=False, damage=final_dmg, source_entity=monster, is_source_player=False)
            
            log_suffix = "\n" + "\n".join(dmg_logs) if dmg_logs else ""
            msg = f"⚔️ {monster['name']} 攻擊了 {target['name']}，造成 {actual_dmg} 點傷害！{log_suffix}"
            if target["hp"] <= 0:
                msg += f"\n💀 {target['name']} 倒下了！"
                
            return {"success": True, "damage": actual_dmg, "msg": msg}
            
        else:
            # 正常怪物行動
            # 1. 確定攻擊目標
            is_charmed = self._has_status(monster, is_player=False, status_name="Charm")
            is_taunted = self._has_status(monster, is_player=False, status_name="Taunt")
            
            target_entity = None
            is_target_player = True
            
            if is_charmed:
                # Charmed: attack another monster
                alive_other_monsters = [m for m in self.monsters if m["hp"] > 0 and m is not monster and not m.get("is_summon")]
                if alive_other_monsters:
                    target_entity = random.choice(alive_other_monsters)
                    is_target_player = False
                    
            if target_entity is None:
                # Check for summons
                alive_summons = [m for m in self.monsters if m["hp"] > 0 and m.get("is_summon")]
                if alive_summons and not is_taunted:
                    # 50% chance to target player, 50% to target a summon
                    if random.random() < 0.5:
                        target_entity = random.choice(alive_summons)
                        is_target_player = False
                        
            if target_entity is None:
                # Default target is player
                target_entity = self.character
                is_target_player = True
                
            target_name = self.character.data.name if is_target_player else target_entity["name"]
            
            # 2. 判定 Banish
            if self._has_status(target_entity, is_target_player, "Banish"):
                return {"success": False, "msg": f"🌀 {target_name} 處於放逐狀態，{monster['name']} 的攻擊無法命中！"}
                
            # 3. 命中判定
            evasion_rate = self._get_entity_evasion(target_entity, is_target_player)
            hit_chance = 90 - (evasion_rate * 100)
            
            # 判定 Invis
            if self._has_status(target_entity, is_target_player, "Invis"):
                hit_chance *= 0.3
                
            if random.randint(1, 100) > hit_chance:
                if is_target_player:
                    return {"success": False, "msg": f"🛡️ {self.character.data.name} 靈巧地躲過了 {monster['name']} 的攻擊！ (迴避 {evasion_rate*100:.1f}%)"}
                else:
                    return {"success": False, "msg": f"🛡️ {target_name} 躲過了 {monster['name']} 的攻擊！"}
                    
            # 4. 減傷計算
            damage_type = monster.get("damage_type", "physical")
            defense = self._get_entity_defense(target_entity, damage_type, is_player=is_target_player)
            
            # 韌性減傷 (比例減傷，僅對玩家生效)
            tenacity_reduction = 1.0
            if is_target_player:
                tenacity_reduction = 1.0 - (c_stats["tenacity"] / 1000)
                tenacity_reduction = max(0.5, tenacity_reduction)
                
            # 怪物傷害：1d20 效能倍率 * (基礎攻擊力)
            m_roll = random.randint(1, 20)
            m_roll_mult = 0.5 + (m_roll * 0.05)
            total_m_power = monster["attack"] * m_roll_mult
            
            # 最終傷害 = (威力 - 限制防禦力最大只能抵擋 80% 威力) * 韌性比例減傷
            max_mitigation = total_m_power * 0.80
            effective_def = min(defense, max_mitigation)
            
            final_dmg = max(1.0, round((total_m_power - effective_def) * tenacity_reduction, 1))
            
            # 5. 應用傷害
            actual_dmg, dmg_logs = self._apply_damage(target_entity, is_target_player, int(final_dmg), monster, is_source_player=False)
            
            # 6. 組裝日誌與說明
            lvl_bonus = self.character.data.level // 2 if is_target_player else target_entity.get("level", 1) // 2
            ts = self.character.total_stats
            
            if is_target_player:
                stat_def = (ts["CON"] * 0.7) + (ts["STR"] * 0.2) + (ts["DEX"] * 0.1)
                def_formula = f"體質:{ts['CON']}*0.7 + 力量:{ts['STR']}*0.2 + 敏捷:{ts['DEX']}*0.1"
                calc_info = (
                    f"\n 🎲 **判定**: {m_roll} (效能 {m_roll_mult:.2f})"
                    f"\n 📊 **威力**: {monster['attack']} * {m_roll_mult:.2f}"
                    f"\n 🛡️ **防禦**: -{defense:.1f} (屬防:{stat_def:.1f} ({def_formula}) + 等級:{lvl_bonus}) (有效減免: {effective_def:.1f}，上限 80%)"
                    f"\n ✨ **減傷**: 韌性免傷 {(1-tenacity_reduction)*100:.0f}%"
                )
            else:
                calc_info = (
                    f"\n 🎲 **判定**: {m_roll} (效能 {m_roll_mult:.2f})"
                    f"\n 📊 **威力**: {monster['attack']} * {m_roll_mult:.2f}"
                    f"\n 🛡️ **防禦**: -{defense:.1f} (有效減免: {effective_def:.1f}，上限 80%)"
                )
                
            log_suffix = "\n" + "\n".join(dmg_logs) if dmg_logs else ""
            msg = f"💢 {monster['name']} 攻擊了 {target_name}，造成 {actual_dmg} 點傷害！{calc_info}{log_suffix}"
            
            if not is_target_player and target_entity["hp"] <= 0:
                msg += f"\n💀 {target_name} 倒下了！"
                
            return {"success": True, "damage": actual_dmg, "msg": msg}

    async def cast_skill(self, skill: Skill, target_idx: Optional[int] = None) -> Dict[str, Any]:
        """
        在戰鬥中施展技能，連動 SkillProcessor 並套用流程控制標記與狀態。
        """
        if self.is_finished:
            return {"success": False, "msg": "戰鬥已經結束。"}

        curr_before = self.get_current_entity()
        if curr_before["type"] != "player": return {"success": False, "msg": "不是玩家的回合。"}
        
        # Ensure status tick is run for this turn
        self._tick_current_entity_at_turn_start()
        
        # Check if the turn changed or battle finished
        curr_after = self.get_current_entity()
        if self.is_finished:
            return {"success": False, "msg": "戰鬥已結束。"}
        if curr_after["type"] != "player":
            return {"success": False, "msg": f"👤 {self.character.data.name} 因暈眩/混亂跳過此回合。"}
            
        # 如果沒有指定 target_idx，自動尋找第一個存活的怪物
        if target_idx is None:
            alive_indices = [i for i, m in enumerate(self.monsters) if m["hp"] > 0]
            if not alive_indices:
                return {"success": False, "msg": "戰場上沒有存活的目標！"}
            target_idx = alive_indices[0]

        # 狂暴 (Berserk) 限制
        if self._has_status(self.character, is_player=True, status_name="Berserk"):
            alive_monsters = [i for i, m in enumerate(self.monsters) if m["hp"] > 0]
            if alive_monsters:
                chosen_target = random.choice(alive_monsters)
            else:
                chosen_target = target_idx
            attack_res = await self.player_attack(chosen_target)
            return {
                "success": True,
                "msg": f"🩸 施法者正處於狂暴狀態！無法使用技能，強制發動普通攻擊！\n{attack_res.get('msg', '')}",
                "final_value": attack_res.get("damage", 0),
                "is_quickcast": False,
                "finished": self.is_finished
            }

        # 取得目標怪物
        target = self.monsters[target_idx]
        
        try:
            # 呼叫技能執行器
            res = SkillProcessor.execute_skill(skill, self.character, target, self)
        except ValueError as e:
            return {"success": False, "msg": f"❌ 施法失敗：{str(e)}"}
            
        logs = res.get("logs", [])
        control_flags = res.get("control_flags", {})
        
        # 檢查戰鬥狀態
        self._check_battle_status()
        
        # 處理流程標記連動：
        
        # 1. 瞬發 (Quickcast)：允許連續行動
        is_quickcast = control_flags.get("quickcast", False)
        
        # 貪婪 (Greed) 結算
        if control_flags.get("greed_active") and target["hp"] <= 0:
            multiplier = random.randint(2, 3)
            orig_gold = target.get("gold_reward", 0)
            target["gold_reward"] = orig_gold * multiplier
            logs.append(f"💰 觸發【貪婪】：擊殺目標，使其金幣掉落翻了 {multiplier} 倍 (從 {orig_gold}G 提升至 {target['gold_reward']}G)！")
        
        # 2. 連鎖 (Chain)：在敵人列表中尋找存活敵人，進行額外傷害
        if control_flags.get("chain_active") and not self.is_finished:
            alive_others = [i for i, m in enumerate(self.monsters) if m["hp"] > 0 and i != target_idx]
            if alive_others:
                next_target_idx = alive_others[0]
                next_target = self.monsters[next_target_idx]
                
                chain_val = round(res.get("final_value", 0) * 0.5, 1)
                next_target["hp"] -= int(chain_val)
                logs.append(f"⚡ 觸發【連鎖彈射】：對 {next_target['name']} 造成了 {chain_val} 點彈射傷害 (傷害減半)！")
                if next_target["hp"] <= 0:
                    logs.append(f"💀 {next_target['name']} 倒下了！")
                    
        # 3. 召喚 (Summon) 標記：向戰鬥序列中添加隨從
        if control_flags.get("summon_active"):
            summon_entity = {
                "name": "召喚火靈",
                "hp": 50,
                "max_hp": 50,
                "attack": 15,
                "defense": 2,
                "m_defense": 2,
                "speed": 8,
                "level": self.character.data.level,
                "gold_reward": 0,
                "exp_reward": 0,
                "is_summon": True
            }
            m_speed = summon_entity["speed"] + random.randint(1, 10)
            self.turn_order.append({"type": "monster", "speed": m_speed, "ref": summon_entity, "index": len(self.monsters)})
            self.monsters.append(summon_entity)
            logs.append("🌀 戰場上多出了一個【召喚火靈】加入序列！")
            
        # 4. 殘響 (Echo) 標記
        if control_flags.get("echo_active"):
            self.delayed_actions.append({
                "caster_type": "player",
                "skill": skill,
                "target_idx": target_idx
            })
            logs.append("🔊 【殘響】已佇列，將在下回合自動重複發動。")

        # 5. 狂暴 (Berserk) 標記
        if control_flags.get("berserk_active"):
            logs.append("🩸 施法者雙眼通紅，陷入狂暴姿態！")

        self._check_battle_status()
        
        # 組合訊息
        skill_logs = "\n" + "\n".join(logs) if logs else ""
        msg = f"🌟 {self.character.data.name} 施展了技能【{skill.name}】！{skill_logs}"
        
        # 如果是瞬發，本回合不切換，直接回傳
        if not is_quickcast and not self.is_finished:
            self.next_turn()
            
        return {
            "success": True, 
            "msg": msg, 
            "final_value": res.get("final_value", 0), 
            "is_quickcast": is_quickcast,
            "finished": self.is_finished
        }

    def _check_battle_status(self):
        """檢查戰鬥是否結束"""
        if self.character.data.vitality.hp <= 0:
            self.is_finished = True
            self.winner = "monster"
            return
            
        non_summon_monsters = [m for m in self.monsters if not m.get("is_summon")]
        if all(m["hp"] <= 0 for m in non_summon_monsters):
            self.is_finished = True
            self.winner = "player"
            return

    def get_battle_summary(self) -> str:
        status = f"👤 **{self.character.data.name}**: {self.character.data.vitality.hp}/{self.character.max_hp} HP\n"
        for i, m in enumerate(self.monsters):
            level_str = f"Lv.{m['level']}"
            hp_str = f"{max(0, m['hp'])}/{m['max_hp']} HP"
            status += f"👾 #{i} **{m['name']}** ({level_str}): {hp_str} {'(已倒下)' if m['hp'] <= 0 else ''}\n"
        return status

    def get_valid_targets(self) -> List[Dict[str, Any]]:
        """回傳目前所有存活敵人的基本資訊，方便 UI 呈現與選擇"""
        return [
            {"index": i, "name": m["name"], "hp": m["hp"], "max_hp": m["max_hp"], "level": m["level"]}
            for i, m in enumerate(self.monsters) if m["hp"] > 0
        ]
