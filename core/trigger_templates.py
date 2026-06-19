# core/trigger_templates.py
"""
觸發器模板庫（Trigger Template Library）

設計原則：
  - 每個模板函式負責組裝一個 100% 格式正確的 flat trigger dict
  - LLM 只需選擇模板 ID + 填寫少量創意參數（數值、名稱等）
  - 所有 action_type 分類、branch_roll 結構、DoT 必填欄位由模板保證
  - 模板函式回傳值可直接送入 TriggerCompiler.compile_flat_triggers()
"""

from __future__ import annotations
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 模板參數型別說明（僅作文件用，不強制 runtime 驗證）
# ---------------------------------------------------------------------------
# flat_value    : 固定傷害/護盾/回血值 (float)
# scaling_stat  : 縮放屬性 "STR"/"DEX"/"CON"/"INT"/"WIS"/"CHA" (str|None)
# value_mult    : 縮放倍率 (float)
# dice          : 骰子字串 e.g. "2d6" (str|None)
# divisor       : 骰子除數 (float, 預設 1)
# chance        : 觸發機率 0~1 (float|None)
# cooldown      : 冷卻回合 (int|None)
# status_name   : 自身增益狀態名稱 (str)
# debuff_name   : 敵方減益狀態名稱 e.g. "Burn"/"Slow"/"Sunder" (str)
# duration      : 狀態持續回合 (int)
# stat_bonuses  : 狀態屬性加成 dict (dict)
# hp_below      : 血量低於 X% 時觸發 (int, 1-100)
# dot_flat      : DoT 每回合固定傷害 (float)
# dot_stat      : DoT 縮放屬性 (str|None)
# dot_mult      : DoT 縮放倍率 (float)
# dot_type      : DoT 傷害類型 "true_damage"/"physical"/"magical"
# ---------------------------------------------------------------------------

DOT_DEBUFFS = {"Burn", "Frostbite", "Bleed", "Poison"}

VALID_DEBUFFS_T1 = {"Burn", "Frostbite", "Bleed", "Poison", "Slow", "Stun", "Root", "Blind", "Doom", "Sunder"}
VALID_DEBUFFS_T2 = {"Burn", "Frostbite", "Bleed", "Slow", "Blind", "Sunder"}


def _clean(val: Any, default: Any) -> Any:
    """若值為 None 則回傳預設值。"""
    return val if val is not None else default


def _dot_fields(debuff_name: str, dot_flat: float, dot_stat: Optional[str],
                dot_mult: float, dot_type: str) -> dict:
    """為 DoT 減益組裝必要欄位。若非 DoT 類型則回傳空 dict。"""
    from core.constants import normalize_status_name
    norm_name = normalize_status_name(debuff_name)
    if norm_name in DOT_DEBUFFS:
        d: dict = {"dot_damage_flat": float(dot_flat)}
        if dot_stat:
            d["dot_scaling_stat"] = dot_stat
            d["dot_multiplier"] = float(dot_mult)
        d["dot_damage_type"] = dot_type or "true_damage"
        return d
    return {}


# ===========================================================================
# ── T1 / T2 / T3 共用模板 ──────────────────────────────────────────────────
# ===========================================================================

def tpl_on_battle_start_buff(
    status_name: str = "戰鬥狀態",
    duration: int = 3,
    stat_bonuses: Optional[dict] = None,
    **_: Any
) -> dict:
    """戰鬥開始時，給自身附加增益狀態（整場戰鬥只觸發一次）。"""
    return {
        "event": "on_battle_start",
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"STR": 10}
        }]
    }


