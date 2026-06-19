# core/skill_processor.py
import random
import re
from typing import Dict, Any, Tuple, Optional
from core.models import Skill, CharacterSchema
from core.constants import STAT_TRANSLATIONS, normalize_status_name, STATUS_REGISTRY
from core.combat_utils import is_mock, get_entity_id, get_entity_attr, set_entity_attr, get_entity_stat, get_entity_combat_stat, add_entity_status_effect, has_status, remove_status, get_entity_name, get_status_effect, change_entity_hp


class SkillExecutionPipeline:
    @classmethod
    def execute(cls, skill: Skill, caster: Any, target: Optional[Any] = None, combat_context: Optional[Any] = None) -> Dict[str, Any]:
        logs = []
        control_flags = {}
        
        # 判定施法者自身是否處於放逐 (Banish)
        if has_status(caster, "Banish"):
            raise ValueError("自身處於放逐狀態，無法使用技能")
            
        # 檢查技能職業限制
        allowed_jobs = getattr(skill, "allowed_jobs", []) or []
        if allowed_jobs:
            caster_jobs = None
            if hasattr(caster, "data") and hasattr(caster.data, "base_jobs"):
                caster_jobs = caster.data.base_jobs
            elif isinstance(caster, dict) and "base_jobs" in caster:
                caster_jobs = caster["base_jobs"]
            
            if caster_jobs is not None:
                if not any(job in caster_jobs for job in allowed_jobs):
                    raise ValueError(f"技能限制：此技能限定職業 【{', '.join(allowed_jobs)}】，你目前無法施展。")

        initial_caster_hp = get_entity_attr(caster, "hp", 100)
        initial_target_hp = get_entity_attr(target, "hp", 100) if target else 100
        
        # 取得 actions 陣列，如果為空且有 legacy 欄位，自動透過模板組裝（相容舊測試）
        actions = list(skill.mechanics.actions)
        if not actions:
            legacy_kw = getattr(skill.mechanics, "keywords", []) or []
            legacy_legendary = getattr(skill.mechanics, "legendary_keyword", None)
            if legacy_kw or legacy_legendary:
                from core.skill_templates import assemble_skill_actions
                choices = []
                for kw in legacy_kw:
                    clean_kw = kw.replace("'", "").replace("-", "_").replace(" ", "_").lower()
                    choices.append({"template_id": f"active_{clean_kw}"})
                if legacy_legendary:
                    clean_lk = legacy_legendary.replace("'", "").replace("-", "_").replace(" ", "_").lower()
                    choices.append({"template_id": f"active_{clean_lk}"})
                actions = assemble_skill_actions(choices)

        # 輔助判定函數
        def _has_special(name: str) -> bool:
            norm_name = normalize_status_name(name)
            return any(a.get("action_type") == "call_special_mechanic" and normalize_status_name(a.get("keyword_name")) == norm_name for a in actions) or \
                   any(a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == norm_name for a in actions)

        action_type = skill.mechanics.action_type
        target_type = skill.mechanics.target_type
        
        # 記錄上一個施放的技能到 caster 上，供 Copy 讀取。
        if not _has_special("Copy"):
            try:
                caster._last_skill_cast = skill
            except AttributeError:
                pass

        # Keyword: Copy (鏡像)：將自己這個技能的公式與特效暫時替換成戰鬥日誌中最後一個發動的技能。
        if _has_special("Copy"):
            last_skill = getattr(caster, "_last_skill_cast", None)
            if last_skill and last_skill.name != skill.name:
                skill.mechanics.formula = last_skill.mechanics.formula
                skill.mechanics.action_type = last_skill.mechanics.action_type
                skill.mechanics.target_type = last_skill.mechanics.target_type
                # 將鏡像技能的 actions 併入
                actions = [a for a in actions if not (a.get("action_type") == "call_special_mechanic" and a.get("keyword_name") == "Copy")]
                actions.extend(last_skill.mechanics.actions)
                skill.mechanics.actions = actions
                logs.append(f"🎭 觸發【鏡像】：成功複製了上一個技能【{last_skill.name}】的機制！")
        
        # 如果是 self，目標即為施法者
        if target_type == "self" or target is None:
            target = caster
            
        # Check row protection for melee skills
        is_melee_skill = "Melee" in getattr(skill.mechanics, "tags", [])
        if is_melee_skill and target is not caster:
            target_row = getattr(target.data, "row", "front") if (hasattr(target, "data") and not isinstance(target, dict)) else target.get("row", "front")
            if target_row == "back":
                has_front_row = False
                if combat_context:
                    is_target_player = (hasattr(target, "data") and not isinstance(target, dict))
                    if is_target_player:
                        char_ref = combat_context.character
                        if char_ref.data.vitality.hp > 0 and getattr(char_ref.data, "row", "front") == "front":
                            has_front_row = True
                        else:
                            for m in combat_context.monsters:
                                if m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front":
                                    has_front_row = True
                                    break
                    else:
                        for m in combat_context.monsters:
                            if not m.get("is_summon") and m.get("hp", 0) > 0 and m.get("row", "front") == "front":
                                has_front_row = True
                                break
                if has_front_row:
                    raise ValueError("無法對後排施展近戰技能：敵方前排仍有存活單位擋路！")
            
        # ---------------------------------------------------------
        # Phase 1: Pre-cast (消耗與前置判定)
        # ---------------------------------------------------------
        def _resolve_cost_val(val: Any, current_val: int, max_val: int) -> int:
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str):
                val_str = val.strip().lower()
                if val_str == "all":
                    return current_val
                if val_str.endswith("%"):
                    try:
                        ratio = float(val_str[:-1]) / 100.0
                        base = max_val if max_val > 0 else current_val
                        return int(base * ratio)
                    except ValueError:
                        pass
            return 0

        costs = skill.mechanics.cost
        
        current_mp = get_entity_attr(caster, "mp", 0)
        max_mp = get_entity_attr(caster, "max_mp", 50)
        current_san = get_entity_attr(caster, "sanity", 100)
        max_san = get_entity_attr(caster, "max_sanity", 100)
        current_stamina = get_entity_attr(caster, "stamina", 100)
        max_stamina = get_entity_attr(caster, "max_stamina", 100)
        current_hp = get_entity_attr(caster, "hp", 100)
        max_hp = get_entity_attr(caster, "max_hp", 100)
        
        resolved_costs = {}
        control_flags["dynamic_cost"] = {}
        
        for res_type, val in costs.items():
            if res_type == "MP":
                base_c = _resolve_cost_val(val, current_mp, max_mp)
            elif res_type == "SAN":
                base_c = _resolve_cost_val(val, current_san, max_san)
            elif res_type == "STAMINA":
                base_c = _resolve_cost_val(val, current_stamina, max_stamina)
            elif res_type == "HP":
                base_c = _resolve_cost_val(val, current_hp, max_hp)
            else:
                base_c = int(val) if isinstance(val, (int, float)) else 0
            resolved_costs[res_type] = base_c
            if isinstance(val, str):
                control_flags["dynamic_cost"][res_type] = base_c

        mp_cost = resolved_costs.get("MP", 0)
        san_cost = resolved_costs.get("SAN", 0)
        stamina_cost = resolved_costs.get("STAMINA", 0)
        hp_cost = resolved_costs.get("HP", 0)
        
        # 檢查超載
        has_overload_debuff = has_status(caster, "Overload_Lock")
        if has_overload_debuff:
            mp_cost *= 2
            logs.append("⚡ 【超載鎖定】作用中，法力消耗翻倍！")
            
        # 靈魂枯竭 (Soul_Exhaustion) 翻倍
        if has_status(caster, "Soul_Exhaustion"):
            mp_cost *= 2
            san_cost *= 2
            stamina_cost *= 2
            hp_cost *= 2
            logs.append("💀 【靈魂枯竭】作用中，所有技能消耗翻倍！")
            
        # 沉默 (Silence) 阻斷：阻斷耗 MP 的傷害型技能
        if has_status(caster, "Silence"):
            if action_type == "damage" and mp_cost > 0:
                raise ValueError("被沉默無法施法")
                
        # 定身 (Root) 阻斷：阻斷物理近戰傷害型技能 (DEX/STR)
        if has_status(caster, "Root"):
            if action_type == "damage" and skill.mechanics.formula.base_stat in ["STR", "DEX"]:
                raise ValueError("被定身無法使用物理近戰技能")
            
        if current_mp < mp_cost:
            raise ValueError(f"法力值不足，需要 {mp_cost} MP，當前 {current_mp}")
        if current_san < san_cost:
            raise ValueError(f"理智值不足，需要 {san_cost} SAN，當前 {current_san}")
        if current_stamina < stamina_cost:
            raise ValueError(f"精力值不足，需要 {stamina_cost} 精力，當前 {current_stamina}")
        if hp_cost > 0 and current_hp <= 1:
            raise ValueError(f"生命值不足以支付消耗，需要 {hp_cost} HP，當前 {current_hp}")
            
        # Keyword: Sacrifice (犧牲)
        if _has_special("Sacrifice"):
            sacrifice_hp = int(current_hp * 0.20)
            set_entity_attr(caster, "hp", max(1, current_hp - sacrifice_hp))
            missing_hp = max_hp - get_entity_attr(caster, "hp", 100)
            control_flags["sacrifice_bonus"] = missing_hp * 0.40
            logs.append(f"🩸 觸發【犧牲】：扣除 20% HP ({sacrifice_hp})，缺失 HP 轉為 {control_flags['sacrifice_bonus']:.1f} 額外威力。")
            current_hp = get_entity_attr(caster, "hp", 100)
            
        # 扣除基本消耗
        set_entity_attr(caster, "mp", max(0, current_mp - mp_cost))
        set_entity_attr(caster, "sanity", max(0, current_san - san_cost))
        if stamina_cost > 0:
            curr_stam = get_entity_attr(caster, "stamina", 100)
            set_entity_attr(caster, "stamina", max(0, curr_stam - stamina_cost))
        if hp_cost > 0:
            curr_hp = get_entity_attr(caster, "hp", 100)
            set_entity_attr(caster, "hp", max(1, curr_hp - hp_cost))
            
        # Legendary Keyword: Blood_Pact (血誓契約)
        if _has_special("Blood_Pact"):
            curr_hp = get_entity_attr(caster, "hp", 100)
            max_hp = get_entity_attr(caster, "max_hp", 100)
            pact_cost = int(curr_hp * 0.20)
            set_entity_attr(caster, "hp", max(1, curr_hp - pact_cost))
            missing_ratio = 1.0 - (get_entity_attr(caster, "hp", 1) / max_hp)
            control_flags["blood_pact_mult"] = 1.0 + missing_ratio * 1.5  # 最高 +150%
            logs.append(f"🩸 觸發【血誓契約】：消耗 20% HP，傷害乘以 {control_flags['blood_pact_mult']:.2f}x！")
            
        # Keyword: Martyr (殉道)
        if _has_special("Martyr"):
            set_entity_attr(caster, "hp", 0)
            control_flags["martyr_active"] = True
            logs.append("☠️ 觸發【殉道】：施法者將自身生命值歸零，引導終極救贖！")
            
        # Keyword: Overload (超載)
        if _has_special("Overload"):
            control_flags["overload_active"] = True
            
        # Keyword: Quickcast (瞬發)
        if _has_special("Quickcast"):
            control_flags["quickcast"] = True
            logs.append("⚡ 觸發【瞬發】：不扣除玩家行動點數，允許連續發動下一個技能。")
            
        # Keyword: Siphon (屬性汲取)
        siphon_act = next((a for a in actions if a.get("action_type") == "call_special_mechanic" and a.get("keyword_name") == "Siphon"), None)
        if siphon_act:
            s_stat = siphon_act.get("stat", "STR").upper()
            steal_percent = float(siphon_act.get("steal_percent", 0.20))
            duration = int(siphon_act.get("duration", 3))
            
            target_stat_val = get_entity_stat(target, s_stat)
            steal_amount = int(target_stat_val * steal_percent)
            
            add_entity_status_effect(
                target,
                "Siphon_Debuff",
                f"屬性汲取：降低 {s_stat} {steal_amount} 點",
                duration,
                bonuses={s_stat: -steal_amount}
            )
            add_entity_status_effect(
                caster,
                "Siphon_Buff",
                f"屬性汲取：增加 {s_stat} {steal_amount} 點",
                duration,
                bonuses={s_stat: steal_amount}
            )
            logs.append(f"🧬 觸發【屬性汲取】：降低目標 {get_entity_name(target)} 的 {s_stat} {steal_amount} 點，並轉移給施法者 {get_entity_name(caster)}，持續 {duration} 回合。")
            
        # Keyword: Detonate (條件引爆)
        detonate_act = next((a for a in actions if a.get("action_type") == "call_special_mechanic" and a.get("keyword_name") == "Detonate"), None)
        if detonate_act and target:
            status_to_detonate = detonate_act.get("status_name", "Burn")
            flat_dmg = float(detonate_act.get("flat_value", 30.0))
            if has_status(target, status_to_detonate):
                remove_status(target, status_to_detonate)
                control_flags["detonate_bonus"] = flat_dmg
                logs.append(f"💥 觸發【引爆】：引爆並消耗了目標身上的【{status_to_detonate}】狀態，造成 {flat_dmg} 點額外真實傷害！")

        # --- 處理共鳴需求 (synergy_requirement) ---
        synergy_req = getattr(skill.mechanics, "synergy_requirement", None)
        if synergy_req and target:
            if "requires_" in synergy_req.lower():
                raw_status = synergy_req.lower().split("requires_")[1]
                status_needed = normalize_status_name(raw_status)
                if not has_status(target, status_needed):
                    raise ValueError(f"需要目標擁有【{status_needed}】狀態才能發動。")
            elif "consumes_" in synergy_req.lower():
                raw_status = synergy_req.lower().split("consumes_")[1]
                status_to_consume = normalize_status_name(raw_status)
                if status_to_consume == "Shields" or status_to_consume == "Shield":
                    shield = get_entity_attr(target, "temp_hp", 0)
                    if shield > 0:
                        set_entity_attr(target, "temp_hp", 0)
                        control_flags["consumed_shield"] = shield
                        logs.append(f"🛡️ 觸發共鳴：吞噬了目標 {shield} 點護盾！")
                    else:
                        logs.append("⚠️ 共鳴提示：目標沒有護盾可吞噬。")
                elif has_status(target, status_to_consume):
                    remove_status(target, status_to_consume)
                    control_flags["consumed_status"] = status_to_consume
                    logs.append(f"🔥 觸發共鳴：吞噬了目標的【{status_to_consume}】狀態！")

        # --- 處理範圍變化 (targeting_modifier) ---
        targeting_mod = getattr(skill.mechanics, "targeting_modifier", None)
        if targeting_mod:
            control_flags["targeting_modifier"] = targeting_mod
            if "chain" in targeting_mod.lower():
                control_flags["chain_active"] = True
                logs.append("⚡ 準備觸發連鎖攻擊！")

        # ---------------------------------------------------------
        # Phase 2: Target & Hit Check (目標與命中檢定)
        # ---------------------------------------------------------
        if has_status(target, "Banish"):
            logs.append(f"🌀 目標 {get_entity_name(target)} 處於放逐狀態，技能無法命中！")
            return {"success": False, "msg": "技能因目標處於放逐狀態而失效。", "logs": logs}
            
        # Legendary Keyword: Epoch_Break (時代終結)
        if _has_special("Epoch_Break"):
            buffs_to_strip = ["Bless", "Shield", "Immune", "Reflect", "Invis"]
            for b in buffs_to_strip:
                remove_status(target, b)
            set_entity_attr(target, "temp_hp", 0)
            control_flags["epoch_break_active"] = True
            logs.append("⚡ 觸發【時代終結】：目標所有增益狀態被抹殺，護盾歸零！")
            
        from core.contexts import ActionContext, DiceContext
        from core.trigger_engine import TriggerEngine

        # Setup ActionContext
        base_accuracy = get_entity_combat_stat(caster, "accuracy", 0.95)
        if has_status(caster, "Blind"):
            base_accuracy *= 0.5
            logs.append("👁️ 【盲目】降低了施法者的命中率！")
            
        base_evasion = 0.0
            
        if target and target_type == "single" and has_status(target, "Invis"):
            base_accuracy *= 0.3
            logs.append(f"👤 目標 {get_entity_name(target)} 處於隱身狀態，極難被選中！")

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

        # Focus (專注) 判定
        if has_status(caster, "Focus"):
            act_ctx.is_crit = True
            remove_status(caster, "Focus")
            logs.append(f"✨ 觸發【專注】：施法者 {get_entity_name(caster)} 的下一擊必定爆擊！")

        is_hit = False
        if act_ctx.is_absolute_hit:
            is_hit = True
            logs.append("✨ 觸發【絕對命中】：技能無視迴避率！")
        else:
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

        dice_ctx = DiceContext(dice_str=formula.dice, caster=caster, combat_context=combat_context)
        TriggerEngine.dispatch_interceptor("on_dice", dice_ctx, caster)

        if dice_ctx.roll_value is not None:
            dice_roll = dice_ctx.roll_value
        else:
            dice_roll = SkillProcessor.roll_dice(dice_ctx.dice_str)

        dice_roll += dice_ctx.roll_modifier
        if dice_ctx.floor_value is not None:
            dice_roll = max(dice_roll, dice_ctx.floor_value)

        # 祝福 (Bless) 骰子補底
        if has_status(caster, "Bless") and dice_roll <= 5:
            dice_roll = 10
            logs.append("🌟 觸發【祝福】補底：擲骰點數小於 5，自動補底提升至 10！")
            if formula.type == "multiplier":
                multiplier = dice_roll / formula.divisor
                if "dynamic_cost" in control_flags and "MP" in control_flags["dynamic_cost"]:
                    if skill.mechanics.cost.get("MP") == "all":
                        consumed = control_flags["dynamic_cost"]["MP"]
                        coeff = 1.0 + consumed * 0.02
                        multiplier *= coeff
                        logs.append(f"🔮 消耗了所有 MP ({consumed})，技能倍率乘以 {coeff:.2f}x！")
                base_val = stat_val * multiplier
            else:
                base_val = dice_roll + stat_val
        else:
            if formula.type == "multiplier":
                multiplier = dice_roll / formula.divisor
                if "dynamic_cost" in control_flags and "MP" in control_flags["dynamic_cost"]:
                    if skill.mechanics.cost.get("MP") == "all":
                        consumed = control_flags["dynamic_cost"]["MP"]
                        coeff = 1.0 + consumed * 0.02
                        multiplier *= coeff
                        logs.append(f"🔮 消耗了所有 MP ({consumed})，技能倍率乘以 {coeff:.2f}x！")
                base_val = stat_val * multiplier
            else:
                base_val = dice_roll + stat_val
                
        skill_power = get_entity_combat_stat(caster, "skill_power", 1.0)
        if combat_context and getattr(combat_context, "_echo_cast_active", False):
            skill_power *= 0.5
        base_val *= skill_power
        
        # Keyword: Stat_Swap (屬性反轉)
        if _has_special("Stat_Swap"):
            base_val *= 1.3
            logs.append("🔄 觸發【屬性反轉】：顛倒因果，威力提升。")
            
        # Keyword: Mimicry (擬態)
        if _has_special("Mimicry"):
            base_val *= 1.2
            logs.append("🎭 觸發【擬態】：複製目標的戰鬥姿態，威力提升。")

        # Keyword: Gamble (豪賭)
        if _has_special("Gamble"):
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

        # Keyword: Desperation (絕境怒火) 增傷
        if has_status(caster, "Desperation"):
            effect = get_status_effect(caster, "Desperation")
            if effect:
                extra_d = effect.extra_data if hasattr(effect, "extra_data") else effect.get("extra_data", {})
                hp_threshold = extra_d.get("hp_threshold", 30.0)
                dmg_bonus = extra_d.get("dmg_bonus", 50.0)
                
                curr_hp = get_entity_attr(caster, "hp", 100)
                max_hp = get_entity_attr(caster, "max_hp", 100)
                if (curr_hp / max_hp) * 100.0 <= hp_threshold:
                    mult = 1.0 + (dmg_bonus / 100.0)
                    base_val *= mult
                    control_flags["desperation_triggered"] = True
                    logs.append(f"💥 觸發【絕境怒火】增傷：生命值低於 {hp_threshold}%，傷害乘以 {mult:.2f}x！")

        # Legendary Keyword: Devil's_Roll (惡魔骰)
        if _has_special("Devil's_Roll"):
            roll = random.randint(1, 6)
            if roll == 1:
                backlash = int(base_val * 0.50)
                curr_hp = get_entity_attr(caster, "hp", 100)
                set_entity_attr(caster, "hp", max(1, curr_hp - backlash))
                base_val = 0.0
                control_flags["devil_roll_failed"] = True
                logs.append(f"🎲 【惡魔骰】骰出 1！大失敗！反噬 {backlash} 真實傷害，技能落空！")
            elif roll <= 3:
                logs.append(f"🎲 【惡魔骰】骰出 {roll}。命運沉默，技能正常發動。")
            elif roll <= 5:
                base_val *= 1.5
                random_debuff = random.choice(["Stun", "Burn", "Doom"])
                control_flags["devil_roll_debuff"] = random_debuff
                logs.append(f"🎲 【惡魔骰】骰出 {roll}！強化！傷害 ×1.5，附加隨機詛咒：{random_debuff}！")
            else:  # roll == 6
                base_val *= 3.0
                control_flags["devil_roll_aoe"] = True
                logs.append(f"🎲 【惡魔骰】骰出 6！！傳說爆發！傷害 ×3，席捲全場！")

        # Legendary Keyword: Last_Rites (終焉禮讚)
        if _has_special("Last_Rites"):
            t_hp = get_entity_attr(target, "hp", 100)
            t_max_hp = get_entity_attr(target, "max_hp", 100)
            if (t_hp / t_max_hp) >= 0.50:
                base_val *= 2.0
                logs.append(f"⚰️ 觸發【終焉禮讚】：目標血量充盈，傷害倍增！")
            else:
                control_flags["last_rites_doom_spread"] = True
                logs.append(f"⚰️ 觸發【終焉禮讚】：目標血量已衰竭，厄運向所有敵人擴散！")

        # Legendary Keyword: Resonance_Break (共鳴破碎)
        if _has_special("Resonance_Break"):
            status_count = 0
            if hasattr(target, "data") and hasattr(target.data, "status_effects"):
                status_count = len(target.data.status_effects)
            elif isinstance(target, dict) and "status_effects" in target:
                status_count = len(target["status_effects"])
            if status_count > 0:
                resonance_mult = 1.0 + status_count * 0.15
                base_val *= resonance_mult
                logs.append(f"💥 觸發【共鳴破碎】：{status_count} 個狀態化為破碎共鳴，傷害 ×{resonance_mult:.2f}！")
            else:
                logs.append(f"💥 觸發【共鳴破碎】：目標無狀態，共鳴未引爆。")

        if "blood_pact_mult" in control_flags:
            base_val *= control_flags["blood_pact_mult"]

        # ---------------------------------------------------------
        # Phase 4: Defense & Penetration (減免與穿透)
        # ---------------------------------------------------------
        # Legendary Keyword: Annihilate (虛滅)
        if _has_special("Annihilate"):
            set_entity_attr(target, "temp_hp", 0)
            control_flags["annihilate_active"] = True
            logs.append("💀 觸發【虛滅】：護盾被抹除，防禦封頂限制解除！")

        # Legendary Keyword: Paradox (矛盾法則)
        if _has_special("Paradox"):
            paradox_bonus = get_entity_combat_stat(
                target, "p_def" if action_type == "damage" else "m_def", 0)
            control_flags["paradox_bonus"] = float(paradox_bonus)
            logs.append(f"🔄 觸發【矛盾法則】：目標防禦力 {paradox_bonus} 將反噬自身！")

        defense_stat = "p_def" if skill.mechanics.action_type == "damage" else "m_def"
        target_def = get_entity_combat_stat(target, defense_stat, 0)
        original_target_def = target_def
        
        # Pierce (穿透)：目標防禦力減半計算
        if _has_special("Pierce"):
            target_def = int(target_def * 0.5)
            logs.append("🎯 觸發【穿透】：目標防禦力減半計算。")
            
        # Apocalypse (天劫降臨) 真實傷害：防禦力直接歸零計算
        if _has_special("Apocalypse"):
            target_def = 0
            logs.append("⚡ 觸發【天劫降臨】：造成無視防禦的真實傷害！")
            
        act_ctx.raw_damage = base_val
        TriggerEngine.dispatch_interceptor("on_calculate_damage", act_ctx, caster, target)
        
        base_val *= act_ctx.damage_multiplier
        
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
            if base_val == 0.0:
                effective_def = 0.0
                final_value = 0.0
            else:
                if "annihilate_active" in control_flags:
                    effective_def = target_def
                    final_value = max(1.0, base_val - effective_def)
                elif _has_special("Apocalypse"):
                    effective_def = 0
                    final_value = base_val
                else:
                    from core.combat import use_marginal_returns
                    if use_marginal_returns():
                        target_lvl = get_entity_attr(target, "level", 1)
                        denom = 50.0 + target_lvl * 5.0
                        mitigation_ratio = min(0.80, target_def / (target_def + denom)) if (target_def + denom) > 0 else 0.0
                        effective_def = base_val * mitigation_ratio
                        final_value = max(1.0, base_val - effective_def)
                    else:
                        max_mitigation = base_val * 0.80
                        effective_def = min(target_def, max_mitigation)
                        final_value = max(1.0, base_val - effective_def)

        # Apply elemental resistance reduction for matching skill tags
        if action_type == "damage" and final_value > 0.0:
            skill_tags = getattr(skill.mechanics, "tags", []) or []
            target_res_dict = {}
            if hasattr(target, "data") and hasattr(target.data, "resistances"):
                target_res_dict = target.data.resistances or {}
            elif isinstance(target, dict):
                target_res_dict = target.get("resistances", {}) or {}
                
            for tag in skill_tags:
                res_val = None
                for k, v in target_res_dict.items():
                    if k.lower() == tag.lower():
                        res_val = float(v)
                        break
                if res_val is not None and res_val > 0:
                    target_lvl = get_entity_attr(target, "level", 1)
                    res_denom = 50.0 + target_lvl * 5.0
                    res_ratio = min(0.80, res_val / (res_val + res_denom))
                    final_value = final_value * (1.0 - res_ratio)
                    logs.append(f"🛡️ 觸發【{tag}】抗性減免：抗性值 {res_val:.1f}，減免了 {res_ratio*100:.1f}% 該屬性傷害！")
            
        # Execute (處決)
        if _has_special("Execute"):
            target_hp = get_entity_attr(target, "hp", 100)
            target_max_hp = get_entity_attr(target, "max_hp", 100)
            if target_hp / target_max_hp < 0.20:
                final_value *= 3.0
                logs.append("🎯 觸發【處決】：目標生命值低於 20%，傷害乘以 3 倍！")
                
        # Sunder (破甲)
        if _has_special("Sunder"):
            add_entity_status_effect(target, "Sunder", "物理防禦降低30%", 3, {"p_def": -0.30})
            logs.append(f"🛡️ 觸發【破甲】：目標物理防禦降低 30%。")
            
        # Keyword: Wall_Break (碎垣)
        if _has_special("Wall_Break"):
            if has_status(target, "Shield"):
                remove_status(target, "Shield")
            set_entity_attr(target, "temp_hp", 0)
            logs.append(f"🧱 觸發【碎垣】：無情擊碎了目標身上的護盾與 temp_hp！")

        if "paradox_bonus" in control_flags:
            final_value += control_flags["paradox_bonus"]

        if "detonate_bonus" in control_flags:
            final_value += control_flags["detonate_bonus"]

        # ---------------------------------------------------------
        # Phase 5: Apply HP/MP Changes (實體數值變更)
        # ---------------------------------------------------------
        final_value = round(final_value, 1)
        
        if "martyr_active" in control_flags:
            final_value *= 3.0
            
        # Reflect (反射)
        if action_type == "damage" and has_status(target, "Reflect"):
            reflected_dmg = round(final_value * 0.5, 1)
            final_value = round(final_value * 0.5, 1)
            curr_hp = get_entity_attr(caster, "hp", 100)
            set_entity_attr(caster, "hp", max(0, curr_hp - int(reflected_dmg)))
            logs.append(f"🪞 目標觸發【反射】：自身受傷減半，並對施法者反彈了 {reflected_dmg} 點傷害！")
            remove_status(target, "Reflect")

        if action_type == "damage":
            if "gamble_backlash" in control_flags:
                backlash = int(round(control_flags["gamble_backlash"], 1))
                curr_hp = get_entity_attr(caster, "hp", 100)
                set_entity_attr(caster, "hp", max(0, curr_hp - backlash))
                logs.append(f"🎲 【豪賭反噬】對施法者自身造成了 {backlash} 點傷害！")
                final_value = 0.0
            else:
                # Multi-hit (多重打擊)
                if _has_special("Multi-hit"):
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
                            logs.append(f"💥 [第 {idx+1} 擊] 對 {get_entity_name(target)} 造成了 {dmg_to_apply} 點傷害！")

                if total_applied_dmg > 0 or len(hits) == 1:
                    stat_name = STAT_TRANSLATIONS.get(formula.base_stat, formula.base_stat)
                    if formula.type == "multiplier":
                        calc_formula_str = f"{stat_name}:{stat_val} * ({dice_roll}/{formula.divisor})"
                    else:
                        calc_formula_str = f"{dice_roll} + {stat_name}:{stat_val}"
                        
                    if skill_power != 1.0:
                        calc_formula_str = f"({calc_formula_str}) * 威力:{skill_power:.1f}"
                        
                    extra_mults = []
                    if _has_special("Stat_Swap"): extra_mults.append("屬反:1.3x")
                    if _has_special("Mimicry"): extra_mults.append("擬態:1.2x")
                    if _has_special("Gamble") and 'gamble_roll' in locals() and gamble_roll == 1: 
                        extra_mults.append("豪賭:3.0x")
                    if "overload_active" in control_flags: extra_mults.append("超載:1.5x")
                    if "martyr_active" in control_flags: extra_mults.append("殉道:3.0x")
                    if "desperation_triggered" in control_flags: extra_mults.append("絕境增傷")
                    
                    if extra_mults:
                        calc_formula_str = f"({calc_formula_str}) * {' * '.join(extra_mults)}"
                        
                    if "sacrifice_bonus" in control_flags:
                        calc_formula_str = f"({calc_formula_str}) + 犧牲威力:{control_flags['sacrifice_bonus']:.1f}"
                        
                    if "detonate_bonus" in control_flags:
                        calc_formula_str = f"({calc_formula_str}) + 引爆傷害:{control_flags['detonate_bonus']:.1f}"
                        
                    defense_type_name = "物理防禦" if defense_stat == "p_def" else "魔法防禦"
                    pierce_suffix = " (穿透減半)" if _has_special("Pierce") else ""
                    def_str = f"{original_target_def}{pierce_suffix}"
                    
                    execute_mult = ""
                    if _has_special("Execute"):
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
                        logs.append(f"💥 總計對 {get_entity_name(target)} 造成了 {total_applied_dmg} 點真實傷害！" + calc_info)
                    else:
                        logs.append(f"💥 對 {get_entity_name(target)} 造成了 {total_applied_dmg} 點真實傷害！" + calc_info)
                        
                    from core.trigger_engine import TriggerEngine
                    TriggerEngine.dispatch_event("on_hit", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                    TriggerEngine.dispatch_event("on_damaged", target, caster, combat_context, damage=total_applied_dmg, context=act_ctx)
                    if act_ctx.is_crit:
                        TriggerEngine.dispatch_event("on_crit", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                    
                    target_hp = get_entity_attr(target, "hp", 0)
                    if target_hp <= 0:
                        TriggerEngine.dispatch_event("on_kill", caster, target, combat_context, damage=total_applied_dmg, context=act_ctx)
                
                # Desperation Lifesteal
                desp_lifesteal = 0.0
                if has_status(caster, "Desperation"):
                    effect = get_status_effect(caster, "Desperation")
                    if effect:
                        extra_d = effect.extra_data if hasattr(effect, "extra_data") else effect.get("extra_data", {})
                        hp_threshold = extra_d.get("hp_threshold", 30.0)
                        lifesteal_percent = extra_d.get("lifesteal_percent", 30.0)
                        curr_hp = get_entity_attr(caster, "hp", 100)
                        max_hp = get_entity_attr(caster, "max_hp", 100)
                        if (curr_hp / max_hp) * 100.0 <= hp_threshold:
                            desp_lifesteal = lifesteal_percent / 100.0

                # Lifesteal (吸血)
                if _has_special("Lifesteal") or desp_lifesteal > 0.0:
                    base_lifesteal = 0.30 if _has_special("Lifesteal") else 0.0
                    total_lifesteal_percent = base_lifesteal + desp_lifesteal
                    heal_amt = int(final_value * total_lifesteal_percent)
                    if has_status(caster, "Eternal_Wound"):
                        heal_amt = 0
                        logs.append(f"🩹 施法者 {get_entity_name(caster)} 處於【永恆創傷】狀態，吸血回復失敗！")
                    else:
                        if has_status(caster, "Bleed"):
                            heal_amt = int(heal_amt * 0.5)
                            logs.append(f"🩸 施法者 {get_entity_name(caster)} 處於【流血】狀態，吸血回復減半！")
                        actual_heal, hp_logs = change_entity_hp(caster, heal_amt, combat_context)
                        logs.extend(hp_logs)
                        logs.append(f"🩸 觸發【吸血】：回復了施法者 {heal_amt} 點生命值。")
                        
                        if heal_amt > 0:
                            from core.trigger_engine import TriggerEngine
                            TriggerEngine.dispatch_event("on_health_up", caster, None, combat_context)
                    
                if _has_special("Vampiric_Aura"):
                    add_entity_status_effect(caster, "Vampiric_Aura", "吸血光環中", 3)
                    logs.append("🌟 觸發【吸血光環】：周圍盟友被吸血光環所籠罩。")
                    
                if _has_special("Soul_Link"):
                    add_entity_status_effect(target, "Soul_Link", "與施法者靈魂連結", 3)
                    add_entity_status_effect(caster, "Soul_Link", "與目標靈魂連結", 3)
                    logs.append("🔗 觸發【靈魂連結】：施法者與目標的生命被絲線綁定！")

                # Legendary Keyword: Soul_Drain (靈魂汲取)
                if _has_special("Soul_Drain") and final_value > 0:
                    drain_mp = int(final_value * 0.20)
                    target_mp = get_entity_attr(target, "mp", 0)
                    actual_drain = min(drain_mp, target_mp)
                    set_entity_attr(target, "mp", max(0, target_mp - actual_drain))
                    
                    if not has_status(caster, "Eternal_Wound"):
                        curr_hp = get_entity_attr(caster, "hp", 100)
                        max_hp  = get_entity_attr(caster, "max_hp", 100)
                        set_entity_attr(caster, "hp", min(max_hp, curr_hp + actual_drain))
                        logs.append(f"🌑 觸發【靈魂汲取】：吸取 {actual_drain} 目標 MP 轉化為自身 HP！")
                    else:
                        logs.append(f"🌑 觸發【靈魂汲取】：吸取 {actual_drain} 目標 MP，但自身回復被【永恆創傷】封印！")
                        
                    if get_entity_attr(target, "mp", 0) <= 0:
                        add_entity_status_effect(
                            target, "Soul_Exhaustion",
                            "靈魂枯竭：所有技能費用翻倍",
                            1
                        )
                        logs.append(f"💀 【靈魂汲取】靈魂枯竭！{get_entity_name(target)} 的技能費用 ×2，持續 1 回合！")
                        
        elif action_type == "heal":
            heal_val = 0.0
            if has_status(target, "Eternal_Wound"):
                final_value = 0.0
                logs.append(f"🩹 {get_entity_name(target)} 的回復能力被【永恆創傷】封印，治療失敗！")
            else:
                heal_val = final_value
                if has_status(target, "Bleed"):
                    heal_val = round(heal_val * 0.5, 1)
                    logs.append(f"🩸 {get_entity_name(target)} 處於【流血】狀態，受到治療量減半！")
                actual_heal, hp_logs = change_entity_hp(target, int(heal_val), combat_context)
                logs.extend(hp_logs)
                    
                if heal_val > 0:
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
            logs.append(f"💚 為 {get_entity_name(target)} 恢復了 {heal_val} 點生命值！" + calc_info)

        # ---------------------------------------------------------
        # Phase 6: Status Application (狀態附加)
        # ---------------------------------------------------------
        # 1. 處理傳送進來的標準 status actions (非寫死特殊機制)
        processed_statuses = {normalize_status_name(s) for s in {"Banish", "Stun", "Silence", "Root", "Slow", "Burn", "Frostbite", "Blind", "Doom", "Charm", "Confusion", "Shield", "Immune", "Invis", "Levitate", "Counter_Stance", "Bless", "Reflect", "Taunt", "Sunder", "Bleed", "Ward", "Desperation", "Phoenix_Rebirth", "Mind_Control"}}
        for act in actions:
            act_type = act.get("action_type")
            tgt = target if act.get("target") == "target" else caster
            if act_type == "apply_status":
                status_name = act.get("status_name")
                if normalize_status_name(status_name) not in processed_statuses:
                    # 如果是姿態切換，清除其他姿態
                    if status_name.startswith("Stance_"):
                        existing_stances = []
                        if hasattr(tgt, "data") and hasattr(tgt.data, "status_effects") and tgt.data.status_effects is not None:
                            existing_stances = [e.name for e in tgt.data.status_effects if e.name.startswith("Stance_") and e.name != status_name]
                        elif isinstance(tgt, dict) and "status_effects" in tgt:
                            existing_stances = [
                                (e.name if hasattr(e, "name") else e.get("name")) 
                                for e in tgt["status_effects"] 
                                if (e.name if hasattr(e, "name") else e.get("name", "")).startswith("Stance_") 
                                and (e.name if hasattr(e, "name") else e.get("name")) != status_name
                            ]
                        for stance in existing_stances:
                            remove_status(tgt, stance)
                            logs.append(f"🔄 移除舊姿態【{stance}】")
                            
                    add_entity_status_effect(
                        tgt,
                        status_name,
                        act.get("description", status_name),
                        act.get("duration", 1),
                        act.get("stat_bonuses"),
                        dot_damage_flat=act.get("dot_damage_flat", 0.0),
                        dot_damage_type=act.get("dot_damage_type", "true_damage"),
                        custom_status_name=act.get("custom_status_name"),
                        canonical_status=act.get("canonical_status")
                    )
                    logs.append(f"✨ 施加狀態【{status_name}】給 {get_entity_name(tgt)}。")
            elif act_type == "gain_shield" and not _has_special("Shield"):
                shield_val = int(act.get("flat_value", 20.0))
                curr_temp = get_entity_attr(tgt, "temp_hp", 0)
                set_entity_attr(tgt, "temp_hp", curr_temp + shield_val)
                add_entity_status_effect(tgt, "Shield", "護盾防護", act.get("duration", 3))
                logs.append(f"🛡️ 獲得【護盾】：為 {get_entity_name(tgt)} 增加 {shield_val} 點臨時生命 (temp_hp)。")
            elif act_type == "heal":
                flat = act.get("flat_value", 0.0)
                res = act.get("target_resource", "hp")
                curr_val = get_entity_attr(tgt, res, 100)
                max_val = get_entity_attr(tgt, f"max_{res}", 100)
                set_entity_attr(tgt, res, min(max_val, curr_val + int(flat)))
                logs.append(f"💚 附加效果為 {get_entity_name(tgt)} 恢復了 {flat} 點 {res}。")
            elif act_type == "inflict_damage":
                flat = act.get("flat_value", 0.0)
                curr_hp = get_entity_attr(tgt, "hp", 100)
                set_entity_attr(tgt, "hp", max(0, curr_hp - int(flat)))
                logs.append(f"💥 附加效果對 {get_entity_name(tgt)} 造成了 {flat} 點真實傷害。")

        # 2. 處理寫死的特殊/傳說機制 status 邏輯 (配合舊代碼/測試語意)
        if _has_special("Banish"):
            add_entity_status_effect(target, "Banish", "放逐狀態：免疫所有技能與攻擊且無法行動", 2)
            logs.append(f"🌀 施加【放逐】給 {get_entity_name(target)}，持續 2 回合。")
        if _has_special("Stun"):
            add_entity_status_effect(target, "Stun", "暈眩：無法行動", 1)
            control_flags["stun_active"] = True
            logs.append(f"🌀 施加【暈眩】給 {get_entity_name(target)}，下回合跳過。")
        if _has_special("Silence"):
            add_entity_status_effect(target, "Silence", "沉默：無法施展傷害技能", 2)
            logs.append(f"🤐 施加【沉默】給 {get_entity_name(target)}，持續 2 回合。")
        if _has_special("Root"):
            add_entity_status_effect(target, "Root", "定身：無法使用物理近戰技能", 2)
            logs.append(f"🕸️ 施加【定身】給 {get_entity_name(target)}，持續 2 回合。")
        if _has_special("Slow"):
            add_entity_status_effect(target, "Slow", "減速", 3, {"DEX": -99})
            control_flags["slow_active"] = True
            logs.append(f"❄️ 施加【減速】給 {get_entity_name(target)}：閃避歸零且出手順序墊底。")
        if _has_special("Burn"):
            add_entity_status_effect(target, "Burn", "灼燒 DoT", 3,
                                     dot_damage_flat=15.0, dot_damage_type="true_damage")
            logs.append(f"🔥 施加【灼燒】給 {get_entity_name(target)}，每回合造成 15 點真實傷害。")
        if _has_special("Frostbite"):
            add_entity_status_effect(target, "Frostbite", "凍傷", 3,
                                     dot_damage_flat=8.0, dot_damage_type="true_damage")
            logs.append(f"🥶 施加【凍傷】給 {get_entity_name(target)}，每回合造成 8 點真實傷害，持續 3 回合。")
        if _has_special("Blind"):
            add_entity_status_effect(target, "Blind", "盲目", 2)
            logs.append(f"🕶️ 施加【盲目】給 {get_entity_name(target)}，持續 2 回合。")
        if _has_special("Doom"):
            add_entity_status_effect(target, "Doom", "厄運宣告：倒數即死", 3)
            logs.append(f"☠️ 施加【厄運宣告】給 {get_entity_name(target)}！3 回合後結算。")
        if _has_special("Charm"):
            add_entity_status_effect(target, "Charm", "傷害反轉並隨機指向隊友", 2)
            control_flags["charm_active"] = True
            logs.append(f"💖 施加【魅惑】給 {get_entity_name(target)}：反轉目標類型隨機攻擊隊友。")
        if _has_special("Confusion"):
            add_entity_status_effect(target, "Confusion", "混難", 2)
            control_flags["confusion_active"] = True
            logs.append(f"💫 施加【混亂】給 {get_entity_name(target)}，每次行動 50% 機率取消。")
            
        if _has_special("Shield"):
            shield_val = int(final_value if action_type in ["heal", "buff"] else 20)
            curr_temp = get_entity_attr(target, "temp_hp", 0)
            set_entity_attr(target, "temp_hp", curr_temp + shield_val)
            add_entity_status_effect(target, "Shield", "護盾防護", 3)
            logs.append(f"🛡️ 獲得【護盾】：為 {get_entity_name(target)} 增加 {shield_val} 點臨時生命 (temp_hp)。")
            
        if _has_special("Immune"):
            add_entity_status_effect(target, "Immune", "免疫所有負面狀態", 2)
            logs.append(f"✨ 獲得【免疫】：施加霸體狀態，持續 2 回合。")
        if _has_special("Invis"):
            add_entity_status_effect(target, "Invis", "隱身中", 3)
            control_flags["invis_active"] = True
            logs.append(f"👤 進入【隱身】狀態：暫時從敵方可選目標列表中移除。")
        if _has_special("Levitate"):
            add_entity_status_effect(target, "Levitate", "浮空狀態", 3)
            logs.append(f"🍃 進入【浮空】狀態，持續 3 回合。")
        if _has_special("Counter_Stance"):
            add_entity_status_effect(target, "Counter_Stance", "反擊架勢", 2)
            logs.append(f"⚔️ 進入【反擊架勢】，受到物理攻擊將會進行反擊。")
        if _has_special("Bless"):
            add_entity_status_effect(target, "Bless", "祝福", 3)
            logs.append(f"🌟 獲得【祝福】：接下來 3 回合若擲骰 <= 5，補底提升至 10。")
        if _has_special("Reflect"):
            add_entity_status_effect(target, "Reflect", "傷害反射盾", 2)
            logs.append(f"🪞 獲得【反射】狀態：記錄下一次傷害減免 50% 並反彈，持續 2 回合。")
        if _has_special("Taunt"):
            add_entity_status_effect(target, "Taunt", "被施法者嘲諷，單體攻擊強制指向施法者", 2)
            logs.append(f"😠 施加【嘲諷】給 {get_entity_name(target)}，強制其單體攻擊指向施法者。")
        if _has_special("Purge"):
            debuffs = {"Stun", "Silence", "Root", "Slow", "Burn", "Frostbite", "Blind", "Doom", "Charm", "Confusion", "Sunder", "Taunt"}
            if hasattr(target, "data") and hasattr(target.data, "status_effects"):
                target.data.status_effects = [
                    e for e in target.data.status_effects
                    if e.name not in debuffs or ("no_purge" in getattr(e, "tags", []))
                ]
            elif isinstance(target, dict) and "status_effects" in target:
                target["status_effects"] = [
                    e for e in target["status_effects"]
                    if (e.name not in debuffs if hasattr(e, "name") else e.get("name") not in debuffs)
                    or ("no_purge" in (e.tags if hasattr(e, "tags") else e.get("tags", [])))
                ]
            logs.append(f"✨ 觸發【淨化】：清除了 {get_entity_name(target)} 身上的所有可淨化負面狀態！")
        if _has_special("Time_Warp"):
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
        if _has_special("Steal"):
            gold_steal = random.randint(10, 30)
            if hasattr(caster, "data") and hasattr(caster.data, "gold"):
                caster.data.gold += gold_steal
            elif isinstance(caster, dict):
                caster["gold"] = caster.get("gold", 0) + gold_steal
            control_flags["steal_active"] = True
            logs.append(f"💰 觸發【竊取】：成功從目標身上竊取了 {gold_steal} 金幣！")

        if _has_special("Doom_Seal"):
            add_entity_status_effect(
                target, "Doom_Seal",
                "不可解除的死亡倒數",
                2,
                tags=["no_purge"]
            )
            logs.append(f"💀 施加【厄印強化】：2 回合後必死，且無法被淨化！")

        if _has_special("Void_Rift"):
            caster_id = get_entity_id(caster)
            add_entity_status_effect(
                target, "Void_Rift",
                "裂隙共鳴：每次受傷後，裂隙施放者承受 25% 反噬真實傷害",
                2,
                extra_data={"rift_caster_id": caster_id}
            )
            logs.append(f"🕳️ 觸發【虛空裂隙】：裂隙共鳴建立！目標每次受傷，施放者也承受 25% 反噬！")

        if _has_special("Eternal_Wound"):
            add_entity_status_effect(
                target, "Eternal_Wound",
                "回復封印：無法通過 any 方式恢復 HP",
                3
            )
            logs.append(f"🩹 觸發【永恆創傷】：{get_entity_name(target)} 的回復能力被封印 3 回合！")

        if _has_special("Abyssal_Mark"):
            add_entity_status_effect(
                target, "Abyssal_Mark",
                "深淵印記：承受所有來源傷害增加 40%",
                2
            )
            logs.append(f"🔱 觸發【深淵印記】：{get_entity_name(target)} 承受傷害提升 40%，持續 2 回合。")

        if _has_special("Fate_Seal"):
            sealed_hp = get_entity_attr(target, "hp", 100)
            add_entity_status_effect(
                target, "Fate_Seal",
                f"命運封印：3 回合後 HP 強制還原為 {sealed_hp}",
                3,
                extra_data={"sealed_hp": sealed_hp}
            )
            logs.append(f"⏳ 觸發【命運封印】：{get_entity_name(target)} 的命運在此刻凝固！3 回合後 HP 強制還原為 {sealed_hp}！")

        # [新增特殊/傳說狀態效果附加邏輯]
        if _has_special("Bleed"):
            bleed_act = next((a for a in actions if a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == "Bleed"), None)
            duration = int(bleed_act.get("duration", 3)) if bleed_act else 3
            dmg = float(bleed_act.get("dot_damage_flat", 15.0)) if bleed_act else 15.0
            status_name = bleed_act.get("status_name") if bleed_act else "Bleed"
            custom_status_name = bleed_act.get("custom_status_name") if bleed_act else None
            canonical_status = bleed_act.get("canonical_status") if bleed_act else None
            add_entity_status_effect(
                target,
                status_name,
                "流血：每回合受到物理持續傷害且治療減半",
                duration,
                dot_damage_flat=dmg,
                dot_damage_type="physical",
                custom_status_name=custom_status_name,
                canonical_status=canonical_status
            )
            logs.append(f"🩸 施加【{status_name}】給 {get_entity_name(target)}，每回合造成 {dmg} 點物理傷害，且使其治療與吸血效果減半，持續 {duration} 回合。")

        if _has_special("Ward"):
            ward_act = next((a for a in actions if a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == "Ward"), None)
            duration = int(ward_act.get("duration", 3)) if ward_act else 3
            status_name = ward_act.get("status_name") if ward_act else "Ward"
            custom_status_name = ward_act.get("custom_status_name") if ward_act else None
            canonical_status = ward_act.get("canonical_status") if ward_act else None
            add_entity_status_effect(
                target,
                status_name,
                "魔防護盾：抵消下一次受到的負面狀態",
                duration,
                custom_status_name=custom_status_name,
                canonical_status=canonical_status
            )
            logs.append(f"🛡️ 施加【{status_name}】給 {get_entity_name(target)}，將抵消下一次受到的負面狀態，持續 {duration} 回合。")

        if _has_special("Desperation"):
            desp_act = next((a for a in actions if a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == "Desperation"), None)
            duration = int(desp_act.get("duration", 3)) if desp_act else 3
            hp_threshold = float(desp_act.get("hp_threshold", 30.0)) if desp_act else 30.0
            dmg_bonus = float(desp_act.get("dmg_bonus", 50.0)) if desp_act else 50.0
            lifesteal_percent = float(desp_act.get("lifesteal_percent", 30.0)) if desp_act else 30.0
            status_name = desp_act.get("status_name") if desp_act else "Desperation"
            custom_status_name = desp_act.get("custom_status_name") if desp_act else None
            canonical_status = desp_act.get("canonical_status") if desp_act else None
            add_entity_status_effect(
                target,
                status_name,
                f"絕境怒火：HP < {hp_threshold}% 時，傷害增加 {dmg_bonus}% 且獲得 {lifesteal_percent}% 吸血",
                duration,
                extra_data={"hp_threshold": hp_threshold, "dmg_bonus": dmg_bonus, "lifesteal_percent": lifesteal_percent},
                custom_status_name=custom_status_name,
                canonical_status=canonical_status
            )
            logs.append(f"🔥 施加【{status_name}】給 {get_entity_name(target)}，當生命值低於 {hp_threshold}% 時，傷害增加 {dmg_bonus}% 且獲得 {lifesteal_percent}% 吸血，持續 {duration} 回合。")

        if _has_special("Fade"):
            fade_act = next((a for a in actions if a.get("action_type") == "call_special_mechanic" and normalize_status_name(a.get("keyword_name")) == "Fade"), None)
            duration = int(fade_act.get("duration", 2)) if fade_act else 2
            if has_status(caster, "Taunt"):
                remove_status(caster, "Taunt")
            add_entity_status_effect(caster, "Invis", "隱身：無法被單體選中", duration)
            logs.append(f"💨 觸發【仇恨消退】：施法者 {get_entity_name(caster)} 移除了嘲諷狀態，並進入隱身狀態，持續 {duration} 回合。")

        if _has_special("Phoenix_Rebirth"):
            pr_act = next((a for a in actions if a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == "Phoenix_Rebirth"), None)
            duration = int(pr_act.get("duration", 3)) if pr_act else 3
            status_name = pr_act.get("status_name") if pr_act else "Phoenix_Rebirth"
            custom_status_name = pr_act.get("custom_status_name") if pr_act else None
            canonical_status = pr_act.get("canonical_status") if pr_act else None
            add_entity_status_effect(
                target,
                status_name,
                "涅槃重燃：死亡後復活，恢復 50% HP/MP",
                duration,
                custom_status_name=custom_status_name,
                canonical_status=canonical_status
            )
            logs.append(f"🔥 施加【{status_name}】給 {get_entity_name(target)}，持續 {duration} 回合。")

        if _has_special("Fate_Swap"):
            caster_max_hp = get_entity_attr(caster, "max_hp", 100)
            target_max_hp = get_entity_attr(target, "max_hp", 100)
            
            caster_ratio = initial_caster_hp / caster_max_hp
            target_ratio = initial_target_hp / target_max_hp
            
            new_caster_hp = int(caster_max_hp * target_ratio)
            new_target_hp = int(target_max_hp * caster_ratio)
            
            set_entity_attr(caster, "hp", max(1, new_caster_hp))
            set_entity_attr(target, "hp", max(1, new_target_hp))
            
            logs.append(f"🔮 觸發【因果互換】：施法者 {get_entity_name(caster)} ({caster_ratio*100:.1f}% HP) 與目標 {get_entity_name(target)} ({target_ratio*100:.1f}% HP) 互換生命值百分比！")

        if _has_special("Mind_Control"):
            mc_act = next((a for a in actions if a.get("action_type") == "apply_status" and normalize_status_name(a.get("status_name")) == "Mind_Control"), None)
            duration = int(mc_act.get("duration", 1)) if mc_act else 1
            status_name = mc_act.get("status_name") if mc_act else "Mind_Control"
            custom_status_name = mc_act.get("custom_status_name") if mc_act else None
            canonical_status = mc_act.get("canonical_status") if mc_act else None
            add_entity_status_effect(
                target,
                status_name,
                "心靈傀儡：被控制，下一次攻擊會打向盟友",
                duration,
                custom_status_name=custom_status_name,
                canonical_status=canonical_status
            )
            logs.append(f"🧠 施加【{status_name}】給 {get_entity_name(target)}，將在下回合控制其攻擊其盟友，持續 {duration} 回合。")

        if _has_special("Apocalypse"):
            add_entity_status_effect(target, "Silence", "沉默：無法施展傷害技能", 2)
            control_flags["apocalypse_aoe"] = True
            logs.append(f"🤐 【天劫降臨】對 {get_entity_name(target)} 施加【沉默】2 回合！")

        # ---------------------------------------------------------
        # Phase 7: Post-cast resolution (後置與連段判定)
        # ---------------------------------------------------------
        if _has_special("Chain"):
            control_flags["chain_active"] = True
            logs.append("⚡ 【連鎖】標記已啟動：尋找下一個存活敵人，無消耗再呼叫同技能（傷害衰減 50%）。")
        if _has_special("Summon"):
            control_flags["summon_active"] = True
            logs.append("🌀 【召喚】印記已亮起：在戰鬥序列中實例化 Entity，由 AI 接管其行為。")
        if _has_special("Resurrect"):
            control_flags["resurrect_active"] = True
            logs.append("🕊️ 【復甦】奧義已啟動，將復活倒下的盟友。")
        if _has_special("Rampage"):
            target_hp = get_entity_attr(target, "hp", 100)
            if target_hp <= 0:
                control_flags["rampage_active"] = True
                logs.append("🩸 擊殺觸發【殺戮盛宴】！獲得額外行動機會。")
        if _has_special("Greed"):
            control_flags["greed_active"] = True
            logs.append("💰 【貪婪】標記已附著：若目標死於此技能，金幣掉落乘以 2~3 倍。")
        if _has_special("Adapt"):
            add_entity_status_effect(caster, "Adapt", "適應性抗性", 3)
            logs.append("🧬 觸發【適應】：獲得對目標屬性的防禦抗性。")
        if _has_special("Echo"):
            control_flags["echo_active"] = True
            logs.append("🔊 觸發【殘響】：下回合將以 50% 的威力自動重複施放此技能。")
        if _has_special("Berserk"):
            add_entity_status_effect(caster, "Berserk", "狂暴中：強制隨機攻擊", 3, {"skill_power": 0.5})
            control_flags["berserk_active"] = True
            logs.append("🩸 觸發【狂暴】：獲得極端強大傷害加成，接下來 3 回合內無法手動下令，系統強迫每回合進行隨機普攻！")
            
        if _has_special("Soul_Shatter"):
            target_hp = get_entity_attr(target, "hp", 100)
            if target_hp <= 0:
                control_flags["soul_shatter_triggered"] = True
                curr_san = get_entity_attr(caster, "sanity", 0)
                max_san = get_entity_attr(caster, "max_sanity", 100)
                set_entity_attr(caster, "sanity", min(max_san, curr_san + 50))
                logs.append("💀 觸發【靈魂粉碎】：靈魂爆裂！全體敵人陷入 Stun，施法者回復 50 SAN！")

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
        return has_status(entity, status_name)

    @staticmethod
    def _remove_status(entity, status_name: str):
        remove_status(entity, status_name)

    @staticmethod
    def _get_name(entity) -> str:
        return get_entity_name(entity)


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
        if getattr(skill, "skill_type", "active") == "passive":
            return skill

        tier_min_divisors = {
            "T1": 5.0,
            "T2": 8.0,
            "T3": 10.0,
            "T4": 12.0,
            "T5": 15.0
        }
        
        base_min = tier_min_divisors.get(skill.tier, 15.0)
        
        if skill.mechanics.target_type == "aoe":
            base_min *= 1.5
            
        formula = skill.mechanics.formula
        if formula.type == "multiplier":
            original = formula.divisor
            formula.divisor = max(base_min, formula.divisor)
            if formula.divisor > original:
                print(f"⚖️ 技能 {skill.name} ({skill.tier}) 分母已從 {original} 校正為 {formula.divisor} (AoE: {skill.mechanics.target_type == 'aoe'})")
        
        # 額外防防呆：只有 T1 (傳說) 或反制 (reactive) 技能允許擁有 triggers，否則清空。非 T1 移除 any 傳說 actions。
        if skill.tier != "T1":
            if skill.mechanics.execution_mode != "reactive":
                skill.executable_triggers = []
            legendaries = {
                "Annihilate", "Soul_Drain", "Blood_Pact", "Devil's_Roll", "Last_Rites", 
                "Resonance_Break", "Paradox", "Doom_Seal", "Void_Rift", "Eternal_Wound", 
                "Abyssal_Mark", "Fate_Seal", "Soul_Shatter", "Time_Warp",
                "Phoenix_Rebirth", "Fate_Swap", "Mind_Control", "Apocalypse"
            }
            # 過濾掉傳說級 actions
            skill.mechanics.actions = [
                act for act in skill.mechanics.actions
                if not (act.get("action_type") == "call_special_mechanic" and act.get("keyword_name") in legendaries)
            ]

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
