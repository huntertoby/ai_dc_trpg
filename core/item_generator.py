# core/item_generator.py
"""
裝備生成器（模板驅動架構）

新架構設計：
  Stage 1A（LLM）：選擇模板 ID + 填寫創意數值/名稱
  Stage 1B（程式）：根據模板組裝 flat trigger，送入 TriggerCompiler
  Stage 2（LLM）：生成裝備名稱、背景故事、特效說明

優點：
  - LLM 完全不需要處理 branch_roll/branch_when、apply_status vs apply_debuff、
    DoT 必填欄位等複雜規則（由模板保證格式正確）
  - LLM 只需填寫少量有創意的參數（數值、名稱、狀態加成）
  - 支援 3 次重試，全部失敗則顯示生成失敗訊息
"""
import asyncio
from typing import Optional, Literal
import sys
import copy

# Configure console output to support UTF-8 on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from core.models import Equipment
from core.equipment import EquipmentBalancer
from core.compiler import TriggerCompiler
from core.trigger_templates import (
    TEMPLATE_REGISTRY,
    get_templates_for_tier,
    build_template_menu,
    assemble_trigger,
)
from core.constants import normalize_status_name, STATUS_REGISTRY
import json
import re

# ---------------------------------------------------------------------------
# Stage 1A JSON Schema（新版：LLM 只選模板 + 填簡單參數）
# ---------------------------------------------------------------------------
EQUIPMENT_STAGE1_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "equipment_stage1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "is_two_handed": {"type": "boolean"},
                "weapon_type":   {"type": ["string", "null"]},
                "damage_type":   {"type": "string"},
                "scaling_stat":  {
                    "type": "string",
                    "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
                },
                "bonuses": {
                    "type": "object",
                    "additionalProperties": {"type": "number"}
                },
                "trigger_choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "template_id": {"type": "string"},
                            "flat_value":  {"type": ["number", "null"]},
                            "dmg_flat":    {"type": ["number", "null"]},
                            "heal_flat":   {"type": ["number", "null"]},
                            "scaling_stat":{"type": ["string", "null"]},
                            "dmg_stat":    {"type": ["string", "null"]},
                            "heal_stat":   {"type": ["string", "null"]},
                            "value_mult":  {"type": ["number", "null"]},
                            "dmg_mult":    {"type": ["number", "null"]},
                            "heal_mult":   {"type": ["number", "null"]},
                            "dice":        {"type": ["string", "null"]},
                            "chance":      {"type": ["number", "null"]},
                            "cooldown":    {"type": ["integer", "null"]},
                            "duration":    {"type": ["integer", "null"]},
                            "hp_below":    {"type": ["integer", "null"]},
                            "status_name": {"type": ["string", "null"]},
                            "debuff_name": {"type": ["string", "null"]},
                            "dot_flat":    {"type": ["number", "null"]},
                            "dot_stat":    {"type": ["string", "null"]},
                            "dot_mult":    {"type": ["number", "null"]},
                            "dot_type":    {"type": ["string", "null"]},
                            "stat_bonuses":{"type": ["object", "null"]},
                            "target_resource": {"type": ["string", "null"]}
                        },
                        "required": ["template_id"]
                    }
                },
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["Fire", "Cold", "Shadow", "Lightning", "Holy", "Dark", "Wind", "Earth", "Water", "Nature", "Poison", "Acid", "Arcane", "Physical", "Chaos", "Melee", "Ranged", "Spell", "Summon", "Defense", "Gamble"]
                    },
                    "minItems": 1,
                    "maxItems": 1
                },
                "allowed_jobs": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["戰士", "騎士", "狂戰士", "武僧", "暗殺者", "盜賊", "遊俠", "巫師", "術士", "死靈法師", "召喚師", "煉金術師", "元素使", "祭司", "德魯伊", "吟遊詩人", "聖騎士", "馴獸師", "商人", "占星師", "獵魔人", "工匠", "神諭者", "破法者", "暗騎士"]
                    }
                }
            },
            "required": ["is_two_handed", "scaling_stat", "bonuses", "trigger_choices", "tags", "allowed_jobs"]
        }
    }
}

EQUIPMENT_STAGE2_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "equipment_stage2",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "name":           {"type": "string"},
                "description":    {"type": "string"},
                "special_effect": {"type": "string"}
            },
            "required": ["name", "description", "special_effect"]
        }
    }
}


# ---------------------------------------------------------------------------
# 模板參數 stat_bonuses 合法鍵（T2 減益強度限制）
# ---------------------------------------------------------------------------
_T2_MAX_DEBUFF = -0.15

INT_STATS = {"p_def", "m_def", "tenacity", "luck",
             "STR", "DEX", "CON", "INT", "WIS", "CHA"}
