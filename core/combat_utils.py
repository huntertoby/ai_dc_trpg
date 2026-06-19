import random
from typing import Dict, Any, List, Optional
from core.models import StatusEffect
from core.constants import normalize_status_name, STATUS_REGISTRY

def is_mock(obj) -> bool:
    return obj.__class__.__name__ in ('Mock', 'MagicMock', 'NonCallableMock')

def get_entity_id(entity) -> str:
    if hasattr(entity, "character_id"):
        return str(entity.character_id)
    if hasattr(entity, "data") and hasattr(entity.data, "character_id"):
        return str(entity.data.character_id)
    return str(id(entity))

def get_entity_name(entity) -> str:
    if hasattr(entity, "data") and hasattr(entity.data, "name"):
        return entity.data.name
    if isinstance(entity, dict):
        return entity.get("name", "未知單位")
    if hasattr(entity, "name"):
        return entity.name
    return "未知單位"

def get_entity_attr(entity, key: str, default: Any = 0) -> Any:
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "vitality"):
            vitality = data.vitality
            if vitality is not None and not is_mock(vitality):
                if key == "hp": return vitality.hp
                if key == "max_hp": 
                    if hasattr(entity, "max_hp") and not is_mock(getattr(entity, "max_hp")):
                        return entity.max_hp
                    con = get_entity_stat(entity, "CON")
                    return 100 + con * 10
                if key == "mp": return vitality.mp
                if key == "max_mp":
                    if hasattr(entity, "max_mp") and not is_mock(getattr(entity, "max_mp")):
                        return entity.max_mp
                    int_val = get_entity_stat(entity, "INT")
                    wis_val = get_entity_stat(entity, "WIS")
                    return 50 + int_val * 10 + wis_val * 5
                if key == "sanity": return vitality.sanity
                if key == "max_sanity":
                    if hasattr(entity, "max_sanity") and not is_mock(getattr(entity, "max_sanity")):
                        return entity.max_sanity
                    wis_val = get_entity_stat(entity, "WIS")
                    return 100 + wis_val * 5
                if key == "stamina": return vitality.stamina
                if key == "temp_hp": return vitality.temp_hp
                if key == "max_stamina":
                    if hasattr(entity, "max_stamina") and not is_mock(getattr(entity, "max_stamina")):
                        return entity.max_stamina
                    con = get_entity_stat(entity, "CON")
                    return 100 + con * 5
                    
    if isinstance(entity, dict):
        if key in ["hp", "max_hp", "mp", "max_mp", "sanity", "max_sanity", "stamina", "max_stamina", "temp_hp"]:
            return entity.get(key, default)
        
    if not is_mock(entity) and hasattr(entity, key):
        val = getattr(entity, key)
        if not is_mock(val):
            return val
            
    return default
 
def change_entity_hp(entity, delta: int, combat_manager=None, source_entity=None, context=None) -> tuple[int, List[str]]:
    """
    統一的生命值調整與判定器。
    delta: 生命值變化量 (正數為治療，負數為傷害)
    combat_manager: 戰鬥管理器，用於處理免死與日誌
    source_entity: 造成變化的來源實體
    context: 戰鬥上下文/技能上下文
    """
    logs = []
    is_player = is_player_entity(entity)
    name = get_entity_name(entity)
    
    curr_hp = get_entity_attr(entity, "hp", 100)
    max_hp = get_entity_attr(entity, "max_hp", 100)
    
    new_hp = curr_hp + delta
    
    if new_hp <= 0 and curr_hp > 0:
        if has_status(entity, "Phoenix_Rebirth"):
            remove_status(entity, "Phoenix_Rebirth")
            max_mp = get_entity_attr(entity, "max_mp", 50)
            
            new_hp = int(max_hp * 0.5)
            new_mp = int(max_mp * 0.5)
            
            if is_player:
                entity.data.vitality.hp = new_hp
                entity.data.vitality.mp = new_mp
                if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
                    entity.save()
            elif isinstance(entity, dict):
                entity["hp"] = new_hp
                entity["mp"] = new_mp
                
            logs.append("🔥 觸發【涅槃重燃】：單位涅槃復活，並回復了 50% 的生命與魔法！")
            return new_hp - curr_hp, logs
        
        if combat_manager is not None:
            from core.trigger_engine import TriggerEngine
            if is_player:
                setattr(entity, "_death_prevented", False)
            elif isinstance(entity, dict):
                entity["_death_prevented"] = False
                
            TriggerEngine.dispatch_event("on_fatal_damage", entity, source_entity, combat_manager, damage=-delta, context=context)
            
            prevented = False
            if is_player and getattr(entity, "_death_prevented", False):
                prevented = True
                setattr(entity, "_death_prevented", False)
            elif isinstance(entity, dict) and entity.get("_death_prevented", False):
                prevented = True
                entity["_death_prevented"] = False
                
            if prevented:
                new_hp = 1
                logs.append("🛡️ 受到致命傷害時觸發免死效果，保留 1 點生命值！")
                
    new_hp = max(0, min(new_hp, max_hp))
    actual_change = new_hp - curr_hp
    
    if is_player:
        entity.data.vitality.hp = new_hp
        if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
            entity.save()
    elif isinstance(entity, dict):
        entity["hp"] = new_hp
        
    return actual_change, logs

