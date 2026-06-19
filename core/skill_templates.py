# core/skill_templates.py
"""
技能模板庫（Skill Template Library）

設計原則：
  - 技能是主動施放的（Active-Cast），沒有被動事件（event）。
  - 每個模板函式回傳一個 actions 列表，代表該機制產生的具體 Action Payload。
  - 支援 T1 傳說專屬模板與 T2/T3 共用模板。
"""

from typing import Any, Optional, List, Dict

# ===========================================================================
# ── 輔育函式 ───────────────────────────────────────────────────────────────
# ===========================================================================
def _clean(val: Any, default: Any) -> Any:
    return val if val is not None else default


# ===========================================================================
# ── 標準/共用技能模板 ────────────────────────────────────────────────────────
# ===========================================================================

def tpl_active_vampiric_strike(**_: Any) -> List[Dict[str, Any]]:
    """造成傷害並依比例 (30%) 吸血。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Lifesteal", "target": "caster"}]


def tpl_active_conditional_detonate(
    status_name: str = "Burn",
    flat_value: float = 30.0,
    **_: Any
) -> List[Dict[str, Any]]:
    """條件引爆：若目標有特定狀態，則引發額外效果/傷害。"""
    return [{
        "action_type": "call_special_mechanic",
        "keyword_name": "Detonate",
        "target": "target",
        "status_name": status_name,
        "flat_value": float(_clean(flat_value, 30.0))
    }]


def tpl_active_sacrifice(
    hp_sacrifice_ratio: float = 0.20,
    **_: Any
) -> List[Dict[str, Any]]:
    """血契犧牲：消耗自身當前 HP，換取額外威力加成。"""
    return [{
        "action_type": "call_special_mechanic",
        "keyword_name": "Sacrifice",
        "target": "caster",
        "hp_sacrifice_ratio": float(_clean(hp_sacrifice_ratio, 0.20))
    }]


def tpl_active_shield(
    flat_value: float = 20.0,
    duration: int = 3,
    **_: Any
) -> List[Dict[str, Any]]:
    """使目標獲得護盾。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Shield",
        "duration": int(_clean(duration, 3)),
        "flat_value": float(_clean(flat_value, 20.0))
    }]


def tpl_active_stun(duration: int = 1, **_: Any) -> List[Dict[str, Any]]:
    """施加暈眩狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Stun", "duration": int(_clean(duration, 1))}]


def tpl_active_silence(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加沉默狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Silence", "duration": int(_clean(duration, 2))}]


def tpl_active_root(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加定身狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Root", "duration": int(_clean(duration, 2))}]


def tpl_active_slow(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """施加減速狀態（閃避率直接歸零）。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Slow",
        "duration": int(_clean(duration, 3)),
        "stat_bonuses": {"DEX": -99}
    }]


def tpl_active_burn(duration: int = 3, dot_damage_flat: float = 15.0, **_: Any) -> List[Dict[str, Any]]:
    """施加灼燒 DoT。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Burn",
        "duration": int(_clean(duration, 3)),
        "dot_damage_flat": float(_clean(dot_damage_flat, 15.0)),
        "dot_damage_type": "true_damage"
    }]


def tpl_active_frostbite(duration: int = 3, dot_damage_flat: float = 8.0, **_: Any) -> List[Dict[str, Any]]:
    """施加凍傷 DoT。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Frostbite",
        "duration": int(_clean(duration, 3)),
        "dot_damage_flat": float(_clean(dot_damage_flat, 8.0)),
        "dot_damage_type": "true_damage"
    }]