FLOAT_STATS = {"crit_rate", "evasion_rate", "accuracy", "skill_power"}
ALL_STAT_BONUSES_KEYS = INT_STATS | FLOAT_STATS


def _sanitize_stat_bonuses(sb: dict, tier: str, is_buff: bool) -> dict:
    """
    清理 stat_bonuses dict：
    - 過濾非法 key
    - 增益只能正數，減益只能負數
    - T2 減益強度不得低於 -0.15
    """
    result = {}
    for k, v in sb.items():
        if k not in ALL_STAT_BONUSES_KEYS:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if is_buff and v <= 0:
            continue
        if not is_buff and v >= 0:
            continue
        # T2 減益強度限制
        if not is_buff and tier == "T2" and v < _T2_MAX_DEBUFF:
            v = _T2_MAX_DEBUFF
        result[k] = v
    return result


def get_equipment_tier_rules(tier: str) -> str:
    """
    根據 tier 回傳觸發器數量限制說明（給 Stage 1A prompt 使用）。
    """
    if tier in ("T4", "T5"):
        return f"【{tier} 詞條規範】\n此稀有度沒有觸發器。trigger_choices 必須是空陣列 []。\n"
    if tier == "T1":
        return "【T1 傳說觸發器規範】\ntrigger_choices 必須包含 2 個觸發器選擇（選 2 個不同的 template_id）。\n可用所有模板，包含 AoE、複合效果、強力減益等。\n"
    elif tier == "T2":
        return "【T2 史詩觸發器規範】\ntrigger_choices 必須包含 1 個觸發器選擇。\n只能選擇非 T1 限定的模板（即 T1/T2 共用 或 T1/T2/T3 共用 的模板）。\n"
    elif tier == "T3":
        return "【T3 稀有觸發器規範】\ntrigger_choices 必須包含 1 個觸發器選擇。\n只能選擇 T1/T2/T3 共用的模板（以自身增益為主，禁止選擇含 debuff 效果的模板）。\n"
    return ""


def validate_equipment_affix_constraints(parsed_data: dict, tier: str) -> tuple[bool, Optional[str]]:
    """
    在 AI 生成後、編譯前進行 soft 驗證。

    檢查 parsed_data 中的 executable_triggers 是否符合 tier 的品質約束。
    如果不符合，返回 (False, error_description)，觸發重試。
    如果符合，返回 (True, None)。

    驗證規則：
    - T3: 所有 action target 必須是 "caster" 或不存在（預設 caster）
    - T2: 不能有 AoE target（all_enemies/all_allies）、不能有複合 action
    - T1: 無限制
    """
    tier_config = EquipmentBalancer.AFFIX_QUALITY_TIERS.get(tier, {})
    triggers = parsed_data.get("executable_triggers", [])

    # T4/T5 不應該有任何觸發器
    if tier in ["T4", "T5"] and triggers:
        return False, f"{tier} 裝備不應該有任何觸發器，但生成了 {len(triggers)} 個。請重新生成。"

    # 全 tier 通用：apply_status 絕對禁止對敵方使用
    for trigger_idx, trigger in enumerate(triggers):
        for action_idx, action in enumerate(trigger.get("actions", [])):
            if action.get("action_type") == "apply_status" and action.get("target") in ["target", "all_enemies"]:
                return False, (
                    f"Trigger {trigger_idx} Action {action_idx}：apply_status 不能對敵方（target/all_enemies）使用。"
                    f" 狀態名稱 '{action.get('status_name', '?')}' 是負面效果請改用 apply_debuff + debuff_name。"
                )

    # T1 無限制，直接通過
    if tier == "T1":
        return True, None

    # T2 驗證：禁 AoE、禁複合
    if tier == "T2":
        can_have_aoe = tier_config.get("can_have_aoe", False)
        can_have_complex = tier_config.get("can_have_complex", False)

        for trigger_idx, trigger in enumerate(triggers):
            # 檢查 AoE
            if not can_have_aoe:
                for action_idx, action in enumerate(trigger.get("actions", [])):
                    target = action.get("target", "")
                    if target and "all_" in target:
                        return False, f"T2 禁止 AoE：Trigger {trigger_idx} Action {action_idx} 的 target 為 '{target}'。"

            # 檢查複合
            if not can_have_complex:
                if EquipmentBalancer.is_complex_trigger(trigger):
                    return False, f"T2 禁止複合效果：Trigger {trigger_idx} 包含多個 action 或混合效果類型。"

    # T3 驗證：禁止減敵方（所有 action target 必須是 caster）
    if tier == "T3":
        can_have_debuff = tier_config.get("can_have_debuff", False)

        if can_have_debuff == False:  # T3 禁止減敵方
            for trigger_idx, trigger in enumerate(triggers):
                for action_idx, action in enumerate(trigger.get("actions", [])):
                    target = action.get("target", "caster")

                    # 檢查 target 是否指向敵方
                    if target not in ["caster", "self", None]:
                        return False, f"T3 禁止減敵方：Trigger {trigger_idx} Action {action_idx} 的 target 為 '{target}'，必須是 'caster'。"

                    # 檢查是否有 debuff_name（絕對禁止）
                    if "debuff_name" in action:
                        return False, f"T3 禁止 debuff：Trigger {trigger_idx} Action {action_idx} 不能有 'debuff_name' 欄位。"

    return True, None


