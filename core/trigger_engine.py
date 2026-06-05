import random
import re
from typing import Any, List, Dict, Optional
from core.contexts import ActionContext, DiceContext
from core.skill_processor import (
    get_entity_stat,
    get_entity_attr,
    set_entity_attr,
    add_entity_status_effect
)

def entity_has_status(entity: Any, status_name: str) -> bool:
    if not entity:
        return False
    if hasattr(entity, "data") and hasattr(entity.data, "status_effects"):
        return any(e.name == status_name for e in entity.data.status_effects)
    elif isinstance(entity, dict) and "status_effects" in entity:
        for effect in entity["status_effects"]:
            if isinstance(effect, dict):
                if effect.get("name") == status_name:
                    return True
            else:
                if getattr(effect, "name", None) == status_name:
                    return True
    return False

def evaluate_condition(condition_str: Optional[str], entity: Any, context: Optional[Any] = None, target: Optional[Any] = None) -> bool:
    if not condition_str:
        return True
    
    parts = [p.strip() for p in condition_str.split(" and ") if p.strip()]
    for part in parts:
        if not _evaluate_single_condition(part, entity, context, target):
            return False
    return True

def _evaluate_single_condition(condition_str: str, entity: Any, context: Optional[Any] = None, target: Optional[Any] = None) -> bool:
    cond = condition_str.strip()
    is_negated = False
    if cond.startswith("not "):
        is_negated = True
        cond = cond[4:].strip()
    elif cond.startswith("!"):
        is_negated = True
        cond = cond[1:].strip()
        
    match = re.match(r"has_status\(['\"](.+?)['\"]\)", cond)
    if match:
        status_name = match.group(1)
        has_it = entity_has_status(entity, status_name)
        return not has_it if is_negated else has_it

    match_target_status = re.match(r"target_has_status\(['\"](.+?)['\"]\)", cond)
    if match_target_status:
        status_name = match_target_status.group(1)
        has_it = entity_has_status(target, status_name) if target else False
        return not has_it if is_negated else has_it

    match_dmg_type = re.match(r"damage_type\(['\"](.+?)['\"]\)", cond)
    if match_dmg_type:
        expected_type = match_dmg_type.group(1)
        actual_type = "physical"
        if context and hasattr(context, "damage_type"):
            actual_type = context.damage_type
        is_match = (actual_type == expected_type)
        return not is_match if is_negated else is_match

    match_stacks = re.match(r"status_stacks\(['\"](.+?)['\"]\)\s*(>=|<=|>|<|==)\s*(\d+)", cond)
    if match_stacks:
        status_name = match_stacks.group(1)
        op = match_stacks.group(2)
        val = int(match_stacks.group(3))
        
        curr_stacks = 0
        if hasattr(entity, "data") and hasattr(entity.data, "status_effects") and entity.data.status_effects is not None:
            effect = next((e for e in entity.data.status_effects if e.name == status_name), None)
            if effect:
                curr_stacks = getattr(effect, "stacks", 1)
        elif isinstance(entity, dict) and "status_effects" in entity:
            effect = next((e for e in entity["status_effects"] if (e.name == status_name if hasattr(e, "name") else e.get("name") == status_name)), None)
            if effect:
                curr_stacks = getattr(effect, "stacks", 1) if hasattr(effect, "stacks") else effect.get("stacks", 1)
                
        if op == ">=": has_cond = curr_stacks >= val
        elif op == "<=": has_cond = curr_stacks <= val
        elif op == ">": has_cond = curr_stacks > val
        elif op == "<": has_cond = curr_stacks < val
        elif op == "==": has_cond = curr_stacks == val
        else: has_cond = False
        return not has_cond if is_negated else has_cond

    match_flag = re.match(r"context_flag\(['\"](.+?)['\"]\)", cond)
    if match_flag:
        flag_name = match_flag.group(1)
        has_flag = False
        if context:
            if hasattr(context, "extra_flags") and flag_name in context.extra_flags:
                has_flag = bool(context.extra_flags[flag_name])
            elif hasattr(context, flag_name):
                has_flag = bool(getattr(context, flag_name))
            # 回退檢索戰鬥級別的臨時 Flag 共享池
            if not has_flag and hasattr(context, "combat_context") and context.combat_context is not None:
                if hasattr(context.combat_context, "_temp_flags") and flag_name in context.combat_context._temp_flags:
                    has_flag = bool(context.combat_context._temp_flags[flag_name])
        return not has_flag if is_negated else has_flag
        
    match_hp_above = re.match(r"health_above\((\d+)\)", cond)
    if match_hp_above:
        pct = float(match_hp_above.group(1))
        curr_hp = get_entity_attr(entity, "hp", 100)
        max_hp = get_entity_attr(entity, "max_hp", 100)
        has_above = (curr_hp / max_hp * 100) > pct if max_hp > 0 else False
        return not has_above if is_negated else has_above

    match_hp_below = re.match(r"health_below\((\d+)\)", cond)
    if match_hp_below:
        pct = float(match_hp_below.group(1))
        curr_hp = get_entity_attr(entity, "hp", 100)
        max_hp = get_entity_attr(entity, "max_hp", 100)
        has_below = (curr_hp / max_hp * 100) <= pct if max_hp > 0 else False
        return not has_below if is_negated else has_below

    # MP checks
    match_mp_above = re.match(r"mp_above\((\d+)\)", cond)
    if match_mp_above:
        pct = float(match_mp_above.group(1))
        curr_mp = get_entity_attr(entity, "mp", 50)
        max_mp = get_entity_attr(entity, "max_mp", 50)
        has_above = (curr_mp / max_mp * 100) > pct if max_mp > 0 else False
        return not has_above if is_negated else has_above

    match_mp_below = re.match(r"mp_below\((\d+)\)", cond)
    if match_mp_below:
        pct = float(match_mp_below.group(1))
        curr_mp = get_entity_attr(entity, "mp", 50)
        max_mp = get_entity_attr(entity, "max_mp", 50)
        has_below = (curr_mp / max_mp * 100) <= pct if max_mp > 0 else False
        return not has_below if is_negated else has_below

    # Stamina checks
    match_stam_above = re.match(r"stamina_above\((\d+)\)", cond)
    if match_stam_above:
        pct = float(match_stam_above.group(1))
        curr_stam = get_entity_attr(entity, "stamina", 100)
        max_stam = get_entity_attr(entity, "max_stamina", 100)
        has_above = (curr_stam / max_stam * 100) > pct if max_stam > 0 else False
        return not has_above if is_negated else has_above

    match_stam_below = re.match(r"stamina_below\((\d+)\)", cond)
    if match_stam_below:
        pct = float(match_stam_below.group(1))
        curr_stam = get_entity_attr(entity, "stamina", 100)
        max_stam = get_entity_attr(entity, "max_stamina", 100)
        has_below = (curr_stam / max_stam * 100) <= pct if max_stam > 0 else False
        return not has_below if is_negated else has_below

    # Sanity checks
    match_san_above = re.match(r"sanity_above\((\d+)\)", cond)
    if match_san_above:
        pct = float(match_san_above.group(1))
        curr_san = get_entity_attr(entity, "sanity", 100)
        max_san = get_entity_attr(entity, "max_sanity", 100)
        has_above = (curr_san / max_san * 100) > pct if max_san > 0 else False
        return not has_above if is_negated else has_above

    match_san_below = re.match(r"sanity_below\((\d+)\)", cond)
    if match_san_below:
        pct = float(match_san_below.group(1))
        curr_san = get_entity_attr(entity, "sanity", 100)
        max_san = get_entity_attr(entity, "max_sanity", 100)
        has_below = (curr_san / max_san * 100) <= pct if max_san > 0 else False
        return not has_below if is_negated else has_below
        
    return True