def tpl_active_blind(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加盲目狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Blind", "duration": int(_clean(duration, 2))}]


def tpl_active_doom(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """施加厄運宣告，倒數即死。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Doom", "duration": int(_clean(duration, 3))}]


def tpl_active_charm(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加魅惑狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Charm", "duration": int(_clean(duration, 2))}]


def tpl_active_confusion(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加混亂狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Confusion", "duration": int(_clean(duration, 2))}]


def tpl_active_immune(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """使目標獲得負面狀態免疫。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Immune", "duration": int(_clean(duration, 2))}]


def tpl_active_invis(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """使目標進入隱身狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Invis", "duration": int(_clean(duration, 3))}]


def tpl_active_levitate(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """使目標進入浮空狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Levitate", "duration": int(_clean(duration, 3))}]


def tpl_active_counter_stance(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """使目標進入反擊架勢。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Counter_Stance", "duration": int(_clean(duration, 2))}]


def tpl_active_bless(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """使目標獲得祝福。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Bless", "duration": int(_clean(duration, 3))}]


def tpl_active_reflect(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """使目標獲得傷害反射盾。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Reflect", "duration": int(_clean(duration, 2))}]


def tpl_active_taunt(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """使目標陷入嘲諷狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Taunt", "duration": int(_clean(duration, 2))}]


def tpl_active_purge(**_: Any) -> List[Dict[str, Any]]:
    """清除目標身上的所有可淨化負面狀態。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Purge", "target": "target"}]


def tpl_active_sunder(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """破甲：使目標物理防禦降低 30%。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Sunder",
        "duration": int(_clean(duration, 3)),
        "stat_bonuses": {"p_def": -0.30}
    }]


def tpl_active_pierce(**_: Any) -> List[Dict[str, Any]]:
    """穿透：無視目標 50% 防禦力。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Pierce", "target": "target"}]


def tpl_active_execute(**_: Any) -> List[Dict[str, Any]]:
    """處決：若目標血量低於 20%，傷害提升為 3 倍。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Execute", "target": "target"}]


def tpl_active_wall_break(**_: Any) -> List[Dict[str, Any]]:
    """碎垣：擊碎目標的護盾與臨時生命。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Wall_Break", "target": "target"}]


def tpl_active_martyr(**_: Any) -> List[Dict[str, Any]]:
    """殉道：生命值歸零，傷害乘以 3 倍。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Martyr", "target": "caster"}]


def tpl_active_overload(**_: Any) -> List[Dict[str, Any]]:
    """超載：威力加成 50%，但施加超載鎖定 (下一回合技能 MP 消耗翻倍)。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Overload", "target": "caster"}]


def tpl_active_quickcast(**_: Any) -> List[Dict[str, Any]]:
    """瞬發：不扣除玩家行動點數，允許連續發動。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Quickcast", "target": "caster"}]


def tpl_active_gamble(**_: Any) -> List[Dict[str, Any]]:
    """豪賭：50% 機率傷害乘以 3 倍，50% 機率無效且自身承受等量傷害。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Gamble", "target": "caster"}]


def tpl_active_steal(**_: Any) -> List[Dict[str, Any]]:
    """竊取：竊取目標 10-30 金幣。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Steal", "target": "target"}]


def tpl_active_vampiric_aura(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """吸血光環：使自身獲得吸血光環。"""
    return [{"action_type": "apply_status", "target": "caster", "status_name": "Vampiric_Aura", "duration": int(_clean(duration, 3))}]


def tpl_active_soul_link(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """靈魂連結：施法者與目標靈魂連結。"""
    return [
        {"action_type": "apply_status", "target": "caster", "status_name": "Soul_Link", "duration": int(_clean(duration, 3))},
        {"action_type": "apply_status", "target": "target", "status_name": "Soul_Link", "duration": int(_clean(duration, 3))}
    ]


def tpl_active_chain(**_: Any) -> List[Dict[str, Any]]:
    """連鎖：連鎖彈跳至下一個存活敵方目標（傷害減半）。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Chain", "target": "target"}]


def tpl_active_summon(**_: Any) -> List[Dict[str, Any]]:
    """召喚：在戰鬥序列中召喚一個隨從。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Summon", "target": "caster"}]


def tpl_active_resurrect(**_: Any) -> List[Dict[str, Any]]:
    """復甦：復活倒下的盟友。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Resurrect", "target": "target"}]


def tpl_active_rampage(**_: Any) -> List[Dict[str, Any]]:
    """殺戮盛宴：擊殺目標時獲得額外行動回合。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Rampage", "target": "caster"}]


def tpl_active_greed(**_: Any) -> List[Dict[str, Any]]:
    """貪婪：若殺死目標，金幣掉落乘以 2~3 倍。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Greed", "target": "target"}]


def tpl_active_adapt(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """適應：獲得對目標屬性的防禦抗性。"""
    return [{"action_type": "apply_status", "target": "caster", "status_name": "Adapt", "duration": int(_clean(duration, 3))}]


def tpl_active_echo(**_: Any) -> List[Dict[str, Any]]:
    """殘響：下回合自動重施此技能（50% 威力）。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Echo", "target": "caster"}]


def tpl_active_berserk(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """狂暴：大幅提升傷害但無法手動操作。"""
    return [{"action_type": "apply_status", "target": "caster", "status_name": "Berserk", "duration": int(_clean(duration, 3)), "stat_bonuses": {"skill_power": 0.5}}]


def tpl_active_banish(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """施加放逐狀態，免疫所有傷害且無法行動。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Banish", "duration": int(_clean(duration, 2))}]


# ===========================================================================
# ── T1 傳說技能模板 ──────────────────────────────────────────────────────────
# ===========================================================================

def tpl_active_epoch_break(**_: Any) -> List[Dict[str, Any]]:
    """時代終結：抹殺目標所有增益狀態與護盾，且本次傷害無視減免。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Epoch_Break", "target": "target"}]


def tpl_active_time_warp(**_: Any) -> List[Dict[str, Any]]:
    """時光回溯：將施法者的生命與魔法還原至上回合快照。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Time_Warp", "target": "caster"}]


def tpl_active_blood_pact(hp_sacrifice_ratio: float = 0.20, **_: Any) -> List[Dict[str, Any]]:
    """血誓契約：消耗 20% HP，獲得基於已損失生命值比例的巨額增傷。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Blood_Pact", "target": "caster", "hp_sacrifice_ratio": float(_clean(hp_sacrifice_ratio, 0.20))}]


def tpl_active_devil_roll(**_: Any) -> List[Dict[str, Any]]:
    """惡魔賭局：隨機觸發反噬、強化（傷害 ×1.5 + 隨機 debuff）或傳說爆發（傷害 ×3 + 全體）。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Devil's_Roll", "target": "caster"}]


def tpl_active_last_rites(**_: Any) -> List[Dict[str, Any]]:
    """終焉禮讚：目標血量充盈則傷害加倍，若衰竭則將厄運擴散至所有敵人。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Last_Rites", "target": "target"}]


def tpl_active_resonance_break(**_: Any) -> List[Dict[str, Any]]:
    """共鳴破碎：根據目標身上的負面狀態數量，每個增加 15% 傷害。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Resonance_Break", "target": "target"}]


def tpl_active_annihilate(**_: Any) -> List[Dict[str, Any]]:
    """虛滅：清除目標護盾並無視防禦封頂限制。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Annihilate", "target": "target"}]


def tpl_active_paradox(**_: Any) -> List[Dict[str, Any]]:
    """矛盾法則：將目標的防禦力數值轉化為額外真實傷害。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Paradox", "target": "target"}]


def tpl_active_doom_seal(**_: Any) -> List[Dict[str, Any]]:
    """厄印強化：施加不可驅散的死亡倒數，2 回合後必死。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Doom_Seal", "target": "target"}]


def tpl_active_void_rift(**_: Any) -> List[Dict[str, Any]]:
    """虛空裂隙：目標每次受傷時，施法者承受其 25% 的反噬傷害。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Void_Rift", "target": "target"}]


def tpl_active_eternal_wound(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """永恆創傷：封印目標的治療與生命恢復。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Eternal_Wound", "target": "target", "duration": int(_clean(duration, 3))}]


def tpl_active_abyssal_mark(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """深淵印記：使目標受到的所有來源傷害增加 40%。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Abyssal_Mark", "target": "target", "duration": int(_clean(duration, 2))}]


def tpl_active_fate_seal(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """命運封印：記錄當前生命，3 回合後強制還原。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Fate_Seal", "target": "target", "duration": int(_clean(duration, 3))}]


def tpl_active_soul_drain(**_: Any) -> List[Dict[str, Any]]:
    """靈魂汲取：竊取目標 20% 傷害的 MP 並回復自身等量生命值。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Soul_Drain", "target": "target"}]


def tpl_active_soul_shatter(**_: Any) -> List[Dict[str, Any]]:
    """靈魂粉碎：若此技能擊殺目標，則眩暈所有敵人並恢復施法者 50 點 SAN 值。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Soul_Shatter", "target": "target"}]


def tpl_active_copy(**_: Any) -> List[Dict[str, Any]]:
    """鏡像：複製上一個施放的技能。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Copy", "target": "caster"}]


def tpl_active_multi_hit(**_: Any) -> List[Dict[str, Any]]:
    """多重打擊：將總傷害拆分為 3-5 次連續打擊。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Multi-hit", "target": "target"}]


def tpl_active_focus(**_: Any) -> List[Dict[str, Any]]:
    """專注：下一擊必爆擊，持續 1 次擊中。"""
    return [{"action_type": "apply_status", "target": "caster", "status_name": "Focus", "duration": 1}]


def tpl_active_siphon(stat: str = "STR", steal_percent: float = 0.20, duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """屬性汲取：降低目標特定屬性並將等量屬性轉移給施法者。"""
    return [{
        "action_type": "call_special_mechanic",
        "keyword_name": "Siphon",
        "target": "target",
        "stat": str(_clean(stat, "STR")),
        "steal_percent": float(_clean(steal_percent, 0.20)),
        "duration": int(_clean(duration, 3))
    }]


def tpl_active_bleed(duration: int = 3, potency_percent: float = 15.0, **_: Any) -> List[Dict[str, Any]]:
    """流血：施加物理 DoT，且使目標受到的所有治療與吸血減半。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Bleed",
        "duration": int(_clean(duration, 3)),
        "dot_damage_flat": float(_clean(potency_percent, 15.0)),
        "dot_damage_type": "physical"
    }]


def tpl_active_ward(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """魔防護盾：抵消下一次受到的負面狀態。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Ward", "duration": int(_clean(duration, 3))}]


def tpl_active_desperation(hp_threshold: float = 30.0, dmg_bonus: float = 50.0, lifesteal_percent: float = 30.0, duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """絕境怒火：生命值低於指定比例時獲得增傷與吸血。"""
    return [{
        "action_type": "apply_status",
        "target": "target",
        "status_name": "Desperation",
        "duration": int(_clean(duration, 3)),
        "hp_threshold": float(_clean(hp_threshold, 30.0)),
        "dmg_bonus": float(_clean(dmg_bonus, 50.0)),
        "lifesteal_percent": float(_clean(lifesteal_percent, 30.0))
    }]


def tpl_active_fade(duration: int = 2, **_: Any) -> List[Dict[str, Any]]:
    """仇恨消退：移除自身嘲諷並使其無法被單體技能選中。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Fade", "target": "caster", "duration": int(_clean(duration, 2))}]


def tpl_active_phoenix_rebirth(duration: int = 3, **_: Any) -> List[Dict[str, Any]]:
    """涅槃重燃：死亡後復活，恢復 50% HP/MP。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Phoenix_Rebirth", "duration": int(_clean(duration, 3))}]


def tpl_active_fate_swap(**_: Any) -> List[Dict[str, Any]]:
    """因果互換：交換雙方生命百分比。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Fate_Swap", "target": "target"}]


def tpl_active_mind_control(duration: int = 1, **_: Any) -> List[Dict[str, Any]]:
    """心靈傀儡：強制目標下次攻擊打友方。"""
    return [{"action_type": "apply_status", "target": "target", "status_name": "Mind_Control", "duration": int(_clean(duration, 1))}]


def tpl_active_apocalypse(**_: Any) -> List[Dict[str, Any]]:
    """天劫降臨：延遲 2 回合，全體真實傷害 + 沉默。"""
    return [{"action_type": "call_special_mechanic", "keyword_name": "Apocalypse", "target": "target"}]


def tpl_active_stance_defensive(duration: int = 99, **_: Any) -> List[Dict[str, Any]]:
    """防守姿態：物理防禦提升 30%，但速度敏捷降低 5 點。"""
    return [{
        "action_type": "apply_status",
        "target": "caster",
        "status_name": "Stance_Defensive",
        "duration": int(_clean(duration, 99)),
        "stat_bonuses": {"p_def": 0.30, "DEX": -5}
    }]


def tpl_active_stance_berserk(duration: int = 99, **_: Any) -> List[Dict[str, Any]]:
    """狂暴姿態：技能威力提升 30%，但物理防禦降低 20%。"""
    return [{
        "action_type": "apply_status",
        "target": "caster",
        "status_name": "Stance_Berserk",
        "duration": int(_clean(duration, 99)),
        "stat_bonuses": {"skill_power": 0.30, "p_def": -0.20}
    }]



# ===========================================================================
# ── 模板註冊與目錄 ──────────────────────────────────────────────────────────
# ===========================================================================

# 格式：{ template_id: (function, 可用 tiers, 中文說明, LLM 可填參數清單) }
TEMPLATE_REGISTRY: Dict[str, tuple] = {
    # T2/T3 可用
    "active_vampiric_strike": (tpl_active_vampiric_strike, {"T1", "T2", "T3"}, "【吸血打擊】造成傷害的 30% 轉化為自身生命回復", []),
    "active_lifesteal": (tpl_active_vampiric_strike, {"T1", "T2", "T3"}, "【吸血打擊】造成傷害的 30% 轉化為自身生命回復", []),
    "active_conditional_detonate": (tpl_active_conditional_detonate, {"T1", "T2", "T3"}, "【條件引爆】若目標有特定狀態（如 Burn），則引爆額外傷害", ["status_name", "flat_value"]),
    "active_sacrifice": (tpl_active_sacrifice, {"T1", "T2", "T3"}, "【血契犧牲】扣除自身 20% HP，將缺失血量轉為技能威力加成", ["hp_sacrifice_ratio"]),
    "active_shield": (tpl_active_shield, {"T1", "T2", "T3"}, "【聖盾保護】使目標獲得吸收傷害的護盾", ["flat_value", "duration"]),
    "active_stun": (tpl_active_stun, {"T1", "T2", "T3"}, "【震懾眩暈】使目標眩暈 1 回合，無法行動", ["duration"], {"cost_modifier": 10}),
    "active_silence": (tpl_active_silence, {"T1", "T2", "T3"}, "【法術封印】使目標陷入沉默狀態 2 回合，無法使用魔法技能", ["duration"], {"cost_modifier": 10}),
    "active_root": (tpl_active_root, {"T1", "T2", "T3"}, "【荊棘定身】使目標定身 2 回合，無法使用物理近戰技能", ["duration"], {"cost_modifier": 10}),
    "active_slow": (tpl_active_slow, {"T1", "T2", "T3"}, "【寒冰減速】使目標閃避率歸零，且出手順序墊底", ["duration"]),
    "active_burn": (tpl_active_burn, {"T1", "T2", "T3"}, "【火焰灼燒】施加灼燒 DoT，每回合造成 15 點真實傷害", ["duration", "dot_damage_flat"]),
    "active_frostbite": (tpl_active_frostbite, {"T1", "T2", "T3"}, "【寒霜凍傷】施加凍傷 DoT，每回合造成 8 點真實傷害", ["duration", "dot_damage_flat"]),
    "active_blind": (tpl_active_blind, {"T1", "T2", "T3"}, "【致盲迷霧】使目標陷入盲目狀態，降低 50% 命中率", ["duration"]),
    "active_doom": (tpl_active_doom, {"T1", "T2", "T3"}, "【厄運宣告】施加死亡倒數，3 回合後結算", ["duration"]),
    "active_charm": (tpl_active_charm, {"T1", "T2", "T3"}, "【魅惑之音】使目標陷入魅惑狀態，反轉目標隨機攻擊隊友", ["duration"]),
    "active_confusion": (tpl_active_confusion, {"T1", "T2", "T3"}, "【思緒混亂】使目標陷入混亂狀態，行動有 50% 機率取消", ["duration"]),
    "active_immune": (tpl_active_immune, {"T1", "T2", "T3"}, "【不滅霸體】獲得負面狀態免疫，持續 2 回合", ["duration"]),
    "active_invis": (tpl_active_invis, {"T1", "T2", "T3"}, "【暗影隱身】進入隱身狀態，極難被單體選中", ["duration"]),
    "active_levitate": (tpl_active_levitate, {"T1", "T2", "T3"}, "【重力浮空】使目標浮空，持續 3 回合", ["duration"]),
    "active_counter_stance": (tpl_active_counter_stance, {"T1", "T2", "T3"}, "【反擊姿態】進入反擊架勢，受物理攻擊時反擊", ["duration"]),
    "active_bless": (tpl_active_bless, {"T1", "T2", "T3"}, "【命運祝福】獲得祝福，擲骰點數 <= 5 時補底為 10", ["duration"]),
    "active_reflect": (tpl_active_reflect, {"T1", "T2", "T3"}, "【鏡面反射】受傷害減半且向攻擊者反彈 50% 傷害", ["duration"]),
    "active_taunt": (tpl_active_taunt, {"T1", "T2", "T3"}, "【野性嘲諷】嘲諷目標，強制其單體攻擊指向施法者", ["duration"]),
    "active_purge": (tpl_active_purge, {"T1", "T2", "T3"}, "【神聖淨化】清除目標身上的所有可驅散負面狀態", []),
    "active_copy": (tpl_active_copy, {"T1", "T2", "T3"}, "【鏡像】複製上一個施放的技能", []),
    "active_multi_hit": (tpl_active_multi_hit, {"T1", "T2", "T3"}, "【多重打擊】將傷害拆分為多段結算", []),
    "active_multihit": (tpl_active_multi_hit, {"T1", "T2", "T3"}, "【多重打擊】將傷害拆分為多段結算", []),
    "active_sunder": (tpl_active_sunder, {"T1", "T2", "T3"}, "【護甲粉碎】破甲，降低目標 30% 物理防禦", ["duration"]),
    "active_pierce": (tpl_active_pierce, {"T1", "T2", "T3"}, "【防線穿透】穿透，無視目標 50% 防禦力", []),
    "active_execute": (tpl_active_execute, {"T1", "T2", "T3"}, "【無情處決】若目標血量低於 20%，傷害提升為 3 倍", []),
    "active_wall_break": (tpl_active_wall_break, {"T1", "T2", "T3"}, "【護盾崩潰】破盾，擊碎目標臨時生命與護盾", []),
    "active_overload": (tpl_active_overload, {"T1", "T2", "T3"}, "【魔力超載】提升 50% 傷害，但下回合施展法術消耗翻倍", []),
    "active_quickcast": (tpl_active_quickcast, {"T1", "T2", "T3"}, "【法術瞬發】不消耗行動點，允許連續施展技能", []),
    "active_gamble": (tpl_active_gamble, {"T1", "T2", "T3"}, "【命運豪賭】50% 機率傷害乘以 3，50% 反噬自身等量傷害", []),
    "active_steal": (tpl_active_steal, {"T1", "T2", "T3"}, "【妙手空空】竊取目標 10-30 金幣", []),
    "active_vampiric_aura": (tpl_active_vampiric_aura, {"T1", "T2", "T3"}, "【吸血光環】施放吸血光環，使周圍盟友獲得吸血能力", ["duration"]),
    "active_soul_link": (tpl_active_soul_link, {"T1", "T2", "T3"}, "【靈魂絲線】將施法者與目標靈魂連結，共享生命波動", ["duration"]),
    "active_chain": (tpl_active_chain, {"T1", "T2", "T3"}, "【雷霆連鎖】雷電彈跳連鎖，尋找下一個存活敵人", []),
    "active_summon": (tpl_active_summon, {"T1", "T2", "T3"}, "【使魔召喚】在戰鬥序列中召喚一個戰鬥單位", []),
    "active_resurrect": (tpl_active_resurrect, {"T1", "T2", "T3"}, "【起死回生】復活已經倒下的盟友", []),
    "active_rampage": (tpl_active_rampage, {"T1", "T2", "T3"}, "【殺戮盛宴】若此技能擊殺目標，則獲得額外回合", []),
    "active_greed": (tpl_active_greed, {"T1", "T2", "T3"}, "【貪婪之證】若此技能擊殺目標，獲得金幣倍增", []),
    "active_adapt": (tpl_active_adapt, {"T1", "T2", "T3"}, "【適應抗性】獲得對目標屬性的防禦抗性", ["duration"]),
    "active_echo": (tpl_active_echo, {"T1", "T2", "T3"}, "【殘響重奏】下回合自動重施此技能（50% 威力）", []),
    "active_berserk": (tpl_active_berserk, {"T1", "T2", "T3"}, "【狂野暴怒】傷害提升但陷入無法手動的隨機狂暴狀態", ["duration"]),
    "active_banish": (tpl_active_banish, {"T1", "T2", "T3"}, "【虛空放逐】放逐目標，免疫所有傷害且無法行動", ["duration"]),

    # T1 專屬傳說級
    "active_epoch_break": (tpl_active_epoch_break, {"T1"}, "【時代終結】抹殺目標所有增益狀態與護盾，本次傷害無視減免", []),
    "active_time_warp": (tpl_active_time_warp, {"T1"}, "【時光回溯】將施法者的生命與魔法還原至上一回合", []),
    "active_blood_pact": (tpl_active_blood_pact, {"T1"}, "【血誓契約】消耗自身 20% HP，基於缺失 HP 比例巨額增傷", ["hp_sacrifice_ratio"]),
    "active_devil_roll": (tpl_active_devil_roll, {"T1"}, "【惡魔骰局】隨機觸發反噬、強化增傷或全體傳說爆發", []),
    "active_devils_roll": (tpl_active_devil_roll, {"T1"}, "【惡魔骰局】隨機觸發反噬、強化增傷或全體傳說爆發", []),
    "active_last_rites": (tpl_active_last_rites, {"T1"}, "【終焉禮讚】對充盈目標傷害加倍，對衰竭目標則將厄運擴散", []),
    "active_resonance_break": (tpl_active_resonance_break, {"T1"}, "【共鳴破碎】根據目標負面狀態數量爆發巨額傷害", []),
    "active_annihilate": (tpl_active_annihilate, {"T1"}, "【虛滅降臨】徹底抹除護盾並無視防禦封頂限制", []),
    "active_paradox": (tpl_active_paradox, {"T1"}, "【矛盾法則】將目標防禦力直接轉化為額外真實傷害", []),
    "active_doom_seal": (tpl_active_doom_seal, {"T1"}, "【厄印強化】施加無法驅散的死亡倒數，2 回合後結算必死", []),
    "active_void_rift": (tpl_active_void_rift, {"T1"}, "【虛空裂隙】建立裂隙，目標受傷時施法者承受 25% 反噬", []),
    "active_eternal_wound": (tpl_active_eternal_wound, {"T1"}, "【永恆創傷】封印目標所有治療與回復效果", ["duration"]),
    "active_abyssal_mark": (tpl_active_abyssal_mark, {"T1"}, "【深淵印記】烙印深淵，目標承受所有來源傷害增加 40%", ["duration"]),
    "active_fate_seal": (tpl_active_fate_seal, {"T1"}, "【命運封印】封鎖生命，3 回合後目標 HP 強制還原至此刻", ["duration"]),
    "active_soul_drain": (tpl_active_soul_drain, {"T1"}, "【靈魂汲取】汲取目標 MP 轉化為自身生命", []),
    "active_soul_shatter": (tpl_active_soul_shatter, {"T1"}, "【靈魂粉碎】擊殺時使全體敵人眩暈且施法者回復 50 SAN", []),
    
    # [新增標準模板]
    "active_focus": (tpl_active_focus, {"T1", "T2", "T3", "T4", "T5"}, "【專注】下一擊必定爆擊", []),
    "active_siphon": (tpl_active_siphon, {"T1", "T2", "T3"}, "【屬性汲取】降低目標特定屬性並轉移等量屬性給施法者", ["stat", "steal_percent", "duration"]),
    "active_bleed": (tpl_active_bleed, {"T1", "T2", "T3", "T4", "T5"}, "【撕裂流血】物理持續傷害，且使目標受到的所有治療與吸血效果減半", ["duration", "potency_percent"]),
    "active_ward": (tpl_active_ward, {"T1", "T2", "T3"}, "【魔防護盾】獲得魔防護盾，抵消下一次受到的負面狀態", ["duration"]),
    "active_desperation": (tpl_active_desperation, {"T1", "T2", "T3"}, "【絕境怒火】生命值低於指定比例時，傷害增加且獲得吸血", ["hp_threshold", "dmg_bonus", "lifesteal_percent", "duration"]),
    "active_fade": (tpl_active_fade, {"T1", "T2", "T3", "T4", "T5"}, "【仇恨消退】移除自身嘲諷狀態，並使其進入隱身狀態", ["duration"]),
    "active_stance_defensive": (tpl_active_stance_defensive, {"T1", "T2", "T3"}, "【防守姿態】提升 30% 物理防禦，但降低 5 點敏捷", ["duration"]),
    "active_stance_berserk": (tpl_active_stance_berserk, {"T1", "T2", "T3"}, "【狂暴姿態】提升 30% 技能威力，但降低 20% 物理防禦", ["duration"]),
    
    # [新增傳說模板]
    "active_phoenix_rebirth": (tpl_active_phoenix_rebirth, {"T1"}, "【涅槃重燃】死亡後復活，恢復 50% HP/MP", ["duration"]),
    "active_fate_swap": (tpl_active_fate_swap, {"T1"}, "【因果互換】互換施法者與目標的生命值百分比", []),
    "active_mind_control": (tpl_active_mind_control, {"T1"}, "【心靈傀儡】控制目標，強制其下一次攻擊隨機指向另一個怪物盟友", ["duration"]),
    "active_apocalypse": (tpl_active_apocalypse, {"T1"}, "【天劫降臨】延遲 2 回合後，對全體敵人造成大量真實傷害並施加沉默", []),
}


def get_templates_for_tier(tier: str) -> dict:
    """回傳指定 tier 可用的技能模板字典。"""
    return {
        tid: entry
        for tid, entry in TEMPLATE_REGISTRY.items()
        if tier in entry[1]
    }


def get_template_metadata(tid: str) -> dict:
    """取得指定模板的元數據（Metadata），若無則回傳空字典。"""
    entry = TEMPLATE_REGISTRY.get(tid)
    if entry and len(entry) > 4:
        return entry[4]
    return {}


def build_template_menu(tier: str) -> str:
    """為 LLM prompt 生成可用技能模板的清單字串（只顯示 tier 可用的模板）。"""
    templates = get_templates_for_tier(tier)
    lines = [f"【{tier} 可用技能機制模板清單】"]
    for tid, entry in templates.items():
        desc = entry[2]
        params = entry[3] if len(entry) > 3 else []
        param_str = ", ".join(params)
        lines.append(f"  - {tid}: {desc}")
        if params:
            lines.append(f"    可填參數: {param_str}")
    return "\n".join(lines)


def assemble_skill_actions(template_choices: List[Dict[str, Any]], tier: str = "T5") -> List[Dict[str, Any]]:
    """
    根據 template_choices 列表中選取的模板和參數，組裝為 flat actions 陣列。
    支持 Tier 與 Intensity 數值縮放，並在 action 中附加自定義狀態別名的元數據。
    """
    actions = []
    
    tier_mults = {"T5": 0.5, "T4": 0.8, "T3": 1.2, "T2": 1.8, "T1": 3.0}
    t_mult = tier_mults.get(tier, 1.0)
    
    # 各機制的數值基準表
    base_val_map = {
        "active_conditional_detonate": 30.0,
        "active_shield": 20.0,
        "active_burn": 15.0,
        "active_frostbite": 8.0,
        "active_bleed": 15.0,
    }
    
    for choice in template_choices:
        tid = choice.get("template_id")
        if not tid:
            continue
        custom_name = choice.get("custom_status_name")
        intensity = choice.get("intensity") or "standard"
        
        entry = TEMPLATE_REGISTRY.get(tid)
        if not entry:
            continue
        
        fn = entry[0]
        params = {}
        
        # 1. 解析 canonical_status 並綁定 custom_status_name
        canonical_base = None
        if len(entry) > 3:
            if "status_name" in entry[3]:
                canonical_base = "status_name"
            elif "debuff_name" in entry[3]:
                canonical_base = "debuff_name"
            
        # 預先取得預設狀態以提取 Canonical 狀態名
        std_status = None
        try:
            default_actions = fn()
            if default_actions:
                std_status = default_actions[0].get("status_name") or default_actions[0].get("debuff_name")
        except Exception:
            pass
            
        if custom_name and canonical_base:
            params[canonical_base] = custom_name
            
        # 2. 強度係數映射
        if len(entry) > 3:
            if "hp_sacrifice_ratio" in entry[3]:
                sac_map = {"standard": 0.20, "high": 0.45, "extreme": 0.75}
                params["hp_sacrifice_ratio"] = sac_map.get(intensity, 0.20)
                
            # 根據模板自訂 base_value 進行階級與強度縮放
            if "flat_value" in entry[3] or "dot_damage_flat" in entry[3]:
                base_val = base_val_map.get(tid, 20.0)
                int_mult = {"standard": 1.0, "high": 1.5, "extreme": 2.2}
                final_val = base_val * t_mult * int_mult[intensity]
                
                if "flat_value" in entry[3]:
                    params["flat_value"] = final_val
                if "dot_damage_flat" in entry[3]:
                    params["dot_damage_flat"] = final_val

        # 3. 實例化 Action Payload
        try:
            res = fn(**params)
            if isinstance(res, list):
                # 附加元數據，供後續 models.py 重新註冊使用
                for act in res:
                    if custom_name and std_status:
                        act["custom_status_name"] = custom_name
                        act["canonical_status"] = std_status
                actions.extend(res)
        except Exception:
            try:
                res = fn()
                if isinstance(res, list):
                    # 動態關聯元數據
                    for act in res:
                        if custom_name and std_status:
                            act["custom_status_name"] = custom_name
                            act["canonical_status"] = std_status
                    actions.extend(res)
            except Exception:
                pass
                
    return actions