def _format_single_action(act: dict) -> str:
    """將單個 action dict 格式化為中文說明字串。"""
    act_type = act.get("action_type")
    target = act.get("target")
    flat = act.get("flat_value", 0.0)

    try:
        flat_f = float(flat)
    except (ValueError, TypeError):
        flat_f = 0.0

    stat = act.get("scaling_stat")
    mult = act.get("value_multiplier")

    if stat and mult:
        val_str = f"{flat} + {mult}x 自身的 {stat}" if flat_f != 0.0 else f"{mult}x 自身的 {stat}"
    else:
        val_str = f"{flat}"

    if act_type == "inflict_damage":
        return f"對 {target} 造成 {val_str} 點真實傷害"
    elif act_type == "gain_shield":
        return f"使 {target} 獲得 {val_str} 點護盾"
    elif act_type == "heal":
        res = act.get("target_resource", "hp")
        return f"使 {target} 恢復 {val_str} 點 {res}"
    elif act_type == "apply_status":
        status_name = act.get("status_name")
        duration = act.get("duration")
        bonuses = act.get("bonuses")
        dot_flat = act.get("dot_damage_flat", 0.0)
        dot_stat = act.get("dot_scaling_stat")
        dot_mult = act.get("dot_multiplier", 0.0)
        s = f"施加狀態【{status_name}】給 {target}，持續 {duration} 回合"
        if bonuses:
            s += f"（屬性加成: {bonuses}）"
        if dot_flat and float(dot_flat) > 0:
            if dot_stat and float(dot_mult) > 0:
                s += f"，每回合造成 {dot_flat} + {dot_mult}x自身{dot_stat} 點真實傷害"
            else:
                s += f"，每回合造成 {dot_flat} 點真實傷害"
        return s
    elif act_type == "remove_status":
        return f"清除 {target} 身上的狀態【{act.get('status_name')}】"
    elif act_type == "purge_debuffs":
        return f"清除 {target} 身上的所有負面狀態"
    elif act_type == "call_special_mechanic":
        return f"觸發系統核心特殊機制【{act.get('keyword_name')}】對象為 {target}"
    elif act_type == "modify_dice":
        return f"修改擲骰結果 [{act.get('param')}] 為 [{act.get('param_value')}]"
    elif act_type == "set_value":
        return f"設置計算數值 [{act.get('param')}] 為 [{act.get('param_value')}]"
    return f"未知行動 [{act_type}]"


def format_triggers_to_pseudocode(triggers: list) -> str:
    if not triggers:
        return "無特殊戰鬥效果"

    lines = []
    for i, t in enumerate(triggers):
        event = t.get("event")
        cond = t.get("condition")
        chance = t.get("chance")
        cooldown = t.get("cooldown")
        branch_roll = t.get("branch_roll")  # e.g. "1d3"

        info = f"效果 {i+1}：觸發事件 [{event}]"
        if chance is not None:
            info += f"，觸發機率 [{int(float(chance)*100)}%]"
        if cooldown is not None:
            info += f"，冷卻時間 [{cooldown} 回合]"
        if cond:
            info += f"，觸發條件 [{cond}]"

        raw_actions = t.get("actions", [])

        if branch_roll:
            # 分離「有 branch_when（條件分支）」與「無 branch_when（固定執行）」的行動
            always_acts = [a for a in raw_actions if not a.get("branch_when")]
            branched_acts = [a for a in raw_actions if a.get("branch_when")]

            parts = []
            if always_acts:
                parts.append("固定執行：" + "、".join(_format_single_action(a) for a in always_acts))

            if branched_acts:
                branch_lines = []
                for act in branched_acts:
                    bw = act.get("branch_when")  # e.g. [1, 1] or [2, 3]
                    lo, hi = bw[0], bw[1]
                    range_str = f"{lo}" if lo == hi else f"{lo}~{hi}"
                    branch_lines.append(f"  - 骰到 {range_str}：{_format_single_action(act)}")
                parts.append(f"隨機分支（擲 {branch_roll}，三選一）：\n" + "\n".join(branch_lines))

            info += " ➔ 行動：\n" + "\n".join(parts)
        else:
            actions = [_format_single_action(a) for a in raw_actions]
            info += " ➔ 行動：" + "、".join(actions)

        lines.append(info)
    return "\n".join(lines)