def _remove_status_effect_obj(entity, effect):
    if hasattr(entity, "data") and hasattr(entity.data, "status_effects") and entity.data.status_effects is not None:
        entity.data.status_effects = [e for e in entity.data.status_effects if e is not effect]
        if hasattr(entity, "save"):
            entity.save()
    elif isinstance(entity, dict) and "status_effects" in entity:
        entity["status_effects"] = [e for e in entity["status_effects"] if e is not effect]

def _handle_status_consume(entity, effect):
    if hasattr(effect, "trigger_limit"):
        limit = effect.trigger_limit
        count = getattr(effect, "trigger_count", 0)
        if limit > 0:
            effect.trigger_count = count + 1
            if effect.trigger_count >= limit:
                _remove_status_effect_obj(entity, effect)
    elif isinstance(effect, dict):
        limit = effect.get("trigger_limit", 0)
        count = effect.get("trigger_count", 0)
        if limit > 0:
            effect["trigger_count"] = count + 1
            if effect["trigger_count"] >= limit:
                _remove_status_effect_obj(entity, effect)
        
    return True

def resolve_action_target(action_target_str: str, owner: Any, event_target: Optional[Any], combat_manager: Optional[Any]) -> List[Any]:
    if action_target_str == "caster":
        return [owner] if owner else []
    if action_target_str == "target" or action_target_str == "attacker":
        return [event_target] if event_target else []
        
    is_owner_player = hasattr(owner, "data") and not isinstance(owner, dict)
    
    if action_target_str == "random_enemy" and combat_manager:
        if is_owner_player:
            alive_monsters = [m for m in combat_manager.monsters if m.get("hp", 0) > 0 and not m.get("is_summon")]
            if alive_monsters:
                return [random.choice(alive_monsters)]
        else:
            if combat_manager.character:
                return [combat_manager.character]
        return []
        
    if action_target_str == "all_enemies":
        if is_owner_player:
            if combat_manager:
                return [m for m in combat_manager.monsters if m.get("hp", 0) > 0 and not m.get("is_summon")]
            return []
        else:
            if combat_manager and combat_manager.character:
                return [combat_manager.character]
            return []
            
    if action_target_str == "all_allies":
        if is_owner_player:
            allies = [owner] if owner else []
            if combat_manager:
                summons = [m for m in combat_manager.monsters if m.get("hp", 0) > 0 and m.get("is_summon")]
                allies.extend(summons)
            return allies
        else:
            if combat_manager:
                return [m for m in combat_manager.monsters if m.get("hp", 0) > 0 and not m.get("is_summon")]
            return [owner] if owner else []
            
    return [event_target] if event_target else []