def set_entity_attr(entity, key: str, value: Any):
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "vitality"):
            vitality = data.vitality
            if vitality is not None and not is_mock(vitality):
                if key == "hp":
                    curr_hp = get_entity_attr(entity, "hp", 100)
                    change_entity_hp(entity, value - curr_hp)
                    return
                if key == "mp":
                    vitality.mp = value
                    return
                if key == "sanity":
                    vitality.sanity = value
                    return
                if key == "stamina":
                    vitality.stamina = value
                    return
                if key == "temp_hp":
                    vitality.temp_hp = value
                    return
    if isinstance(entity, dict):
        if key in ["hp", "mp", "sanity", "stamina", "temp_hp"]:
            if key == "hp":
                curr_hp = get_entity_attr(entity, "hp", 100)
                change_entity_hp(entity, value - curr_hp)
                return
            entity[key] = value
            return
    if not is_mock(entity) and hasattr(entity, key):
        setattr(entity, key, value)


def get_entity_stat(entity, stat_name: str) -> int:
    stat_name = stat_name.upper()
    if stat_name == "MAX_HP":
        return get_entity_attr(entity, "max_hp", 100)
    if stat_name == "MAX_MP":
        return get_entity_attr(entity, "max_mp", 50)
    if hasattr(entity, "total_stats"):
        stats = entity.total_stats
        if stats is not None and not is_mock(stats):
            if isinstance(stats, dict):
                return stats.get(stat_name, 10)
            
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "primary_stats"):
            p_stats = data.primary_stats
            if p_stats is not None and not is_mock(p_stats):
                if hasattr(p_stats, stat_name):
                    return getattr(p_stats, stat_name)
                    
    if isinstance(entity, dict):
        base_val = 10
        if stat_name in ["STR", "DEX", "CON"]:
            base_val = entity.get("attack", 10)
        elif stat_name in ["INT", "WIS", "CHA"]:
            base_val = entity.get("attack", 10)
        else:
            base_val = entity.get(stat_name.lower(), 10)
            
        effects = entity.get("status_effects", [])
        bonus_val = 0
        for effect in effects:
            bonuses = effect.bonuses if hasattr(effect, "bonuses") else effect.get("bonuses", {})
            if stat_name in bonuses:
                bonus_val += bonuses[stat_name]
            elif stat_name.lower() in bonuses:
                bonus_val += bonuses[stat_name.lower()]
        return max(1, base_val + int(bonus_val))
        
    return 10

def is_player_entity(entity) -> bool:
    if hasattr(entity, "data") and hasattr(entity.data, "status_effects"):
        return True
    return False

