# core/skill_processor.py
import random
import re
from typing import Dict, Any, Tuple, Optional
from core.models import Skill, CharacterSchema
from core.constants import STAT_TRANSLATIONS

def is_mock(obj) -> bool:
    return obj.__class__.__name__ in ('Mock', 'MagicMock', 'NonCallableMock')

# 實體屬性獲取輔助方法
def get_entity_attr(entity, key: str, default: Any = 0) -> Any:
    # 優先檢查 data
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
 
def set_entity_attr(entity, key: str, value: Any):
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "vitality"):
            vitality = data.vitality
            if vitality is not None and not is_mock(vitality):
                if key == "hp":
                    vitality.hp = value
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
            
    # 若是 Mock 且 data 為實體對象，回退至 primary_stats 讀取
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "primary_stats"):
            p_stats = data.primary_stats
            if p_stats is not None and not is_mock(p_stats):
                if hasattr(p_stats, stat_name):
                    return getattr(p_stats, stat_name)
                    
    if isinstance(entity, dict):
        if stat_name in ["STR", "DEX", "CON"]:
            return entity.get("attack", 10)
        if stat_name in ["INT", "WIS", "CHA"]:
            return entity.get("attack", 10)
        return entity.get(stat_name.lower(), 10)
        
    return 10

def get_entity_combat_stat(entity, stat_name: str, default: Any = 0) -> Any:
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
        if stat_name == "p_def": return entity.get("defense", default)
        if stat_name == "m_def": return entity.get("m_defense", default)
        if stat_name == "crit_rate": return entity.get("crit_rate", 0.05)
        if stat_name == "evasion_rate": return entity.get("evasion_rate", 0.05)
        if stat_name == "accuracy": return entity.get("accuracy", 0.95)
        if stat_name == "skill_power": return entity.get("skill_power", 1.0)
        
    return default

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
):
    # 檢查是否為 Mock 且沒有 data
    if is_mock(entity) and not hasattr(entity, "data"):
        return
        
    # 免疫 (Immune) 攔截機制：
    # 當施加的狀態為 Debuff 且角色擁有「Immune」或「霸體」狀態時，直接攔截並忽略。
    debuffs = {"Stun", "Silence", "Root", "Slow", "Burn", "Frostbite", "Blind", "Doom", "Charm", "Confusion", "Sunder"}
    if name in debuffs:
        if SkillExecutionPipeline._has_status(entity, "Immune") or SkillExecutionPipeline._has_status(entity, "霸體"):
            return
            
    # Stacking logic: if status already exists, increment stacks and reset duration
    existing_effect = None
    if hasattr(entity, "data") and hasattr(entity.data, "status_effects") and entity.data.status_effects is not None:
        existing_effect = next((e for e in entity.data.status_effects if e.name == name), None)
    elif isinstance(entity, dict) and "status_effects" in entity:
        existing_effect = next((e for e in entity["status_effects"] if (e.name == name if hasattr(e, "name") else e.get("name") == name)), None)

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

    from core.models import StatusEffect
    bonuses = bonuses or {}
    executable_triggers = executable_triggers or []
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
    )
    if hasattr(entity, "data"):
        data = entity.data
        if data is not None and not is_mock(data) and hasattr(data, "status_effects"):
            data.status_effects.append(effect)
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
            "trigger_count": 0
        })

