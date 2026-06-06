# core/compiler.py
import re
import uuid
from typing import List, Dict, Any, Tuple

class TriggerCompiler:
    # 戰鬥屬性 Key 映射表
    STAT_BONUS_MAPPING = {
        "physical_defense": "p_def", "物理防禦": "p_def", "pdef": "p_def", "p_def": "p_def",
        "magic_defense": "m_def", "魔法防禦": "m_def", "mdef": "m_def", "m_def": "m_def",
        "crit_rate": "crit_rate", "爆擊率": "crit_rate", "crit": "crit_rate",
        "evasion_rate": "evasion_rate", "閃避率": "evasion_rate", "evasion": "evasion_rate",
        "accuracy": "accuracy", "命中率": "accuracy", "acc": "accuracy",
        "skill_power": "skill_power", "技能威力": "skill_power", "power": "skill_power",
        "tenacity": "tenacity", "韌性": "tenacity", "ten": "tenacity",
        "luck": "luck", "幸運": "luck", "lucky": "luck"
    }

    # 合法屬性係數
    ALLOWED_SCALING_STATS = {
        "STR", "DEX", "CON", "INT", "WIS", "CHA", "MAX_HP", "DAMAGE_TAKEN"
    }

    # 攔截器事件
    INTERCEPTOR_EVENTS = {"on_prepare", "on_dice", "on_calculate_damage"}
    
    # 後置普通事件
    COMBAT_EVENTS = {
        "on_battle_start", "on_turn_start", "on_turn_end", "on_hit", 
        "on_damaged", "on_kill", "on_health_below", "on_health_up", 
        "on_crit", "on_miss", "on_dodge", "on_fatal_damage"
    }

    @classmethod
    def compile_flat_triggers(cls, flat_triggers: Any) -> List[Dict[str, Any]]:
        """
        將 AI Stage 1 的扁平/樂高 Trigger JSON 編譯為 100% 格式正確的 Trigger DSL。
        """
        if not isinstance(flat_triggers, list):
            return []

        compiled_triggers = []

        for trigger_raw in flat_triggers:
            if not isinstance(trigger_raw, dict):
                continue

            # 1. 解析事件與對應名稱修正 (on_cast -> on_prepare)
            event_raw = trigger_raw.get("event", "")
            if not isinstance(event_raw, str):
                continue
                
            event = event_raw.strip()
            if event == "on_cast":
                event = "on_prepare"

            # 驗證事件是否在白名單中
            if event not in cls.INTERCEPTOR_EVENTS and event not in cls.COMBAT_EVENTS:
                continue

            # 2. 條件扁平化解析與轉譯
            conditions = []
            
            # HP 門檻條件
            hp_below_val = None
            if "hp_below" in trigger_raw and trigger_raw["hp_below"] is not None:
                try:
                    hp_below_val = cls._parse_percent(trigger_raw["hp_below"])
                    conditions.append(f"health_below({int(hp_below_val)})")
                except (ValueError, TypeError):
                    pass

            hp_above_val = None
            if "hp_above" in trigger_raw and trigger_raw["hp_above"] is not None:
                try:
                    hp_above_val = cls._parse_percent(trigger_raw["hp_above"])
                    conditions.append(f"health_above({int(hp_above_val)})")
                except (ValueError, TypeError):
                    pass

            # Caster 狀態條件
            if "caster_has_status" in trigger_raw and trigger_raw["caster_has_status"]:
                status = str(trigger_raw["caster_has_status"]).strip()
                conditions.append(f"has_status('{status}')")
            if "caster_not_status" in trigger_raw and trigger_raw["caster_not_status"]:
                status = str(trigger_raw["caster_not_status"]).strip()
                conditions.append(f"!has_status('{status}')")

            # Target 狀態條件
            if "target_has_status" in trigger_raw and trigger_raw["target_has_status"]:
                status = str(trigger_raw["target_has_status"]).strip()
                conditions.append(f"target_has_status('{status}')")
            if "target_not_status" in trigger_raw and trigger_raw["target_not_status"]:
                status = str(trigger_raw["target_not_status"]).strip()
                conditions.append(f"!target_has_status('{status}')")

            # 原生 condition 字串合併支援
            raw_cond = trigger_raw.get("condition")
            if raw_cond and isinstance(raw_cond, str):
                conditions.append(raw_cond.strip())

            # 合併為 "A and B" 格式
            condition_str = " and ".join(conditions) if conditions else None

            # 3. 讀取 Trigger 級別屬性
            cooldown = trigger_raw.get("cooldown")
            chance = trigger_raw.get("chance")
            dice_roll_str = trigger_raw.get("dice_roll")
            if dice_roll_str:
                dice_roll_str = str(dice_roll_str).strip()
            
            health_threshold = trigger_raw.get("health_threshold")
            if health_threshold is not None:
                health_threshold = cls._parse_percent(health_threshold)
            elif event == "on_health_below" and hp_below_val is not None:
                health_threshold = hp_below_val
                
            target_health_below = trigger_raw.get("target_health_below")
            if target_health_below is not None:
                target_health_below = cls._parse_percent(target_health_below)
                
            target_health_above = trigger_raw.get("target_health_above")
            if target_health_above is not None:
                target_health_above = cls._parse_percent(target_health_above)

            # 4. 行為解析與分類過濾
            actions_raw = trigger_raw.get("actions", [])
            if not isinstance(actions_raw, list):
                actions_raw = [actions_raw] if isinstance(actions_raw, dict) else []

            interceptor_actions = []
            combat_actions = []

            for act_raw in actions_raw:
                if not isinstance(act_raw, dict):
                    continue

                compiled_acts = cls._compile_single_action(act_raw)
                for act in compiled_acts:
                    act_type = act.get("action_type")
                    if act_type in ("set_flag", "set_value", "modify_dice"):
                        interceptor_actions.append(act)
                    else:
                        combat_actions.append(act)

            # 5. 跨事件 Flag 自動拆分與組裝
            # 情境一：同時有攔截器行為與普通戰鬥行為
            if interceptor_actions and combat_actions:
                # 建立隨機唯一的 Flag
                unique_flag = f"_auto_flag_{uuid.uuid4().hex[:6]}"
                
                # A. 建立前置攔截器 Trigger
                interceptor_event = event if event in cls.INTERCEPTOR_EVENTS else "on_calculate_damage"
                trigger_a = {
                    "event": interceptor_event,
                    "actions": interceptor_actions + [{
                        "action_type": "set_flag",
                        "param": unique_flag,
                        "param_value": True
                    }]
                }
                if cooldown is not None: trigger_a["cooldown"] = int(cooldown)
                if chance is not None: trigger_a["chance"] = float(chance)
                if condition_str: trigger_a["condition"] = condition_str
                
                # B. 建立後置事件 Trigger
                combat_event = event if event in cls.COMBAT_EVENTS else "on_hit"
                trigger_b = {
                    "event": combat_event,
                    "condition": f"context_flag('{unique_flag}')" + (f" and {condition_str}" if condition_str else ""),
                    "actions": combat_actions
                }
                if health_threshold is not None: trigger_b["health_threshold"] = float(health_threshold)
                if target_health_below is not None: trigger_b["target_health_below"] = float(target_health_below)
                if target_health_above is not None: trigger_b["target_health_above"] = float(target_health_above)
                if dice_roll_str: trigger_b["dice_roll"] = dice_roll_str

                compiled_triggers.append(trigger_a)
                compiled_triggers.append(trigger_b)

            # 情境二：只有攔截器行為
            elif interceptor_actions:
                actual_event = event if event in cls.INTERCEPTOR_EVENTS else "on_calculate_damage"
                t = {"event": actual_event, "actions": interceptor_actions}
                if cooldown is not None: t["cooldown"] = int(cooldown)
                if chance is not None: t["chance"] = float(chance)
                if condition_str: t["condition"] = condition_str
                if dice_roll_str: t["dice_roll"] = dice_roll_str
                compiled_triggers.append(t)

            # 情境三：只有普通戰鬥行為
            elif combat_actions:
                actual_event = event if event in cls.COMBAT_EVENTS else "on_hit"
                t = {"event": actual_event, "actions": combat_actions}
                if cooldown is not None: t["cooldown"] = int(cooldown)
                if chance is not None: t["chance"] = float(chance)
                if condition_str: t["condition"] = condition_str
                if health_threshold is not None: t["health_threshold"] = float(health_threshold)
                if target_health_below is not None: t["target_health_below"] = float(target_health_below)
                if target_health_above is not None: t["target_health_above"] = float(target_health_above)
                if dice_roll_str: t["dice_roll"] = dice_roll_str
                compiled_triggers.append(t)

        return compiled_triggers

    @classmethod
    def _compile_single_action(cls, act: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        編譯單一 Action，包含類型防呆、欄位轉換與複合行為展開。
        """
        action_type = act.get("action_type", "")
        if not isinstance(action_type, str):
            return []

        action_type = action_type.strip()
        compiled = []

        # 1. 轉譯 debuff
        if action_type == "apply_debuff":
            action_type = "apply_status"

        # 2. 轉譯複合行為：purge_debuffs (由引擎直接支援)
        if action_type == "purge_debuffs":
            target = act.get("target", "caster")
            compiled = [
                {"action_type": "purge_debuffs", "target": target}
            ]

        # 3. 展開複合行為：apply_shield
        elif action_type == "apply_shield":
            shield_name = act.get("shield_name", "Shield")
            duration = cls._to_int(act.get("duration"), 3)
            target = act.get("target", "caster")
            
            flat = cls._to_float(act.get("flat_value"), 0.0)
            stat = cls._clean_stat(act.get("scaling_stat"))
            dice = act.get("dice")
            if dice:
                dice = str(dice).strip()
            divisor = cls._to_float(act.get("divisor"), 1.0)
            
            con_mult = act.get("con_multiplier")
            if stat is None and con_mult is not None:
                stat = "CON"
                mult = cls._to_float(con_mult, 1.0)
            else:
                if stat is None and flat == 0.0 and not dice:
                    stat = "CON"
                raw_mult = act.get("value_multiplier") or act.get("multiplier") or con_mult
                if raw_mult is not None:
                    mult = cls._to_float(raw_mult, 0.0)
                else:
                    mult = 1.0 if stat else 0.0
            
            compiled = [
                {
                    "action_type": "apply_status",
                    "status_name": shield_name,
                    "duration": duration,
                    "target": target
                },
                {
                    "action_type": "gain_shield",
                    "flat_value": flat,
                    "scaling_stat": stat,
                    "value_multiplier": mult,
                    "dice": dice,
                    "divisor": divisor,
                    "target": target
                }
            ]

        # 4. 欄位對應轉換與參數清洗
        # A. inflict_damage
        elif action_type == "inflict_damage":
            target = act.get("target", "target")
            flat = cls._to_float(act.get("flat_value"), 0.0)
            stat = cls._clean_stat(act.get("scaling_stat"))
            raw_mult = act.get("value_multiplier") or act.get("multiplier")
            if raw_mult is not None:
                mult = cls._to_float(raw_mult, 0.0)
            else:
                mult = 1.0 if stat else 0.0
            dice = act.get("dice")
            if dice:
                dice = str(dice).strip()
            divisor = cls._to_float(act.get("divisor"), 1.0)
            
            compiled = [{
                "action_type": "inflict_damage",
                "target": target,
                "flat_value": flat,
                "scaling_stat": stat,
                "value_multiplier": mult,
                "dice": dice,
                "divisor": divisor,
                "damage_type": "true_damage"
            }]

        # B. gain_shield
        elif action_type == "gain_shield":
            target = act.get("target", "caster")
            flat = cls._to_float(act.get("flat_value"), 0.0)
            stat = cls._clean_stat(act.get("scaling_stat"))
            raw_mult = act.get("value_multiplier") or act.get("multiplier")
            if raw_mult is not None:
                mult = cls._to_float(raw_mult, 0.0)
            else:
                mult = 1.0 if stat else 0.0
            dice = act.get("dice")
            if dice:
                dice = str(dice).strip()
            divisor = cls._to_float(act.get("divisor"), 1.0)

            compiled = [{
                "action_type": "gain_shield",
                "target": target,
                "flat_value": flat,
                "scaling_stat": stat,
                "value_multiplier": mult,
                "dice": dice,
                "divisor": divisor
            }]

        # C. heal
        elif action_type == "heal":
            target = act.get("target", "caster")
            flat = cls._to_float(act.get("flat_value"), 0.0)
            stat = cls._clean_stat(act.get("scaling_stat"))
            raw_mult = act.get("value_multiplier") or act.get("multiplier")
            if raw_mult is not None:
                mult = cls._to_float(raw_mult, 0.0)
            else:
                mult = 1.0 if stat else 0.0
            res = act.get("target_resource", "hp")
            if res not in ("hp", "mp", "sanity"):
                res = "hp"
            dice = act.get("dice")
            if dice:
                dice = str(dice).strip()
            divisor = cls._to_float(act.get("divisor"), 1.0)

            compiled = [{
                "action_type": "heal",
                "target": target,
                "flat_value": flat,
                "scaling_stat": stat,
                "value_multiplier": mult,
                "target_resource": res,
                "dice": dice,
                "divisor": divisor
            }]

        # D. apply_status
        elif action_type == "apply_status":
            target = act.get("target", "caster" if act.get("action_type") == "apply_status" else "target")
            status_name = act.get("status_name") or act.get("debuff_name")
            if not status_name:
                return []
            duration = cls._to_int(act.get("duration"), 1)
            
            bonuses = {}
            bonuses_raw = act.get("bonuses") or act.get("stat_bonuses")
            if isinstance(bonuses_raw, dict):
                for k, v in bonuses_raw.items():
                    clean_k = cls.STAT_BONUS_MAPPING.get(str(k).lower().strip())
                    if clean_k:
                        bonuses[clean_k] = cls._to_float(v, 0.0)

            compiled = [{
                "action_type": "apply_status",
                "target": target,
                "status_name": status_name,
                "duration": duration,
                "bonuses": bonuses
            }]

        # E. remove_status
        elif action_type == "remove_status":
            target = act.get("target", "caster")
            status_name = act.get("status_name")
            if not status_name:
                return []
            compiled = [{
                "action_type": "remove_status",
                "target": target,
                "status_name": status_name
            }]

        # F. call_special_mechanic / call_special
        elif action_type in ("call_special_mechanic", "call_special"):
            kw = act.get("keyword_name")
            if kw not in ("Time_Warp", "Prevent_Death"):
                return []
            compiled = [{
                "action_type": "call_special_mechanic",
                "target": "caster",
                "keyword_name": kw
            }]

        # G. modify_dice
        elif action_type == "modify_dice":
            param = act.get("param")
            if param not in ("floor_value", "roll_modifier"):
                return []
            val = cls._to_int(act.get("param_value"), 0)
            compiled = [{
                "action_type": "modify_dice",
                "param": param,
                "param_value": val
            }]

        # H. set_value
        elif action_type == "set_value":
            param = act.get("param")
            if param not in ("damage_multiplier", "defense_ignore_ratio"):
                return []
            val = cls._to_float(act.get("param_value"), 1.0)
            compiled = [{
                "action_type": "set_value",
                "param": param,
                "param_value": val
            }]

        # Append dice_range if present
        dice_range = act.get("dice_range")
        if isinstance(dice_range, list) and len(dice_range) == 2:
            try:
                dice_range = [int(dice_range[0]), int(dice_range[1])]
                for item in compiled:
                    item["dice_range"] = dice_range
            except (ValueError, TypeError):
                pass

        return compiled

    # --- 輔助清洗工具方法 ---
    @classmethod
    def _to_float(cls, val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            val_str = str(val).strip().replace("x", "").replace("X", "")
            if "%" in val_str:
                return float(val_str.replace("%", "")) / 100.0
            return float(val_str)
        except (ValueError, TypeError):
            return default

    @classmethod
    def _to_int(cls, val: Any, default: int = 0) -> int:
        if val is None:
            return default
        try:
            return int(float(str(val).strip()))
        except (ValueError, TypeError):
            return default

    @classmethod
    def _clean_stat(cls, stat: Any) -> Any:
        if not stat:
            return None
        stat_str = str(stat).strip().upper()
        if stat_str in cls.ALLOWED_SCALING_STATS:
            return stat_str
        return None

    @classmethod
    def _parse_percent(cls, val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            val_str = str(val).strip().replace("x", "").replace("X", "")
            if "%" in val_str:
                return float(val_str.replace("%", ""))
            
            num = float(val_str)
            # 如果是 0.0 到 1.0 之間的小數（包含 1.0），轉成百分比（即乘以 100）
            if 0.0 < num <= 1.0:
                return num * 100.0
            return num
        except (ValueError, TypeError):
            return default