def tpl_on_battle_start_shield(
    flat_value: float = 20.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    **_: Any
) -> dict:
    """戰鬥開始時，給自身獲得護盾（整場戰鬥只觸發一次）。"""
    return {
        "event": "on_battle_start",
        "actions": [{
            "action_type": "gain_shield",
            "target": "caster",
            "flat_value": float(_clean(flat_value, 20.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }


def tpl_on_turn_start_buff(
    status_name: str = "鬥志",
    duration: int = 1,
    stat_bonuses: Optional[dict] = None,
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """每回合開始時，給自身附加增益狀態（必須設 cooldown）。"""
    t: dict = {
        "event": "on_turn_start",
        "cooldown": int(_clean(cooldown, 3)),
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"STR": 8}
        }]
    }
    return t


def tpl_on_turn_end_heal(
    flat_value: float = 10.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    target_resource: str = "hp",
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """每回合結束時，回復 HP/MP/Sanity（必須設 cooldown）。"""
    return {
        "event": "on_turn_end",
        "cooldown": int(_clean(cooldown, 3)),
        "actions": [{
            "action_type": "heal",
            "target": "caster",
            "flat_value": float(_clean(flat_value, 10.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
            "target_resource": target_resource or "hp"
        }]
    }


def tpl_on_damaged_shield(
    flat_value: float = 15.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    chance: Optional[float] = None,
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """受到傷害時，給自身獲得護盾。"""
    t: dict = {
        "event": "on_damaged",
        "actions": [{
            "action_type": "gain_shield",
            "target": "caster",
            "flat_value": float(_clean(flat_value, 15.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_damaged_buff(
    status_name: str = "痛定思痛",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    chance: Optional[float] = None,
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """受到傷害時，給自身附加增益狀態（逆境激發）。"""
    t: dict = {
        "event": "on_damaged",
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"p_def": 20, "tenacity": 15}
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_health_below_buff(
    status_name: str = "死鬥覺醒",
    duration: int = 3,
    stat_bonuses: Optional[dict] = None,
    hp_below: int = 30,
    **_: Any
) -> dict:
    """血量低於 X% 時，觸發自身增益（整場只觸發一次，cooldown: 99）。"""
    return {
        "event": "on_health_below",
        "hp_below": int(_clean(hp_below, 30)),
        "cooldown": 99,
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"STR": 20, "crit_rate": 0.20}
        }]
    }


def tpl_on_fatal_damage_buff(
    status_name: str = "不死之志",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    **_: Any
) -> dict:
    """受到致命傷害（本應致死）時，觸發強力增益（死鬥/不屈）。整場一次。"""
    return {
        "event": "on_fatal_damage",
        "cooldown": 99,
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"STR": 25, "crit_rate": 0.25, "evasion_rate": 0.15}
        }]
    }


# ===========================================================================
# ── T1 / T2 共用模板 ────────────────────────────────────────────────────────
# ===========================================================================

def tpl_on_hit_damage(
    flat_value: float = 20.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    dice: Optional[str] = None,
    chance: Optional[float] = 0.30,
    cooldown: Optional[int] = 2,
    target: str = "target",
    **_: Any
) -> dict:
    """擊中目標時，造成額外真實傷害。"""
    t: dict = {
        "event": "on_hit",
        "actions": [{
            "action_type": "inflict_damage",
            "target": target,
            "flat_value": float(_clean(flat_value, 20.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
            "dice": dice,
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_hit_damage_dot(
    flat_value: float = 15.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    debuff_name: str = "Burn",
    dot_flat: float = 10.0,
    dot_stat: Optional[str] = None,
    dot_mult: float = 0.0,
    dot_type: str = "true_damage",
    duration: int = 3,
    chance: Optional[float] = 0.35,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """擊中目標時，造成額外傷害並附加 DoT 狀態。"""
    debuff_name = debuff_name if debuff_name in DOT_DEBUFFS else "Burn"
    dot_action: dict = {
        "action_type": "apply_debuff",
        "target": "target",
        "debuff_name": debuff_name,
        "duration": int(duration),
    }
    dot_action.update(_dot_fields(debuff_name, dot_flat, dot_stat, dot_mult, dot_type))

    t: dict = {
        "event": "on_hit",
        "actions": [
            {
                "action_type": "inflict_damage",
                "target": "target",
                "flat_value": float(_clean(flat_value, 15.0)),
                "scaling_stat": scaling_stat,
                "value_multiplier": float(_clean(value_mult, 0.0)),
            },
            dot_action
        ]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_hit_debuff(
    debuff_name: str = "Slow",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    dot_flat: float = 0.0,
    dot_stat: Optional[str] = None,
    dot_mult: float = 0.0,
    dot_type: str = "true_damage",
    chance: Optional[float] = 0.30,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """擊中目標時，附加減益狀態。"""
    action: dict = {
        "action_type": "apply_debuff",
        "target": "target",
        "debuff_name": debuff_name,
        "duration": int(duration),
    }
    if stat_bonuses:
        action["stat_bonuses"] = stat_bonuses
    action.update(_dot_fields(debuff_name, dot_flat, dot_stat, dot_mult, dot_type))

    t: dict = {"event": "on_hit", "actions": [action]}
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_hit_drain(
    dmg_flat: float = 15.0,
    dmg_stat: Optional[str] = None,
    dmg_mult: float = 0.0,
    heal_flat: float = 10.0,
    heal_stat: Optional[str] = None,
    heal_mult: float = 0.0,
    chance: Optional[float] = 0.30,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """擊中目標時，對目標造成傷害並同時回復自身 HP（吸血）。"""
    t: dict = {
        "event": "on_hit",
        "actions": [
            {
                "action_type": "inflict_damage",
                "target": "target",
                "flat_value": float(_clean(dmg_flat, 15.0)),
                "scaling_stat": dmg_stat,
                "value_multiplier": float(_clean(dmg_mult, 0.0)),
            },
            {
                "action_type": "heal",
                "target": "caster",
                "flat_value": float(_clean(heal_flat, 10.0)),
                "scaling_stat": heal_stat,
                "value_multiplier": float(_clean(heal_mult, 0.0)),
                "target_resource": "hp"
            }
        ]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_crit_damage(
    flat_value: float = 25.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    target: str = "target",
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """觸發暴擊時，額外造成真實傷害。"""
    t: dict = {
        "event": "on_crit",
        "actions": [{
            "action_type": "inflict_damage",
            "target": target,
            "flat_value": float(_clean(flat_value, 25.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_crit_heal(
    flat_value: float = 15.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    target_resource: str = "hp",
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """觸發暴擊時，回復自身 HP（暴擊吸血）。"""
    t: dict = {
        "event": "on_crit",
        "actions": [{
            "action_type": "heal",
            "target": "caster",
            "flat_value": float(_clean(flat_value, 15.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
            "target_resource": target_resource or "hp"
        }]
    }
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_crit_debuff(
    debuff_name: str = "Sunder",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    dot_flat: float = 0.0,
    dot_stat: Optional[str] = None,
    dot_mult: float = 0.0,
    dot_type: str = "true_damage",
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """觸發暴擊時，對目標附加減益。"""
    action: dict = {
        "action_type": "apply_debuff",
        "target": "target",
        "debuff_name": debuff_name,
        "duration": int(duration),
    }
    if stat_bonuses:
        action["stat_bonuses"] = stat_bonuses
    action.update(_dot_fields(debuff_name, dot_flat, dot_stat, dot_mult, dot_type))

    t: dict = {"event": "on_crit", "actions": [action]}
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


# ===========================================================================
# ── T1 限定模板 ─────────────────────────────────────────────────────────────
# ===========================================================================

def tpl_on_hit_damage_buff(
    dmg_flat: float = 20.0,
    dmg_stat: Optional[str] = None,
    dmg_mult: float = 0.0,
    status_name: str = "戰鬥狂熱",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    chance: Optional[float] = 0.35,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """擊中目標時，造成傷害並同時提升自身屬性（攻擊連動增益）。T1 限定。"""
    t: dict = {
        "event": "on_hit",
        "actions": [
            {
                "action_type": "inflict_damage",
                "target": "target",
                "flat_value": float(_clean(dmg_flat, 20.0)),
                "scaling_stat": dmg_stat,
                "value_multiplier": float(_clean(dmg_mult, 0.0)),
            },
            {
                "action_type": "apply_status",
                "target": "caster",
                "status_name": status_name,
                "duration": int(duration),
                "stat_bonuses": stat_bonuses or {"STR": 10, "crit_rate": 0.10}
            }
        ]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_hit_aoe(
    flat_value: float = 15.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    chance: Optional[float] = 0.30,
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """擊中目標時，對所有敵人造成 AoE 真實傷害。T1 限定。"""
    t: dict = {
        "event": "on_hit",
        "actions": [{
            "action_type": "inflict_damage",
            "target": "all_enemies",
            "flat_value": float(_clean(flat_value, 15.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_kill_buff(
    status_name: str = "嗜血",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    **_: Any
) -> dict:
    """擊殺目標時，獲得嗜血增益狀態（無冷卻，擊殺才觸發）。T1 限定。"""
    return {
        "event": "on_kill",
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"STR": 20, "crit_rate": 0.20}
        }]
    }


def tpl_on_kill_aoe(
    flat_value: float = 20.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    **_: Any
) -> dict:
    """擊殺目標時，對所有剩餘敵人造成 AoE 傷害（斬殺爆炸）。T1 限定。"""
    return {
        "event": "on_kill",
        "actions": [{
            "action_type": "inflict_damage",
            "target": "all_enemies",
            "flat_value": float(_clean(flat_value, 20.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }


def tpl_on_dodge_buff(
    status_name: str = "幻影步法",
    duration: int = 1,
    stat_bonuses: Optional[dict] = None,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """成功閃避攻擊後，提升自身屬性（幻影之舞）。T1 限定。"""
    t: dict = {
        "event": "on_dodge",
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"DEX": 15, "evasion_rate": 0.15}
        }]
    }
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_miss_buff(
    status_name: str = "逆境之力",
    duration: int = 2,
    stat_bonuses: Optional[dict] = None,
    cooldown: Optional[int] = 3,
    **_: Any
) -> dict:
    """攻擊未命中時，反轉化為自身增益（逆境激發）。T1 限定。"""
    t: dict = {
        "event": "on_miss",
        "actions": [{
            "action_type": "apply_status",
            "target": "caster",
            "status_name": status_name,
            "duration": int(duration),
            "stat_bonuses": stat_bonuses or {"accuracy": 0.20, "crit_rate": 0.15}
        }]
    }
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_damaged_reflect(
    flat_value: float = 10.0,
    scaling_stat: Optional[str] = None,
    value_mult: float = 0.0,
    chance: Optional[float] = None,
    cooldown: Optional[int] = 2,
    **_: Any
) -> dict:
    """受到傷害時，反傷攻擊者（真實傷害）。T1 限定。"""
    t: dict = {
        "event": "on_damaged",
        "actions": [{
            "action_type": "inflict_damage",
            "target": "target",
            "flat_value": float(_clean(flat_value, 10.0)),
            "scaling_stat": scaling_stat,
            "value_multiplier": float(_clean(value_mult, 0.0)),
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


# ===========================================================================
# ── 新增/喚醒的高階趣味模板 ───────────────────────────────────────────────
# ===========================================================================

def tpl_on_dice_modify(
    param: str = "roll_modifier",
    param_value: int = 2,
    **_: Any
) -> dict:
    """進行任意擲骰檢定時，修改骰子結果（保底或加值）。"""
    param = param if param in ("floor_value", "roll_modifier") else "roll_modifier"
    return {
        "event": "on_dice",
        "actions": [{
            "action_type": "modify_dice",
            "param": param,
            "param_value": int(param_value)
        }]
    }


def tpl_on_dice_reroll(
    param_value: int = 2,
    **_: Any
) -> dict:
    """進行任意擲骰檢定時，當點數小於等於設定值時進行重骰。"""
    return {
        "event": "on_dice",
        "actions": [{
            "action_type": "modify_dice",
            "param": "reroll_threshold",
            "param_value": int(param_value)
        }]
    }


def tpl_on_calc_dmg_multiplier(
    param_value: float = 1.25,
    chance: Optional[float] = None,
    cooldown: Optional[int] = None,
    **_: Any
) -> dict:
    """進行傷害結算時，獲得傷害百分比增幅。"""
    t: dict = {
        "event": "on_calculate_damage",
        "actions": [{
            "action_type": "set_value",
            "param": "damage_multiplier",
            "param_value": float(param_value)
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_calc_ignore_defense(
    param_value: float = 0.30,
    chance: Optional[float] = None,
    cooldown: Optional[int] = None,
    **_: Any
) -> dict:
    """進行傷害結算時，無視目標防禦百分比（破甲）。"""
    t: dict = {
        "event": "on_calculate_damage",
        "actions": [{
            "action_type": "set_value",
            "param": "defense_ignore_ratio",
            "param_value": float(param_value)
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_calc_absolute_hit(
    chance: Optional[float] = None,
    cooldown: Optional[int] = None,
    **_: Any
) -> dict:
    """進行傷害計算或法術準備時，本次攻擊/法術絕對命中。"""
    t: dict = {
        "event": "on_calculate_damage",
        "actions": [{
            "action_type": "set_value",
            "param": "is_absolute_hit",
            "param_value": True
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_calc_guaranteed_crit(
    chance: Optional[float] = None,
    cooldown: Optional[int] = None,
    **_: Any
) -> dict:
    """進行傷害計算或法術準備時，本次攻擊/法術必定暴擊。"""
    t: dict = {
        "event": "on_calculate_damage",
        "actions": [{
            "action_type": "set_value",
            "param": "is_crit",
            "param_value": True
        }]
    }
    if chance is not None:
        t["chance"] = float(chance)
    if cooldown is not None:
        t["cooldown"] = int(cooldown)
    return t


def tpl_on_crit_time_warp(
    chance: float = 0.15,
    cooldown: int = 4,
    **_: Any
) -> dict:
    """觸發暴擊時，有机率獲得額外回合（時光回溯）。T1限定。"""
    return {
        "event": "on_crit",
        "chance": float(chance),
        "cooldown": int(cooldown),
        "actions": [{
            "action_type": "call_special_mechanic",
            "target": "caster",
            "keyword_name": "Time_Warp"
        }]
    }


def tpl_on_fatal_prevent_death(
    **_: Any
) -> dict:
    """受到致命傷害時，免除本次死亡並重置生命/魔法上限。T1限定。整場戰鬥一次。"""
    return {
        "event": "on_fatal_damage",
        "cooldown": 99,
        "actions": [{
            "action_type": "call_special_mechanic",
            "target": "caster",
            "keyword_name": "Prevent_Death"
        }]
    }


# ===========================================================================
# ── 模板目錄（Registry）────────────────────────────────────────────────────
# ===========================================================================

# 格式：{ template_id: (function, 可用 tiers, 中文說明, LLM 可填參數清單) }
TEMPLATE_REGISTRY: dict[str, tuple] = {
    # T1/T2/T3 共用
    "on_battle_start_buff": (
        tpl_on_battle_start_buff,
        {"T1", "T2", "T3"},
        "【戰鬥開始增益】整場戰鬥開始時，給自身附加屬性增益狀態（只觸發一次）",
        ["status_name", "duration", "stat_bonuses"]
    ),
    "on_battle_start_shield": (
        tpl_on_battle_start_shield,
        {"T1", "T2", "T3"},
        "【戰鬥開始護盾】整場戰鬥開始時，給自身獲得護盾（只觸發一次）",
        ["flat_value", "scaling_stat", "value_mult"]
    ),
    "on_turn_start_buff": (
        tpl_on_turn_start_buff,
        {"T1", "T2", "T3"},
        "【每回合增益】每回合開始時，給自身附加屬性增益狀態",
        ["status_name", "duration", "stat_bonuses", "cooldown"]
    ),
    "on_turn_end_heal": (
        tpl_on_turn_end_heal,
        {"T1", "T2", "T3"},
        "【每回合回復】每回合結束時，回復自身 HP/MP/Sanity",
        ["flat_value", "scaling_stat", "value_mult", "target_resource", "cooldown"]
    ),
    "on_damaged_shield": (
        tpl_on_damaged_shield,
        {"T1", "T2", "T3"},
        "【受傷護盾】受到傷害時，給自身獲得護盾",
        ["flat_value", "scaling_stat", "value_mult", "chance", "cooldown"]
    ),
    "on_damaged_buff": (
        tpl_on_damaged_buff,
        {"T1", "T2", "T3"},
        "【受傷激發】受到傷害時，給自身附加增益（逆境激發）",
        ["status_name", "duration", "stat_bonuses", "chance", "cooldown"]
    ),
    "on_health_below_buff": (
        tpl_on_health_below_buff,
        {"T1", "T2", "T3"},
        "【低血量覺醒】血量低於 X% 時，觸發強力增益（整場一次）",
        ["status_name", "duration", "stat_bonuses", "hp_below"]
    ),
    "on_fatal_damage_buff": (
        tpl_on_fatal_damage_buff,
        {"T1", "T2", "T3"},
        "【死鬥不屈】受到致命傷害時，獲得強力增益（整場一次）",
        ["status_name", "duration", "stat_bonuses"]
    ),
    # T1/T2 共用
    "on_hit_damage": (
        tpl_on_hit_damage,
        {"T1", "T2"},
        "【擊中傷害】擊中目標時，額外造成真實傷害",
        ["flat_value", "scaling_stat", "value_mult", "dice", "chance", "cooldown"]
    ),
    "on_hit_damage_dot": (
        tpl_on_hit_damage_dot,
        {"T1"},
        "【擊中傷害+DoT】擊中目標時，造成額外傷害並附加持續傷害狀態（Burn/Bleed/Frostbite/Poison）",
        ["flat_value", "scaling_stat", "value_mult", "debuff_name", "dot_flat", "dot_stat",
         "dot_mult", "dot_type", "duration", "chance", "cooldown"]
    ),
    "on_hit_debuff": (
        tpl_on_hit_debuff,
        {"T1", "T2"},
        "【擊中減益】擊中目標時，附加減益狀態（Slow/Stun/Sunder/Blind等）",
        ["debuff_name", "duration", "stat_bonuses", "dot_flat", "dot_stat", "dot_mult",
         "chance", "cooldown"]
    ),
    "on_hit_drain": (
        tpl_on_hit_drain,
        {"T1"},
        "【擊中吸血】擊中目標時，對目標造成傷害並回復自身 HP（吸血）",
        ["dmg_flat", "dmg_stat", "dmg_mult", "heal_flat", "heal_stat", "heal_mult",
         "chance", "cooldown"]
    ),
    "on_crit_damage": (
        tpl_on_crit_damage,
        {"T1", "T2"},
        "【暴擊傷害】觸發暴擊時，額外對目標造成真實傷害",
        ["flat_value", "scaling_stat", "value_mult", "cooldown"]
    ),
    "on_crit_heal": (
        tpl_on_crit_heal,
        {"T1", "T2"},
        "【暴擊吸血】觸發暴擊時，回復自身 HP（暴擊吸血）",
        ["flat_value", "scaling_stat", "value_mult", "target_resource", "cooldown"]
    ),
    "on_crit_debuff": (
        tpl_on_crit_debuff,
        {"T1", "T2"},
        "【暴擊減益】觸發暴擊時，對目標附加減益狀態",
        ["debuff_name", "duration", "stat_bonuses", "dot_flat", "dot_stat", "dot_mult",
         "cooldown"]
    ),
    # T1 限定
    "on_hit_damage_buff": (
        tpl_on_hit_damage_buff,
        {"T1"},
        "【擊中傷害+增益】擊中目標時，造成傷害並同時提升自身屬性（攻擊連動增益）",
        ["dmg_flat", "dmg_stat", "dmg_mult", "status_name", "duration", "stat_bonuses",
         "chance", "cooldown"]
    ),
    "on_hit_aoe": (
        tpl_on_hit_aoe,
        {"T1"},
        "【擊中 AoE】擊中目標時，對所有敵人造成 AoE 真實傷害",
        ["flat_value", "scaling_stat", "value_mult", "chance", "cooldown"]
    ),
    "on_kill_buff": (
        tpl_on_kill_buff,
        {"T1"},
        "【嗜血增益】擊殺目標時，獲得強力嗜血狀態",
        ["status_name", "duration", "stat_bonuses"]
    ),
    "on_kill_aoe": (
        tpl_on_kill_aoe,
        {"T1"},
        "【擊殺爆炸】擊殺目標時，對所有剩餘敵人造成 AoE 傷害（斬殺爆炸）",
        ["flat_value", "scaling_stat", "value_mult"]
    ),
    "on_dodge_buff": (
        tpl_on_dodge_buff,
        {"T1"},
        "【閃避增益】成功閃避後，提升自身屬性（幻影之舞）",
        ["status_name", "duration", "stat_bonuses", "cooldown"]
    ),
    "on_miss_buff": (
        tpl_on_miss_buff,
        {"T1"},
        "【逆境增益】攻擊未命中時，轉化為自身強力增益",
        ["status_name", "duration", "stat_bonuses", "cooldown"]
    ),
    "on_damaged_reflect": (
        tpl_on_damaged_reflect,
        {"T1"},
        "【反傷】受到傷害時，對攻擊者反射真實傷害",
        ["flat_value", "scaling_stat", "value_mult", "chance", "cooldown"]
    ),
    # T1/T2 共用 (新增高階趣味詞條)
    "on_dice_modify": (
        tpl_on_dice_modify,
        {"T1", "T2"},
        "【擲骰修飾】進行任意擲骰檢定時，為骰子點數加值或提供保底",
        ["param", "param_value"]
    ),
    "on_dice_reroll": (
        tpl_on_dice_reroll,
        {"T1", "T2"},
        "【擲骰重骰】進行任意擲骰檢定時，若骰子結果小於等於設定值則自動重骰",
        ["param_value"]
    ),
    "on_calc_dmg_multiplier": (
        tpl_on_calc_dmg_multiplier,
        {"T1", "T2"},
        "【傷害增幅】進行傷害結算時，本次傷害獲得額外百分比增幅（如 1.25 倍）",
        ["param_value", "chance", "cooldown"]
    ),
    "on_calc_ignore_defense": (
        tpl_on_calc_ignore_defense,
        {"T1", "T2"},
        "【無視防禦】進行傷害結算時，無視目標防禦力百分比（破甲效果，如 0.30 無視 30%）",
        ["param_value", "chance", "cooldown"]
    ),
    "on_calc_absolute_hit": (
        tpl_on_calc_absolute_hit,
        {"T1", "T2"},
        "【絕對命中】進行傷害結算時，本次攻擊或法術必定命中（無視閃避）",
        ["chance", "cooldown"]
    ),
    "on_calc_guaranteed_crit": (
        tpl_on_calc_guaranteed_crit,
        {"T1", "T2"},
        "【必定暴擊】進行傷害結算時，本次攻擊或法術必定觸發暴擊",
        ["chance", "cooldown"]
    ),
    # T1 限定 (神級詞條)
    "on_crit_time_warp": (
        tpl_on_crit_time_warp,
        {"T1"},
        "【時光回溯】觸發暴擊時，有机率獲得額外回合並回溯生命/魔法",
        ["chance", "cooldown"]
    ),
    "on_fatal_prevent_death": (
        tpl_on_fatal_prevent_death,
        {"T1"},
        "【免死保護】受到致命傷害時免除死亡，重置生命魔法，整場限一次",
        []
    ),
}


def get_templates_for_tier(tier: str) -> dict[str, tuple]:
    """
    回傳指定 tier 可用的模板字典。
    key = template_id, value = (fn, tiers, description, params)
    """
    return {
        tid: entry
        for tid, entry in TEMPLATE_REGISTRY.items()
        if tier in entry[1]
    }


def build_template_menu(tier: str) -> str:
    """
    為 LLM prompt 生成可用模板的清單字串（只顯示 tier 可用的模板）。
    """
    templates = get_templates_for_tier(tier)
    lines = [f"【{tier} 可用觸發器模板清單】"]
    for tid, (_, _, desc, params) in templates.items():
        param_str = ", ".join(params)
        lines.append(f"  - {tid}: {desc}")
        lines.append(f"    可填參數: {param_str}")
    return "\n".join(lines)


def assemble_trigger(template_id: str, params: dict) -> Optional[dict]:
    """
    根據 template_id 和 LLM 填入的參數，組裝並回傳完整的 flat trigger dict。
    若模板不存在則回傳 None。
    """
    entry = TEMPLATE_REGISTRY.get(template_id)
    if entry is None:
        return None
    fn = entry[0]
    try:
        return fn(**params)
    except Exception as e:
        # 防呆：若參數有問題，用預設值跑一次
        try:
            return fn()
        except Exception:
            return None