class SkillExecutionPipeline:
    @classmethod
    def execute(cls, skill: Skill, caster: Any, target: Optional[Any] = None, combat_context: Optional[Any] = None) -> Dict[str, Any]:
        logs = []
        control_flags = {}
        
        # 判定施法者自身是否處於放逐 (Banish)
        if cls._has_status(caster, "Banish"):
            raise ValueError("自身處於放逐狀態，無法使用技能")
        
        # 1. 取得基本屬性
        keywords = set(skill.mechanics.keywords)
        action_type = skill.mechanics.action_type
        target_type = skill.mechanics.target_type
        
        # 記錄上一個施放的技能到 caster 上，供 Copy 讀取。
        # 為了避免 Copy 記錄自己，只有非 Copy 技能才記錄為上一個技能。
        if "Copy" not in keywords:
            try:
                caster._last_skill_cast = skill
            except AttributeError:
                pass

        # Keyword: Copy (鏡像)：將自己這個技能的公式與特效暫時替換成戰鬥日誌中最後一個發動的技能。
        if "Copy" in keywords:
            last_skill = getattr(caster, "_last_skill_cast", None)
            if last_skill and last_skill.name != skill.name:
                skill.mechanics.formula = last_skill.mechanics.formula
                skill.mechanics.action_type = last_skill.mechanics.action_type
                skill.mechanics.target_type = last_skill.mechanics.target_type
                # 更新 keywords，排除 Copy，併入複製技能的關鍵字
                new_kw = set(last_skill.mechanics.keywords)
                new_kw.discard("Copy")
                keywords = new_kw
                skill.mechanics.keywords = list(new_kw)
                logs.append(f"🎭 觸發【鏡像】：成功複製了上一個技能【{last_skill.name}】的機制！")
        
        # 如果是 self，目標即為施法者
        if target_type == "self" or target is None:
            target = caster
            
        # ---------------------------------------------------------
        # Phase 1: Pre-cast (消耗與前置判定)
        # ---------------------------------------------------------
        costs = skill.mechanics.cost
        mp_cost = costs.get("MP", 0)
        san_cost = costs.get("SAN", 0)
        stamina_cost = costs.get("STAMINA", 0)
        
        # 檢查超載
        has_overload_debuff = cls._has_status(caster, "Overload_Lock")
        if has_overload_debuff:
            mp_cost *= 2
            logs.append("⚡ 【超載鎖定】作用中，法力消耗翻倍！")
            
        # 沉默 (Silence) 阻斷：阻斷耗 MP 的傷害型技能
        if cls._has_status(caster, "Silence"):
            if action_type == "damage" and mp_cost > 0:
                raise ValueError("被沉默無法施法")
                
        # 定身 (Root) 阻斷：阻斷物理近戰傷害型技能 (DEX/STR)
        if cls._has_status(caster, "Root"):
            if action_type == "damage" and skill.mechanics.formula.base_stat in ["STR", "DEX"]:
                raise ValueError("被定身無法使用物理近戰技能")
            
        current_mp = get_entity_attr(caster, "mp", 0)
        current_san = get_entity_attr(caster, "sanity", 100)
        current_stamina = get_entity_attr(caster, "stamina", 100)
        
        if current_mp < mp_cost:
            raise ValueError(f"法力值不足，需要 {mp_cost} MP，當前 {current_mp}")
        if current_san < san_cost:
            raise ValueError(f"理智值不足，需要 {san_cost} SAN，當前 {current_san}")
        if current_stamina < stamina_cost:
            raise ValueError(f"精力值不足，需要 {stamina_cost} 精力，當前 {current_stamina}")
            
        # Keyword: Sacrifice (犧牲)：額外扣除玩家當前 HP 的 10%，倍率 +1.0
        if "Sacrifice" in keywords:
            curr_hp = get_entity_attr(caster, "hp", 100)
            sacrifice_hp = int(curr_hp * 0.10)
            set_entity_attr(caster, "hp", max(1, curr_hp - sacrifice_hp))
            
            scaling_stat = skill.mechanics.formula.base_stat
            caster_stat = get_entity_stat(caster, scaling_stat)
            control_flags["sacrifice_bonus"] = caster_stat * 1.0
            logs.append(f"🩸 觸發【犧牲】：扣除當前 HP 的 10% ({sacrifice_hp} 點)，倍率額外 +1.0 (+{caster_stat} 威力)。")
            
        # 扣除基本消耗
        set_entity_attr(caster, "mp", max(0, current_mp - mp_cost))
        set_entity_attr(caster, "sanity", max(0, current_san - san_cost))
        if stamina_cost > 0:
            curr_stam = get_entity_attr(caster, "stamina", 100)
            set_entity_attr(caster, "stamina", max(0, curr_stam - stamina_cost))
            
        # Keyword: Martyr (殉道)
        if "Martyr" in keywords:
            set_entity_attr(caster, "hp", 0)
            control_flags["martyr_active"] = True
            logs.append("☠️ 觸發【殉道】：施法者將自身生命值歸零，引導終極救贖！")
            
        # Keyword: Overload (超載)
        if "Overload" in keywords:
            control_flags["overload_active"] = True
            
        # Keyword: Quickcast (瞬發)
        if "Quickcast" in keywords:
            control_flags["quickcast"] = True
            logs.append("⚡ 觸發【瞬發】：不扣除玩家行動點數，允許連續發動下一個技能。")

        # ---------------------------------------------------------
        # Phase 2: Target & Hit Check (目標與命中檢定)
        # ---------------------------------------------------------
        if cls._has_status(target, "Banish"):
            logs.append(f"🌀 目標 {cls._get_name(target)} 處於放逐狀態，技能無法命中！")
            return {"success": False, "msg": "技能因目標處於放逐狀態而失效。", "logs": logs}
            
        from core.contexts import ActionContext, DiceContext
        from core.trigger_engine import TriggerEngine

        # Setup ActionContext
        base_accuracy = get_entity_combat_stat(caster, "accuracy", 0.95)
        if cls._has_status(caster, "Blind"):
            base_accuracy *= 0.5
            logs.append("👁️ 【盲目】降低了施法者的命中率！")
            
        base_evasion = 0.0
            
        if target and target_type == "single" and cls._has_status(target, "Invis"):
            base_accuracy *= 0.3
            logs.append(f"👤 目標 {cls._get_name(target)} 處於隱身狀態，極難被選中！")

        base_crit = get_entity_combat_stat(caster, "crit_rate", 0.05)

        skill_dmg_type = "physical"
        if skill.mechanics.formula and skill.mechanics.formula.base_stat in ["INT", "WIS", "CHA"]:
            skill_dmg_type = "magical"

        act_ctx = ActionContext(
            accuracy=base_accuracy,
            evasion_rate=base_evasion,
            crit_rate=base_crit,
            damage_type=skill_dmg_type,
            combat_context=combat_context
        )

        # 觸發技能命中前攔截
        TriggerEngine.dispatch_interceptor("on_prepare", act_ctx, caster, target)

        is_hit = False
        if act_ctx.is_absolute_hit:
            is_hit = True
            logs.append("✨ 觸發【絕對命中】：技能無視迴避率！")
        else:
            # Check accuracy vs evasion
            hit_chance = act_ctx.accuracy * (1.0 - act_ctx.evasion_rate)
            is_hit = (random.random() <= hit_chance)

        if not is_hit:
            TriggerEngine.dispatch_event("on_miss", caster, target, combat_context)
            if target:
                TriggerEngine.dispatch_event("on_dodge", target, caster, combat_context)
            logs.append("❌ 技能未命中！")
            return {"success": False, "msg": "技能未命中目標。", "logs": logs}

        # ---------------------------------------------------------
        # Phase 3: Formula & Calculations (數值計算與修正)
        # ---------------------------------------------------------
        stats_dict = caster.total_stats if hasattr(caster, "total_stats") else {
            "STR": get_entity_stat(caster, "STR"),
            "DEX": get_entity_stat(caster, "DEX"),
            "CON": get_entity_stat(caster, "CON"),
            "INT": get_entity_stat(caster, "INT"),
            "WIS": get_entity_stat(caster, "WIS"),
            "CHA": get_entity_stat(caster, "CHA")
        }
        
        formula = skill.mechanics.formula
        stat_val = stats_dict.get(formula.base_stat, 5)

        # DiceContext for skill roll
        dice_ctx = DiceContext(dice_str=formula.dice, caster=caster, combat_context=combat_context)
        TriggerEngine.dispatch_interceptor("on_dice", dice_ctx, caster)

        if dice_ctx.roll_value is not None:
            dice_roll = dice_ctx.roll_value
        else:
            dice_roll = SkillProcessor.roll_dice(dice_ctx.dice_str)

        dice_roll += dice_ctx.roll_modifier
        if dice_ctx.floor_value is not None:
            dice_roll = max(dice_roll, dice_ctx.floor_value)

        # 祝福 (Bless) 骰子補底：小於 5 補底為 10
        if cls._has_status(caster, "Bless") and dice_roll <= 5:
            dice_roll = 10
            logs.append("🌟 觸發【祝福】補底：擲骰點數小於 5，自動補底提升至 10！")
            # 重新計算 base_val
            if formula.type == "multiplier":
                multiplier = dice_roll / formula.divisor
                base_val = stat_val * multiplier
            else:
                base_val = dice_roll + stat_val
        else:
            if formula.type == "multiplier":
                multiplier = dice_roll / formula.divisor
                base_val = stat_val * multiplier
            else:
                base_val = dice_roll + stat_val
                
        skill_power = get_entity_combat_stat(caster, "skill_power", 1.0)
        if combat_context and getattr(combat_context, "_echo_cast_active", False):
            skill_power *= 0.5
        base_val *= skill_power
        
        # Keyword: Stat_Swap (屬性反轉)
        if "Stat_Swap" in keywords:
            base_val *= 1.3
            logs.append("🔄 觸發【屬性反轉】：顛倒因果，威力提升。")
            
        # Keyword: Mimicry (擬態)
        if "Mimicry" in keywords:
            base_val *= 1.2
            logs.append("🎭 觸發【擬態】：複製目標的戰鬥姿態，威力提升。")

        # Keyword: Gamble (豪賭)：擲 1d2。結果 1 乘 3，結果 2 自身承受等量傷害
        if "Gamble" in keywords:
            gamble_roll = random.randint(1, 2)
            if gamble_roll == 1:
                base_val *= 3.0
                logs.append("🎲 觸發【豪賭】結果為 1：技能傷害乘 3 倍！")
            else:
                control_flags["gamble_backlash"] = base_val
                base_val = 0.0
                logs.append("🎲 觸發【豪賭】結果為 2：傷害無效，且施法者自身將承受等量反噬傷害！")
                
        if "overload_active" in control_flags:
            base_val *= 1.5
            logs.append("⚡ 觸發【超載】：技能威力提升 50%！")
            add_entity_status_effect(caster, "Overload_Lock", "超載懲罰：法力消耗翻倍", 2)
            
        if "sacrifice_bonus" in control_flags:
            base_val += control_flags["sacrifice_bonus"]

        # ---------------------------------------------------------
        # Phase 4: Defense & Penetration (減免與穿透)
        # ---------------------------------------------------------
        defense_stat = "p_def" if skill.mechanics.action_type == "damage" else "m_def"
        target_def = get_entity_combat_stat(target, defense_stat, 0)
        original_target_def = target_def
        
        # Pierce (穿透)：目標防禦力減半計算
        if "Pierce" in keywords:
            target_def = int(target_def * 0.5)
            logs.append("🎯 觸發【穿透】：目標防禦力減半計算。")
            
        # 觸發傷害計算前攔截
        act_ctx.raw_damage = base_val
        TriggerEngine.dispatch_interceptor("on_calculate_damage", act_ctx, caster, target)
        
        base_val *= act_ctx.damage_multiplier
        
        # 判定技能爆擊 (1.5x)
        is_crit = act_ctx.is_crit or (random.random() < act_ctx.crit_rate)
        act_ctx.is_crit = is_crit
        if is_crit:
            base_val *= 1.5
            logs.append("✨ **技能爆擊！** 技能基礎威力提升 50%！")

        if act_ctx.defense_ignore_ratio > 0:
            target_def = int(target_def * (1.0 - act_ctx.defense_ignore_ratio))
            logs.append(f"🎯 觸發無視防禦：無視了 {act_ctx.defense_ignore_ratio*100:.0f}% 的防禦力。")
            
        final_value = base_val
        effective_def = 0
        if action_type == "damage":
            # 限制防禦力最多只能抵擋 80% 威力
            max_mitigation = base_val * 0.80
            effective_def = min(target_def, max_mitigation)
            final_value = max(1.0, base_val - effective_def)
            
        # Execute (處決)：目標血量低於 20%，傷害乘以 3
        if "Execute" in keywords:
            target_hp = get_entity_attr(target, "hp", 100)
            target_max_hp = get_entity_attr(target, "max_hp", 100)
            if target_hp / target_max_hp < 0.20:
                final_value *= 3.0
                logs.append("🎯 觸發【處決】：目標生命值低於 20%，傷害乘以 3 倍！")
                
        # Sunder (破甲)：目標物理防禦力降低 30%（百分比乘法模式），持續 3 回合
        if "Sunder" in keywords:
            add_entity_status_effect(target, "Sunder", "物理防禦降低30%", 3, {"p_def": -0.30})
            logs.append(f"🛡️ 觸發【破甲】：目標物理防禦降低 30%。")
            
        # Keyword: Wall_Break (碎垣)
        if "Wall_Break" in keywords:
            if cls._has_status(target, "Shield"):
                cls._remove_status(target, "Shield")
            set_entity_attr(target, "temp_hp", 0)
            logs.append(f"🧱 觸發【碎垣】：無情擊碎了目標身上的護盾與 temp_hp！")

        # ---------------------------------------------------------
        # Phase 5: Apply HP/MP Changes (實體數值變更)
        # ---------------------------------------------------------
        final_value = round(final_value, 1)
        
        if "martyr_active" in control_flags:
            final_value *= 3.0
            
        # Reflect (反射)：自身減免 50% 傷害，並對攻擊者觸發反彈
        if action_type == "damage" and cls._has_status(target, "Reflect"):
            reflected_dmg = round(final_value * 0.5, 1)
            final_value = round(final_value * 0.5, 1)
            curr_hp = get_entity_attr(caster, "hp", 100)
            set_entity_attr(caster, "hp", max(0, curr_hp - int(reflected_dmg)))
            logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對施法者反彈了 {reflected_dmg} 點傷害！")
            cls._remove_status(target, "Reflect")

        if action_type == "damage":
            # 處理 Gamble 失敗反噬
            if "gamble_backlash" in control_flags:
                backlash = int(round(control_flags["gamble_backlash"], 1))
                curr_hp = get_entity_attr(caster, "hp", 100)
                set_entity_attr(caster, "hp", max(0, curr_hp - backlash))
                logs.append(f"🎲 【豪賭反噬】對施法者自身造成了 {backlash} 點傷害！")
                final_value = 0.0
            else:
                # Multi-hit (多重打擊) 拆分處理
                if "Multi-hit" in keywords:
                    hits_count = random.randint(3, 5)
                    split_val = round(final_value / hits_count, 1)
                    hits = [split_val] * hits_count
                    logs.append(f"⚔️ 觸發【多重打擊】：將總傷害拆分為 {hits_count} 次打擊 ({split_val}/次) 連續結算！")
                else:
                    hits = [final_value]

                total_applied_dmg = 0
                for idx, hit_dmg in enumerate(hits):
                    curr_temp = get_entity_attr(target, "temp_hp", 0)
                    dmg_to_apply = int(hit_dmg)
                    
                    if curr_temp > 0:
                        if curr_temp >= dmg_to_apply:
                            set_entity_attr(target, "temp_hp", curr_temp - dmg_to_apply)
                            logs.append(f"🛡️ [第 {idx+1} 擊] 護盾 (temp_hp) 抵擋了 {dmg_to_apply} 點傷害！剩餘護盾：{curr_temp - dmg_to_apply}")
                            dmg_to_apply = 0
                        else:
                            dmg_to_apply -= curr_temp
                            set_entity_attr(target, "temp_hp", 0)
                            logs.append(f"🛡️ [第 {idx+1} 擊] 護盾 (temp_hp) 被擊破，抵擋了 {curr_temp} 點傷害！")
                    
                    if dmg_to_apply > 0:
                        curr_hp = get_entity_attr(target, "hp", 100)
                        set_entity_attr(target, "hp", max(0, curr_hp - dmg_to_apply))
                        total_applied_dmg += dmg_to_apply
                        if len(hits) > 1:
                            logs.append(f"💥 [第 {idx+1} 擊] 對 {cls._get_name(target)} 造成了 {dmg_to_apply} 點傷害！")

                if total_applied_dmg > 0 or len(hits) == 1:
                    stat_name = STAT_TRANSLATIONS.get(formula.base_stat, formula.base_stat)
                    if formula.type == "multiplier":
                        calc_formula_str = f"{stat_name}:{stat_val} * ({dice_roll}/{formula.divisor})"
                    else:
                        calc_formula_str = f"{dice_roll} + {stat_name}:{stat_val}"
                        
                    if skill_power != 1.0:
                        calc_formula_str = f"({calc_formula_str}) * 威力:{skill_power:.1f}"
                        
                    extra_mults = []
                    if "Stat_Swap" in keywords: extra_mults.append("屬反:1.3x")
                    if "Mimicry" in keywords: extra_mults.append("擬態:1.2x")
                    if "Gamble" in keywords and 'gamble_roll' in locals() and gamble_roll == 1: 
                        extra_mults.append("豪賭:3.0x")
                    if "overload_active" in control_flags: extra_mults.append("超載:1.5x")
                    if "martyr_active" in control_flags: extra_mults.append("殉道:3.0x")
                    
                    if extra_mults:
                        calc_formula_str = f"({calc_formula_str}) * {' * '.join(extra_mults)}"
                        
                    if "sacrifice_bonus" in control_flags:
                        calc_formula_str = f"({calc_formula_str}) + 犧牲威力:{control_flags['sacrifice_bonus']:.1f}"
                        
                    defense_type_name = "物理防禦" if defense_stat == "p_def" else "魔法防禦"
                    pierce_suffix = " (穿透減半)" if "Pierce" in keywords else ""
                    def_str = f"{original_target_def}{pierce_suffix}"
                    
                    execute_mult = ""
                    if "Execute" in keywords:
                        target_hp = get_entity_attr(target, "hp", 100)
                        target_max_hp = get_entity_attr(target, "max_hp", 100)
                        if target_hp / target_max_hp < 0.20:
                            execute_mult = " * 🎯處決:3.0x"
                            
                    calc_info = (
                        f"\n 🎲 **判定**: {dice_roll} (公式: {formula.dice})"
                        f"\n 📊 **威力**: ({calc_formula_str}){execute_mult} = {final_value:.1f}"
                        f"\n 🛡️ **防禦**: -{effective_def:.1f} (目標 {defense_type_name} {def_str}，有效減免: {effective_def:.1f}，上限 80%)"
                    )
                    if len(hits) > 1:
                        logs.append(f"💥 總計對 {cls._get_name(target)} 造成了 {total_applied_dmg} 點真實傷害！" + calc_info)
                    else:
                        logs.append(f"💥 對 {cls._get_name(target)} 造成了 {total_applied_dmg} 點真實傷害！" + calc_info)
                        
                    # 觸發後置傷害與擊殺事件
                    from core.trigger_engine import TriggerEngine
                    TriggerEngine.dispatch_event("on_hit", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                    TriggerEngine.dispatch_event("on_damaged", target, caster, combat_context, damage=total_applied_dmg, context=act_ctx)
                    if act_ctx.is_crit:
                        TriggerEngine.dispatch_event("on_crit", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                    
                    target_hp = get_entity_attr(target, "hp", 0)
                    if target_hp <= 0:
                        TriggerEngine.dispatch_event("on_kill", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                
                # Lifesteal (吸血)：實際造成傷害的 30% 進行回復 (update_vitality)
                if "Lifesteal" in keywords:
                    heal_amt = int(final_value * 0.30)
                    curr_hp = get_entity_attr(caster, "hp", 100)
                    if hasattr(caster, "update_vitality") and not is_mock(getattr(caster, "update_vitality")):
                        caster.update_vitality(hp=curr_hp + heal_amt)
                    else:
                        max_hp = get_entity_attr(caster, "max_hp", 100)
                        set_entity_attr(caster, "hp", min(max_hp, curr_hp + heal_amt))
                    logs.append(f"🩸 觸發【吸血】：回復了施法者 {heal_amt} 點生命值。")
                    
                    if heal_amt > 0:
                        from core.trigger_engine import TriggerEngine
                        TriggerEngine.dispatch_event("on_health_up", caster, None, combat_context)
                    
                if "Vampiric_Aura" in keywords:
                    add_entity_status_effect(caster, "Vampiric_Aura", "吸血光環中", 3)
                    logs.append("🌟 觸發【吸血光環】：周圍盟友被吸血光環所籠罩。")
                    
                if "Soul_Link" in keywords:
                    add_entity_status_effect(target, "Soul_Link", "與施法者靈魂連結", 3)
                    add_entity_status_effect(caster, "Soul_Link", "與目標靈魂連結", 3)
                    logs.append("🔗 觸發【靈魂連結】：施法者與目標的生命被絲線綁定！")
                    
        elif action_type == "heal":
            curr_hp = get_entity_attr(target, "hp", 100)
            max_hp = get_entity_attr(target, "max_hp", 100)
            if hasattr(target, "update_vitality") and not is_mock(getattr(target, "update_vitality")):
                target.update_vitality(hp=curr_hp + int(final_value))
            else:
                set_entity_attr(target, "hp", min(max_hp, curr_hp + int(final_value)))
                
            if final_value > 0:
                from core.trigger_engine import TriggerEngine
                TriggerEngine.dispatch_event("on_health_up", target, caster, combat_context)
                
            stat_name = STAT_TRANSLATIONS.get(formula.base_stat, formula.base_stat)
            if formula.type == "multiplier":
                calc_formula_str = f"{stat_name}:{stat_val} * ({dice_roll}/{formula.divisor})"
            else:
                calc_formula_str = f"{dice_roll} + {stat_name}:{stat_val}"
                
            if skill_power != 1.0:
                calc_formula_str = f"({calc_formula_str}) * 威力:{skill_power:.1f}"
                
            calc_info = (
                f"\n 🎲 **判定**: {dice_roll} (公式: {formula.dice})"
                f"\n 📊 **治療量**: ({calc_formula_str}) = {final_value:.1f}"
            )
            logs.append(f"💚 為 {cls._get_name(target)} 恢復了 {final_value} 點生命值！" + calc_info)

        # ---------------------------------------------------------
        # Phase 6: Status Application (狀態附加)
        # ---------------------------------------------------------
        if "Banish" in keywords:
            add_entity_status_effect(target, "Banish", "放逐狀態：免疫所有技能與攻擊且無法行動", 2)
            logs.append(f"🌀 施加【放逐】給 {cls._get_name(target)}，持續 2 回合。")
        if "Stun" in keywords:
            add_entity_status_effect(target, "Stun", "暈眩：無法行動", 1)
            control_flags["stun_active"] = True
            logs.append(f"🌀 施加【暈眩】給 {cls._get_name(target)}，下回合跳過。")
        if "Silence" in keywords:
            add_entity_status_effect(target, "Silence", "沉默：無法施展傷害技能", 2)
            logs.append(f"🤐 施加【沉默】給 {cls._get_name(target)}，持續 2 回合。")
        if "Root" in keywords:
            add_entity_status_effect(target, "Root", "定身：無法使用物理近戰技能", 2)
            logs.append(f"🕸️ 施加【定身】給 {cls._get_name(target)}，持續 2 回合。")
        if "Slow" in keywords:
            add_entity_status_effect(target, "Slow", "減速", 3, {"DEX": -99}) # 閃避率直接歸零
            control_flags["slow_active"] = True
            logs.append(f"❄️ 施加【減速】給 {cls._get_name(target)}：閃避歸零且出手順序墊底。")
        if "Burn" in keywords:
            add_entity_status_effect(target, "Burn", "灼燒 DoT", 3,
                                     dot_damage_flat=15.0, dot_damage_type="true_damage")
            logs.append(f"🔥 施加【灼燒】給 {cls._get_name(target)}，每回合造成 15 點真實傷害。")
        if "Frostbite" in keywords:
            add_entity_status_effect(target, "Frostbite", "凍傷", 3,
                                     dot_damage_flat=8.0, dot_damage_type="true_damage")
            logs.append(f"🥶 施加【凍傷】給 {cls._get_name(target)}，每回合造成 8 點真實傷害，持續 3 回合。")
        if "Blind" in keywords:
            add_entity_status_effect(target, "Blind", "盲目", 2)
            logs.append(f"🕶️ 施加【盲目】給 {cls._get_name(target)}，持續 2 回合。")
        if "Doom" in keywords:
            add_entity_status_effect(target, "Doom", "厄運宣告：倒數即死", 3)
            logs.append(f"☠️ 施加【厄運宣告】給 {cls._get_name(target)}！3 回合後結算。")
        if "Charm" in keywords:
            add_entity_status_effect(target, "Charm", "魅惑", 2)
            control_flags["charm_active"] = True
            logs.append(f"💖 施加【魅惑】給 {cls._get_name(target)}：反轉目標類型隨機攻擊隊友。")
        if "Confusion" in keywords:
            add_entity_status_effect(target, "Confusion", "混亂", 2)
            control_flags["confusion_active"] = True
            logs.append(f"💫 施加【混亂】給 {cls._get_name(target)}，每次行動 50% 機率取消。")
            
        # Shield (護盾)：為角色建立 temp_hp
        if "Shield" in keywords:
            shield_val = int(final_value if action_type in ["heal", "buff"] else 20)
            curr_temp = get_entity_attr(target, "temp_hp", 0)
            set_entity_attr(target, "temp_hp", curr_temp + shield_val)
            add_entity_status_effect(target, "Shield", "護盾防護", 3)
            logs.append(f"🛡️ 獲得【護盾】：為 {cls._get_name(target)} 增加 {shield_val} 點臨時生命 (temp_hp)。")
            
        if "Immune" in keywords:
            add_entity_status_effect(target, "Immune", "免疫所有負面狀態", 2)
            logs.append(f"✨ 獲得【免疫】：施加霸體狀態，持續 2 回合。")
        if "Invis" in keywords:
            add_entity_status_effect(target, "Invis", "隱身中", 3)
            control_flags["invis_active"] = True
            logs.append(f"👤 進入【隱身】狀態：暫時從敵方可選目標列表中移除。")
        if "Levitate" in keywords:
            add_entity_status_effect(target, "Levitate", "浮空狀態", 3)
            logs.append(f"🍃 進入【浮空】狀態，持續 3 回合。")
        if "Counter_Stance" in keywords:
            add_entity_status_effect(target, "Counter_Stance", "反擊架勢", 2)
            logs.append(f"⚔️ 進入【反擊架勢】，受到物理攻擊將會進行反擊。")
        if "Bless" in keywords:
            add_entity_status_effect(target, "Bless", "祝福", 3)
            logs.append(f"🌟 獲得【祝福】：接下來 3 回合若擲骰 <= 5，補底提升至 10。")
        if "Reflect" in keywords:
            add_entity_status_effect(target, "Reflect", "傷害反射盾", 2)
            logs.append(f"🪞 獲得【反射】狀態：記錄下一次傷害減免 50% 並反彈，持續 2 回合。")
        if "Taunt" in keywords:
            add_entity_status_effect(target, "Taunt", "被施法者嘲諷，單體攻擊強制指向施法者", 2)
            logs.append(f"😠 施加【嘲諷】給 {cls._get_name(target)}，強制其單體攻擊指向施法者。")
        if "Purge" in keywords:
            debuffs = {"Stun", "Silence", "Root", "Slow", "Burn", "Frostbite", "Blind", "Doom", "Charm", "Confusion", "Sunder", "Taunt"}
            if hasattr(target, "data") and hasattr(target.data, "status_effects"):
                target.data.status_effects = [e for e in target.data.status_effects if e.name not in debuffs]
            elif isinstance(target, dict) and "status_effects" in target:
                target["status_effects"] = [
                    e for e in target["status_effects"]
                    if (e.name not in debuffs if hasattr(e, "name") else e.get("name") not in debuffs)
                ]
            logs.append(f"✨ 觸發【淨化】：清除了 {cls._get_name(target)} 身上的所有負面狀態！")
        if "Time_Warp" in keywords:
            prev_hp = getattr(caster, "_hp_snapshot", None)
            prev_mp = getattr(caster, "_mp_snapshot", None)
            if prev_hp is not None and prev_mp is not None:
                set_entity_attr(caster, "hp", prev_hp)
                set_entity_attr(caster, "mp", prev_mp)
                logs.append(f"⏳ 觸發【時光回溯】：回溯施法者的生命值至 {prev_hp} HP，魔法值至 {prev_mp} MP！")
            else:
                max_hp = get_entity_attr(caster, "max_hp", 100)
                max_mp = get_entity_attr(caster, "max_mp", 50)
                set_entity_attr(caster, "hp", max_hp)
                set_entity_attr(caster, "mp", max_mp)
                logs.append("⏳ 觸發【時光回溯】：未偵測到上一回合快照，已重置生命與魔法至上限！")
            try:
                caster._hp_snapshot = get_entity_attr(caster, "hp", 100)
                caster._mp_snapshot = get_entity_attr(caster, "mp", 50)
            except AttributeError:
                pass
        if "Steal" in keywords:
            gold_steal = random.randint(10, 30)
            if hasattr(caster, "data") and hasattr(caster.data, "gold"):
                caster.data.gold += gold_steal
            elif isinstance(caster, dict):
                caster["gold"] = caster.get("gold", 0) + gold_steal
            control_flags["steal_active"] = True
            logs.append(f"💰 觸發【竊取】：成功從目標身上竊取了 {gold_steal} 金幣！")

        # ---------------------------------------------------------
        # Phase 7: Post-cast resolution (後置與連段判定)
        # ---------------------------------------------------------
        if "Chain" in keywords:
            control_flags["chain_active"] = True
            logs.append("⚡ 【連鎖】標記已啟動：尋找下一個存活敵人，無消耗再呼叫同技能（傷害衰減 50%）。")
        if "Summon" in keywords:
            control_flags["summon_active"] = True
            logs.append("🌀 【召喚】印記已亮起：在戰鬥序列中實例化 Entity，由 AI 接管其行為。")
        if "Resurrect" in keywords:
            control_flags["resurrect_active"] = True
            logs.append("🕊️ 【復甦】奧義已啟動，將復活倒下的盟友。")
        if "Rampage" in keywords:
            target_hp = get_entity_attr(target, "hp", 100)
            if target_hp <= 0:
                control_flags["rampage_active"] = True
                logs.append("🩸 擊殺觸發【殺戮盛宴】！獲得額外行動機會。")
        if "Greed" in keywords:
            control_flags["greed_active"] = True
            logs.append("💰 【貪婪】標記已附著：若目標死於此技能，金幣掉落乘以 2~3 倍。")
        if "Adapt" in keywords:
            add_entity_status_effect(caster, "Adapt", "適應性抗性", 3)
            logs.append("🧬 觸發【適應】：獲得對目標屬性的防禦抗性。")
        if "Echo" in keywords:
            control_flags["echo_active"] = True
            logs.append("🔊 觸發【殘響】：下回合將以 50% 的威力自動重複施放此技能。")
        if "Berserk" in keywords:
            add_entity_status_effect(caster, "Berserk", "狂暴中：強制隨機攻擊", 3, {"skill_power": 0.5})
            control_flags["berserk_active"] = True
            logs.append("🩸 觸發【狂暴】：獲得極端強大傷害加成，接下來 3 回合內無法手動下令，系統強迫每回合進行隨機普攻！")
            
        if hasattr(caster, "save"): caster.save()
        if hasattr(target, "save"): target.save()
        
        return {
            "success": True,
            "final_value": final_value,
            "dice_roll": dice_roll,
            "dice_type": skill.mechanics.formula.dice,
            "logs": logs,
            "control_flags": control_flags
        }

    @staticmethod
    def _has_status(entity, status_name: str) -> bool:
        if hasattr(entity, "data") and hasattr(entity.data, "status_effects"):
            return any(e.name == status_name for e in entity.data.status_effects)
        if isinstance(entity, dict) and "status_effects" in entity:
            effects = entity["status_effects"]
            return any(
                (e.name == status_name if hasattr(e, "name") else e.get("name") == status_name)
                for e in effects
            )
        return False

    @staticmethod
    def _remove_status(entity, status_name: str):
        if hasattr(entity, "data") and hasattr(entity.data, "status_effects"):
            entity.data.status_effects = [e for e in entity.data.status_effects if e.name != status_name]
        elif isinstance(entity, dict) and "status_effects" in entity:
            entity["status_effects"] = [
                e for e in entity["status_effects"]
                if (e.name != status_name if hasattr(e, "name") else e.get("name") != status_name)
            ]

    @staticmethod
    def _get_name(entity) -> str:
        if hasattr(entity, "data"):
            return entity.data.name
        if isinstance(entity, dict):
            return entity.get("name", "未知單位")
        return "未知單位"

class SkillProcessor:
    @staticmethod
    def roll_dice(dice_str: str) -> int:
        """解析 NdM±X 格式並回傳隨機結果 (例如: 1d20, 2d6+3, 1d10-1)"""
        match = re.match(r"(\d+)d(\d+)(?:([+-])(\d+))?", dice_str.lower().strip())
        if not match:
            return 0
        
        num_str, sides_str, sign, modifier_str = match.groups()
        num = int(num_str)
        sides = int(sides_str)
        
        total = sum(random.randint(1, sides) for _ in range(num))
        
        if sign and modifier_str:
            modifier = int(modifier_str)
            if sign == '+':
                total += modifier
            elif sign == '-':
                total -= modifier
                
        return max(0, total)

    @classmethod
    def validate_and_clamp_skill(cls, skill: Skill) -> Skill:
        """
        技能平衡器：根據階級 (Tier) 與目標類型 (AoE) 強制校正分母 (Divisor)。
        """
        tier_min_divisors = {
            "T1": 4.0,  # 傳說：最高 5.0x
            "T2": 6.0,  # 史詩：最高 3.3x
            "T3": 8.0,  # 稀有：最高 2.5x
            "T4": 10.0, # 精良：最高 2.0x
            "T5": 12.0  # 普通：最高 1.6x
        }
        
        base_min = tier_min_divisors.get(skill.tier, 12.0)
        
        if skill.mechanics.target_type == "aoe":
            base_min *= 1.5
            
        formula = skill.mechanics.formula
        if formula.type == "multiplier":
            original = formula.divisor
            formula.divisor = max(base_min, formula.divisor)
            if formula.divisor > original:
                print(f"⚖️ 技能 {skill.name} ({skill.tier}) 分母已從 {original} 校正為 {formula.divisor} (AoE: {skill.mechanics.target_type == 'aoe'})")
        
        # 額外防防呆：只有 T1 (傳說) 技能允許擁有 triggers，非 T1 清空
        if skill.tier != "T1":
            skill.executable_triggers = []

        return skill

    @classmethod
    def calculate_base_value(cls, skill: Skill, total_stats: Dict[str, int]) -> Tuple[float, int]:
        """
        計算技能的基礎數值（傷害或治療）。
        回傳: (最終數值, 骰子點數)
        """
        formula = skill.mechanics.formula
        dice_roll = cls.roll_dice(formula.dice)
        stat_val = total_stats.get(formula.base_stat, 5)

        if formula.type == "multiplier":
            multiplier = dice_roll / formula.divisor
            final_val = stat_val * multiplier
        else:
            final_val = dice_roll + stat_val
            
        return final_val, dice_roll

    @classmethod
    def execute_skill(cls, skill: Skill, character: Any, target: Optional[Any] = None, combat_context: Optional[Any] = None) -> Dict[str, Any]:
        """
        執行技能的預運算邏輯，使用生命週期管道。
        """
        import copy
        skill = copy.deepcopy(skill)
        res = SkillExecutionPipeline.execute(skill, character, target, combat_context)
        
        if not res.get("success"):
            return {
                "success": False,
                "skill_name": skill.name,
                "final_value": 0,
                "dice_roll": 0,
                "dice_type": skill.mechanics.formula.dice,
                "keywords": skill.mechanics.keywords,
                "narrative_effect": skill.mechanics.narrative_effect,
                "logs": res.get("logs", []),
                "control_flags": res.get("control_flags", {})
            }
            
        return {
            "success": True,
            "skill_name": skill.name,
            "final_value": res["final_value"],
            "dice_roll": res["dice_roll"],
            "dice_type": res["dice_type"],
            "keywords": skill.mechanics.keywords,
            "narrative_effect": skill.mechanics.narrative_effect,
            "logs": res.get("logs", []),
            "control_flags": res.get("control_flags", {})
        }

