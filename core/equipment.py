# core/equipment.py
from typing import Dict, Any
from core.models import Equipment

class EquipmentBalancer:
    # =========================================================================
    # 詞條品質分層配置 (品質 tier 決定觸發器上限、品質要求、限制條件)
    # =========================================================================
    AFFIX_QUALITY_TIERS = {
        "T1": {
            "allowed_qualities": ["noble", "complex"],
            "max_triggers": 2,
            "can_have_aoe": True,
            "can_have_complex": True,
            "can_have_debuff": True,
            "max_debuff_strength": None,
            "description": "2個高貴詞條，允許所有類型效果"
        },
        "T2": {
            "allowed_qualities": ["standard"],
            "max_triggers": 1,
            "can_have_aoe": False,
            "can_have_complex": False,
            "can_have_debuff": True,
            "max_debuff_strength": -0.15,
            "description": "1個中級詞條，禁AoE/複合，減益≤-15%"
        },
        "T3": {
            "allowed_qualities": ["basic"],
            "max_triggers": 1,
            "can_have_aoe": False,
            "can_have_complex": False,
            "can_have_debuff": False,
            "can_have_buff": True,
            "description": "1個基礎詞條，只能自增益，禁止減敵方"
        },
        "T4": {
            "allowed_qualities": [],
            "max_triggers": 0,
            "description": "無觸發器"
        },
        "T5": {
            "allowed_qualities": [],
            "max_triggers": 0,
            "description": "無觸發器"
        }
    }

    # 稀有度倍率配置 (T1 最稀有, T5 最普通)
    TIER_SUB_MULTIPLIERS = {
        "T5": 0.0,
        "T4": 0.8,
        "T3": 1.5,
        "T2": 2.5,
        "T1": 4.0
    }

    AFFIX_SLOTS = {
        "T5": 0, "T4": 1, "T3": 2, "T2": 3, "T1": 3
    }

    STAT_WEIGHTS = {
        "STR": 1.0, "DEX": 1.0, "CON": 1.0, "INT": 1.0, "WIS": 1.0, "CHA": 1.0,
        "crit_rate": 1000.0,
        "evasion_rate": 1000.0,
        "accuracy": 1000.0,
        "skill_power": 1000.0,
        "tenacity": 1.0,
        "luck": 5.0,
        "p_def": 1.0,
        "m_def": 1.0
    }

    @classmethod
    def calculate_budgets(cls, item_level: int, tier: str) -> dict:
        primary_budget = (10 + (item_level * 2.5)) * 0.75
        sub_base = (item_level * 0.25)
        multiplier = cls.TIER_SUB_MULTIPLIERS.get(tier, 0.0)
        sub_budget = sub_base * multiplier
        return {"primary": primary_budget, "sub": sub_budget}

    @classmethod
    def validate_and_clamp(cls, equipment: Equipment) -> Equipment:
        budgets = cls.calculate_budgets(equipment.item_level, equipment.tier)
        
        primary_list = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        allowed_subs = ["crit_rate", "evasion_rate", "accuracy", "skill_power", "tenacity", "luck", "p_def", "m_def"]
        
        equipment.bonuses = {
            k: v for k, v in equipment.bonuses.items() 
            if v > 0 and (k in primary_list or k in allowed_subs)
        }
        
        proposed_primary = {k: v for k, v in equipment.bonuses.items() if k in primary_list}
        proposed_sub = {k: v for k, v in equipment.bonuses.items() if k in allowed_subs}

        if not proposed_primary:
            proposed_primary = {"CON": budgets["primary"]}
        
        p_cost = sum(proposed_primary.values())
        if p_cost > 0:
            ratio = budgets["primary"] / p_cost
            proposed_primary = {k: float(max(1, round(v * ratio))) for k, v in proposed_primary.items()}
        
        max_slots = cls.AFFIX_SLOTS.get(equipment.tier, 0)
        if max_slots > 0:
            if not proposed_sub:
                proposed_sub = {"luck": 1.0} 
            
            sorted_subs = sorted(
                proposed_sub.items(), 
                key=lambda x: x[1] * cls.STAT_WEIGHTS.get(x[0], 1.0), 
                reverse=True
            )
            proposed_sub = dict(sorted_subs[:max_slots])

            s_cost = sum(abs(v) * cls.STAT_WEIGHTS.get(k, 1.0) for k, v in proposed_sub.items())
            if s_cost > 0 and budgets["sub"] > 0:
                ratio = budgets["sub"] / s_cost
                new_sub = {}
                for k, v in proposed_sub.items():
                    w = cls.STAT_WEIGHTS.get(k, 1.0)
                    final_v = v * ratio
                    if w < 10:
                        new_sub[k] = float(max(1, round(final_v)))
                    else:
                        new_sub[k] = float(max(0.01, round(final_v, 2)))
                proposed_sub = new_sub
        else:
            proposed_sub = {}

        final_bonuses = {**proposed_primary, **proposed_sub}
        
        if equipment.slot_type in ["main_hand", "off_hand"]:
            is_shield = equipment.weapon_type in ["小盾", "巨盾"]
            is_focus = equipment.weapon_type in ["法器", "魔導書"]
            
            if equipment.slot_type == "main_hand" or (equipment.slot_type == "off_hand" and not is_shield and not is_focus):
                ilvl = equipment.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(equipment.tier, 1.0)
                
                if equipment.is_two_handed:
                    atk_val = (15.0 + ilvl * 3.0) * mult
                else:
                    atk_val = (5.0 + ilvl * 1.5) * mult
                final_bonuses["ATK"] = float(round(atk_val, 1))
            elif is_shield:
                ilvl = equipment.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(equipment.tier, 1.0)
                if equipment.weapon_type == "巨盾":
                    def_val = (10.0 + ilvl * 2.0) * mult
                else:
                    def_val = (5.0 + ilvl * 1.0) * mult
                final_bonuses["p_def"] = float(round(def_val, 1))
            elif is_focus and equipment.slot_type == "off_hand":
                ilvl = equipment.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(equipment.tier, 1.0)
                def_val = (5.0 + ilvl * 1.0) * mult
                final_bonuses["m_def"] = float(round(def_val, 1))
        elif equipment.slot_type in ["head", "shoulders", "cloak", "chest", "hands", "legs", "feet"]:
            ilvl = equipment.item_level
            tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
            mult = tier_mults.get(equipment.tier, 1.0)
            
            if equipment.slot_type == "chest":
                p_val = (8.0 + ilvl * 1.6) * mult
                m_val = (4.0 + ilvl * 0.8) * mult
            elif equipment.slot_type == "legs":
                p_val = (5.0 + ilvl * 1.0) * mult
                m_val = (2.5 + ilvl * 0.5) * mult
            elif equipment.slot_type == "head":
                p_val = (3.0 + ilvl * 0.6) * mult
                m_val = (1.5 + ilvl * 0.3) * mult
            elif equipment.slot_type == "cloak":
                p_val = (1.0 + ilvl * 0.2) * mult
                m_val = (3.0 + ilvl * 0.6) * mult
            else:  # shoulders, hands, feet
                p_val = (2.0 + ilvl * 0.4) * mult
                m_val = (1.0 + ilvl * 0.2) * mult
                
            final_bonuses["p_def"] = float(round(p_val, 1))
            final_bonuses["m_def"] = float(round(m_val, 1))

        equipment.bonuses = {k: v for k, v in final_bonuses.items() if v > 0}

        tier_config = cls.AFFIX_QUALITY_TIERS.get(equipment.tier, {})
        max_triggers = tier_config.get("max_triggers", 0)
        if max_triggers > 0:
            equipment.executable_triggers = equipment.executable_triggers[:max_triggers]
            equipment = cls.validate_affix_quality(equipment, equipment.tier)
        else:
            equipment.executable_triggers = []

        if equipment.tier != "T1":
            equipment.special_effect = ""

        return equipment

    @staticmethod
    def is_complex_trigger(trigger: dict) -> bool:
        actions = trigger.get("actions", [])

        if len(actions) > 1:
            return True

        if len(actions) == 1:
            action = actions[0]
            has_status = "status_name" in action and action.get("status_name")
            has_debuff = "debuff_name" in action and action.get("debuff_name")

            if has_status and has_debuff:
                return True

        return False

    @classmethod
    def validate_affix_quality(cls, equipment: "Equipment", tier: str) -> "Equipment":
        if tier not in cls.AFFIX_QUALITY_TIERS:
            return equipment

        tier_config = cls.AFFIX_QUALITY_TIERS.get(tier, {})
        allowed_qualities = tier_config.get("allowed_qualities", [])
        can_have_aoe = tier_config.get("can_have_aoe", False)
        can_have_complex = tier_config.get("can_have_complex", False)
        can_have_debuff = tier_config.get("can_have_debuff", False)
        max_debuff_strength = tier_config.get("max_debuff_strength")

        deleted_triggers = []
        remaining_triggers = []

        for idx, trigger in enumerate(equipment.executable_triggers):
            violation_reasons = []

            if not can_have_aoe:
                for action in trigger.get("actions", []):
                    target = action.get("target", "")
                    if target and "all_" in target:
                        violation_reasons.append(f"T{tier[-1]} 禁止 AoE (檢測到 target: {target})")
                        break

            if not can_have_complex:
                if cls.is_complex_trigger(trigger):
                    violation_reasons.append(f"T{tier[-1]} 禁止複合效果")

            if tier == "T3":
                for action_idx, action in enumerate(trigger.get("actions", [])):
                    target = action.get("target", "caster")
                    if target not in ["caster", "self"]:
                        violation_reasons.append(
                            f"T3 禁止減敵方效果：Action {action_idx} target='{target}' (必須是 'caster')"
                        )
                        break
                    if "debuff_name" in action or action.get("action_type") == "apply_debuff":
                        violation_reasons.append(f"T3 禁止 debuff (檢測到 apply_debuff 行動)")
                        break

            if can_have_debuff and max_debuff_strength is not None:
                for action in trigger.get("actions", []):
                    bonuses = action.get("stat_bonuses", {})
                    for stat, value in bonuses.items():
                        if isinstance(value, (int, float)) and -1 < value < 0:
                            if value < max_debuff_strength:
                                violation_reasons.append(
                                    f"T2 減益強度超限：{stat}={value} (最大 {max_debuff_strength})"
                                )
                                break

            if violation_reasons:
                deleted_triggers.append({
                    "index": idx,
                    "trigger": trigger,
                    "reasons": violation_reasons
                })
            else:
                remaining_triggers.append(trigger)

        equipment.executable_triggers = remaining_triggers

        if deleted_triggers and not hasattr(equipment, "_validation_log"):
            equipment._validation_log = deleted_triggers

        return equipment

    @classmethod
    def get_tier_color(cls, tier: str) -> int:
        colors = {"T1": 0xf1c40f, "T2": 0x9b59b6, "T3": 0x3498db, "T4": 0x2ecc71, "T5": 0x95a5a6}
        return colors.get(tier, 0xffffff)
