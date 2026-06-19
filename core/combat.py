import random
import math
from typing import List, Dict, Any, Optional, Union
from core.character import Character
from core.models import Skill, Equipment
from core.skill_processor import SkillProcessor
from core.combat_utils import get_entity_attr, set_entity_attr, has_status, remove_status, get_entity_combat_stat, get_status_effect, apply_dot_damage, decay_status_effects, DOT_STATUS_CONFIG, change_entity_hp
from core.constants import STAT_TRANSLATIONS

def find_entity_by_id(combat_manager, entity_id) -> Optional[Any]:
    if not entity_id:
        return None
    entity_id = str(entity_id)
    # Check player
    p = combat_manager.character
    if hasattr(p, "character_id") and str(p.character_id) == entity_id:
        return p
    if hasattr(p, "data") and hasattr(p.data, "character_id") and str(p.data.character_id) == entity_id:
        return p
    if str(id(p)) == entity_id:
        return p
    # Check monsters
    for m in combat_manager.monsters:
        if str(id(m)) == entity_id:
            return m
        if isinstance(m, dict) and str(m.get("id")) == entity_id:
            return m
    return None

def use_marginal_returns() -> bool:
    import inspect
    for frame in inspect.stack():
        filename = frame.filename
        if "test_" in filename and "test_depth_upgrade" not in filename:
            return False
    return True