def _build_stage1_example(tier: str, slot_type: str, budgets: dict) -> str:
    """
    為新版 Stage 1A 生成「完美合規」的 JSON 輸出範例。
    LLM 只需選 template_id + 填少量創意參數。
    """
    is_weapon = slot_type in ("main_hand", "off_hand")
    primary_stat = "STR" if is_weapon else "CON"
    tag = "Melee" if is_weapon else "Defense"
    jobs = ["戰士", "騎士"] if is_weapon else ["戰士", "騎士", "巫師"]

    if tier in ("T4", "T5"):
        example = {
            "is_two_handed": False,
            "weapon_type": "長劍" if slot_type == "main_hand" else None,
            "damage_type": "physical",
            "scaling_stat": primary_stat,
            "bonuses": {primary_stat: round(float(budgets["primary"]), 1)},
            "tags": [tag],
            "allowed_jobs": jobs,
            "trigger_choices": []
        }
    elif tier == "T3":
        example = {
            "is_two_handed": False,
            "weapon_type": "長劍" if slot_type == "main_hand" else None,
            "damage_type": "physical",
            "scaling_stat": primary_stat,
            "bonuses": {primary_stat: round(float(budgets["primary"]), 1), "p_def": 5.0},
            "tags": [tag],
            "allowed_jobs": jobs,
            "trigger_choices": [
                {
                    "template_id": "on_damaged_buff",
                    "status_name": "不屈之志",
                    "duration": 2,
                    "stat_bonuses": {"p_def": 25, "tenacity": 20},
                    "cooldown": 3
                }
            ]
        }
    elif tier == "T2":
        example = {
            "is_two_handed": False,
            "weapon_type": "長劍" if slot_type == "main_hand" else None,
            "damage_type": "physical",
            "scaling_stat": primary_stat,
            "bonuses": {primary_stat: round(float(budgets["primary"]), 1), "crit_rate": 0.06},
            "tags": [tag],
            "allowed_jobs": jobs,
            "trigger_choices": [
                {
                    "template_id": "on_hit_debuff",
                    "debuff_name": "Sunder",
                    "duration": 2,
                    "stat_bonuses": {"p_def": -0.12},
                    "chance": 0.30,
                    "cooldown": 2
                }
            ]
        }
    else:  # T1
        example = {
            "is_two_handed": False,
            "weapon_type": "長劍" if slot_type == "main_hand" else None,
            "damage_type": "physical",
            "scaling_stat": primary_stat,
            "bonuses": {primary_stat: round(float(budgets["primary"]), 1), "crit_rate": 0.06},
            "tags": [tag],
            "allowed_jobs": jobs,
            "trigger_choices": [
                {
                    "template_id": "on_hit_damage_dot",
                    "flat_value": 25.0,
                    "scaling_stat": primary_stat,
                    "value_mult": 1.2,
                    "debuff_name": "Burn",
                    "dot_flat": 18.0,
                    "dot_stat": primary_stat,
                    "dot_mult": 0.5,
                    "dot_type": "true_damage",
                    "duration": 3,
                    "chance": 0.40,
                    "cooldown": 2
                },
                {
                    "template_id": "on_turn_start_buff",
                    "status_name": "戰意高漲",
                    "duration": 2,
                    "stat_bonuses": {primary_stat: 12, "crit_rate": 0.15},
                    "cooldown": 3
                }
            ]
        }

    return json.dumps(example, ensure_ascii=False, indent=2)