class TriggerEngine:
    _dispatching = set()

    @staticmethod
    def _check_target_health_filters(trigger: Dict[str, Any], target: Optional[Any]) -> bool:
        target_below = trigger.get("target_health_below")
        target_above = trigger.get("target_health_above")
        if target_below is None and target_above is None:
            return True
            
        if not target:
            return False
            
        target_hp = get_entity_attr(target, "hp", 100)
        target_max_hp = get_entity_attr(target, "max_hp", 100)
        if target_max_hp > 0:
            target_pct = (target_hp / target_max_hp) * 100.0
            if target_below is not None and target_pct > target_below:
                return False
            if target_above is not None and target_pct < target_above:
                return False
        return True

    @staticmethod
    def get_active_triggers(entity: Any) -> List[Dict[str, Any]]:
        triggers = []
        if not entity:
            return triggers

        # 1. 讀取裝備的觸發器 (Equipment Triggers)
        if hasattr(entity, "data") and hasattr(entity.data, "equipment_slots"):
            slots = entity.data.equipment_slots
            for slot_name in slots.model_fields.keys():
                eq = getattr(slots, slot_name, None)
                if eq:
                    eq_triggers = getattr(eq, "executable_triggers", None)
                    if eq_triggers and isinstance(eq_triggers, list):
                        triggers.extend(eq_triggers)

        # 2. 讀取狀態效果的觸發器 (Status Effect Triggers)
        if hasattr(entity, "data") and hasattr(entity.data, "status_effects") and entity.data.status_effects is not None:
            for effect in entity.data.status_effects:
                eff_triggers = getattr(effect, "executable_triggers", None)
                if eff_triggers and isinstance(eff_triggers, list):
                    for t in eff_triggers:
                        if isinstance(t, dict):
                            t_copy = dict(t)
                            t_copy["_owner_effect"] = effect
                            t_copy["_orig_trigger"] = t
                            triggers.append(t_copy)
        elif isinstance(entity, dict) and "status_effects" in entity:
            for effect in entity["status_effects"]:
                if isinstance(effect, dict):
                    eff_triggers = effect.get("executable_triggers")
                else:
                    eff_triggers = getattr(effect, "executable_triggers", None)
                if eff_triggers and isinstance(eff_triggers, list):
                    for t in eff_triggers:
                        if isinstance(t, dict):
                            t_copy = dict(t)
                            t_copy["_owner_effect"] = effect
                            t_copy["_orig_trigger"] = t
                            triggers.append(t_copy)

        # 3. 讀取技能的觸發器 (Skill Triggers)
        if hasattr(entity, "data") and hasattr(entity.data, "abilities"):
            for skill in entity.data.abilities:
                skill_triggers = getattr(skill, "executable_triggers", None)
                if skill_triggers and isinstance(skill_triggers, list):
                    triggers.extend(skill_triggers)
        elif isinstance(entity, dict) and "abilities" in entity:
            for skill in entity["abilities"]:
                if isinstance(skill, dict):
                    skill_triggers = skill.get("executable_triggers")
                else:
                    skill_triggers = getattr(skill, "executable_triggers", None)
                if skill_triggers and isinstance(skill_triggers, list):
                    triggers.extend(skill_triggers)

        # 4. 讀取實體本身的直接觸發器 (例如怪物自帶詞條，或技能自帶觸發)
        if isinstance(entity, dict):
            direct_triggers = entity.get("executable_triggers")
            if direct_triggers and isinstance(direct_triggers, list):
                triggers.extend(direct_triggers)
        else:
            direct_triggers = getattr(entity, "executable_triggers", None)
            if direct_triggers and isinstance(direct_triggers, list):
                triggers.extend(direct_triggers)

        return triggers

    @staticmethod
    def dispatch_interceptor(event: str, context: Any, caster: Any, target: Optional[Any] = None):
        """
        在公式計算前攔截並修改 Context 屬性（支援 ActionContext 與 DiceContext）。
        """
        caster_triggers = TriggerEngine.get_active_triggers(caster)
        target_triggers = TriggerEngine.get_active_triggers(target) if target else []

        # 處理施法者觸發器
        for trigger in caster_triggers:
            if trigger.get("event") == event:
                if trigger.get("cooldown_left", 0) > 0:
                    continue
                t_chance = trigger.get("chance", 1.0)
                if t_chance < 1.0 and random.random() > t_chance:
                    continue
                if not evaluate_condition(trigger.get("condition"), caster, context, target):
                    continue
                if not TriggerEngine._check_target_health_filters(trigger, target):
                    continue
                
                executed_any = False
                for action in trigger.get("actions", []):
                    chance = action.get("chance", 1.0)
                    if chance < 1.0 and random.random() > chance:
                        continue
                    
                    action_type = action.get("action_type")
                    if action_type in ("set_flag", "set_value", "modify_dice"):
                        param = action.get("param")
                        val = action.get("param_value")
                        if param is not None:
                            if hasattr(context, param):
                                setattr(context, param, val)
                                executed_any = True
                            elif hasattr(context, "extra_flags"):
                                context.extra_flags[param] = val
                                # 同步寫入戰鬥等級的臨時 Flag 共享池
                                if hasattr(context, "combat_context") and context.combat_context is not None:
                                    if not hasattr(context.combat_context, "_temp_flags"):
                                        context.combat_context._temp_flags = {}
                                    context.combat_context._temp_flags[param] = val
                                executed_any = True
                
                if executed_any:
                    if "cooldown" in trigger:
                        orig = trigger.get("_orig_trigger", trigger)
                        orig["cooldown_left"] = trigger["cooldown"]
                        trigger["cooldown_left"] = trigger["cooldown"]
                    if "_owner_effect" in trigger:
                        _handle_status_consume(caster, trigger["_owner_effect"])

        # 處理目標觸發器
        for trigger in target_triggers:
            if trigger.get("event") == event:
                if trigger.get("cooldown_left", 0) > 0:
                    continue
                t_chance = trigger.get("chance", 1.0)
                if t_chance < 1.0 and random.random() > t_chance:
                    continue
                if not evaluate_condition(trigger.get("condition"), target, context, caster):
                    continue
                if not TriggerEngine._check_target_health_filters(trigger, caster):
                    continue
                
                executed_any = False
                for action in trigger.get("actions", []):
                    chance = action.get("chance", 1.0)
                    if chance < 1.0 and random.random() > chance:
                        continue
                    
                    action_type = action.get("action_type")
                    if action_type in ("set_flag", "set_value", "modify_dice"):
                        param = action.get("param")
                        val = action.get("param_value")
                        if param is not None:
                            if hasattr(context, param):
                                setattr(context, param, val)
                                executed_any = True
                            elif hasattr(context, "extra_flags"):
                                context.extra_flags[param] = val
                                # 同步寫入戰鬥等級的臨時 Flag 共享池
                                if hasattr(context, "combat_context") and context.combat_context is not None:
                                    if not hasattr(context.combat_context, "_temp_flags"):
                                        context.combat_context._temp_flags = {}
                                    context.combat_context._temp_flags[param] = val
                                executed_any = True
                            
                if executed_any:
                    if "cooldown" in trigger:
                        orig = trigger.get("_orig_trigger", trigger)
                        orig["cooldown_left"] = trigger["cooldown"]
                        trigger["cooldown_left"] = trigger["cooldown"]
                    if "_owner_effect" in trigger:
                        _handle_status_consume(target, trigger["_owner_effect"])

    @staticmethod
    def dispatch_event(event: str, caster: Any, target: Optional[Any], combat_manager: Optional[Any], **kwargs):
        guard_key = (id(caster), event)
        if guard_key in TriggerEngine._dispatching:
            return
        TriggerEngine._dispatching.add(guard_key)
        try:
            TriggerEngine._dispatch_event_raw(event, caster, target, combat_manager, **kwargs)
        finally:
            TriggerEngine._dispatching.discard(guard_key)

    @staticmethod
    def _dispatch_event_raw(event: str, caster: Any, target: Optional[Any], combat_manager: Optional[Any], **kwargs):
        """
        在特定事件觸發時，遍歷並執行對應的 JSON Actions。
        """
        triggers = TriggerEngine.get_active_triggers(caster)
        logs = []
        context = kwargs.get("context")

        for trigger in triggers:
            if trigger.get("event") == event:
                if trigger.get("cooldown_left", 0) > 0:
                    continue
                t_chance = trigger.get("chance", 1.0)
                if t_chance < 1.0 and random.random() > t_chance:
                    continue
                if not evaluate_condition(trigger.get("condition"), caster, context, target):
                    continue
                
                # 如果是血量低於百分比判定
                if event == "on_health_below":
                    threshold = trigger.get("health_threshold", 100)
                    curr_hp = get_entity_attr(caster, "hp", 100)
                    max_hp = get_entity_attr(caster, "max_hp", 100)
                    if max_hp > 0 and (curr_hp / max_hp * 100) > threshold:
                        continue
                
                # 用 helper 函式進行目標血量百分比條件過濾
                if not TriggerEngine._check_target_health_filters(trigger, target):
                    continue
                
                executed_any = False
                for action in trigger.get("actions", []):
                    chance = action.get("chance", 1.0)
                    if chance < 1.0 and random.random() > chance:
                        continue
                    
                    action_type = action.get("action_type")
                    target_str = action.get("target", "target")
                    action_targets = resolve_action_target(target_str, caster, target, combat_manager)
                    if not action_targets:
                        continue

                    for action_target in action_targets:
                        if action_type == "inflict_damage":
                            flat = action.get("flat_value", 0.0)
                            stat = action.get("scaling_stat")
                            mult = action.get("value_multiplier", 1.0)
                            damage_type = action.get("damage_type", "true_damage")
                            
                            val = flat
                            if stat:
                                if stat.upper() == "DAMAGE_TAKEN":
                                    val += kwargs.get("damage", 0) * mult
                                else:
                                    val += get_entity_stat(caster, stat) * mult
                            
                            val = int(round(val))
                            if val > 0:
                                if combat_manager:
                                    is_target_player = (action_target == combat_manager.character)
                                    is_source_player = (caster == combat_manager.character)
                                    actual, dmg_logs = combat_manager._apply_damage(
                                        action_target,
                                        is_target_player=is_target_player,
                                        damage=val,
                                        source_entity=caster,
                                        is_source_player=is_source_player
                                    )
                                    source_name = TriggerEngine._get_name(caster)
                                    target_name = TriggerEngine._get_name(action_target)
                                    log_msg = f"💥 觸發效果：{source_name} 對 {target_name} 額外造成 {actual} 點 {damage_type} 傷害！"
                                    combat_manager.battle_logs.append(log_msg)
                                    if dmg_logs:
                                        combat_manager.battle_logs.extend(dmg_logs)
                                    logs.append(log_msg)
                                else:
                                    curr_hp = get_entity_attr(action_target, "hp", 100)
                                    set_entity_attr(action_target, "hp", max(0, curr_hp - val))
                                executed_any = True

                        elif action_type == "gain_shield":
                            flat = action.get("flat_value", 0.0)
                            stat = action.get("scaling_stat")
                            mult = action.get("value_multiplier", 1.0)
                            
                            val = flat
                            if stat:
                                if stat.upper() == "DAMAGE_TAKEN":
                                    val += kwargs.get("damage", 0) * mult
                                else:
                                    val += get_entity_stat(caster, stat) * mult
                            
                            val = int(round(val))
                            if val > 0:
                                curr_temp = get_entity_attr(action_target, "temp_hp", 0)
                                set_entity_attr(action_target, "temp_hp", curr_temp + val)
                                add_entity_status_effect(action_target, "Shield", "護盾防護", 3)
                                
                                target_name = TriggerEngine._get_name(action_target)
                                log_msg = f"🛡️ 觸發效果：{target_name} 獲得了 {val} 點臨時護盾！"
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                executed_any = True

                        elif action_type == "heal":
                            flat = action.get("flat_value", 0.0)
                            stat = action.get("scaling_stat")
                            mult = action.get("value_multiplier", 1.0)
                            resource = action.get("target_resource", "hp")
                            
                            val = flat
                            if stat:
                                if stat.upper() == "DAMAGE_TAKEN":
                                    val += kwargs.get("damage", 0) * mult
                                else:
                                    val += get_entity_stat(caster, stat) * mult
                            
                            val = int(round(val))
                            if val > 0:
                                curr_val = get_entity_attr(action_target, resource, 100)
                                max_val = get_entity_attr(action_target, "max_" + resource, 100)
                                set_entity_attr(action_target, resource, min(max_val, curr_val + val))
                                
                                target_name = TriggerEngine._get_name(action_target)
                                res_name = "生命值" if resource == "hp" else ("魔法值" if resource == "mp" else "理智值")
                                log_msg = f"💚 觸發效果：為 {target_name} 恢復了 {val} 點 {res_name}！"
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                
                                if resource == "hp":
                                    TriggerEngine.dispatch_event("on_health_up", action_target, caster, combat_manager)
                                executed_any = True

                        elif action_type == "apply_status":
                            status_name = action.get("status_name")
                            duration = action.get("duration", 1)
                            status_triggers = action.get("executable_triggers", [])
                            status_bonuses = action.get("bonuses", {})
                            max_stacks = action.get("max_stacks", 5)
                            trigger_limit = action.get("trigger_limit", 0)
                            if status_name:
                                add_entity_status_effect(
                                    action_target, 
                                    status_name, 
                                    f"由觸發效果施加的{status_name}", 
                                    duration, 
                                    bonuses=status_bonuses, 
                                    executable_triggers=status_triggers,
                                    max_stacks=max_stacks,
                                    trigger_limit=trigger_limit
                                )
                                target_name = TriggerEngine._get_name(action_target)
                                log_msg = f"✨ 觸發效果：施加狀態【{status_name}】給 {target_name}，持續 {duration} 回合。"
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                executed_any = True

                        elif action_type == "remove_status":
                            status_name = action.get("status_name")
                            if status_name:
                                from core.skill_processor import SkillExecutionPipeline
                                SkillExecutionPipeline._remove_status(action_target, status_name)
                                target_name = TriggerEngine._get_name(action_target)
                                log_msg = f"✨ 觸發效果：清除了 {target_name} 身上的狀態【{status_name}】。"
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                executed_any = True

                        elif action_type == "purge_debuffs":
                            debuffs = ["Stun", "Silence", "Root", "Slow", "Burn", "Frostbite", "Blind", "Doom", "Charm", "Confusion", "Sunder", "Taunt"]
                            from core.skill_processor import SkillExecutionPipeline
                            for debuff in debuffs:
                                if entity_has_status(action_target, debuff):
                                    SkillExecutionPipeline._remove_status(action_target, debuff)
                            target_name = TriggerEngine._get_name(action_target)
                            log_msg = f"✨ 觸發效果：清除了 {target_name} 身上的所有負面狀態！"
                            if combat_manager:
                                combat_manager.battle_logs.append(log_msg)
                            logs.append(log_msg)
                            executed_any = True

                        elif action_type == "call_special_mechanic":
                            keyword = action.get("keyword_name")
                            if keyword == "Time_Warp":
                                prev_hp = getattr(action_target, "_hp_snapshot", None)
                                prev_mp = getattr(action_target, "_mp_snapshot", None)
                                if prev_hp is not None and prev_mp is not None:
                                    set_entity_attr(action_target, "hp", prev_hp)
                                    set_entity_attr(action_target, "mp", prev_mp)
                                    log_msg = f"⏳ 觸發效果【時光回溯】：將生命與魔法回溯至 {prev_hp} HP / {prev_mp} MP！"
                                else:
                                    max_hp = get_entity_attr(action_target, "max_hp", 100)
                                    max_mp = get_entity_attr(action_target, "max_mp", 50)
                                    set_entity_attr(action_target, "hp", max_hp)
                                    set_entity_attr(action_target, "mp", max_mp)
                                    log_msg = "⏳ 觸發效果【時光回溯】：重置生命與魔法至上限！"
                                
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                executed_any = True
                            elif keyword == "Prevent_Death":
                                if isinstance(action_target, dict):
                                    action_target["_death_prevented"] = True
                                else:
                                    setattr(action_target, "_death_prevented", True)
                                log_msg = "🛡️ 觸發免死防護，免疫本次死亡！"
                                if combat_manager:
                                    combat_manager.battle_logs.append(log_msg)
                                logs.append(log_msg)
                                executed_any = True
                
                if executed_any:
                    if "cooldown" in trigger:
                        orig = trigger.get("_orig_trigger", trigger)
                        orig["cooldown_left"] = trigger["cooldown"]
                        trigger["cooldown_left"] = trigger["cooldown"]
                    if "_owner_effect" in trigger:
                        _handle_status_consume(caster, trigger["_owner_effect"])

    @staticmethod
    def _get_name(entity) -> str:
        if hasattr(entity, "data"):
            return entity.data.name
        if isinstance(entity, dict):
            return entity.get("name", "未知單位")
        return "未知單位"
