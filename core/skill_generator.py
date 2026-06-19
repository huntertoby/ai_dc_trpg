# core/skill_generator.py
import json
from typing import Optional, List, Dict

from core.constants import normalize_status_name, STATUS_REGISTRY
from core.models import Skill
from core.skill_processor import SkillProcessor
from utils.json_utils import repair_and_parse_json


def instantiate_skill(d: dict) -> Skill:
    return Skill(**d)


# ---------------------------------------------------------------------------
# Stage 1 & 2 JSON Schemas
# ---------------------------------------------------------------------------
SKILL_STAGE1_SCHEMA = {
    "type": "json_schema",

    "json_schema": {

        "name": "skill_stage1",

        "strict": True,

        "schema": {

            "type": "object",

            "properties": {

                "skill_type": {"type": "string", "enum": ["active", "passive"]},

                "bonuses": {

                    "type": ["object", "null"],

                    "additionalProperties": {"type": "number"}

                },

                "action_type": {"type": "string", "enum": ["damage", "heal", "buff", "debuff"]},

                "target_type": {"type": "string", "enum": ["single", "aoe", "self", "allies"]},

                "base_stat": {"type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]},

                "is_magical": {"type": "boolean"},

                "template_choices": {

                    "type": "array",

                    "items": {

                        "type": "object",

                        "properties": {

                            "template_id": {"type": "string"},

                            "custom_status_name": {"type": ["string", "null"]},

                            "intensity": {"type": ["string", "null"], "enum": ["standard", "high", "extreme"]}

                        },

                        "required": ["template_id"],

                        "additionalProperties": False

                    }

                },

                "targeting_modifier": {"type": ["string", "null"], "enum": ["chain", None]},

                "synergy_requirement": {"type": ["string", "null"]},

                "execution_mode": {"type": "string",
                                   "enum": ["immediate", "delayed", "stance_switch", "channeled", "reactive"]},

                "cost_preference": {"type": ["string", "null"], "enum": ["zero", "low", "standard", "heavy"]},

                "evolution_threshold": {"type": ["integer", "null"]},

                "tags": {

                    "type": "array",

                    "items": {

                        "type": "string",

                        "enum": ["Fire", "Cold", "Shadow", "Lightning", "Holy", "Dark", "Wind", "Earth", "Water", "Nature", "Poison", "Acid", "Arcane", "Physical", "Chaos", "Melee", "Ranged", "Spell", "Summon", "Defense", "Gamble"]

                    }

                },

                "reactive_trigger": {

                    "type": ["object", "null"],

                    "properties": {

                        "event": {

                            "type": "string",

                            "enum": ["on_dodge", "on_damaged", "on_ally_damaged", "on_crit", "on_fatal_damage",
                                     "on_kill"]

                        },

                        "condition": {

                            "type": "string",

                            "enum": ["none", "health_below_30", "target_is_burning"]

                        },

                        "action_type": {

                            "type": "string",

                            "enum": ["inflict_damage", "gain_shield", "heal", "apply_status"]

                        },

                        "action_target": {

                            "type": "string",

                            "enum": ["caster", "attacker", "target"]

                        },

                        "status_to_apply": {

                            "type": ["string", "null"]

                        }

                    },

                    "required": ["event", "condition", "action_type", "action_target", "status_to_apply"],

                    "additionalProperties": False

                },

                "allowed_jobs": {

                    "type": "array",

                    "items": {

                        "type": "string",

                        "enum": ["戰士", "騎士", "狂戰士", "武僧", "暗殺者", "盜賊", "遊俠", "巫師", "術士", "死靈法師",
                                 "召喚師", "煉金術師", "元素使", "祭司", "德魯伊", "吟遊詩人", "聖騎士", "馴獸師",
                                 "商人", "占星師", "獵魔人", "工匠", "神諭者", "破法者", "暗騎士"]

                    }

                }

            },

            "required": [

                "skill_type",

                "bonuses",

                "action_type",

                "target_type",

                "base_stat",

                "is_magical",

                "template_choices",

                "targeting_modifier",

                "synergy_requirement",

                "execution_mode",

                "cost_preference",

                "evolution_threshold",

                "tags",

                "reactive_trigger",

                "allowed_jobs"

            ],

            "additionalProperties": False

        }

    }

}

SKILL_STAGE2_SCHEMA = {

    "type": "json_schema",

    "json_schema": {

        "name": "skill_stage2",

        "strict": True,

        "schema": {

            "type": "object",

            "properties": {

                "name": {"type": "string"},

                "description": {"type": "string"},

                "narrative_effect": {"type": "string"}

            },

            "required": ["name", "description", "narrative_effect"],

            "additionalProperties": False

        }

    }

}

STARTER_SKILLS_STAGE1_SCHEMA = {

    "type": "json_schema",

    "json_schema": {

        "name": "starter_skills_stage1",

        "strict": True,

        "schema": {

            "type": "object",

            "properties": {

                "skills": {

                    "type": "array",

                    "items": {

                        "type": "object",

                        "properties": {

                            "skill_type": {"type": "string", "enum": ["active", "passive"]},

                            "bonuses": {

                                "type": ["object", "null"],

                                "additionalProperties": {"type": "number"}

                            },

                            "tier": {"type": "string", "enum": ["T4", "T5"]},

                            "action_type": {"type": "string", "enum": ["damage", "heal", "buff", "debuff"]},

                            "target_type": {"type": "string", "enum": ["single", "aoe", "self", "allies"]},

                            "base_stat": {"type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]},

                            "is_magical": {"type": "boolean"},

                            "template_choices": {

                                "type": "array",

                                "items": {

                                    "type": "object",

                                    "properties": {

                                        "template_id": {"type": "string"},

                                        "custom_status_name": {"type": ["string", "null"]},

                                        "intensity": {"type": ["string", "null"],
                                                      "enum": ["standard", "high", "extreme"]}

                                    },

                                    "required": ["template_id"],

                                    "additionalProperties": False

                                }

                            },

                            "targeting_modifier": {"type": ["string", "null"], "enum": ["chain", None]},

                            "synergy_requirement": {"type": ["string", "null"]},

                            "execution_mode": {"type": "string",
                                               "enum": ["immediate", "delayed", "stance_switch", "channeled"]},

                            "cost_preference": {"type": ["string", "null"],
                                                "enum": ["zero", "low", "standard", "heavy"]},

                            "evolution_threshold": {"type": ["integer", "null"]},

                            "tags": {

                                "type": "array",

                                "items": {

                                    "type": "string",

                                    "enum": ["Fire", "Cold", "Shadow", "Lightning", "Holy", "Dark", "Wind", "Earth", "Water", "Nature", "Poison", "Acid", "Arcane", "Physical", "Chaos", "Melee", "Ranged", "Spell", "Summon", "Defense", "Gamble"]

                                }

                            },

                            "allowed_jobs": {

                                "type": "array",

                                "items": {

                                    "type": "string",

                                    "enum": ["戰士", "騎士", "狂戰士", "武僧", "暗殺者", "盜賊", "遊俠", "巫師", "術士",
                                             "死靈法師", "召喚師", "煉金術師", "元素使", "祭司", "德魯伊", "吟遊詩人",
                                             "聖騎士", "馴獸師", "商人", "占星師", "獵魔人", "工匠", "神諭者", "破法者",
                                             "暗騎士"]

                                }

                            }

                        },

                        "required": [

                            "skill_type",

                            "bonuses",

                            "tier",

                            "action_type",

                            "target_type",

                            "base_stat",

                            "is_magical",

                            "template_choices",

                            "targeting_modifier",

                            "synergy_requirement",

                            "execution_mode",

                            "cost_preference",

                            "evolution_threshold",

                            "tags",

                            "allowed_jobs"

                        ],

                        "additionalProperties": False

                    }

                }

            },

            "required": ["skills"],

            "additionalProperties": False

        }

    }

}

STARTER_SKILLS_STAGE2_SCHEMA = {

    "type": "json_schema",

    "json_schema": {

        "name": "starter_skills_stage2",

        "strict": True,

        "schema": {

            "type": "object",

            "properties": {

                "skills": {

                    "type": "array",

                    "items": {

                        "type": "object",

                        "properties": {

                            "name": {"type": "string"},

                            "description": {"type": "string"},

                            "narrative_effect": {"type": "string"}

                        },

                        "required": ["name", "description", "narrative_effect"],

                        "additionalProperties": False

                    }

                }

            },

            "required": ["skills"],

            "additionalProperties": False

        }

    }

}


# ---------------------------------------------------------------------------

# Cost & Formula Logic Helpers

# ---------------------------------------------------------------------------

def calculate_skill_cost(

        tier: str,

        target_type: str,

        is_magical: bool,

        template_choices: list,

        cost_pref: Optional[str],

        description: str

) -> dict:
    # 判斷描述中是否有無消耗意圖

    desc_lower = description.lower()

    if cost_pref == "zero" or any(
            kw in desc_lower for kw in ["無消耗", "無代價", "不消耗", "零消耗", "不用法力", "不用體力"]):
        return {}

    # 1. 階級基礎值

    base_costs = {"T5": 5, "T4": 10, "T3": 15, "T2": 25, "T1": 40}

    cost_val = base_costs.get(tier, 5)

    san_val = 0

    # 2. AoE 加乘

    if target_type in ("aoe", "allies"):
        cost_val = int(cost_val * 1.5)

    # 3. 模板額外代價

    for choice in template_choices:

        tid = choice.get("template_id", "")

        from core.skill_templates import get_template_metadata
        meta = get_template_metadata(tid)

        cost_modifier = meta.get("cost_modifier", 0)
        if cost_modifier:
            cost_val += cost_modifier
        elif tid in ("active_stun", "active_silence", "active_root"):
            cost_val += 10

        san_modifier = meta.get("san_modifier", 0)
        if san_modifier:
            san_val += san_modifier
        else:
            from core.constants import LEGENDARY_KEYWORDS
            clean_tid = tid.replace("active_", "")
            for lk in LEGENDARY_KEYWORDS:
                if lk.lower() == clean_tid.lower() or lk.lower().replace("_", "") == clean_tid.lower().replace("_", ""):
                    san_val += 10

    # 4. 根據偏好調整

    pref_mult = {"low": 0.4, "standard": 1.0, "heavy": 1.6}

    mult = pref_mult.get(cost_pref or "standard", 1.0)

    cost_val = int(cost_val * mult)

    san_val = int(san_val * mult)

    cost = {}

    # 5. 根據 is_magical 決定消耗類型（MP 或 STAMINA）

    resource_type = "MP" if is_magical else "STAMINA"

    if cost_val > 0:
        cost[resource_type] = cost_val

    if san_val > 0:
        cost["SAN"] = san_val

    return cost


def build_skill_formula_and_cost(parsed_data: dict, tier: str, description: str) -> dict:
    if parsed_data.get("skill_type") == "passive":
        parsed_data["formula"] = {
            "type": "multiplier",
            "base_stat": parsed_data.get("base_stat", "STR"),
            "dice": "0",
            "divisor": 1.0
        }
        parsed_data["cost"] = {}
        return parsed_data

    target_type = parsed_data.get("target_type", "single")

    is_magical = parsed_data.get("is_magical", True)

    cost_pref = parsed_data.get("cost_preference")

    template_choices = parsed_data.get("template_choices", [])

    # 1. 決定 Dice & Divisor

    dice_map = {

        "T5": {"single": "1d10", "aoe": "1d12"},

        "T4": {"single": "1d12", "aoe": "2d8"},

        "T3": {"single": "2d8", "aoe": "2d10"},

        "T2": {"single": "2d10", "aoe": "3d8"},

        "T1": {"single": "3d8", "aoe": "3d10"},

    }

    t_dice_map = dice_map.get(tier, {"single": "1d10", "aoe": "1d12"})

    dice_val = t_dice_map.get(target_type) or t_dice_map["single"]

    rules = TIER_RULES.get(tier, TIER_RULES["T5"])

    divisor_val = rules["min_divisor_aoe"] if target_type == "aoe" else rules["min_divisor_single"]

    parsed_data["formula"] = {

        "type": "multiplier",

        "base_stat": parsed_data.get("base_stat", "STR"),

        "dice": dice_val,

        "divisor": divisor_val

    }

    # 2. 計算 Cost

    parsed_data["cost"] = calculate_skill_cost(

        tier=tier,

        target_type=target_type,

        is_magical=is_magical,

        template_choices=template_choices,

        cost_pref=cost_pref,

        description=description

    )

    return parsed_data


# ---------------------------------------------------------------------------

# Status Check & Normalization

# ---------------------------------------------------------------------------

def check_and_normalize_skill_statuses(stage1_data: dict) -> dict:
    """

    檢查技能生成第一階段數據中的狀態效果。

    若能在註冊表中找到則標準化，找不到則印出警告並保留。

    """

    if not stage1_data:
        return stage1_data

    # 1. 處理 template_choices 中的 custom_status_name / status_name / debuff_name

    choices = stage1_data.get("template_choices", [])

    for choice in choices:

        if isinstance(choice, dict):

            for field in ["custom_status_name", "status_name", "debuff_name"]:

                if field in choice and choice[field]:

                    raw_status = choice[field]

                    norm_status = normalize_status_name(raw_status)

                    if norm_status in STATUS_REGISTRY:

                        choice[field] = norm_status

                    else:

                        print(
                            f"[Skill Gen] Warning: Status '{raw_status}' not found in STATUS_REGISTRY. Keeping as-is.")

                        choice[field] = norm_status

    # 2. 處理 synergy_requirement 中的 requires_xxx / consumes_xxx

    synergy_req = stage1_data.get("synergy_requirement")

    if synergy_req and isinstance(synergy_req, str):

        low_req = synergy_req.lower()

        if "requires_" in low_req:

            prefix = "requires_"

            try:

                raw_status = synergy_req.split(prefix)[1]

                norm_status = normalize_status_name(raw_status)

                if norm_status in STATUS_REGISTRY:

                    stage1_data["synergy_requirement"] = f"requires_{norm_status}"

                else:

                    print(
                        f"[Skill Gen] Warning: Synergy requirement status '{raw_status}' not found in STATUS_REGISTRY. Keeping as-is.")

                    stage1_data["synergy_requirement"] = f"requires_{norm_status}"

            except IndexError:

                pass

        elif "consumes_" in low_req:

            prefix = "consumes_"

            try:

                raw_status = synergy_req.split(prefix)[1]

                norm_status = normalize_status_name(raw_status)

                if norm_status in STATUS_REGISTRY:

                    stage1_data["synergy_requirement"] = f"consumes_{norm_status}"

                else:

                    print(
                        f"[Skill Gen] Warning: Synergy requirement status '{raw_status}' not found in STATUS_REGISTRY. Keeping as-is.")

                    stage1_data["synergy_requirement"] = f"consumes_{norm_status}"

            except IndexError:

                pass

    return stage1_data


# ---------------------------------------------------------------------------

# Backward Compatibility Helpers

# ---------------------------------------------------------------------------

def validate_keywords_safety(keywords: List[str], legendary_keyword: Optional[str] = None) -> Optional[str]:
    """檢驗關鍵字安全性（Stub 函數，保留相容性）"""

    kw_set = set(keywords)

    if legendary_keyword:
        kw_set.add(legendary_keyword)

    if "Invis" in kw_set and "Taunt" in kw_set:
        return "隱身 (Invis) 與 嘲諷 (Taunt) 不能同時存在"

    if "Combo_Starter" in kw_set and "Combo_Finisher" in kw_set:
        return "連擊起手 (Combo_Starter) 與 連擊終結 (Combo_Finisher) 不能同時存在"

    if "Stun" in kw_set and "Silence" in kw_set:
        return "暈眩 (Stun) 已包含沉默效果，兩者不應共存"

    return None


TIER_RULES = {

    "T5": {

        "template_slots": 0,

        "targeting_modifier": None,

        "synergy_requirement": None,

        "execution_mode": ["immediate"],

        "min_divisor_single": 15.0,

        "min_divisor_aoe": 22.5,

        "description": "T5 基礎招式：無模板、無修正、即時施放、低傷害。"

    },

    "T4": {

        "template_slots": 1,

        "targeting_modifier": None,

        "synergy_requirement": None,

        "execution_mode": ["immediate", "reactive"],

        "min_divisor_single": 12.0,

        "min_divisor_aoe": 18.0,

        "description": "T4 進階技能：至多 1 個標準模板，無修正，即時施放或被動反制。"

    },

    "T3": {

        "template_slots": 2,

        "max_modifiers": 1,

        "execution_mode": ["immediate", "delayed", "reactive"],

        "min_divisor_single": 10.0,

        "min_divisor_aoe": 15.0,

        "description": "T3 高階技能：至多 2 個模板，可用延遲施放或被動反制。"

    },

    "T2": {

        "template_slots": 2,

        "execution_mode": ["immediate", "delayed", "stance_switch", "reactive"],

        "min_divisor_single": 8.0,

        "min_divisor_aoe": 12.0,

        "description": "T2 專精技能：固定 2 模板，開放姿態切換與被動反制。"

    },

    "T1": {

        "template_slots_range": [2, 3],

        "execution_mode": ["immediate", "delayed", "stance_switch", "channeled", "reactive"],

        "min_divisor_single": 5.0,

        "min_divisor_aoe": 7.5,

        "description": "T1 傳說技能：2-3 模板（含傳說專屬），全模式開放。"

    }

}


def get_tier_rules(tier: str, kw_count: Optional[int] = None) -> str:
    """獲取不同階級的生成規則"""

    rules = TIER_RULES.get(tier, TIER_RULES["T5"])

    desc = rules["description"]

    cost_rule = "（必須設定 MP/SAN 等代價）" if tier == "T1" else ""

    return f"- {tier}：{desc}{cost_rule}"


def _enforce_tier_constraints(parsed_data: dict, tier: str) -> dict:
    rules = TIER_RULES.get(tier, TIER_RULES["T5"])

    # 被動技能特別處理
    if parsed_data.get("skill_type") == "passive":
        parsed_data["template_choices"] = []
        parsed_data["targeting_modifier"] = None
        parsed_data["synergy_requirement"] = None
        parsed_data["execution_mode"] = "immediate"
        parsed_data["cost_preference"] = "zero"
        parsed_data["reactive_trigger"] = None
        parsed_data["action_type"] = "buff"
        parsed_data["target_type"] = "self"

        # 限制並過濾 bonuses 數值
        bonuses = parsed_data.get("bonuses") or {}
        valid_bonuses = {}

        limits = {
            "T5": {"primary": 2.0, "rate": 0.01, "defense": 2.0},
            "T4": {"primary": 5.0, "rate": 0.02, "defense": 5.0},
            "T3": {"primary": 10.0, "rate": 0.05, "defense": 10.0},
            "T2": {"primary": 15.0, "rate": 0.08, "defense": 15.0},
            "T1": {"primary": 25.0, "rate": 0.12, "defense": 25.0},
        }
        tier_limit = limits.get(tier, limits["T5"])

        primary_stats = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
        rate_stats = {"crit_rate", "evasion_rate", "accuracy"}
        defense_stats = {"p_def", "m_def"}

        for k, v in bonuses.items():
            if not isinstance(v, (int, float)):
                continue
            if k in primary_stats:
                valid_bonuses[k] = min(v, tier_limit["primary"])
            elif k in rate_stats:
                valid_bonuses[k] = min(v, tier_limit["rate"])
            elif k in defense_stats:
                valid_bonuses[k] = min(v, tier_limit["defense"])

        parsed_data["bonuses"] = valid_bonuses
    else:
        # 主動技能的 bonuses 必須為空
        parsed_data["bonuses"] = {}

        # 1. template_choices 數量限制
        choices = parsed_data.get("template_choices", [])
        if tier == "T5":
            parsed_data["template_choices"] = []
        elif tier == "T4":
            parsed_data["template_choices"] = choices[:1]
        elif tier == "T3":
            parsed_data["template_choices"] = choices[:2]
        elif tier == "T2":
            parsed_data["template_choices"] = choices[:2]
        elif tier == "T1":
            parsed_data["template_choices"] = choices[:3]

        # 2. targeting_modifier / synergy_requirement
        if tier in ("T4", "T5"):
            parsed_data["targeting_modifier"] = None
            parsed_data["synergy_requirement"] = None
        elif tier == "T3":
            # 最多保留 1 個 modifier
            if parsed_data.get("targeting_modifier") and parsed_data.get("synergy_requirement"):
                parsed_data["synergy_requirement"] = None

        # Clean up invalid targeting_modifier values
        if parsed_data.get("targeting_modifier") and parsed_data.get("targeting_modifier") != "chain":
            parsed_data["targeting_modifier"] = None

        # 3. execution_mode
        allowed = rules.get("execution_mode", ["immediate"])
        if parsed_data.get("execution_mode") not in allowed:
            parsed_data["execution_mode"] = "immediate"

        # 4. 過濾不符合層級的模板
        from core.skill_templates import get_templates_for_tier
        available_templates = get_templates_for_tier(tier)
        parsed_data["template_choices"] = [
            tc for tc in parsed_data.get("template_choices", [])
            if tc.get("template_id") in available_templates
        ]

        # 5. target_type 限制與相容性檢查
        if tier == "T5":
            # T5 基礎招式不允許 AOE 範圍攻擊
            if parsed_data.get("target_type") in ("aoe", "allies"):
                parsed_data["target_type"] = "single"

        # 確保 action_type (傷害/扣益 vs 治療/增益) 與 target_type 的陣營/目標類型相容
        action_type = parsed_data.get("action_type", "damage")
        target_type = parsed_data.get("target_type", "single")
        if action_type in ("damage", "debuff") and target_type == "allies":
            parsed_data["target_type"] = "aoe"
        elif action_type in ("heal", "buff") and target_type == "aoe":
            parsed_data["target_type"] = "allies"

    return parsed_data


def _enforce_divisor_floor(parsed_data: dict, tier: str) -> dict:
    rules = TIER_RULES.get(tier, TIER_RULES["T5"])

    target_type = parsed_data.get("target_type", "single")

    if target_type == "aoe":

        floor = rules["min_divisor_aoe"]

    else:

        floor = rules["min_divisor_single"]

    formula = parsed_data.get("formula", {})

    if formula and isinstance(formula, dict):

        if formula.get("divisor", 0) < floor:
            formula["divisor"] = floor

    return parsed_data


# ---------------------------------------------------------------------------

# Format Actions to Pseudocode

# ---------------------------------------------------------------------------

def _format_single_action(act: dict) -> str:
    """將單個 action dict 格式化為說明字串。"""

    act_type = act.get("action_type")

    target = act.get("target", "target")

    if target == "caster":

        target_zh = "自身"

    else:

        target_zh = "目標"

    SPECIAL_MECHANIC_EXPLANATIONS = {

        "Detonate": "引爆：若目標擁有特定狀態（如 Burn 灼燒），則消耗該狀態並額外造成傷害",

        "Multi-hit": "多重打擊：將單次傷害拆分為 3 至 5 次連續打擊進行結算",

        "Lifesteal": "吸血打擊：將造成傷害的 30% 轉化為自身生命回復",

        "Sacrifice": "血契犧牲：消耗自身 20% HP 轉化為技能威力加成",

        "Purge": "神聖淨化：清除目標身上的所有可驅散負面狀態",

        "Pierce": "防線穿透：穿透目標，無視其 50% 防禦力",

        "Execute": "無情處決：若目標生命值低於 20%，傷害提升至 3 倍",

        "Wall_Break": "護盾崩潰：擊碎目標的臨時生命與護盾",

        "Martyr": "殉道救贖：生命值歸零，傷害乘以 3 倍",

        "Overload": "魔力超載：提升 50% 傷害，但下一回合技能消耗翻倍",

        "Quickcast": "法術瞬發：不消耗行動點數，允許連續發動技能",

        "Gamble": "命運豪賭：50% 機率傷害乘以 3，50% 反噬自身等量傷害",

        "Steal": "妙手空空：竊取目標金幣",

        "Chain": "雷霆連鎖：彈跳至下一個存活的敵方目標（傷害減半）",

        "Summon": "使魔召喚：在戰鬥中召喚一個戰從單位協助戰鬥",

        "Resurrect": "起死回生：復活已倒下的盟友",

        "Rampage": "殺戮盛宴：擊殺目標時獲得額外行動回合",

        "Greed": "貪婪之證：若擊殺目標，金幣掉落翻倍",

        "Echo": "殘響重奏：下一回合以 50% 威力自動重施此技能",

        "Epoch_Break": "時代終結：抹殺目標所有增益與護盾，且本次傷害無視減免",

        "Time_Warp": "時光回溯：將施法者的生命與魔法還原至上一回合",

        "Blood_Pact": "血誓契約：消耗 20% HP，獲得基於已損失生命值比例的巨額增傷",

        "Devil's_Roll": "惡魔骰局：隨機觸發反噬、增傷強化或全體傳說爆發",

        "Last_Rites": "終焉禮讚：對充盈目標傷害加倍，對衰竭目標則將厄運擴散",

        "Resonance_Break": "共鳴破碎：根據目標身上的負面狀態數量，每個增加 15% 傷害",

        "Annihilate": "虛滅降臨：清除目標護盾並無視防禦封頂限制",

        "Paradox": "矛盾法則：將目標的防禦力數值轉化為額外真實傷害",

        "Doom_Seal": "厄印強化：施加無法驅散的死亡倒數，2 回合後必死",

        "Void_Rift": "虛空裂隙：建立裂隙，目標受傷時施法者承受 25% 反噬",

        "Eternal_Wound": "永恆創傷：封印目標的所有治療與回復效果",

        "Abyssal_Mark": "深淵印記：使目標受到的所有來源傷害增加 40%",

        "Fate_Seal": "命運封印：記錄當前生命，3 回合後強制還原",

        "Soul_Drain": "靈魂汲取：竊取目標 20% 傷害的 MP 並回復自身等量生命值",

        "Soul_Shatter": "靈魂粉碎：若擊殺目標，則眩暈所有敵人並恢復自身 50 SAN",

        "Copy": "鏡像複製：複製上一個施放的技能",

        "Focus": "專注：下一擊必定爆擊",

        "Siphon": "屬性汲取：降低目標特定屬性並轉移等量屬性給自身",

        "Bleed": "撕裂流血：物理持續傷害且治療減半",

        "Ward": "魔防護盾：抵消下一次受到的負面狀態",

        "Desperation": "絕境怒火：生命值低於指定比例時獲得增傷與吸血",

        "Fade": "仇恨消退：移除自身嘲諷並進入隱身狀態",

        "Phoenix_Rebirth": "涅槃重燃：死亡後復活，恢復 50% HP/MP",

        "Fate_Swap": "因果互換：交換雙方生命值百分比",

        "Mind_Control": "心靈傀儡：強制目標下一次隨機攻擊其怪物盟友",

        "Apocalypse": "天劫降臨：延遲 2 回合，全體真實傷害 + 沉默"

    }

    STATUS_TRANSLATIONS_EXPLAINED = {

        "Burn": "灼燒（每回合造成持續真實傷害）",

        "Stun": "眩暈（無法行動，跳過回合）",

        "Silence": "沉默（無法施展需要法力的傷害技能）",

        "Root": "定身（無法使用物理近戰技能）",

        "Slow": "減速（閃避率歸零，出手順序墊底）",

        "Frostbite": "凍傷（每回合造成持續真實傷害）",

        "Blind": "盲目（降低 50% 命中率）",

        "Doom": "厄運宣告（死亡倒數，結算即死）",

        "Charm": "魅惑（反轉目標隨機攻擊隊友）",

        "Confusion": "混亂（行動有 50% 機率取消）",

        "Shield": "護盾（獲得吸收傷害的護盾）",

        "Immune": "不滅霸體（免疫所有負面狀態）",

        "Invis": "隱身（極難被單體選中）",

        "Levitate": "重力浮空（使目標浮空）",

        "Counter_Stance": "反擊架勢（受到物理攻擊時進行反擊）",

        "Bless": "祝福（擲骰點數小於等於 5 時自動補底為 10）",

        "Reflect": "鏡面反射（受傷減半且反彈 50% 傷害）",

        "Taunt": "野性嘲諷（強制單體攻擊指向嘲諷者）",

        "Sunder": "破甲（降低 30% 物理防禦）",

        "Bleed": "撕裂流血（每回合造成持續物理傷害且治療與吸血減半）",

        "Ward": "魔防護盾（抵消下一次受到的負面狀態）",

        "Desperation": "絕境怒火（生命值低於指定比例時獲得增傷與吸血）",

        "Phoenix_Rebirth": "涅槃重燃（死亡後復活，恢復 50% HP/MP）",

        "Mind_Control": "心靈傀儡（被控制，強制其攻擊怪物盟友）"

    }

    if act_type == "apply_status":

        status_name = act.get("status_name")

        duration = act.get("duration", 0)

        bonuses = act.get("stat_bonuses")

        dot_flat = act.get("dot_damage_flat", 0.0)

        dot_type = act.get("dot_damage_type", "true_damage")

        status_desc = STATUS_TRANSLATIONS_EXPLAINED.get(status_name, status_name)

        s = f"施加狀態【{status_desc}】給 {target_zh}，持續 {duration} 回合"

        if bonuses:
            s += f"（屬性加成: {bonuses}）"

        if dot_flat and float(dot_flat) > 0:
            s += f"，每回合造成 {dot_flat} 點{dot_type}"

        return s

    elif act_type == "gain_shield":

        flat = act.get("flat_value", 0.0)

        stat = act.get("scaling_stat")

        mult = act.get("value_multiplier", 0.0)

        val_str = f"{flat}"

        if stat and mult:
            val_str += f" + {mult}x 自身的 {stat}"

        return f"使 {target_zh} 獲得 {val_str} 點護盾"

    elif act_type == "heal":

        flat = act.get("flat_value", 0.0)

        res = act.get("target_resource", "hp")

        return f"使 {target_zh} 恢復 {flat} 點 {res}"

    elif act_type == "inflict_damage":

        flat = act.get("flat_value", 0.0)

        return f"對 {target_zh} 造成 {flat} 點傷害"

    elif act_type == "call_special_mechanic":

        kw = act.get("keyword_name")

        kw_desc = SPECIAL_MECHANIC_EXPLANATIONS.get(kw, kw)

        return f"觸發特殊機制【{kw_desc}】對象為 {target_zh}"

    return f"未知行動 [{act_type}]"


def format_actions_to_pseudocode(actions: list) -> str:
    if not actions:
        return "無額外戰鬥效果"

    return "、".join(_format_single_action(a) for a in actions)


# ---------------------------------------------------------------------------

# Fix Skill Structure

# ---------------------------------------------------------------------------

def fix_skill_structure(d):
    if isinstance(d, dict):

        if "name" not in d:
            d["name"] = "未知技能"

        if "tier" in d and isinstance(d["tier"], int):
            d["tier"] = f"T{d['tier']}"

        if "tier" not in d:
            d["tier"] = "T5"

        if "formula" in d:

            f = d["formula"]

            if isinstance(f, str):

                d["formula"] = {"type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0}

            elif isinstance(f, dict):

                if "denominator" in f:
                    f["divisor"] = f.pop("denominator")

                if "multiplier_value" in f:
                    f.pop("multiplier_value")

                if "base_stat" in f and f["base_stat"] not in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
                    f["base_stat"] = "STR"

        else:

            d["formula"] = {"type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0}

        if "cost" in d and isinstance(d["cost"], dict):
            d["cost"] = {k: v for k, v in d["cost"].items() if k in ["MP", "SAN", "STAMINA"]}

        if "mechanics" not in d:

            mechanics_keys = ["action_type", "formula", "cost", "actions", "target_type", "narrative_effect",
                              "targeting_modifier", "synergy_requirement", "execution_mode", "tags"]

            new_mechanics = {}

            for k in list(d.keys()):

                if k in mechanics_keys:
                    new_mechanics[k] = d.pop(k)

            d["mechanics"] = new_mechanics

        m = d["mechanics"]

        if "action_type" not in m: m["action_type"] = "damage"

        if "target_type" not in m: m["target_type"] = "single"

        if "cost" not in m: m["cost"] = {}

        if "actions" not in m: m["actions"] = []

        if "narrative_effect" not in m: m["narrative_effect"] = ""

        if "targeting_modifier" not in m: m["targeting_modifier"] = None

        if "synergy_requirement" not in m: m["synergy_requirement"] = None

        if "execution_mode" not in m: m["execution_mode"] = "immediate"

        if "tags" not in m: m["tags"] = []

        if "formula" not in m: m["formula"] = d["formula"]

        if isinstance(m.get("cost"), dict):
            m["cost"] = {k: v for k, v in m["cost"].items() if k in ["MP", "SAN", "STAMINA"]}

        # Convert legacy fields if present

        legacy_kw = m.pop("keywords", None) or d.pop("keywords", None) or []

        legacy_legendary = m.pop("legendary_keyword", None) or d.pop("legendary_keyword", None)

        if legacy_kw or legacy_legendary:

            from core.skill_templates import assemble_skill_actions

            choices = []

            for kw in legacy_kw:
                clean_kw = kw.replace("'", "").replace("-", "_").replace(" ", "_").lower()

                choices.append({"template_id": f"active_{clean_kw}"})

            if legacy_legendary:
                clean_lk = legacy_legendary.replace("'", "").replace("-", "_").replace(" ", "_").lower()

                choices.append({"template_id": f"active_{clean_lk}"})

            m["actions"].extend(assemble_skill_actions(choices))

        if "executable_triggers" not in d:
            d["executable_triggers"] = []

    return d


# ---------------------------------------------------------------------------

# Template Dynamic Filtering & Fuzzy Keyword Map

# ---------------------------------------------------------------------------

TEMPLATE_KEYWORD_MAP = {

    "active_vampiric_strike": ["吸血", "吸取生命", "回復自身傷害", "生命轉化", "生命汲取", "血療", "噬血"],

    "active_lifesteal": ["吸血", "吸取生命", "回復自身傷害", "生命轉化", "生命汲取", "血療", "噬血"],

    "active_conditional_detonate": ["引爆", "引燃", "引發額外", "爆炸", "引爆傷害", "觸發額外"],

    "active_sacrifice": ["犧牲", "血契", "扣除自身", "扣血", "獻祭", "自殘", "代價", "誓約"],

    "active_shield": ["護盾", "防護罩", "聖盾", "吸收傷害", "金鐘罩", "臨時生命", "屏障"],

    "active_stun": ["暈眩", "眩暈", "昏迷", "不能行動", "震懾", "擊暈", "石化", "冰凍", "定身"],

    "active_silence": ["沉默", "禁言", "封印技能", "不能施法", "封法", "禁魔", "封鎖魔法"],

    "active_root": ["定身", "纏繞", "荊棘", "困住", "鎖定位置", "無法移動", "束縛"],

    "active_slow": ["減速", "遲緩", "降低閃避", "泥沼", "重力", "虛弱", "泥潭"],

    "active_burn": ["灼燒", "火焰", "燃燒", "DoT", "引燃", "烈焰", "火"],

    "active_frostbite": ["凍傷", "寒冰", "減速", "冰霜", "凍結", "冰", "極寒"],

    "active_blind": ["盲目", "致盲", "降低命中", "失明", "煙霧", "黑暗", "瞎"],

    "active_doom": ["逆運", "厄運", "宣告", "即死", "死亡倒數", "死亡宣告", "必死"],

    "active_charm": ["魅惑", "控制", "反轉目標", "隨機攻擊隊友", "誘惑", "迷惑"],

    "active_confusion": ["混亂", "思緒混亂", "機率取消", "迷失", "神智不清"],

    "active_immune": ["不滅", "霸體", "免疫", "狀態免疫", "金身", "淨化"],

    "active_invis": ["隱身", "暗影", "難以選中", "潛行", "消失", "隱形"],

    "active_levitate": ["浮空", "重力", "上升", "漂浮", "浮起"],

    "active_counter_stance": ["反擊架勢", "反擊姿態", "迎擊", "格擋反擊"],

    "active_bless": ["祝福", "命運", "補底", "神恩", "加持"],

    "active_reflect": ["反射", "鏡面", "反彈", "鏡射"],

    "active_taunt": ["嘲諷", "強制攻擊", "吸引仇恨", "挑釁"],

    "active_purge": ["淨化", "清除負面", "驅散", "神聖淨化", "洗滌"],

    "active_copy": ["鏡像", "複製", "模仿", "學習", "鏡子"],

    "active_multi_hit": ["多重打擊", "連擊", "多段傷害", "連續攻擊", "二連擊", "三連"],

    "active_multihit": ["多重打擊", "連擊", "多段傷害", "連續攻擊", "二連擊", "三連"],

    "active_sunder": ["破甲", "降低防禦", "粉碎護甲", "削防"],

    "active_pierce": ["穿透", "無視防禦", "防線穿透", "破甲"],

    "active_execute": ["無情處決", "處決", "斬殺", "血量低於", "秒殺"],

    "active_wall_break": ["碎垣", "擊碎護盾", "破盾", "崩潰"],

    "active_overload": ["超載", "魔力超載", "過載", "雙倍消耗"],

    "active_quickcast": ["瞬發", "不消耗行動", "連續發動"],

    "active_gamble": ["豪賭", "命運豪賭", "機率傷害", "反噬"],

    "active_steal": ["妙手空空", "竊取", "偷錢", "小偷"],

    "active_vampiric_aura": ["吸血光環", "吸血", "盟友吸血"],

    "active_soul_link": ["靈魂絲線", "靈魂連結", "共享生命", "綁定"],

    "active_chain": ["連鎖", "雷霆連鎖", "彈跳"],

    "active_summon": ["召喚", "召喚隨從", "使魔召喚", "召喚獸"],

    "active_resurrect": ["復甦", "復活", "起死回生"],

    "active_rampage": ["殺戮盛宴", "狂暴", "擊殺獲得額外"],

    "active_greed": ["貪婪之證", "貪婪", "金幣倍增"],

    "active_adapt": ["適應抗性", "適應", "抗性"],

    "active_echo": ["殘響重奏", "殘響", "下回合重複"],

    "active_berserk": ["狂野暴怒", "狂暴", "無法操作"],

    "active_banish": ["虛空放逐", "放逐", "無法行動"],

    "active_epoch_break": ["時代終結", "終結", "抹殺增益"],

    "active_time_warp": ["時光回溯", "回溯", "還原生命"],

    "active_blood_pact": ["血誓契約", "血誓", "巨額增傷"],

    "active_devil_roll": ["惡魔骰", "惡魔賭局", "命運之骰"],

    "active_devils_roll": ["惡魔骰", "惡魔賭局", "命運之骰"],

    "active_last_rites": ["終焉禮讚", "終焉", "擴散"],

    "active_resonance_break": ["共鳴破碎", "共鳴", "狀態數量"],

    "active_annihilate": ["虛滅", "虛滅降臨", "抹除護盾"],

    "active_paradox": ["矛盾法則", "矛盾", "防禦力轉化"],

    "active_doom_seal": ["厄印強化", "厄印", "必死"],

    "active_void_rift": ["虛空裂隙", "裂隙", "反噬"],

    "active_eternal_wound": ["永恆創傷", "封印治療", "無法回復"],

    "active_abyssal_mark": ["深淵印記", "深淵", "受傷增加"],

    "active_fate_seal": ["命運封印", "封印", "強制還原"],

    "active_soul_drain": ["靈魂汲取", "汲取", "吸取MP"],

    "active_soul_shatter": ["靈魂粉碎", "擊殺眩暈", "粉碎"],

    "active_focus": ["專注", "暴擊", "必定爆擊"],

    "active_siphon": ["屬性汲取", "降低屬性", "轉移屬性"],

    "active_bleed": ["流血", "撕裂", "流血狀態", "持續物理"],

    "active_ward": ["魔防護盾", "抵消負面", "護盾"],

    "active_desperation": ["絕境怒火", "絕境", "生命值低於"],

    "active_fade": ["仇恨消退", "隱身", "移除嘲諷"],

    "active_phoenix_rebirth": ["涅槃重燃", "涅槃", "死亡復活"],

    "active_fate_swap": ["因果互換", "交換生命", "血量互換"],

    "active_mind_control": ["心靈傀儡", "心靈控制", "傀儡"],

    "active_apocalypse": ["天劫降臨", "天劫", "全體真實"]

}

# 核心基礎模板，以及百搭特色模板（常駐趣味底包）

CORE_TEMPLATES = {"active_shield", "active_stun", "active_burn", "active_slow", "active_gamble", "active_copy"}


def get_filtered_template_menu(description: str, tier: str) -> str:
    """根據玩家的描述，動態過濾並返回最相關的技能模板清單，並附加趣味常駐模板。"""

    from core.skill_templates import get_templates_for_tier

    available_templates = get_templates_for_tier(tier)

    matched_tids = set()

    desc_lower = description.lower()

    # 掃描近義詞

    for tid, keywords in TEMPLATE_KEYWORD_MAP.items():

        if tid in available_templates:

            if any(kw in desc_lower for kw in keywords):
                matched_tids.add(tid)

    # 補上常駐核心與趣味底包（取交集以符合該 Tier 限制）

    matched_tids.update(CORE_TEMPLATES.intersection(available_templates.keys()))

    # 限制選單上限（最多 8 個），避免 Prompt 過長

    matched_list = list(matched_tids)[:8]

    lines = [f"【{tier} 可用技能機制模板清單】(請在此清單中選擇最契合的模板)"]

    for tid in matched_list:
        entry = available_templates[tid]

        desc = entry[2]

        params = entry[3] if len(entry) > 3 else []

        param_str = f" (可填參數: {', '.join(params)})" if params else ""

        lines.append(f"  - {tid}: {desc}{param_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------

# Generate Single Skill (Two-Stage)

# ---------------------------------------------------------------------------

async def generate_single_skill(description: str, tier: str, llm_client, kw_count: Optional[int] = None) -> Optional[
    Skill]:
    """生成單一技能 (雙階段)"""

    from core.skill_templates import assemble_skill_actions

    template_menu = get_filtered_template_menu(description, tier)

    if tier == "T1":

        tier_rules = """- 可選 2 至 3 個 template_choices 欄位。可以使用 T1 傳說級或標準級模板。

- 開放所有 execution_mode 模式 (immediate, delayed, stance_switch, channeled, reactive)。"""

    elif tier == "T2":

        tier_rules = """- 固定選擇 2 個 template_choices 欄位。只能使用標準級模板。

- 開放 execution_mode 模式 (immediate, delayed, stance_switch, reactive)。"""

    elif tier == "T3":

        tier_rules = """- 至多選擇 2 個 template_choices 欄位。只能使用標準級模板。

- targeting_modifier 與 synergy_requirement 合計至多保留 1 個。

- 開放 execution_mode 模式 (immediate, delayed, reactive)。"""

    elif tier == "T4":

        tier_rules = """- 至多選擇 1 個 template_choices 欄位。只能使用標準級模板。

- targeting_modifier 與 synergy_requirement 必須為 null。

- 開放 execution_mode 模式 (immediate, reactive)。"""

    else:  # T5

        tier_rules = """- 必須保持 template_choices 為空列表 []。

- targeting_modifier 與 synergy_requirement 必須為 null。

- 僅開放 execution_mode 模式 (immediate)。"""

    system_prompt_stage1 = f"""你是一個專業的 TRPG 技能設計師。

請根據玩家的描述，進行第一階段設計：

①決定 skill_type （預設為 "active"，若描述特別指明是常駐被動天賦/屬性提升，則設定為 "passive"）

②若為被動技能，設定 bonuses 屬性加成，否則 bonuses 設為 null

③決定 action_type 和 target_type

④設定 base_stat（STR/DEX/CON/INT/WIS/CHA，依據技能主題決定最契合的主屬性）

⑤決定 is_magical（是否為消耗法力 MP 的魔法技能；若為 False 則自動消耗精力 STAMINA）

⑥從機制模板清單中選擇適合的 template_choices，並可選擇性自訂狀態名稱 (custom_status_name) 及指定強度 (intensity: standard/high/extreme)。

⑦設定 execution_mode、targeting_modifier、synergy_requirement、cost_preference。

⑧若且唯若 execution_mode 為 "reactive" 時，設定 reactive_trigger 內容，否則 reactive_trigger 必須填為 null。

⑨決定 allowed_jobs 限制：必須挑選 2-3 個最適合使用此技能的基準職業。



【階級生成規則 - {tier}】

{tier_rules}



【可用技能機制模板清單】

{template_menu}



【特別注意事項】

- 僅輸出 JSON 格式，不要包含任何額外解釋文字或 markdown 標籤。

"""

    prompt = f"描述：{description}\n請進行技能的第一階段生成。"

    stage1_data = None

    for attempt in range(3):

        try:

            response_text = await llm_client.call(

                prompt=prompt,

                system_prompt=system_prompt_stage1,

                temperature=0.2 + (attempt * 0.05),

                response_schema=SKILL_STAGE1_SCHEMA,

                enable_thinking=False

            )

            parsed_data = repair_and_parse_json(response_text)

            if parsed_data:



                # Enforce strict constraints and floors

                parsed_data = _enforce_tier_constraints(parsed_data, tier)

                parsed_data = build_skill_formula_and_cost(parsed_data, tier, description)

                choices = parsed_data.get("template_choices", [])

                # 檢查新版 template_choices 產生的關鍵字安全性

                from core.models import SkillMechanics

                temp_mech = SkillMechanics(actions=assemble_skill_actions(choices, tier=tier))

                safety_error = validate_keywords_safety(temp_mech.keywords, temp_mech.legendary_keyword)

                if safety_error:
                    print(f"新版機制衝突 (嘗試 {attempt + 1}/3): {safety_error}")

                    continue

                stage1_data = check_and_normalize_skill_statuses(parsed_data)

                break

        except Exception as e:

            print(f"Stage 1A 生成失敗 (嘗試 {attempt + 1}/3): {e}")

    if not stage1_data:
        return None

    # Stage 1B: 組裝 actions

    if stage1_data.get("skill_type") == "passive":
        actions = []
        bonuses = stage1_data.get("bonuses") or {}
        bonus_desc = ", ".join([f"{k} 增加 {v}" for k, v in bonuses.items()])
        full_pseudocode = f"常駐被動效果：\n屬性加成：{bonus_desc or '無'}"

        system_prompt_stage2 = f"""你是一個優秀的 TRPG 故事設計師。

請根據第一階段的屬性加成與被動效果，為該被動技能設計中文名稱 (name)、簡短描述 (description) 與技能效果說明 (narrative_effect)。

【被動效果資訊】
{full_pseudocode}

【寫作風格與限制】
1. name: 具有奇幻氣息與獨特設計感，嚴禁俗套 RPG 詞彙。
2. description: 控制在 50~70 字，描寫常駐的被動視覺特徵、肉體或靈魂深處的異動、環境的微弱共鳴，具有實體感。
3. narrative_effect: 必須清楚且精確地描述所獲得的常駐屬性加成（例如「常駐提升力量 5 點」），確保效果與被動效果資訊中的加成 100% 吻合！

僅輸出 JSON 格式，不要任何說明文字。
"""
    else:
        actions = assemble_skill_actions(stage1_data.get("template_choices", []), tier=tier)
        extra_pseudocode = format_actions_to_pseudocode(actions)
        act_type_str = {"damage": "造成傷害", "heal": "進行治療", "buff": "施加增益", "debuff": "施加減益"}.get(
            stage1_data.get("action_type", ""), "造成傷害")
        tgt_type_str = {"single": "單體目標", "aoe": "群體範圍", "self": "自身", "allies": "全體盟友"}.get(
            stage1_data.get("target_type", ""), "單體目標")
        full_pseudocode = f"基礎效果：對【{tgt_type_str}】【{act_type_str}】\n附加機制：{extra_pseudocode}"

        system_prompt_stage2 = f"""你是一個優秀的 TRPG 故事設計師。

請根據第一階段組裝好的戰鬥邏輯與偽代碼，為該技能設計中文名稱 (name)、簡短描述 (description) 與技能特效說明 (narrative_effect)。

【技能戰鬥邏輯偽代碼】
{full_pseudocode}

【寫作風格與限制】
1. name: 具有奇幻氣息與獨特設計感，嚴禁俗套 RPG 詞彙。
2. description: 控制在 50~70 字，描寫視覺特徵、能量流動、微觀痕跡，具有實體感。
3. narrative_effect: 根據戰鬥邏輯偽代碼中的具體效果，確保說明中的機制、狀態、數值與偽代碼 100% 吻合！例如如果偽代碼中提到施加 Stun，說明中必須寫「眩暈」，絕不能漏掉或自行發明！

【階級設定與警告】T1 為最高傳說級，T5 為最低基礎級。當前生成階級為：【{tier}】
1. 若為 T4/T5 低階技能：請務必嚴格過濾玩家描述中不合理的字眼（如無敵、秒殺、絕對防禦等），僅保留基礎視覺特效
2. 若為 T1/T2 高階技能：允許保留史詩、毀天滅地的修辭與氣場。
3. 鐵律：無論任何階級，實際戰鬥效果「僅有上方偽代碼所述」。絕不能在 narrative_effect 中「無中生有」偽代碼沒提到的狀態或機制！

僅輸出 JSON 格式，不要任何說明文字。
"""

    prompt_stage2 = (
        f"玩家原始描述：{description}\n"
        f"請進行第二階段故事包裝。"
    )

    for attempt in range(3):

        try:

            response_text = await llm_client.call(

                prompt=prompt_stage2,

                system_prompt=system_prompt_stage2,

                temperature=0.2 + (attempt * 0.05),

                response_schema=SKILL_STAGE2_SCHEMA,

                enable_thinking=True

            )

            parsed_data2 = repair_and_parse_json(response_text)

            if parsed_data2:

                executable_triggers = []

                if stage1_data.get("execution_mode") == "reactive" and stage1_data.get("reactive_trigger"):

                    rt = stage1_data["reactive_trigger"]

                    cond_str = None

                    if rt["condition"] == "health_below_30":

                        cond_str = "health_below(30)"

                    elif rt["condition"] == "target_is_burning":

                        cond_str = "target_has_status('Burn')"

                    formula_data = stage1_data.get("formula", {})

                    dice_val = formula_data.get("dice", "1d10")

                    divisor_val = formula_data.get("divisor", 12.0)

                    action_payload = {

                        "action_type": rt["action_type"],

                        "target": rt["action_target"],

                        "scaling_stat": stage1_data.get("base_stat", "STR"),

                        "value_multiplier": 1.0,

                        "dice": dice_val,

                        "divisor": divisor_val

                    }

                    if rt["action_type"] == "apply_status" and rt.get("status_to_apply"):
                        action_payload["status_name"] = rt["status_to_apply"]

                        action_payload["duration"] = 2

                    trigger_payload = {

                        "event": rt["event"],

                        "cooldown": 2,

                        "chance": 1.0,

                        "condition": cond_str,

                        "actions": [action_payload]

                    }

                    from core.compiler import TriggerCompiler

                    compiled = TriggerCompiler.compile_flat_triggers([trigger_payload])

                    if compiled:
                        executable_triggers.extend(compiled)

                final_dict = {

                    "name": parsed_data2.get("name"),

                    "description": parsed_data2.get("description"),

                    "tier": tier,

                    "skill_type": stage1_data.get("skill_type", "active"),

                    "allowed_jobs": stage1_data.get("allowed_jobs", []),

                    "bonuses": stage1_data.get("bonuses") or {},

                    "action_type": stage1_data.get("action_type"),

                    "target_type": stage1_data.get("target_type"),

                    "cost": stage1_data.get("cost"),

                    "formula": stage1_data.get("formula"),

                    "narrative_effect": parsed_data2.get("narrative_effect"),

                    "targeting_modifier": stage1_data.get("targeting_modifier"),

                    "synergy_requirement": stage1_data.get("synergy_requirement"),

                    "execution_mode": stage1_data.get("execution_mode"),

                    "evolution_threshold": stage1_data.get("evolution_threshold") or 0,

                    "tags": stage1_data.get("tags", []),

                    "actions": actions,

                    "executable_triggers": executable_triggers

                }

                final_dict = fix_skill_structure(final_dict)

                skill = instantiate_skill(final_dict)

                SkillProcessor.validate_and_clamp_skill(skill)

                return skill

        except Exception as e:

            print(f"Stage 2 生成失敗 (嘗試 {attempt + 1}/3): {e}")

    return None


# ---------------------------------------------------------------------------

# Generate Starter Skills (Two-Stage)

# ---------------------------------------------------------------------------

async def generate_starter_skills(char_data: Dict, llm_client, t4_kw_count: Optional[int] = None) -> List[Skill]:
    """為新角色生成 3 個初始技能 (2個 T5, 1個 T4)"""

    from core.skill_templates import build_template_menu, assemble_skill_actions

    system_prompt_stage1 = f"""你是一個專業的 TRPG 技能設計師。

請為以下角色設計 3 個初始技能的第一階段設計。

初始技能包含 2 個 T5 (基礎招式) 與 1 個 T4 (進階技巧)。



【角色資訊】

名稱：{char_data.get('name')}

職業：{char_data.get('job_name')}

背景：{char_data.get('background')}



【階級生成規則與限制】

- T5 技能：必須保持 template_choices 為空列表 []。僅限 immediate 模式。

- T4 技能：至多 1 個標準級模板（template_choices 包含 1 個項目）。僅限 immediate 模式。



【可用技能機制模板清單】

{build_template_menu("T4")}



【要求決定欄位】

①決定 skill_type （一律填為 "active"）

②設定 bonuses （一律填為 null）

③決定 action_type 和 target_type

④設定 base_stat（STR/DEX/CON/INT/WIS/CHA，根據初始技能類型匹配主角屬性）

⑤決定 is_magical（是否消耗法力 MP；若否則消耗體力 STAMINA）

⑥在 template_choices 中挑選模板（T5 為 []，T4 為至多 1 個項目）並可選擇性自訂狀態名稱及強度

⑦設定 execution_mode（一律為 immediate）與 cost_preference

⑧決定 allowed_jobs 限制：挑選 2-3 個最適合主角職業使用的基準職業（主角的職業通常為主角 base_jobs 中的職業）



僅輸出 JSON 格式，不要包含任何解釋文字。

"""

    prompt = "請為角色生成 3 個初始技能的第一階段設定。"

    stage1_data = None

    for attempt in range(3):

        try:

            response_text = await llm_client.call(

                prompt=prompt,

                system_prompt=system_prompt_stage1,

                temperature=0.2 + (attempt * 0.05),

                response_schema=STARTER_SKILLS_STAGE1_SCHEMA,

                enable_thinking=False

            )

            parsed_data = repair_and_parse_json(response_text)

            if parsed_data and isinstance(parsed_data, dict) and "skills" in parsed_data:

                skills_list = parsed_data["skills"]



                # 確保符合 rules 並建構公式/消耗

                for s in parsed_data["skills"]:
                    s_tier = s.get("tier", "T5")

                    s = _enforce_tier_constraints(s, s_tier)

                    s = build_skill_formula_and_cost(s, s_tier, "")

                    s = check_and_normalize_skill_statuses(s)

                stage1_data = parsed_data

                break

        except Exception as e:

            print(f"初始技能 Stage 1A 生成失敗 (嘗試 {attempt + 1}/3): {e}")

    if not stage1_data:
        return []

    skills_stage1 = stage1_data["skills"]

    # 組合 actions

    for s in skills_stage1:
        s["actions"] = assemble_skill_actions(s.get("template_choices", []), tier=s.get("tier", "T5"))

    # Stage 2: 故事包裝與特效說明

    system_prompt_stage2 = f"""你是一個優秀的 TRPG 故事設計師。

請為這 3 個初始技能包裝故事。根據第一階段的數值與 action_type，撰寫名稱、描述與特效說明。



【角色資訊】

名稱：{char_data.get('name')}

職業：{char_data.get('job_name')}

背景：{char_data.get('background')}



僅輸出 JSON 格式，不要任何解釋文字。

"""

    prompt_stage2 = f"技能 Stage1 設定為：{json.dumps(skills_stage1, ensure_ascii=False)}\n請包裝這 3 個技能的故事。"

    for attempt in range(3):

        try:

            response_text = await llm_client.call(

                prompt=prompt_stage2,

                system_prompt=system_prompt_stage2,

                temperature=0.2 + (attempt * 0.05),

                response_schema=STARTER_SKILLS_STAGE2_SCHEMA,

                enable_thinking=True

            )

            parsed_data2 = repair_and_parse_json(response_text)

            if parsed_data2 and isinstance(parsed_data2, dict) and "skills" in parsed_data2:

                skills_stage2 = parsed_data2["skills"]

                valid_skills = []

                for i, s1 in enumerate(skills_stage1):
                    s2 = skills_stage2[i] if i < len(skills_stage2) else {"name": "未知技能", "description": "無描述",
                                                                          "narrative_effect": ""}

                    final_dict = {

                        "name": s2.get("name"),

                        "description": s2.get("description"),

                        "tier": s1.get("tier"),

                        "skill_type": s1.get("skill_type", "active"),

                        "allowed_jobs": s1.get("allowed_jobs", []),

                        "bonuses": s1.get("bonuses") or {},

                        "action_type": s1.get("action_type"),

                        "target_type": s1.get("target_type"),

                        "cost": s1.get("cost"),

                        "formula": s1.get("formula"),

                        "narrative_effect": s2.get("narrative_effect"),

                        "targeting_modifier": s1.get("targeting_modifier"),

                        "synergy_requirement": s1.get("synergy_requirement"),

                        "execution_mode": s1.get("execution_mode"),

                        "evolution_threshold": s1.get("evolution_threshold") or 0,

                        "tags": s1.get("tags", []),

                        "actions": s1.get("actions", [])

                    }

                    final_dict = fix_skill_structure(final_dict)

                    skill = instantiate_skill(final_dict)

                    SkillProcessor.validate_and_clamp_skill(skill)

                    valid_skills.append(skill)

                if len(valid_skills) == len(skills_stage1):
                    return valid_skills

        except Exception as e:

            print(f"初始技能 Stage 2 生成失敗 (嘗試 {attempt + 1}/3): {e}")

    return []


# ---------------------------------------------------------------------------

# Test Helper

# ---------------------------------------------------------------------------

async def generate_single_skill_test(description: str, tier: str, llm_client) -> Optional[Skill]:
    return await generate_single_skill(description, tier, llm_client)