def _assemble_triggers_from_choices(
    trigger_choices: list,
    tier: str,
    max_triggers: int
) -> list:
    """
    Stage 1B：將 LLM 選擇的模板參數組裝為完整的 flat trigger dict 列表，
    送入 TriggerCompiler.compile_flat_triggers()。

    - 驗證 template_id 是否在該 tier 的可用模板中
    - 使用模板函式組裝 trigger
    - 限制數量至 max_triggers
    """
    available = get_templates_for_tier(tier)
    flat_triggers = []

    for choice in trigger_choices[:max_triggers]:
        if not isinstance(choice, dict):
            continue
        tid = choice.get("template_id", "")
        if tid not in available:
            print(f"⚠️ template_id '{tid}' 在 {tier} 不可用，跳過")
            continue

        # 清理 stat_bonuses（如果有）
        params = dict(choice)
        params.pop("template_id", None)

        # 執行狀態/debuff對照與標準化
        for field in ["status_name", "debuff_name"]:
            if field in params and params[field]:
                raw_status = params[field]
                norm_status = normalize_status_name(raw_status)
                if norm_status in STATUS_REGISTRY:
                    params[field] = norm_status
                else:
                    print(f"[Item Gen] Warning: Status/Debuff '{raw_status}' not found in STATUS_REGISTRY. Keeping as-is.")
                    params[field] = norm_status

        sb = params.get("stat_bonuses")
        if sb and isinstance(sb, dict):
            # 判斷是增益還是減益模板（含 debuff_name 的是減益）
            is_buff = "debuff_name" not in choice
            params["stat_bonuses"] = _sanitize_stat_bonuses(sb, tier, is_buff)
            # 確保清理後不為空
            if not params["stat_bonuses"]:
                # 給預設值
                if is_buff:
                    params["stat_bonuses"] = {"STR": 10}
                else:
                    params.pop("stat_bonuses", None)

        trig = assemble_trigger(tid, params)
        if trig:
            flat_triggers.append(trig)

    return flat_triggers