def get_entity_combat_stat(entity, stat_name: str, default: Any = 0) -> Any:
    is_player = is_player_entity(entity)
    
    if stat_name in ["p_def", "m_def"]:
        damage_type = "physical" if stat_name == "p_def" else "magical"
        if is_player:
            c_stats = entity.combat_stats if hasattr(entity, "combat_stats") else {}
            base_def = c_stats.get(stat_name, default) if isinstance(c_stats, dict) else getattr(c_stats, stat_name, default)
            return max(1, int(base_def))
        else:
            base_def = entity.get("defense", default) if damage_type == "physical" else entity.get("m_defense", default)
            stat_key = "p_def" if damage_type == "physical" else "m_def"
            alt_key = "defense" if damage_type == "physical" else "m_defense"
            effects = entity.get("status_effects", [])
            
            absolute_bonus = 0
            multiplier = 1.0

            for effect in effects:
                bonuses = effect.bonuses if hasattr(effect, "bonuses") else effect.get("bonuses", {})
                value = None
                if stat_key in bonuses:
                    value = bonuses[stat_key]
                elif alt_key in bonuses:
                    value = bonuses[alt_key]

                if value is not None:
                    if isinstance(value, (int, float)) and -1 < value < 0:
                        multiplier *= (1 + value)
                    else:
                        absolute_bonus += value

            final_def = (base_def + absolute_bonus) * multiplier
            return int(final_def)
            
    if stat_name == "evasion_rate":
        if is_player:
            evasion = entity.combat_stats.get("evasion_rate", default) if hasattr(entity, "combat_stats") and isinstance(entity.combat_stats, dict) else default
            return max(0.0, min(1.0, float(evasion)))
        else:
            if has_status(entity, "Slow"):
                return 0.0
            return max(0.0, min(1.0, float(entity.get("evasion_rate", default))))
            
    if hasattr(entity, "combat_stats"):
        stats = entity.combat_stats
        if stats is not None and not is_mock(stats):
            if isinstance(stats, dict):
                return stats.get(stat_name, default)
            if hasattr(stats, "get"):
                val = stats.get(stat_name, default)
                if not is_mock(val):
                    return val
                    
    if isinstance(entity, dict):
        if stat_name == "crit_rate": return entity.get("crit_rate", 0.05)
        if stat_name == "accuracy": return entity.get("accuracy", 0.95)
        if stat_name == "skill_power": return entity.get("skill_power", 1.0)
        
    return default

def has_status(entity, status_name: str) -> bool:
    norm_query = normalize_status_name(status_name)
    if is_player_entity(entity):
        return any(normalize_status_name(e.name) == norm_query for e in entity.data.status_effects)
    elif isinstance(entity, dict):
        effects = entity.get("status_effects", [])
        return any(
            (normalize_status_name(e.name) == norm_query if hasattr(e, "name") else normalize_status_name(e.get("name")) == norm_query)
            for e in effects
        )
    return False

def remove_status(entity, status_name: str):
    norm_query = normalize_status_name(status_name)
    if is_player_entity(entity):
        if hasattr(entity.data, "status_effects"):
            entity.data.status_effects = [e for e in entity.data.status_effects if normalize_status_name(e.name) != norm_query]
            if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
                entity.save()
    elif isinstance(entity, dict):
        if "status_effects" in entity:
            entity["status_effects"] = [
                e for e in entity["status_effects"]
                if (normalize_status_name(e.name) != norm_query if hasattr(e, "name") else normalize_status_name(e.get("name")) != norm_query)
            ]

def get_status_effect(entity, status_name: str) -> Optional[Any]:
    norm_query = normalize_status_name(status_name)
    if is_player_entity(entity):
        effects = entity.data.status_effects or []
        return next((e for e in effects if normalize_status_name(e.name) == norm_query), None)
    elif isinstance(entity, dict):
        for e in entity.get("status_effects", []):
            n = e.name if hasattr(e, "name") else e.get("name")
            if normalize_status_name(n) == norm_query:
                return e
    return None