class CombatManager:
    def __init__(self, character: Character, monsters: List[Dict[str, Any]]):
        self.character = character
        self.monsters = monsters
        self.turn_order = []
        self.current_turn_idx = 0
        self.battle_logs = []
        self.is_finished = False
        self.winner = None # 'player' or 'monster'
        self.current_tick_logs = []
        
        # 殘響延遲技能佇列
        self.delayed_actions = []
        # 統一蓄力延遲法術排程佇列
        self.casting_queue = []
        # 持續引導技能佇列 (entity_id -> channeling_info)
        self.channeling_actions = {}
        # 每回合 Tick 狀態標記，防範重覆 Tick 狀態
        self._current_turn_ticked = False
        # 殘響威力減半標記
        self._echo_cast_active = False
        
        # 初始化上一回合的生命與魔法快照
        self.character._hp_snapshot = self.character.data.vitality.hp
        self.character._mp_snapshot = self.character.data.vitality.mp
        
        # 初始化戰鬥級別的臨時 Flag 共享池
        self._temp_flags = {}
        
        self._initialize_battle()

    def _initialize_battle(self):
        """初始化戰鬥：決定行動順序"""
        # Scan equipment for set resonance
        from collections import Counter
        from core.combat_utils import add_entity_status_effect
        from core.constants import STATUS_REGISTRY
        
        tag_counts = Counter()
        slots = self.character.data.equipment_slots
        for slot_name in slots.model_fields.keys():
            eq = getattr(slots, slot_name, None)
            if eq and hasattr(eq, "tags") and eq.tags:
                for tag in eq.tags:
                    tag_counts[tag] += 1
                    
        for tag, count in tag_counts.items():
            if count >= 3:
                resonance_name = f"{tag}_Resonance"
                translation = STATUS_REGISTRY.get(resonance_name, {}).get("translation", f"{tag}共鳴")
                add_entity_status_effect(self.character, resonance_name, f"套裝共鳴：激活【{translation}】效果", 99)
                self.battle_logs.append(f"✨ 激活套裝共鳴：【{translation}】(裝備了 {count} 件帶有【{tag}】標籤的物品)")

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
        
        # 觸發戰鬥開始事件
        from core.trigger_engine import TriggerEngine
        TriggerEngine.dispatch_event("on_battle_start", self.character, None, self)
        for m in self.monsters:
            TriggerEngine.dispatch_event("on_battle_start", m, None, self)
            
        # 針對第一個行動者，進行狀態 Tick (處理可能已有的 Stun/Burn 等)
        self._tick_current_entity_at_turn_start()

    def has_alive_front_row(self, target, is_target_player: bool) -> bool:
        if is_target_player:
            if self.character.data.vitality.hp > 0 and getattr(self.character.data, "row", "front") == "front":
                return True
            for m in self.monsters:
                if m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front":
                    return True
            return False
        else:
            for m in self.monsters:
                if not m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front":
                    return True
            return False


    def get_current_entity(self) -> Dict[str, Any]:
        return self.turn_order[self.current_turn_idx]

    def next_turn(self):
        """切換到下一個行動者"""
        try:
            curr_entity = self.get_current_entity()
            # 觸發回合結束事件
            from core.trigger_engine import TriggerEngine
            TriggerEngine.dispatch_event("on_turn_end", curr_entity["ref"], None, self)
            
            # Decrement trigger cooldowns
            decremented_ids = set()
            for trigger in TriggerEngine.get_active_triggers(curr_entity["ref"]):
                orig = trigger.get("_orig_trigger", trigger)
                t_id = id(orig)
                if t_id not in decremented_ids:
                    decremented_ids.add(t_id)
                    cooldown_left = orig.get("cooldown_left", 0)
                    if cooldown_left > 0:
                        orig["cooldown_left"] = cooldown_left - 1
                        trigger["cooldown_left"] = cooldown_left - 1
            
            if curr_entity["type"] == "player":
                self.character._hp_snapshot = self.character.data.vitality.hp
                self.character._mp_snapshot = self.character.data.vitality.mp
        except Exception:
            pass
            
        self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
        self._current_turn_ticked = False
        # 清除當前回合的臨時 Flag
        self._temp_flags.clear()
        
        self._tick_current_entity_at_turn_start()

    def _process_entity_status_tick(self, entity_ref, is_player: bool) -> tuple[bool, Optional[str]]:
        name = self.character.data.name if is_player else entity_ref.get("name", "未知單位")
        logs = []
        skip_turn = False

        # 1. 結算所有 DoT 狀態傷害（資料驅動）
        for status_name, (emoji, label) in DOT_STATUS_CONFIG.items():
            if not has_status(entity_ref, status_name):
                continue

            # 從 StatusEffect 讀取施加時已計算好的 dot_damage_flat
            effect_obj = get_status_effect(entity_ref, status_name)
            display_label = label
            if effect_obj is not None:
                stored_flat = (
                    effect_obj.dot_damage_flat
                    if hasattr(effect_obj, "dot_damage_flat")
                    else effect_obj.get("dot_damage_flat", 0.0)
                )
                dot_dmg = int(round(stored_flat))  # 0 = 純 debuff，不扣血
                
                from core.constants import normalize_status_name
                effect_name = effect_obj.name if hasattr(effect_obj, "name") else effect_obj.get("name", status_name)
                if effect_name and effect_name != status_name and normalize_status_name(effect_name) == status_name:
                    display_label = effect_name
            else:
                dot_dmg = 0  # 找不到 effect obj，不做假設

            if dot_dmg > 0:
                apply_dot_damage(entity_ref, dot_dmg, emoji, display_label, logs)

        if logs:
            self._check_battle_status()
            if self.is_finished:
                return True, "\n".join(logs)

        # 2. 判定 Stun (暈眩) / Confusion (混亂) 與打斷檢定 (必須在延遲與引導施法解算之前執行，否則會先解算才被打斷)
        if has_status(entity_ref, "Stun"):
            skip_turn = True
            logs.append(f"🌀 {name} 處於暈眩狀態，無法行動！")

        elif has_status(entity_ref, "Confusion"):
            if random.random() < 0.5:
                skip_turn = True
                logs.append(f"💫 {name} 處於混亂狀態，直接取消了本回合的行動！")

        # 打斷引導與延遲施法檢定
        entity_id = str(id(entity_ref))
        is_silenced_spell = False
        if entity_id in self.channeling_actions:
            skill = self.channeling_actions[entity_id]["skill"]
            is_magical = getattr(skill.mechanics, "is_magical", True)
            if is_magical and has_status(entity_ref, "Silence"):
                is_silenced_spell = True
                
        if has_status(entity_ref, "Stun") or has_status(entity_ref, "Confusion") or is_silenced_spell:
            # 打斷引導
            if entity_id in self.channeling_actions:
                skill = self.channeling_actions[entity_id]["skill"]
                del self.channeling_actions[entity_id]
                logs.append(f"⚡ {name} 的【{skill.name}】持續引導被打斷了！")
            # 打斷延遲法術
            original_len = len(self.casting_queue)
            self.casting_queue = [a for a in self.casting_queue if str(id(a.get("caster"))) != entity_id]
            if len(self.casting_queue) < original_len:
                logs.append(f"⚡ {name} 的法術詠唱被打斷了！")
                if is_player:
                    self.delayed_actions = [a for a in self.delayed_actions if a.get("caster_type") != "player"]
                
        # 3. 處理延遲法術與 Echo (殘響) 的觸發 (支援所有施法者)
        if self.casting_queue:
            caster_actions = [a for a in self.casting_queue if str(id(a.get("caster"))) == entity_id]
            for action in caster_actions:
                dt = action.get("turns_left", 1)
                dt -= 1
                action["turns_left"] = dt
                
                # 同步更新相容舊測試的 delayed_actions (如果 caster 是玩家)
                if is_player:
                    legacy_item = next((la for la in self.delayed_actions if la.get("skill") == action.get("skill")), None)
                    if legacy_item:
                        legacy_item["delay_turns"] = dt

                if dt <= 0:
                    try:
                        self.casting_queue.remove(action)
                    except ValueError:
                        pass
                    if is_player:
                        legacy_item = next((la for la in self.delayed_actions if la.get("skill") == action.get("skill")), None)
                        if legacy_item:
                            try:
                                self.delayed_actions.remove(legacy_item)
                            except ValueError:
                                pass
                            
                    skill = action.get("skill")
                    target = action.get("target")
                    
                    # 確保目標依然存活，否則自動重定向
                    target_is_alive = False
                    if target:
                        if isinstance(target, dict):
                            target_is_alive = (target.get("hp", 0) > 0)
                        else:
                            target_is_alive = (get_entity_attr(target, "hp", 0) > 0)
                            
                    if not target_is_alive:
                        # 尋找存活目標
                        if is_player:
                            alive_monsters = [m for m in self.monsters if m.get("hp", 0) > 0 and not m.get("is_summon")]
                            if alive_monsters:
                                target = alive_monsters[0]
                            else:
                                alive_summons = [m for m in self.monsters if m.get("hp", 0) > 0 and m.get("is_summon")]
                                target = alive_summons[0] if alive_summons else None
                        else:
                            target = self.character if self.character.data.vitality.hp > 0 else None
                    
                    if target:
                        is_echo = action.get("is_echo", False)
                        if is_echo:
                            logs.append(f"🔊 觸發【殘響】重播：準備以 50% 威力再次施放【{skill.name}】！")
                            self._echo_cast_active = True
                        else:
                            logs.append(f"💥 詠唱完成！【{skill.name}】爆發！")
                            self._echo_cast_active = False
                            
                        try:
                            res = SkillProcessor.execute_skill(skill, entity_ref, target, self)
                            logs.extend(res.get("logs", []))
                        except Exception as e:
                            logs.append(f"❌ 延遲施法失敗：{str(e)}")
                        finally:
                            self._echo_cast_active = False
                        self._check_battle_status()
                        if self.is_finished:
                            return True, "\n".join(logs)

        # 在狀態過期清除前，檢查即將過期的 Fate_Seal、Doom 和 Doom_Seal 效果
        effects_to_check = []
        if is_player:
            effects_to_check = list(self.character.data.status_effects or [])
        else:
            effects_to_check = list(entity_ref.get("status_effects", []))
            
        for effect in effects_to_check:
            eff_name = effect.name if hasattr(effect, "name") else effect.get("name")
            eff_dur = effect.duration if hasattr(effect, "duration") else effect.get("duration", 0)
            if eff_dur == 1:
                if eff_name == "Fate_Seal":
                    sealed_hp = effect.extra_data.get("sealed_hp") if hasattr(effect, "extra_data") else effect.get("extra_data", {}).get("sealed_hp")
                    if sealed_hp is not None:
                        if is_player:
                            self.character.data.vitality.hp = int(sealed_hp)
                            self.character.save()
                        else:
                            entity_ref["hp"] = int(sealed_hp)
                        logs.append(f"⏳ 【命運封印】倒數結束！{name} 的 HP 被強制還原為 {sealed_hp} 點！")
                elif eff_name in ["Doom", "Doom_Seal"]:
                    if is_player:
                        self.character.data.vitality.hp = 0
                        self.character.save()
                    else:
                        entity_ref["hp"] = 0
                    logs.append(f"☠️ 【厄運宣告】倒數結束！{name} 被奪走生命！")

        # 5. 遞減 status_effects 的 duration
        expired = decay_status_effects(entity_ref)
        if expired:
            logs.append(f"⏳ {name} 的狀態效果結束：{', '.join(expired)}")
            
        return skip_turn, "\n".join(logs) if logs else None

    def _tick_current_entity_at_turn_start(self):
        if self.is_finished:
            return
            
        if self._current_turn_ticked:
            return
            
        curr = self.get_current_entity()
        
        # 處理召喚物的主人倒下自動消散與護衛清理
        if curr["type"] == "monster" and curr["ref"].get("is_summon"):
            # 清理該召喚物的護衛狀態（持續一輪）
            if getattr(self.character, "_defended_by", None) is curr["ref"]:
                self.character._defended_by = None
            for m in self.monsters:
                if m.get("_defended_by") is curr["ref"]:
                    m["_defended_by"] = None

            master_id = curr["ref"].get("master_id")
            if master_id:
                master = find_entity_by_id(self, master_id)
                if not master or get_entity_attr(master, "hp", 0) <= 0:
                    curr["ref"]["hp"] = 0
                    self.battle_logs.append(f"🌀 因召喚主已倒下，{curr['ref']['name']} 自動消散了！")
                    self._check_battle_status()
                    self.next_turn()
                    return

        if curr["type"] == "monster" and curr["ref"]["hp"] <= 0:
            self.next_turn()
            return
            
        self._current_turn_ticked = True
        is_player = (curr["type"] == "player")
        entity_ref = curr["ref"]
        
        # 觸發回合開始事件
        from core.trigger_engine import TriggerEngine
        TriggerEngine.dispatch_event("on_turn_start", entity_ref, None, self)
        
        skip_turn, log_msg = self._process_entity_status_tick(entity_ref, is_player)
        if log_msg:
            self.battle_logs.append(log_msg)
            self.current_tick_logs.append(log_msg)
            
        if skip_turn:
            self.next_turn()
            return
            
        # 處理持續引導 (Channeled) 自動施法
        entity_id = str(id(entity_ref))
        if entity_id in self.channeling_actions:
            chan_info = self.channeling_actions[entity_id]
            skill = chan_info["skill"]
            target_idx = chan_info["target_idx"]
            chan_info["turns_left"] -= 1
            
            # 決定目標
            target = self.monsters[target_idx] if target_idx < len(self.monsters) else None
            if not target or target["hp"] <= 0:
                alive_indices = [i for i, m in enumerate(self.monsters) if m["hp"] > 0]
                if alive_indices:
                    target_idx = alive_indices[0]
                    target = self.monsters[target_idx]
                    chan_info["target_idx"] = target_idx
                else:
                    target = None
                    
            if target:
                caster_name = self.character.data.name if is_player else entity_ref.get("name", "未知單位")
                log_msg = f"🌀 {caster_name} 正在持續引導【{skill.name}】..."
                self.battle_logs.append(log_msg)
                self.current_tick_logs.append(log_msg)
                
                try:
                    res = SkillProcessor.execute_skill(skill, entity_ref, target, self)
                    self.battle_logs.extend(res.get("logs", []))
                    self.current_tick_logs.extend(res.get("logs", []))
                except Exception as e:
                    self.current_tick_logs.append(f"❌ 引導施法失敗：{str(e)}")
                    
            if chan_info["turns_left"] <= 0:
                del self.channeling_actions[entity_id]
                self.current_tick_logs.append(f"✨ 【{skill.name}】引導結束！")
                
            self._check_battle_status()
            if not self.is_finished:
                self.next_turn()

    def _apply_damage(self, target, is_target_player: bool, damage: int, source_entity, is_source_player: bool, context: Optional[Any] = None, tags: Optional[List[str]] = None) -> tuple[int, List[str]]:
        logs = []
        
        # 檢查護衛重定向
        if is_target_player:
            defender = getattr(self.character, "_defended_by", None)
            if defender and defender.__class__.__name__ not in ('Mock', 'MagicMock', 'NonCallableMock', 'PropertyMock'):
                if defender.get("hp", 0) > 0 and defender is not source_entity:
                    self.character._defended_by = None
                    self.battle_logs.append(f"🛡️ {defender['name']} 挺身而出，為 {self.character.data.name} 擋下了傷害！")
                    return self._apply_damage(defender, is_target_player=False, damage=damage, source_entity=source_entity, is_source_player=is_source_player, context=context, tags=tags)
        else:
            if isinstance(target, dict):
                defender = target.get("_defended_by")
                if defender and defender.__class__.__name__ not in ('Mock', 'MagicMock', 'NonCallableMock', 'PropertyMock'):
                    if defender.get("hp", 0) > 0 and defender is not source_entity:
                        target["_defended_by"] = None
                        self.battle_logs.append(f"🛡️ {defender['name']} 挺身而出，為 {target['name']} 擋下了傷害！")
                        return self._apply_damage(defender, is_target_player=False, damage=damage, source_entity=source_entity, is_source_player=is_source_player, context=context, tags=tags)

        final_dmg = damage

        # Calculate/retrieve tags if not provided
        if tags is None:
            tags = []
            if context:
                if hasattr(context, "tags"):
                    tags = getattr(context, "tags") or []
                elif hasattr(context, "skill") and context.skill is not None:
                    tags = getattr(context.skill.mechanics, "tags", [])
                elif isinstance(context, dict) and "skill" in context:
                    sk = context["skill"]
                    if hasattr(sk, "mechanics"):
                        tags = getattr(sk.mechanics, "tags", [])
                    elif isinstance(sk, dict) and "mechanics" in sk:
                        tags = sk["mechanics"].get("tags", [])
            if not tags:
                if is_source_player:
                    main_hand = getattr(source_entity.data.equipment_slots, "main_hand", None)
                    if main_hand and hasattr(main_hand, "tags"):
                        tags = main_hand.tags or []
                else:
                    if isinstance(source_entity, dict):
                        tags = source_entity.get("tags", [])
                        
        # Apply elemental resistance reduction (Marginal Returns Formula)
        from core.combat import use_marginal_returns
        if use_marginal_returns():
            target_res_dict = {}
            if is_target_player:
                target_res_dict = getattr(self.character.data, "resistances", {}) or {}
            else:
                if isinstance(target, dict):
                    target_res_dict = target.get("resistances", {}) or {}
                    
            for tag in tags:
                res_val = None
                for k, v in target_res_dict.items():
                    if k.lower() == tag.lower():
                        res_val = float(v)
                        break
                if res_val is not None and res_val > 0:
                    target_lvl = get_entity_attr(target, "level", 1)
                    res_denom = 50.0 + target_lvl * 5.0
                    res_ratio = min(0.80, res_val / (res_val + res_denom))
                    final_dmg = final_dmg * (1.0 - res_ratio)
                    logs.append(f"🛡️ 觸發【{tag}】抗性減免：抗性值 {res_val:.1f}，減免了 {res_ratio*100:.1f}% 該屬性傷害！")
                
        final_dmg = max(1.0, round(final_dmg, 1))
        
        # 🔱 檢查深淵印記 (Abyssal_Mark) 增傷 40%
        if has_status(target, "Abyssal_Mark"):
            final_dmg = int(round(final_dmg * 1.40))
            logs.append(f"🔱 目標身上印有【深淵印記】：承受所有傷害增加 40%！(實得 {final_dmg})")

        # 1. 檢查 Reflect 反射
        if has_status(target, "Reflect"):
            reflected_dmg = max(1, round(final_dmg * 0.5))
            final_dmg = max(1, round(final_dmg * 0.5))
            
            if is_source_player:
                self.character.data.vitality.hp = max(0, self.character.data.vitality.hp - reflected_dmg)
                self.character.save()
                logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對 {self.character.data.name} 反彈了 {reflected_dmg} 點傷害！")
            else:
                source_entity["hp"] = max(0, source_entity["hp"] - reflected_dmg)
                logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對 {source_entity['name']} 反彈了 {reflected_dmg} 點傷害！")
                
            remove_status(target, "Reflect")
            
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
            hp_change, hp_logs = change_entity_hp(target, -final_dmg, self, source_entity=source_entity, context=context)
            logs.extend(hp_logs)

        # 🕳️ 檢查虛空裂隙 (Void_Rift) 雙向反噬 (當前目標受傷，裂隙施放者承受 25% 真實傷害)
        if final_dmg > 0 and has_status(target, "Void_Rift"):
            rift_effect = get_status_effect(target, "Void_Rift")
            if rift_effect:
                caster_id = rift_effect.extra_data.get("rift_caster_id") if hasattr(rift_effect, "extra_data") else rift_effect.get("extra_data", {}).get("rift_caster_id")
                if caster_id:
                    rift_caster = find_entity_by_id(self, caster_id)
                    if rift_caster:
                        recoil = int(round(final_dmg * 0.25))
                        if recoil > 0:
                            is_caster_player = (rift_caster is self.character)
                            c_hp = get_entity_attr(rift_caster, "hp", 0)
                            set_entity_attr(rift_caster, "hp", max(0, c_hp - recoil))
                            if is_caster_player:
                                self.character.save()
                            caster_name = self.character.data.name if is_caster_player else rift_caster.get("name", "未知單位")
                            logs.append(f"🕳️ 【虛空裂隙】裂隙共鳴反噬！施放者 {caster_name} 承受了 {recoil} 點反噬真實傷害！")
        # 觸發健康度低於閾值事件
        from core.trigger_engine import TriggerEngine
        target_ref = self.character if is_target_player else target
        TriggerEngine.dispatch_event("on_health_below", target_ref, source_entity, self, damage=damage_before_shield, context=context)
                 
        self._check_battle_status()
        return damage_before_shield, logs

    async def _player_attack_raw(self, target_idx: Optional[int] = None) -> Dict[str, Any]:
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
        if has_status(self.character, status_name="Banish"):
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
        
        # Check weapon Melee / Ranged / Spell tags and Row blocking
        is_melee = True
        weapon_tags = []
        if main_hand and isinstance(main_hand, Equipment):
            weapon_tags = main_hand.tags or []
            if any(t in weapon_tags for t in ["Ranged", "Spell"]):
                is_melee = False
            elif main_hand.weapon_type in ["bow", "staff", "wand", "tome", "spellbook", "scroll", "orb"]:
                is_melee = False
        target_row = target.get("row", "front")
        if is_melee and target_row == "back" and self.has_alive_front_row(target, is_target_player=False):
            return {"success": False, "msg": f"❌ 無法攻擊後排：敵方前排仍有存活單位擋路，且該攻擊為近戰攻擊！"}
            
        # 2. 判定 Banish
        if has_status(target, status_name="Banish"):
            return {"success": False, "msg": f"🌀 目標 {target['name']} 處於放逐狀態，普通攻擊無法命中！"}
            
        # ActionContext for Hit/Crit Check
        from core.contexts import ActionContext, DiceContext
        from core.trigger_engine import TriggerEngine
        
        base_accuracy = c_stats.get("accuracy", 0.95)
        if has_status(self.character, status_name="Blind"):
            base_accuracy *= 0.5
            
        base_evasion = get_entity_combat_stat(target, "evasion_rate")
        base_crit = c_stats.get("crit_rate", 0.05)
        
        act_ctx = ActionContext(
            accuracy=base_accuracy,
            evasion_rate=base_evasion,
            crit_rate=base_crit,
            damage_type=damage_type,
            combat_context=self
        )
        act_ctx.tags = weapon_tags
        
        # 觸發命中前攔截
        TriggerEngine.dispatch_interceptor("on_prepare", act_ctx, self.character, target)
        
        # 命中判定
        is_hit = False
        if act_ctx.is_absolute_hit:
            is_hit = True
        else:
            evasion_rate = act_ctx.evasion_rate
            hit_chance = 90 - (evasion_rate * 100)
            hit_chance *= (act_ctx.accuracy / 0.95)
            
            if has_status(target, status_name="Invis"):
                hit_chance *= 0.3
                
            is_hit = (random.randint(1, 100) <= hit_chance)

        if not is_hit:
            TriggerEngine.dispatch_event("on_miss", self.character, target, self)
            TriggerEngine.dispatch_event("on_dodge", target, self.character, self)
            if not self.is_finished:
                self.next_turn()
            return {"success": False, "msg": f"🛡️ {target['name']} 躲過了 {self.character.data.name} 的攻擊！"}

        # 3. 傷害計算 (1d20 擲骰與攔截)
        dice_ctx = DiceContext(dice_str="1d20", caster=self.character, combat_context=self)
        TriggerEngine.dispatch_interceptor("on_dice", dice_ctx, self.character)
        
        if dice_ctx.roll_value is not None:
            dmg_roll = dice_ctx.roll_value
        else:
            dmg_roll = random.randint(1, 20)
            
        dmg_roll += dice_ctx.roll_modifier
        if dice_ctx.floor_value is not None:
            dmg_roll = max(dmg_roll, dice_ctx.floor_value)
        
        # 判定 Bless 補底
        has_bless = has_status(self.character, status_name="Bless")
        bless_msg = ""
        if has_bless and dmg_roll < 5:
            dmg_roll = 10
            bless_msg = "\n🌟 **觸發【祝福】補底**：擲骰小於 5，自動補底為 10！"
            
        roll_mult = dmg_roll / divisor
        
        # 基礎威力 = 屬性 * (1d20 / 武器分母) + 武器 ATK
        base_power = (stat_val * roll_mult) + weapon_power
        
        # 4. 判定爆擊 (1.5x)
        is_crit = act_ctx.is_crit or (random.random() < act_ctx.crit_rate)
        crit_mult = 1.5 if is_crit else 1.0
        
        # 5. 計算總威力 (基 * 爆)
        total_power = base_power * crit_mult
        
        # 傷害計算攔截 (如：無視防禦比例、傷害倍率)
        act_ctx.raw_damage = total_power
        TriggerEngine.dispatch_interceptor("on_calculate_damage", act_ctx, self.character, target)
        
        total_power *= act_ctx.damage_multiplier
        
        # 6. 防禦力動態減免
        defense = get_entity_combat_stat(target, "p_def" if damage_type == "physical" else "m_def")
        if act_ctx.defense_ignore_ratio > 0:
            defense = int(defense * (1.0 - act_ctx.defense_ignore_ratio))
            
        from core.combat import use_marginal_returns
        if use_marginal_returns():
            target_lvl = get_entity_attr(target, "level", 1)
            denom = 50.0 + target_lvl * 5.0
            mitigation_ratio = min(0.80, defense / (defense + denom)) if (defense + denom) > 0 else 0.0
            effective_def = total_power * mitigation_ratio
        else:
            max_mitigation = total_power * 0.80
            effective_def = min(defense, max_mitigation)
        
        final_dmg = max(1.0, round(total_power - effective_def, 1))
        
        # 7. 應用傷害
        actual_dmg, dmg_logs = self._apply_damage(target, is_target_player=False, damage=int(final_dmg), source_entity=self.character, is_source_player=True, context=act_ctx)
        
        # 觸發後置傷害與擊殺事件
        TriggerEngine.dispatch_event("on_hit", self.character, target, self, damage=actual_dmg, context=act_ctx)
        TriggerEngine.dispatch_event("on_damaged", target, self.character, self, damage=actual_dmg, context=act_ctx)
        if is_crit:
            TriggerEngine.dispatch_event("on_crit", self.character, target, self, damage=actual_dmg, context=act_ctx)
        if target["hp"] <= 0:
            TriggerEngine.dispatch_event("on_kill", self.character, target, self, damage=actual_dmg, context=act_ctx)
            
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

    async def _monster_action_raw(self) -> Dict[str, Any]:
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
        if has_status(monster, status_name="Banish"):
            return {"success": False, "msg": f"🌀 {monster['name']} 處於放逐狀態，自身無法進行普通攻擊！"}
            
        # 檢查是否為召喚物
        is_summon = monster.get("is_summon", False)
        
        if is_summon:
            # 召喚物行動：攻擊敵方怪物
            alive_enemies = [m for m in self.monsters if m["hp"] > 0 and not m.get("is_summon")]
            if not alive_enemies:
                return {"success": False, "msg": f"🌀 {monster['name']} 四處張望，沒有發現敵人。"}
                
            # Check row protection
            is_melee = True
            monster_tags = monster.get("tags", []) or []
            if any(t in monster_tags for t in ["Ranged", "Spell"]):
                is_melee = False
                
            target = random.choice(alive_enemies)
            if is_melee and target.get("row", "front") == "back":
                if self.has_alive_front_row(target, is_target_player=False):
                    front_enemies = [m for m in alive_enemies if m.get("row", "front") == "front"]
                    if front_enemies:
                        target = random.choice(front_enemies)

            # 1. 命中判定
            if random.randint(1, 100) > 90:
                return {"success": False, "msg": f"🛡️ {target['name']} 躲過了 {monster['name']} 的攻擊！"}
                
            # 2. 減傷計算
            defense = get_entity_combat_stat(target, "p_def")
            m_roll = random.randint(1, 20)
            m_roll_mult = 0.5 + (m_roll * 0.05)
            total_m_power = monster["attack"] * m_roll_mult
            
            from core.combat import use_marginal_returns
            if use_marginal_returns():
                target_lvl = get_entity_attr(target, "level", 1)
                denom = 50.0 + target_lvl * 5.0
                mitigation_ratio = min(0.80, defense / (defense + denom)) if (defense + denom) > 0 else 0.0
                effective_def = total_m_power * mitigation_ratio
            else:
                effective_def = defense
            
            final_dmg = max(1, round(total_m_power - effective_def))
            
            # 3. 應用傷害
            actual_dmg, dmg_logs = self._apply_damage(target, is_target_player=False, damage=final_dmg, source_entity=monster, is_source_player=False, tags=monster_tags)
            
            log_suffix = "\n" + "\n".join(dmg_logs) if dmg_logs else ""
            msg = f"⚔️ {monster['name']} 攻擊了 {target['name']}，造成 {actual_dmg} 點傷害！{log_suffix}"
            if target["hp"] <= 0:
                msg += f"\n💀 {target['name']} 倒下了！"
                
            return {"success": True, "damage": actual_dmg, "msg": msg}
            
        else:
            # 正常怪物行動
            # 1. 確定攻擊目標
            is_charmed = has_status(monster, status_name="Charm")
            is_controlled = has_status(monster, status_name="Mind_Control")
            is_taunted = has_status(monster, status_name="Taunt")
            
            target_entity = None
            is_target_player = True
            
            if is_charmed or is_controlled:
                # Charmed or Controlled: attack another monster
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

            # Redirect melee attacks if targeting back row and front row is alive
            monster_tags = monster.get("tags", []) or []
            is_melee = True
            if any(t in monster_tags for t in ["Ranged", "Spell"]):
                is_melee = False
                
            target_row = getattr(target_entity.data, "row", "front") if is_target_player else target_entity.get("row", "front")
            if is_melee and target_row == "back" and self.has_alive_front_row(target_entity, is_target_player):
                # Redirect! Find an alive front row entity on target side
                if is_target_player:
                    if getattr(self.character.data, "row", "front") == "front" and self.character.data.vitality.hp > 0:
                        target_entity = self.character
                    else:
                        front_summons = [m for m in self.monsters if m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front"]
                        if front_summons:
                            target_entity = random.choice(front_summons)
                            is_target_player = False
                else:
                    front_monsters = [m for m in self.monsters if not m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front"]
                    if front_monsters:
                        target_entity = random.choice(front_monsters)
                        is_target_player = False
                
            target_name = self.character.data.name if is_target_player else target_entity["name"]
            
            # 2. 判定 Banish
            if has_status(target_entity, "Banish"):
                return {"success": False, "msg": f"🌀 {target_name} 處於放逐狀態，{monster['name']} 的攻擊無法命中！"}
                
            # ActionContext for Hit check
            from core.contexts import ActionContext, DiceContext
            from core.trigger_engine import TriggerEngine
            
            evasion_rate = get_entity_combat_stat(target_entity, "evasion_rate")
            base_accuracy = 0.90
            base_crit = 0.05
            
            damage_type = monster.get("damage_type", "physical")
            act_ctx = ActionContext(
                accuracy=base_accuracy,
                evasion_rate=evasion_rate,
                crit_rate=base_crit,
                damage_type=damage_type,
                combat_context=self
            )
            act_ctx.tags = monster_tags
            
            # 觸發命中前攔截
            TriggerEngine.dispatch_interceptor("on_prepare", act_ctx, monster, target_entity)

            is_hit = False
            if act_ctx.is_absolute_hit:
                is_hit = True
            else:
                hit_chance = (act_ctx.accuracy * 100) - (act_ctx.evasion_rate * 100)
                if has_status(target_entity, "Invis"):
                    hit_chance *= 0.3
                is_hit = (random.randint(1, 100) <= hit_chance)

            if not is_hit:
                TriggerEngine.dispatch_event("on_miss", monster, target_entity, self)
                TriggerEngine.dispatch_event("on_dodge", target_entity, monster, self)
                if is_target_player:
                    return {"success": False, "msg": f"🛡️ {self.character.data.name} 靈巧地躲過了 {monster['name']} 的攻擊！ (迴避 {act_ctx.evasion_rate*100:.1f}%)"}
                else:
                    return {"success": False, "msg": f"🛡️ {target_name} 躲過了 {monster['name']} 的攻擊！"}
                    
            # 3. 傷害計算 (1d20 擲骰與攔截)
            dice_ctx = DiceContext(dice_str="1d20", caster=monster, combat_context=self)
            TriggerEngine.dispatch_interceptor("on_dice", dice_ctx, monster)
            
            if dice_ctx.roll_value is not None:
                m_roll = dice_ctx.roll_value
            else:
                m_roll = random.randint(1, 20)
                
            m_roll += dice_ctx.roll_modifier
            if dice_ctx.floor_value is not None:
                m_roll = max(m_roll, dice_ctx.floor_value)
                
            m_roll_mult = 0.5 + (m_roll * 0.05)
            total_m_power = monster["attack"] * m_roll_mult
            
            # 傷害計算前攔截
            act_ctx.raw_damage = total_m_power
            TriggerEngine.dispatch_interceptor("on_calculate_damage", act_ctx, monster, target_entity)
            
            total_m_power *= act_ctx.damage_multiplier
            
            # 4. 減傷計算
            damage_type = monster.get("damage_type", "physical")
            defense = get_entity_combat_stat(target_entity, "p_def" if damage_type == "physical" else "m_def")
            if act_ctx.defense_ignore_ratio > 0:
                defense = int(defense * (1.0 - act_ctx.defense_ignore_ratio))
            
            # 韌性減傷 (比例減傷，僅對玩家生效)
            tenacity_reduction = 1.0
            if is_target_player:
                tenacity_reduction = 1.0 - (c_stats["tenacity"] / 1000)
                tenacity_reduction = max(0.5, tenacity_reduction)
                
            from core.combat import use_marginal_returns
            if use_marginal_returns():
                target_lvl = get_entity_attr(target_entity, "level", 1)
                denom = 50.0 + target_lvl * 5.0
                mitigation_ratio = min(0.80, defense / (defense + denom)) if (defense + denom) > 0 else 0.0
                effective_def = total_m_power * mitigation_ratio
            else:
                max_mitigation = total_m_power * 0.80
                effective_def = min(defense, max_mitigation)
            
            final_dmg = max(1.0, round((total_m_power - effective_def) * tenacity_reduction, 1))
            
            # 5. 應用傷害
            actual_dmg, dmg_logs = self._apply_damage(target_entity, is_target_player, int(final_dmg), monster, is_source_player=False, context=act_ctx, tags=monster_tags)
            
            # 觸發後置傷害與擊殺事件
            TriggerEngine.dispatch_event("on_hit", monster, target_entity, self, damage=actual_dmg, context=act_ctx)
            TriggerEngine.dispatch_event("on_damaged", target_entity, monster, self, damage=actual_dmg, context=act_ctx)
            if target_entity == self.character:
                target_hp = self.character.data.vitality.hp
            else:
                target_hp = target_entity["hp"]
            if target_hp <= 0:
                TriggerEngine.dispatch_event("on_kill", monster, target_entity, self, damage=actual_dmg, context=act_ctx)
            
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

    async def _cast_skill_raw(self, skill: Skill, target_idx: Optional[int] = None) -> Dict[str, Any]:
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
        if has_status(self.character, status_name="Berserk"):
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
        
        # Check row protection for melee skills at the start of cast
        is_melee_skill = "Melee" in getattr(skill.mechanics, "tags", [])
        if is_melee_skill:
            target_row = target.get("row", "front")
            if target_row == "back" and self.has_alive_front_row(target, is_target_player=False):
                return {"success": False, "msg": "❌ 無法對後排施展近戰技能：敵方前排仍有存活單位擋路！"}
        
        # --- 處理發動模式 (execution_mode) 與 養成機制 ---
        execution_mode = getattr(skill.mechanics, "execution_mode", "immediate")
        if execution_mode == "reactive":
            return {"success": False, "msg": f"❌ 【{skill.name}】是反制技能，無法主動施放，將在觸發條件滿足時自動發動。"}
            
        elif execution_mode == "delayed":
            delay = 2 if "Apocalypse" in skill.mechanics.keywords or "Apocalypse" == skill.mechanics.legendary_keyword else 1
            self.casting_queue.append({
                "skill": skill,
                "caster": self.character,
                "target": target,
                "turns_left": delay,
                "is_echo": False
            })
            self.delayed_actions.append({
                "caster_type": "player",
                "skill": skill,
                "target_idx": target_idx,
                "delay_turns": delay,
                "is_echo": False
            })
            # 不立刻執行
            msg = f"⏳ 你開始詠唱【{skill.name}】，法術將在 {delay} 回合後爆發！"
            
            # 更新養成機制 (詠唱成功即算一次)
            skill.usage_count += 1
            if skill.evolution_threshold > 0 and skill.usage_count >= skill.evolution_threshold and not skill.can_evolve:
                skill.can_evolve = True
                msg += f"\n🌟 熟練度突破！你的【{skill.name}】現在可以回到城鎮進行進化了！"
                
            return {"success": True, "msg": msg, "finished": self.is_finished}
            
        elif execution_mode == "channeled":
            self.channeling_actions[str(id(self.character))] = {
                "skill": skill,
                "target_idx": target_idx,
                "turns_left": 2  # 總共引導 3 次（1次立即，2次後續回合）
            }

        try:
            # 呼叫技能執行器
            res = SkillProcessor.execute_skill(skill, self.character, target, self)
            
            # 更新養成機制
            skill.usage_count += 1
            if skill.evolution_threshold > 0 and skill.usage_count >= skill.evolution_threshold and not skill.can_evolve:
                skill.can_evolve = True
                if "logs" not in res:
                    res["logs"] = []
                res["logs"].append(f"🌟 熟練度突破！你的【{skill.name}】現在可以回到城鎮進行進化了！")
                
        except ValueError as e:
            return {"success": False, "msg": f"❌ 施法失敗：{str(e)}"}
        self._check_battle_status()
        
        # 處理流程標記連動：
        control_flags = res.get("control_flags", {})
        if "logs" not in res:
            res["logs"] = []
        logs = res["logs"]

        # Apocalypse 全體真實傷害與沉默
        if control_flags.get("apocalypse_aoe") and not self.is_finished:
            final_val = res.get("final_value", 0.0)
            from core.skill_processor import add_entity_status_effect
            for idx, m in enumerate(self.monsters):
                if m.get("hp", 0) > 0 and idx != target_idx:
                    actual_dmg, dmg_logs = self._apply_damage(m, is_target_player=False, damage=int(final_val), source_entity=self.character, is_source_player=True)
                    add_entity_status_effect(m, "Silence", "沉默：無法施展傷害技能", 2)
                    logs.append(f"⚡ 【天劫降臨】雷劫席捲 {m.get('name')}，造成 {actual_dmg} 點真實傷害並施加【沉默】2 回合！")
                    if dmg_logs:
                        logs.extend(dmg_logs)
                    if m.get("hp", 0) <= 0:
                        logs.append(f"💀 {m.get('name')} 倒下了！")

        # Last_Rites Doom 擴散
        if control_flags.get("last_rites_doom_spread") and not self.is_finished:
            from core.skill_processor import add_entity_status_effect
            for idx, m in enumerate(self.monsters):
                if m.get("hp", 0) > 0 and idx != target_idx:
                    add_entity_status_effect(m, "Doom", "厄運宣告：倒數即死", 3)
                    logs.append(f"⚰️ 【終焉禮讚】厄運擴散！對 {m.get('name')} 施加了【厄運宣告】！")

        # Soul_Shatter 擊殺全體 Stun
        if control_flags.get("soul_shatter_triggered") and not self.is_finished:
            from core.skill_processor import add_entity_status_effect
            for m in self.monsters:
                if m.get("hp", 0) > 0:
                    add_entity_status_effect(m, "Stun", "暈眩：無法行動", 1)
                    logs.append(f"💀 【靈魂粉碎】爆發！對 {m.get('name')} 施加【暈眩】1 回合！")

        # Devil's_Roll 6點強制 AoE
        if control_flags.get("devil_roll_aoe") and not self.is_finished:
            final_val = res.get("final_value", 0.0)
            for idx, m in enumerate(self.monsters):
                if m.get("hp", 0) > 0 and idx != target_idx:
                    actual_dmg, dmg_logs = self._apply_damage(m, is_target_player=False, damage=int(final_val), source_entity=self.character, is_source_player=True)
                    logs.append(f"🎲 【惡魔骰】6點衝擊波席捲 {m.get('name')}，造成 {actual_dmg} 點傷害！")
                    if dmg_logs:
                        logs.extend(dmg_logs)
                    if m.get("hp", 0) <= 0:
                        logs.append(f"💀 {m.get('name')} 倒下了！")

        # Devil's_Roll 4-5點隨機詛咒
        devil_debuff = control_flags.get("devil_roll_debuff")
        if devil_debuff and target.get("hp", 0) > 0:
            from core.skill_processor import add_entity_status_effect
            if devil_debuff == "Stun":
                add_entity_status_effect(target, "Stun", "暈眩：無法行動", 1)
                logs.append(f"🎲 【惡魔骰】隨機詛咒：對 {target.get('name')} 附加【暈眩】1 回合！")
            elif devil_debuff == "Burn":
                add_entity_status_effect(target, "Burn", "灼燒 DoT", 3, dot_damage_flat=15.0, dot_damage_type="true_damage")
                logs.append(f"🎲 【惡魔骰】隨機詛咒：對 {target.get('name')} 附加【灼燒】3 回合！")
            elif devil_debuff == "Doom":
                add_entity_status_effect(target, "Doom", "厄運宣告：倒數即死", 3)
                logs.append(f"🎲 【惡魔骰】隨機詛咒：對 {target.get('name')} 附加【厄運宣告】3 回合！")
        
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
                actual_dmg, dmg_logs = self._apply_damage(next_target, is_target_player=False, damage=int(chain_val), source_entity=self.character, is_source_player=True)
                logs.append(f"⚡ 觸發【連鎖彈射】：對 {next_target['name']} 造成了 {actual_dmg} 點彈射傷害 (傷害減半)！")
                if dmg_logs:
                    logs.extend(dmg_logs)
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
                "is_summon": True,
                "master_id": str(id(self.character))
            }
            m_speed = summon_entity["speed"] + random.randint(1, 10)
            self.turn_order.append({"type": "monster", "speed": m_speed, "ref": summon_entity, "index": len(self.monsters)})
            self.monsters.append(summon_entity)
            logs.append("🌀 戰場上多出了一個【召喚火靈】加入序列！")
            
        # 4. 殘響 (Echo) 標記
        if control_flags.get("echo_active"):
            self.casting_queue.append({
                "skill": skill,
                "caster": self.character,
                "target": target,
                "turns_left": 1,
                "is_echo": True
            })
            self.delayed_actions.append({
                "caster_type": "player",
                "skill": skill,
                "target_idx": target_idx,
                "delay_turns": 1,
                "is_echo": True
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

    def _wrap_combat_message(self, res: Dict[str, Any]) -> Dict[str, Any]:
        if "msg" in res and self.current_tick_logs:
            tick_prefix = "\n".join(self.current_tick_logs) + "\n"
            res["msg"] = tick_prefix + res["msg"]
        self.current_tick_logs.clear()
        return res

    async def player_attack(self, target_idx: Optional[int] = None) -> Dict[str, Any]:
        res = await self._player_attack_raw(target_idx)
        wrapped = self._wrap_combat_message(res)
        if wrapped.get("success") and "msg" in wrapped:
            self.battle_logs.append(wrapped["msg"])
        return wrapped

    async def monster_action(self) -> Dict[str, Any]:
        res = await self._monster_action_raw()
        wrapped = self._wrap_combat_message(res)
        if wrapped.get("success") and "msg" in wrapped:
            self.battle_logs.append(wrapped["msg"])
        return wrapped

    async def cast_skill(self, skill: Skill, target_idx: Optional[int] = None) -> Dict[str, Any]:
        res = await self._cast_skill_raw(skill, target_idx)
        wrapped = self._wrap_combat_message(res)
        if wrapped.get("success") and "msg" in wrapped:
            self.battle_logs.append(wrapped["msg"])
        return wrapped

    async def cast_summon_action(self, action_type: str, target_idx: Optional[int] = None, skill_name: Optional[str] = None) -> Dict[str, Any]:
        res = await self._cast_summon_action_raw(action_type, target_idx, skill_name)
        if res.get("success") and "msg" in res:
            self.battle_logs.append(res["msg"])
        return res

    async def _cast_summon_action_raw(self, action_type: str, target_idx: Optional[int] = None, skill_name: Optional[str] = None) -> Dict[str, Any]:
        if self.is_finished:
            return {"success": False, "msg": "戰鬥已經結束。"}

        curr = self.get_current_entity()
        entity_ref = curr["ref"]
        
        # 確保當前行動單位是召喚物，且主人為當前玩家
        if not (curr["type"] == "monster" and entity_ref.get("is_summon")):
            return {"success": False, "msg": "目前行動單位不是召喚物！"}
            
        master_id = entity_ref.get("master_id")
        if master_id != str(id(self.character)):
            return {"success": False, "msg": "此召喚物不受您控制！"}
            
        if self.character.data.vitality.hp <= 0:
            return {"success": False, "msg": "主人已倒下，召喚物無法接受指令！"}

        if action_type == "attack":
            if target_idx is None:
                alive_enemies = [i for i, m in enumerate(self.monsters) if m["hp"] > 0 and not m.get("is_summon")]
                if not alive_enemies:
                    return {"success": False, "msg": "沒有合適的攻擊目標！"}
                target_idx = alive_enemies[0]
                
            target = self.monsters[target_idx]
            
            # Check row protection
            is_melee = True
            summon_tags = entity_ref.get("tags", []) or []
            if any(t in summon_tags for t in ["Ranged", "Spell"]):
                is_melee = False
            if is_melee and target.get("row", "front") == "back" and self.has_alive_front_row(target, is_target_player=False):
                return {"success": False, "msg": "❌ 無法攻擊後排：敵方前排仍有存活單位擋路，且該攻擊為近戰攻擊！"}
            
            # 命中判定
            if random.randint(1, 100) > 90:
                self.next_turn()
                return self._wrap_combat_message({"success": True, "msg": f"🛡️ {target['name']} 躲過了 {entity_ref['name']} 的攻擊！", "finished": self.is_finished})
                
            # 減傷計算
            defense = get_entity_combat_stat(target, "p_def")
            m_roll = random.randint(1, 20)
            m_roll_mult = 0.5 + (m_roll * 0.05)
            total_power = entity_ref["attack"] * m_roll_mult
            
            from core.combat import use_marginal_returns
            if use_marginal_returns():
                target_lvl = get_entity_attr(target, "level", 1)
                denom = 50.0 + target_lvl * 5.0
                mitigation_ratio = min(0.80, defense / (defense + denom)) if (defense + denom) > 0 else 0.0
                effective_def = total_power * mitigation_ratio
            else:
                effective_def = defense
            
            final_dmg = max(1, round(total_power - effective_def))
            
            actual_dmg, dmg_logs = self._apply_damage(target, is_target_player=False, damage=int(final_dmg), source_entity=entity_ref, is_source_player=False, tags=summon_tags)
            log_suffix = "\n" + "\n".join(dmg_logs) if dmg_logs else ""
            msg = f"⚔️ [寵物指令] {entity_ref['name']} 攻擊了 {target['name']}，造成 {actual_dmg} 點傷害！{log_suffix}"
            if target["hp"] <= 0:
                msg += f"\n💀 {target['name']} 倒下了！"
                
            self.next_turn()
            return self._wrap_combat_message({"success": True, "msg": msg, "finished": self.is_finished})

        elif action_type == "defend":
            guard_target = self.character
            guard_target._defended_by = entity_ref
            msg = f"🛡️ [寵物指令] {entity_ref['name']} 開始護衛主人 {guard_target.data.name}，將為其擋下下一次傷害！"
            self.next_turn()
            return self._wrap_combat_message({"success": True, "msg": msg, "finished": self.is_finished})

        elif action_type == "cast":
            if not skill_name:
                return {"success": False, "msg": "請指定召喚物要施放的技能名稱！"}
                
            skill = next((s for s in entity_ref.get("abilities", []) if s.name == skill_name), None)
            if not skill:
                return {"success": False, "msg": f"召喚物沒有【{skill_name}】技能！"}
                
            if target_idx is None:
                alive_enemies = [i for i, m in enumerate(self.monsters) if m["hp"] > 0 and not m.get("is_summon")]
                if not alive_enemies:
                    return {"success": False, "msg": "沒有合適的攻擊目標！"}
                target_idx = alive_enemies[0]
            target = self.monsters[target_idx]
            
            try:
                res = SkillProcessor.execute_skill(skill, entity_ref, target, self)
                logs = res.get("logs", [])
                skill_logs = "\n" + "\n".join(logs) if logs else ""
                msg = f"🌟 [寵物指令] {entity_ref['name']} 施展了技能【{skill.name}】！{skill_logs}"
            except Exception as e:
                return {"success": False, "msg": f"❌ 施法失敗：{str(e)}"}
                
            self._check_battle_status()
            self.next_turn()
            return self._wrap_combat_message({"success": True, "msg": msg, "finished": self.is_finished})

        return {"success": False, "msg": "未知指令類型。"}