async def generate_equipment_by_ai(
    description: str,
    item_level: int,
    tier: Literal["T1", "T2", "T3", "T4", "T5"],
    slot_type: str,
    llm_client
) -> Optional[Equipment]:
    """
    呼叫 AI 雙階段生成裝備。

    Stage 1A（LLM）：選擇觸發器模板 + 填寫創意數值/名稱 + bonuses 分配
    Stage 1B（程式）：根據模板組裝 flat trigger，送入 TriggerCompiler
    Stage 2（LLM）：生成裝備名稱、背景故事、特效說明

    支援最多 3 次重試；全部失敗則返回 None 並輸出失敗訊息。
    """
    budgets = EquipmentBalancer.calculate_budgets(item_level, tier)
    affix_slots = EquipmentBalancer.AFFIX_SLOTS.get(tier, 0)
    tier_config = EquipmentBalancer.AFFIX_QUALITY_TIERS.get(tier, {})
    max_triggers = tier_config.get("max_triggers", 0)

    # Dynamically build stage 1 schema with minItems/maxItems based on tier triggers
    stage1_schema = copy.deepcopy(EQUIPMENT_STAGE1_SCHEMA)
    trigger_choices_prop = stage1_schema["json_schema"]["schema"]["properties"]["trigger_choices"]
    trigger_choices_prop["minItems"] = max_triggers
    trigger_choices_prop["maxItems"] = max_triggers

    from core.constants import WEAPON_TYPES
    weapon_list_str = ", ".join(WEAPON_TYPES.keys())

    # -----------------------------------------------------------------------
    # Stage 1A System Prompt（模板選擇版）
    # -----------------------------------------------------------------------
    tier_rules = get_equipment_tier_rules(tier)
    tier_example = _build_stage1_example(tier, slot_type, budgets)
    template_menu = build_template_menu(tier) if max_triggers > 0 else ""

    system_prompt_stage1 = f"""你是一個 TRPG 裝備生成助理。你的工作是：
①分配屬性（bonuses）②從模板清單中選擇觸發器（trigger_choices）③填寫創意參數與職業限制。
觸發器的完整結構由系統模板保證正確，你只需要填寫數值與名稱即可。

【裝備基本限制】
- slot_type（部位）: 必須輸出部位 `{slot_type}`（但 JSON 欄位中不需要包含 slot_type）
- 主屬性 (bonuses 中的 STR/DEX/CON/INT/WIS/CHA): 分配約 {budgets['primary']} 點（可小幅調整±10%）
  防具優先配置 CON；武器優先配置 STR 或 DEX；法杖/魔導書優先配置 INT
- 附屬性 (bonuses 中的其他欄位): 最多 {affix_slots} 條
  合法鍵: p_def, m_def, crit_rate, evasion_rate, accuracy, skill_power, tenacity, luck
- scaling_stat: 只能填 STR / DEX / CON / INT / WIS / CHA（大寫）
- allowed_jobs: 必須挑選 2-3 個最適合穿戴此裝備的基準職業（例如法師法袍限定巫師、術士、元素使，重甲限定戰士、騎士、聖騎士等）
- tags: 必須且只能挑選 1 個最契合裝備特性的標籤（例如近戰武器選 Melee，遠程選 Ranged，法杖選 Spell 等，不能同時選多個）

【觸發器規範 - {tier}】
{tier_rules}

{template_menu}

【填寫說明】
- template_id: 從上方清單中選擇模板名稱（必須完全一致）
- status_name: 你可以自由命名增益狀態（中文，有創意的名稱）
- stat_bonuses: 依照模板說明填寫數值
  增益狀態（apply_status）填正數，例: {{"STR": 15, "crit_rate": 0.12}}
  減益（apply_debuff）填負數，例: {{"p_def": -0.12}}
- 數值可根據 item_level={item_level} 適當調整（高等級裝備數值更高）

【合規輸出範例（{tier}）】
{tier_example}

只輸出 JSON，禁止任何說明文字。"""

    prompt = f"描述：{description}\n請根據部位 `{slot_type}` 的特性生成裝備，發揮創意設計觸發器效果。"

    # -----------------------------------------------------------------------
    # Stage 2 System Prompt（故事包裝）
    # -----------------------------------------------------------------------
    system_prompt_stage2 = """你是一個優秀 TRPG 故事設計師。根據裝備數值與編譯後的戰鬥邏輯偽代碼，撰寫中文名稱、背景故事與效果說明。

【事件類型翻譯對照（必須嚴格遵守，不可自行解釋）】
  on_battle_start      = 「每場戰鬥開始時（整場戰鬥只觸發一次）」
  on_turn_start        = 「每回合開始時」（絕對不是「戰鬥開始」）
  on_turn_end          = 「每回合結束時」
  on_hit               = 「擊中目標時」
  on_damaged           = 「受到傷害時」
  on_kill              = 「擊殺目標時」
  on_crit              = 「觸發暴擊時」
  on_miss              = 「攻擊未命中時」
  on_dodge             = 「成功閃避時」
  on_fatal_damage      = 「受到致命傷害時」
  on_health_below      = 「血量低於 X% 時」
  on_dice              = 「進行任意擲骰檢定時」
  on_calculate_damage  = 「進行傷害數值結算時」

【行為與數值翻譯對照（必須嚴格遵守，不可自行發明）】
  Time_Warp            = 「獲得額外回合並回溯生命與魔法」
  Prevent_Death        = 「免除死亡並將生命與魔法重置至上限」
  roll_modifier        = 「擲骰結果增加 X 點」
  floor_value          = 「擲骰結果低於 X 時以 X 計算（保底 X 點）」
  reroll_threshold     = 「擲骰結果小於或等於 X 時將重新擲骰」
  damage_multiplier    = 「本次攻擊傷害提升為 X 倍」
  defense_ignore_ratio = 「無視目標 X% 的防禦力」
  is_absolute_hit      = 「本次攻擊必定命中（無視閃避）」
  is_crit              = 「本次攻擊必定觸發暴擊」

【偽代碼結構說明——必須完全理解後再翻譯】

▶ 固定執行行動：每次觸發時必然執行的效果。
▶ 隨機分支（擲 NdM，X選一）：每次觸發只隨機執行其中一個分支，不會全部執行。
  - 例：「隨機分支（擲 1d3，三選一）：骰到1：效果A、骰到2：效果B、骰到3：效果C」
    → 翻譯為：「隨機觸發效果A、B、C 之一（各 1/3 機率）」
  - 偽代碼中有「隨機分支」時，絕對禁止把所有分支都寫成「同時觸發」！
▶ 偽代碼若同時包含「固定執行」和「隨機分支」，說明兩部分都要翻譯到 special_effect 中。

【寫作風格與限制】
1. name：具備獨特設計感與奇幻韻味，但嚴禁過度中二或俗套。避免濫用「深淵、毀滅、裁決、遠古、神魔、命運」等過度常見的經典 RPG 詞彙，除非玩家的描述特別要求。
2. description：描寫外觀、材質、使用痕跡或工藝細節。
   - 避免陳腔濫調，例如「落敗王朝」、「邪神耳語」、「無光之火」等氾濫的奇幻網文套路。
   - 字數嚴格控制在 50~70 字之間，用克制、冷靜但有張力的筆調寫出裝備的獨特性，追求短小精悍。
   - 專注於物理實體感（如：磨損細節、特異材質、獨特工藝、微弱能量波動）。
3. 核心主題契合：名稱與背景故事（description）必須緊扣「玩家原始設計主旨」，將該主旨融入外觀與背景設定中（例如：主旨為「賭命」時，應體現博弈、賭徒、高風險等意象；主旨為「火焰」時體現溫熱或灼燒等），不可天馬行空地偏離主旨。
4. special_effect：
   - 將 caster 翻譯為「裝備者」，target 翻譯為「目標」，嚴禁直接出現英文代碼。
   - 嚴格且誠實地翻譯偽代碼，禁止添加偽代碼中不存在的機制。
   - 數值、狀態名稱、持續回合必須與偽代碼完全一致。
   - 含「真實傷害」時，需在說明中標注「無視防禦力（真實傷害）」。
   - 事件類型必須依照上方翻譯對照表翻譯，不可自行猜測。
   - 有隨機分支時，必須在說明中清楚表達「隨機效果之一」而非列出所有效果為同時發生.
5. 嚴格禁止直接抄襲或套用範例中的「潮汐導引儀」或「羅盤」字眼，必須根據玩家給出的描述與部位特性生成全新的原創內容。
6. T1/T2/T3 裝備的 special_effect 請依觸發器偽代碼撰寫效果說明；T4/T5 裝備的 special_effect 必須是空字串 ""。

只輸出 JSON，不要任何說明文字。

範例格式（以「鏽蝕的航海羅盤」為例，供參考格式用，請勿照抄）：
{
  "name": "潮汐導引儀",
  "description": "這枚黃銅羅盤的外殼被海水蝕出斑駁綠鏽，指針不再指向北方，而是隨著潮汐的起伏微微顫動，散發著微弱的海浪氣息。",
  "special_effect": "潮汐庇護：每回合開始時，若自身生命值低於 30%，有 40% 機率獲得 20 點護盾，持續 2 回合；冷卻 3 回合。"
}
"""

    from utils.json_utils import repair_and_parse_json

    # -----------------------------------------------------------------------
    # Stage 1A：3 次重試循環
    # -----------------------------------------------------------------------
    MAX_RETRIES = 3
    eq: Optional[Equipment] = None
    last_error: str = ""

    for attempt in range(1, MAX_RETRIES + 1):
        retry_hint = ""
        if attempt > 1 and last_error:
            retry_hint = f"\n\n【上次生成錯誤，請修正後重試（第 {attempt} 次）】\n錯誤原因：{last_error}\n請針對錯誤原因修正，重新生成完整 JSON。"

        try:
            response_text = await llm_client.call(
                prompt=prompt + retry_hint,
                system_prompt=system_prompt_stage1,
                temperature=0.2 + (attempt - 1) * 0.05,  # 降低溫度，確保 JSON schema 嚴格合規
                response_schema=stage1_schema,
                enable_thinking=False  # 對於結構化任務，關閉 reasoning 確保格式合規
            )

            parsed_data = repair_and_parse_json(response_text)
            if not parsed_data:
                last_error = "JSON 解析失敗，無法取得有效的 JSON 輸出"
                print(f"⚠️ Stage1A 第 {attempt} 次嘗試：JSON 解析失敗")
                continue

            # --- Stage 1B：防呆與組裝 ---
            # 1. 基本欄位防呆
            if "damage_type" not in parsed_data or parsed_data.get("damage_type") is None:
                parsed_data["damage_type"] = "physical"

            stat = parsed_data.get("scaling_stat", "")
            valid_stats = ["STR", "DEX", "INT", "WIS", "CHA", "CON"]
            if not isinstance(stat, str) or stat.upper() not in valid_stats:
                parsed_data["scaling_stat"] = "CON" if slot_type not in ["main_hand", "off_hand"] else "STR"
            else:
                parsed_data["scaling_stat"] = stat.upper()

            # 2. 建立 Equipment 物件（stage1 schema 沒有 slot_type/tier/name 欄位，手動注入）
            tags = parsed_data.get("tags", [])
            if not isinstance(tags, list):
                tags = [tags] if tags else []
            tags = [t for t in tags if t][:1]

            eq_data = {
                "name": "未命名",
                "slot_type": slot_type,
                "tier": tier,
                "item_level": item_level,
                "is_two_handed": parsed_data.get("is_two_handed", False),
                "weapon_type": parsed_data.get("weapon_type"),
                "damage_type": parsed_data.get("damage_type", "physical"),
                "scaling_stat": parsed_data["scaling_stat"],
                "bonuses": parsed_data.get("bonuses", {}),
                "tags": tags,
                "allowed_jobs": parsed_data.get("allowed_jobs", []),
                "executable_triggers": [],
            }

            eq = Equipment(**eq_data)

            # 3. 武器類型防呆
            if slot_type in ["main_hand", "off_hand"] and not eq.weapon_type:
                bonuses = eq.bonuses
                if bonuses.get("INT", 0) > bonuses.get("STR", 0):
                    eq.weapon_type = "法杖"
                elif bonuses.get("WIS", 0) > bonuses.get("STR", 0):
                    eq.weapon_type = "聖印"
                else:
                    eq.weapon_type = "長劍" if slot_type == "main_hand" else "小盾"
            if slot_type not in ["main_hand", "off_hand"]:
                eq.weapon_type = None

            # 4. Stage 1B：模板組裝觸發器
            if max_triggers > 0:
                trigger_choices = parsed_data.get("trigger_choices", [])
                if not trigger_choices:
                    last_error = (
                        f"{tier} 需要 {max_triggers} 個觸發器，但 trigger_choices 為空。"
                        f"請從模板清單中選擇 {max_triggers} 個模板。"
                    )
                    print(f"⚠️ Stage1A 第 {attempt} 次嘗試：{last_error}")
                    eq = None
                    continue

                flat_triggers = _assemble_triggers_from_choices(trigger_choices, tier, max_triggers)

                if len(flat_triggers) < max_triggers:
                    last_error = (
                        f"{tier} 需要 {max_triggers} 個觸發器，"
                        f"但只有 {len(flat_triggers)} 個有效。"
                        f"請確認 template_id 是否在可用模板清單中，"
                        f"且填寫了必要的參數（如 status_name 需要 stat_bonuses）。"
                    )
                    print(f"⚠️ Stage1A 第 {attempt} 次嘗試：{last_error}")
                    eq = None
                    continue

                # 4.5. 進行 soft 驗證，獲取詳細錯誤訊息以指導 AI 重試
                is_valid, error_msg = validate_equipment_affix_constraints(
                    {"executable_triggers": flat_triggers}, tier
                )
                if not is_valid:
                    last_error = error_msg or "品質約束驗證失敗"
                    print(f"⚠️ Stage1A 第 {attempt} 次嘗試：品質約束驗證失敗：{last_error}")
                    eq = None
                    continue

                compiled_triggers = TriggerCompiler.compile_flat_triggers(flat_triggers)
                eq.executable_triggers = compiled_triggers[:max_triggers]
            else:
                eq.executable_triggers = []

            # 5. 套用預算過濾器（includes validate_affix_quality）
            eq = EquipmentBalancer.validate_and_clamp(eq)

            # 6. 檢查觸發器是否因過濾或刪除導致數量不足（T1/T2/T3）
            if max_triggers > 0 and len(eq.executable_triggers) < max_triggers:
                reasons_str = ""
                if hasattr(eq, "_validation_log") and eq._validation_log:
                    reasons = []
                    for log in eq._validation_log:
                        reasons.extend(log.get("reasons", []))
                    if reasons:
                        reasons_str = "。原因：" + "；".join(reasons)
                
                last_error = (
                    f"生成的觸發器數量不足（需要 {max_triggers} 個，實際 {len(eq.executable_triggers)} 個）"
                    f"{reasons_str}。請確認模板選擇符合 {tier} 規範。"
                )
                print(f"⚠️ Stage1A 第 {attempt} 次嘗試：{last_error}")
                eq = None
                continue

            # 7. 通過！跳出重試循環
            print(f"✅ Stage1A 第 {attempt} 次嘗試成功")
            last_error = ""
            break

        except Exception as e:
            last_error = f"發生例外錯誤: {str(e)}"
            print(f"⚠️ Stage1A 第 {attempt} 次嘗試例外：{e}")
            eq = None

    # --- 全部重試失敗 ---
    if eq is None:
        print(f"❌ 裝備生成失敗：{description} ({tier} {slot_type}) 在 {MAX_RETRIES} 次嘗試後仍未成功。最後錯誤：{last_error}")
        return None

    # -----------------------------------------------------------------------
    # Stage 2：故事包裝（名稱、背景、特效說明）
    # -----------------------------------------------------------------------
    try:
        pseudocode = format_triggers_to_pseudocode(eq.executable_triggers)
        stage2_prompt = f"""請為以下裝備填寫中文名稱、故事背景，並將編譯後的邏輯偽代碼精確翻譯為寫實的特殊效果描述：

玩家原始設計主旨：{description}
裝備部位：{slot_type}
稀有度：{tier}
裝備等級：Lv.{item_level}
武器類型：{eq.weapon_type}
加成屬性：{eq.bonuses}
編譯後邏輯偽代碼：
{pseudocode}
"""
        response_stage2_text = await llm_client.call(
            prompt=stage2_prompt,
            system_prompt=system_prompt_stage2,
            temperature=0.6,  # 提高溫度以增加故事創意，防範複製範例
            response_schema=EQUIPMENT_STAGE2_SCHEMA,
            enable_thinking=True
        )
        parsed_stage2 = repair_and_parse_json(response_stage2_text)
        if parsed_stage2:
            eq.name = parsed_stage2.get("name", eq.name)
            eq.description = parsed_stage2.get("description", eq.description)
            if tier_config.get("max_triggers", 0) > 0:
                eq.special_effect = parsed_stage2.get("special_effect", "")
            else:
                eq.special_effect = ""
    except Exception as e2:
        print(f"⚠️ Stage2 錯誤: {e2}")

    return eq