def add_entity_status_effect(
    entity,
    name: str,
    description: str,
    duration: int,
    bonuses: dict = None,
    executable_triggers: list = None,
    max_stacks: int = 5,
    trigger_limit: int = 0,
    dot_damage_flat: float = 0.0,
    dot_scaling_stat: str = None,
    dot_multiplier: float = 0.0,
    dot_damage_type: str = "true_damage",
    extra_data: dict = None,
    tags: list = None,
    custom_status_name: str = None,
    canonical_status: str = None,
):
    if is_mock(entity) and not hasattr(entity, "data"):
        return
        
    norm_name = normalize_status_name(name)
    debuffs = {k for k, v in STATUS_REGISTRY.items() if v.get("is_debuff", False)}
    if norm_name in debuffs:
        if has_status(entity, "Immune"):
            return
        if has_status(entity, "Ward"):
            remove_status(entity, "Ward")
            return
            
    existing_effect = get_status_effect(entity, norm_name)

    if existing_effect:
        if hasattr(existing_effect, "stacks"):
            existing_effect.stacks = min(existing_effect.stacks + 1, existing_effect.max_stacks)
            existing_effect.duration = duration
        else:
            curr_stacks = existing_effect.get("stacks", 1)
            m_stacks = existing_effect.get("max_stacks", max_stacks)
            existing_effect["stacks"] = min(curr_stacks + 1, m_stacks)
            existing_effect["duration"] = duration
        
        if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
            entity.save()
        return

    bonuses = bonuses or {}
    executable_triggers = executable_triggers or []
    extra_data = extra_data or {}
    tags = tags or []
    
    if is_player_entity(entity):
        effect = StatusEffect(
            name=name,
            description=description,
            duration_type="turns",
            duration=duration,
            bonuses=bonuses,
            executable_triggers=executable_triggers,
            stacks=1,
            max_stacks=max_stacks,
            trigger_limit=trigger_limit,
            trigger_count=0,
            dot_damage_flat=dot_damage_flat,
            dot_scaling_stat=dot_scaling_stat,
            dot_multiplier=dot_multiplier,
            dot_damage_type=dot_damage_type,
            tags=tags,
            extra_data=extra_data,
            custom_status_name=custom_status_name,
            canonical_status=canonical_status
        )
        entity.data.status_effects.append(effect)
        if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
            entity.save()
        return
        
    if isinstance(entity, dict):
        if "status_effects" not in entity:
            entity["status_effects"] = []
        entity["status_effects"].append({
            "name": name,
            "description": description,
            "duration": duration,
            "bonuses": bonuses,
            "executable_triggers": executable_triggers,
            "stacks": 1,
            "max_stacks": max_stacks,
            "trigger_limit": trigger_limit,
            "trigger_count": 0,
            "tags": tags,
            "extra_data": extra_data,
            "dot_damage_flat": dot_damage_flat,
            "custom_status_name": custom_status_name,
            "canonical_status": canonical_status
        })

def decay_status_effects(entity) -> List[str]:
    expired = []
    if is_player_entity(entity):
        remaining = []
        for effect in entity.data.status_effects:
            if effect.duration_type == "turns":
                effect.duration -= 1
                if effect.duration > 0:
                    remaining.append(effect)
                else:
                    expired.append(effect.name)
            else:
                remaining.append(effect)
        entity.data.status_effects = remaining
        if hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
            entity.save()
    elif isinstance(entity, dict):
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

DOT_STATUS_CONFIG = {
    "Burn":      ("🔥", "灼燒"),
    "Frostbite": ("🥶", "凍傷"),
    "Bleed":     ("🩸", "流血"),
    "Poison":    ("☠️", "中毒"),
}

def apply_dot_damage(entity, dmg: int, emoji: str, label: str, logs: list):
    name = get_entity_name(entity)
    temp_hp = get_entity_attr(entity, "temp_hp", 0)
    
    if temp_hp > 0:
        absorbed = min(temp_hp, dmg)
        set_entity_attr(entity, "temp_hp", temp_hp - absorbed)
        dmg -= absorbed
        if dmg == 0:
            logs.append(f"{emoji} {name} 受到{label} DoT {absorbed} 點傷害，被護盾完全吸收！")
        else:
            logs.append(f"{emoji} {name} 受到{label} DoT 傷害，護盾破裂吸收了 {absorbed} 點！")
            
    if dmg > 0:
        hp = get_entity_attr(entity, "hp", 0)
        set_entity_attr(entity, "hp", max(0, hp - dmg))
        logs.append(f"{emoji} {name} 受到{label} DoT，扣除 {dmg} 點生命值！")
        
    if is_player_entity(entity) and hasattr(entity, "save") and not is_mock(getattr(entity, "save")):
        entity.save()
