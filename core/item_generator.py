# core/item_generator.py
import asyncio
from typing import Optional, Literal
from core.models import Equipment
from core.equipment import EquipmentBalancer
from core.character import Character
from core.compiler import TriggerCompiler
import json
import re

# ---------------------------------------------------------------------------
# Stage 1 JSON Schema（強制 LM Studio grammar-based sampling）
# ---------------------------------------------------------------------------
EQUIPMENT_STAGE1_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "equipment_stage1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "slot_type":      {"type": "string"},
                "tier":           {"type": "string"},
                "item_level":     {"type": "integer"},
                "is_two_handed":  {"type": "boolean"},
                "weapon_type":    {"type": ["string", "null"]},
                "damage_type":    {"type": "string"},
                "scaling_stat":   {
                    "type": "string",
                    "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
                },
                "bonuses": {
                    "type": "object",
                    "additionalProperties": {"type": "number"}
                },
                "executable_triggers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event":    {"type": "string"},
                            "chance":   {"type": ["number", "null"]},
                            "cooldown": {"type": ["integer", "null"]},
                            "hp_below": {"type": ["integer", "null"]},
                            "hp_above": {"type": ["integer", "null"]},
                            "caster_has_status":  {"type": ["string", "null"]},
                            "caster_not_status":  {"type": ["string", "null"]},
                            "target_has_status":  {"type": ["string", "null"]},
                            "target_not_status":  {"type": ["string", "null"]},
                            "dice_roll": {"type": ["string", "null"]},
                            "actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action_type":     {"type": "string"},
                                        "target":          {"type": ["string", "null"]},
                                        "flat_value":      {"type": ["number", "null"]},
                                        "scaling_stat":    {"type": ["string", "null"]},
                                        "value_multiplier":{"type": ["number", "null"]},
                                        "dice":            {"type": ["string", "null"]},
                                        "divisor":         {"type": ["number", "null"]},
                                        "status_name":     {"type": ["string", "null"]},
                                        "debuff_name":     {"type": ["string", "null"]},
                                        "duration":        {"type": ["integer", "null"]},
                                        "target_resource": {"type": ["string", "null"]},
                                        "stat_bonuses":    {"type": ["object", "null"]},
                                        "dice_range":      {"type": ["array", "null"]},
                                        "keyword_name":    {"type": ["string", "null"]},
                                        "param":           {"type": ["string", "null"]},
                                        "param_value":     {"type": ["number", "null"]}
                                    },
                                    "required": ["action_type"]
                                }
                            }
                        },
                        "required": ["event", "actions"]
                    }
                }
            },
            "required": [
                "slot_type", "tier", "item_level", "is_two_handed",
                "scaling_stat", "bonuses", "executable_triggers"
            ]
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


def format_triggers_to_pseudocode(triggers: list) -> str:
    if not triggers:
        return "無特殊戰鬥效果"

    lines = []
    for i, t in enumerate(triggers):
        event = t.get("event")
        cond = t.get("condition")
        chance = t.get("chance")
        cooldown = t.get("cooldown")

        info = f"效果 {i+1}：觸發事件 [{event}]"
        if chance is not None:
            info += f"，觸發機率 [{int(float(chance)*100)}%]"
        if cooldown is not None:
            info += f"，冷卻時間 [{cooldown} 回合]"
        if cond:
            info += f"，觸發條件 [{cond}]"

        actions = []
        for act in t.get("actions", []):
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
                if flat_f == 0.0:
                    val_str = f"{mult}x 自身的 {stat}"
                else:
                    val_str = f"{flat} + {mult}x 自身的 {stat}"
            else:
                val_str = f"{flat}"

            if act_type == "inflict_damage":
                actions.append(f"對 {target} 造成 {val_str} 點真實傷害")
            elif act_type == "gain_shield":
                actions.append(f"使 {target} 獲得 {val_str} 點護盾")
            elif act_type == "heal":
                res = act.get("target_resource", "hp")
                actions.append(f"使 {target} 恢復 {val_str} 點 {res}")
            elif act_type == "apply_status":
                status_name = act.get("status_name")
                duration = act.get("duration")
                bonuses = act.get("bonuses")
                status_info = f"施加狀態【{status_name}】給 {target}，持續 {duration} 回合"
                if bonuses:
                    status_info += f" (屬性加成: {bonuses})"
                actions.append(status_info)
            elif act_type == "remove_status":
                actions.append(f"清除 {target} 身上的狀態【{act.get('status_name')}】")
            elif act_type == "purge_debuffs":
                actions.append(f"清除 {target} 身上的所有負面狀態")
            elif act_type == "call_special_mechanic":
                actions.append(f"觸發系統核心特殊機制【{act.get('keyword_name')}】對象為 {target}")
            elif act_type == "modify_dice":
                actions.append(f"修改擲骰結果 [{act.get('param')}] 為 [{act.get('param_value')}]")
            elif act_type == "set_value":
                actions.append(f"設置計算數值 [{act.get('param')}] 為 [{act.get('param_value')}]")

        info += " ➔ 行動：" + "、".join(actions)
        lines.append(info)
    return "\n".join(lines)


def _build_theme_hint(description: str) -> str:
    """
    根據玩家描述動態產生少量主題提示，取代原本整塊 EQUIPMENT_KEYWORDS 注入。
    只在描述有明確關鍵字時才加入對應的狀態名稱建議，減少無關 token。
    """
    desc = description.lower()
    hints = []

    if any(w in desc for w in ["火", "燃燒", "灼", "炎", "flame", "fire", "burn"]):
        hints.append("火焰主題可用狀態名稱：Burn")
    if any(w in desc for w in ["冰", "霜", "凍", "frost", "ice", "freeze"]):
        hints.append("冰霜主題可用狀態名稱：Slow、Frostbite")
    if any(w in desc for w in ["雷", "電", "閃", "thunder", "lightning", "shock"]):
        hints.append("雷電主題可用狀態名稱：Stun、Slow")
    if any(w in desc for w in ["暗", "影", "詛咒", "死", "doom", "shadow", "curse", "blind"]):
        hints.append("暗影主題可用狀態名稱：Blind、Doom、Slow")
    if any(w in desc for w in ["聖", "神", "治療", "淨化", "holy", "divine", "heal", "bless"]):
        hints.append("神聖主題可用狀態名稱：Bless、Shield、Immune")
    if any(w in desc for w in ["風", "速", "閃避", "隱", "wind", "swift", "evasion", "invis"]):
        hints.append("疾風主題可用狀態名稱：Invis、Slow")

    if not hints:
        return ""
    return "【主題狀態提示（僅在描述有提及時才可使用）】\n" + "\n".join(f"- {h}" for h in hints)


async def generate_equipment_by_ai(
    description: str,
    item_level: int,
    tier: Literal["T1", "T2", "T3", "T4", "T5"],
    slot_type: str,
    llm_client
) -> Optional[Equipment]:
    """
    呼叫 AI 雙階段生成裝備敘述與數值，第一階段生成扁平邏輯，第二階段進行故事包裝。
    """
    budgets = EquipmentBalancer.calculate_budgets(item_level, tier)
    affix_slots = EquipmentBalancer.AFFIX_SLOTS.get(tier, 0)

    from core.constants import WEAPON_TYPES
    weapon_list_str = ", ".join(WEAPON_TYPES.keys())

    # 動態主題提示（只在描述有對應關鍵字時才注入）
    theme_hint = _build_theme_hint(description)

    # -----------------------------------------------------------------------
    # 階段 1 System Prompt
    # 設計原則：
    #   - 移除 on_cast（已在 compiler 轉為攔截器，語意易混淆）
    #   - apply_status / apply_debuff   明確分離，各自有固定 target 預設
    #   - modify_dice / set_value 獨立成「進階攔截器」區塊，禁止與基礎效果混用
    #   - 移除 purge_debuffs / apply_shield 的主動列舉（只在最後附帶說明）
    #   - 不再注入 EQUIPMENT_KEYWORDS 全表，改用動態 theme_hint
    # -----------------------------------------------------------------------
    system_prompt_stage1 = f"""你是一個專業的 TRPG 數值設計師。請根據玩家的描述，設計一件裝備。
裝備部位 (slot_type) 必須是：`{slot_type}`。

【預算規範】
- 裝備等級: {item_level} | 稀有度: {tier}
- 主屬性預算 (STR/DEX/CON/INT/WIS/CHA): {budgets['primary']} 點，請用滿。防具優先分配 CON。
- 附屬性預算: {budgets['sub']} 點，上限 {affix_slots} 條。
  合法附屬性：crit_rate, evasion_rate, accuracy, skill_power, tenacity, luck
- scaling_stat 只能填：STR / DEX / CON / INT / WIS / CHA（大寫）

【T1 傳說特效規範】
僅 T1 裝備需要在 executable_triggers 設計 1~2 條傳說特效。
其他階級的 executable_triggers 必須是空陣列 []。

▌基礎效果零件（優先使用）
合法事件：
  on_battle_start（戰鬥開始）、on_turn_start（回合開始）、on_turn_end（回合結束）
  on_hit（擊中後）、on_damaged（受傷後）、on_kill（擊殺後）
  on_crit（爆擊後）、on_miss（未命中後）、on_dodge（閃避後）
  on_fatal_damage（瀕死致命傷前）
  on_health_below（生命低於門檻，必須同級附帶 hp_below，值為 1~100 整數）

合法行動：
  inflict_damage  → 對 target 造成真實傷害
    欄位：flat_value（數字）, scaling_stat, value_multiplier, dice（字串如"1d20"）, divisor（浮點數）, target
    target 只能填：caster / target / all_enemies / all_allies

  gain_shield     → 使 target 獲得護盾
    欄位：flat_value, scaling_stat, value_multiplier, dice, divisor, target

  heal            → 使 target 恢復資源
    欄位：flat_value, scaling_stat, value_multiplier, dice, divisor, target, target_resource（hp/mp/sanity）

  apply_status    → 【自身增益專用】對裝備者施加正面狀態，不需填 target（預設 caster）
    欄位：status_name, duration, stat_bonuses
    ⚠️ stat_bonuses 必填至少一個鍵，空 {{}} 代表無效果！

    ┌─────────────── stat_bonuses 完整鍵值參考 ───────────────┐
    │ 防禦類（integer）                                        │
    │   p_def        物理防禦加成      e.g. {{"p_def": 30}}    │
    │   m_def        魔法防禦加成      e.g. {{"m_def": 25}}    │
    │                                                          │
    │ 攻擊/爆擊類（float，爆擊率用 0.0~1.0）                   │
    │   crit_rate    爆擊率加成        e.g. {{"crit_rate": 0.15}} │
    │   skill_power  技能威力倍率加成  e.g. {{"skill_power": 0.3}} │
    │                                                          │
    │ 命中/迴避類（float，0.0~1.0）                            │
    │   evasion_rate 迴避率加成        e.g. {{"evasion_rate": 0.1}} │
    │   accuracy     命中率加成        e.g. {{"accuracy": 0.05}} │
    │                                                          │
    │ 其他戰鬥屬性（integer）                                  │
    │   tenacity     韌性（減傷）加成  e.g. {{"tenacity": 40}} │
    │   luck         幸運加成          e.g. {{"luck": 5}}      │
    │                                                          │
    │ 基礎屬性（integer）                                      │
    │   STR/DEX/CON/INT/WIS/CHA       e.g. {{"STR": 15}}      │
    └──────────────────────────────────────────────────────────┘

    快速對照（依狀態類型選擇）：
      護盾/防禦狀態  → p_def 或 m_def（+20~50）
      狂化/爆發狀態  → STR 或 crit_rate（STR +10~20 / crit_rate +0.1~0.2）
      技能增幅狀態   → skill_power（+0.2~0.5）
      靈敏/閃避狀態  → evasion_rate（+0.1~0.2）或 DEX（+10~20）
      韌性/不屈狀態  → tenacity（+30~60）
      智力/魔力狀態  → INT 或 skill_power
    可同時填多鍵：{{"p_def": 25, "tenacity": 20}}

  apply_debuff    → 【敵人減益專用】對目標施加負面狀態，不需填 target（預設 target）
    欄位：debuff_name, duration, stat_bonuses
    debuff 的 stat_bonuses 填負數以削弱目標：
      {{"p_def": -20}}  削減物理防禦
      {{"evasion_rate": -0.1}}  降低迴避
      {{"crit_rate": -0.1}}  降低爆擊
    或留空 {{}} 表示純標記型 debuff（如 Burn/Slow 由引擎硬編碼處理）

  remove_status   → 清除狀態
    欄位：status_name, target

  call_special    → 觸發特殊機制（限 Time_Warp 或 Prevent_Death）
    欄位：keyword_name

▌進階攔截器零件（僅在描述明確提及「骰子修改」或「無視防禦」時才使用）
合法事件：on_dice（擲骰前）、on_calculate_damage（傷害計算前）
合法行動：
  modify_dice  → param: floor_value 或 roll_modifier，param_value: 整數
  set_value    → param: damage_multiplier 或 defense_ignore_ratio，param_value: 浮點數

⚠️ 進階攔截器行動（modify_dice / set_value）必須單獨放在 on_dice 或 on_calculate_damage 事件中，
   嚴禁與 inflict_damage / heal 等基礎行動混放在同一個 trigger！

▌觸發條件（非必填，與 event 同級）
  chance（0.0~1.0）, cooldown（整數）
  hp_below（整數 1~100）, hp_above（整數 1~100）
  caster_has_status / caster_not_status, target_has_status / target_not_status

  dice_roll + dice_range：【隨機分支】想讓同一觸發器根據骰點走不同結果時使用。
    在 trigger 設 "dice_roll": "1d2"，再對每個 action 設 "dice_range": [min, max]，
    骰點落在範圍內的 action 才執行，其餘跳過。
    典型用途：「50% 狂化 OR 50% 自傷」、「三選一隨機異常狀態」等互斥效果。
    ⚠️ 沒有 dice_roll 時，action 不需要填 dice_range（填了無效）。

▌瀕死救急特別規則
  使用 on_health_below 時，必須設 cooldown: 99（每場戰鬥限一次）。

▌flat_value 型別規定
  flat_value 只能是數字（如 15.0），嚴禁寫骰子字串。
  骰子數值請用獨立的 dice 欄位（如 "dice": "1d20"）搭配 divisor。

▌特殊行動附錄（只在描述明確提及時才使用）
  purge_debuffs：清除目標所有負面狀態。僅當描述提到「驅散/淨化/解控」時才可使用。
  apply_shield：施加護盾狀態。僅當描述提到「獲得護盾」時才可使用。
    欄位：shield_name, flat_value, scaling_stat, value_multiplier, dice, divisor, duration, target

{theme_hint}

只輸出 JSON，不要任何說明文字。

【JSON 範例 甲：進攻型武器（涵蓋：on_hit / on_turn_start / chance / cooldown / inflict_damage 完整三欄 / apply_debuff 標記型 / apply_debuff 削弱型 / dice_roll 隨機分支 / apply_status 增益）】
{{
  "slot_type": "{slot_type}",
  "tier": "{tier}",
  "item_level": {item_level},
  "is_two_handed": false,
  "weapon_type": "長劍",
  "damage_type": "physical",
  "scaling_stat": "STR",
  "bonuses": {{"STR": 22.0, "crit_rate": 0.06}},
  "executable_triggers": [
    {{
      "event": "on_hit",
      "chance": 0.35,
      "cooldown": 2,
      "actions": [
        {{"action_type": "inflict_damage", "flat_value": 28.0, "scaling_stat": "STR", "value_multiplier": 1.6, "target": "target"}},
        {{"action_type": "apply_debuff", "debuff_name": "Burn", "duration": 3}}
      ]
    }},
    {{
      "event": "on_turn_start",
      "dice_roll": "1d2",
      "actions": [
        {{"action_type": "apply_status", "status_name": "血怒", "duration": 2, "stat_bonuses": {{"STR": 18, "crit_rate": 0.18}}, "dice_range": [2, 2]}},
        {{"action_type": "apply_debuff", "debuff_name": "破甲", "duration": 2, "stat_bonuses": {{"p_def": -22}}, "dice_range": [1, 1]}}
      ]
    }}
  ]
}}

【JSON 範例 乙：生存型防具（涵蓋：on_damaged / on_health_below / cooldown:99 救急 / apply_status 防禦增益 / heal 帶 scaling / gain_shield / 多行動同一 trigger）】
{{
  "slot_type": "{slot_type}",
  "tier": "{tier}",
  "item_level": {item_level},
  "is_two_handed": false,
  "weapon_type": null,
  "damage_type": "physical",
  "scaling_stat": "CON",
  "bonuses": {{"CON": 22.0, "p_def": 14.0, "tenacity": 9.0}},
  "executable_triggers": [
    {{
      "event": "on_damaged",
      "cooldown": 2,
      "actions": [
        {{"action_type": "apply_status", "status_name": "不屈之盾", "duration": 2, "stat_bonuses": {{"p_def": 32, "tenacity": 26}}}}
      ]
    }},
    {{
      "event": "on_health_below",
      "hp_below": 30,
      "cooldown": 99,
      "actions": [
        {{"action_type": "heal", "flat_value": 0.0, "scaling_stat": "CON", "value_multiplier": 1.8, "target": "caster"}},
        {{"action_type": "gain_shield", "flat_value": 15.0, "scaling_stat": "CON", "value_multiplier": 0.6, "target": "caster"}}
      ]
    }}
  ]
}}
"""

    prompt = f"描述：{description}\n請嚴格依照部位 `{slot_type}` 生成裝備。"

    # -----------------------------------------------------------------------
    # 階段 2 System Prompt（故事包裝，使用 schema 強制輸出格式）
    # -----------------------------------------------------------------------
    system_prompt_stage2 = """你是一個優秀的奇幻 TRPG 故事設計師。根據裝備數值與編譯後的戰鬥邏輯，撰寫中文名稱、背景故事與效果說明。

規則：
1. name：具備高級感與詩意（例：不要寫「火焰手套」，改寫「余燼灰滅之擁」）。
2. description：描寫外觀、質感與歷史淵源，約 100 字，富有畫面感。
3. special_effect：
   - 將 caster 翻譯為「裝備者」，target 翻譯為「目標」，嚴禁直接出現英文代碼。
   - 嚴格且誠實地翻譯傳入的偽代碼，禁止添加未在偽代碼中存在的機制。
   - 數值、狀態名稱、持續回合必須與偽代碼完全一致。
   - 含 inflict_damage 時，需在說明中標注「無視防禦力（真實傷害）」。
4. 非 T1 裝備的 special_effect 必須是空字串 ""。

只輸出 JSON，不要任何說明文字。

範例：
{
  "name": "余燼灰滅之擁",
  "description": "這副手套的邊緣已被無光之火熏得焦黑，穿戴者握緊雙拳時，內部隱隱流動著暗淡橘紅熔岩，散發硫磺與落敗王朝的餘溫。",
  "special_effect": "灰燼裁決：擊中敵人時有 30% 機率額外造成 15 點無視防禦力的真實傷害，並對目標附加灼燒狀態持續 3 回合；冷卻 2 回合。"
}
"""

    try:
        # --- 階段 1：生成基礎裝備與扁平觸發器（使用 json_schema 強制格式）---
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt_stage1,
            temperature=0.3,
            response_schema=EQUIPMENT_STAGE1_SCHEMA
        )

        from utils.json_utils import repair_and_parse_json
        parsed_data = repair_and_parse_json(response_text)

        if parsed_data:
            # 建立初步模型前的欄位防呆
            if "name" not in parsed_data:
                parsed_data["name"] = "未命名"
            if "description" not in parsed_data:
                parsed_data["description"] = ""
            if parsed_data.get("damage_type") is None:
                parsed_data["damage_type"] = "physical"

            # scaling_stat 防呆
            stat = parsed_data.get("scaling_stat")
            if not isinstance(stat, str) or stat.upper() not in ["STR", "DEX", "INT", "WIS", "CHA", "CON"]:
                parsed_data["scaling_stat"] = "STR"
            else:
                parsed_data["scaling_stat"] = stat.upper()

            eq = Equipment(**parsed_data)
            eq.item_level = item_level
            eq.tier = tier
            eq.slot_type = slot_type

            # 手部武器預設防呆
            if slot_type in ["main_hand", "off_hand"] and not eq.weapon_type:
                if eq.bonuses.get("INT", 0) > eq.bonuses.get("STR", 0):
                    eq.weapon_type = "法杖"
                elif eq.bonuses.get("WIS", 0) > eq.bonuses.get("STR", 0):
                    eq.weapon_type = "聖印"
                else:
                    eq.weapon_type = "長劍" if slot_type == "main_hand" else "小盾"

            # 確保非武器部位的 weapon_type 為 None
            if slot_type not in ["main_hand", "off_hand"]:
                eq.weapon_type = None

            # 編譯 T1 觸發器
            if tier == "T1":
                flat_triggers = parsed_data.get("executable_triggers", [])
                compiled_triggers = TriggerCompiler.compile_flat_triggers(flat_triggers)
                eq.executable_triggers = compiled_triggers
            else:
                eq.executable_triggers = []

            # 套用預算過濾器
            eq = EquipmentBalancer.validate_and_clamp(eq)

            # --- 階段 2：故事背景、自然語言特效包裝（使用 json_schema 強制格式）---
            pseudocode = format_triggers_to_pseudocode(eq.executable_triggers)
            stage2_prompt = f"""請為以下裝備填寫令人驚嘆的中文名稱、故事背景，並將編譯後的邏輯偽代碼精確翻譯為寫實的特殊效果描述：

裝備部位：{slot_type}
稀有度：{tier}
裝備等級：Lv.{item_level}
武器類型：{eq.weapon_type}
加成屬性：{eq.bonuses}
編譯後邏輯偽代碼：
{pseudocode}
"""
            try:
                response_stage2_text = await llm_client.call(
                    prompt=stage2_prompt,
                    system_prompt=system_prompt_stage2,
                    temperature=0.7,
                    response_schema=EQUIPMENT_STAGE2_SCHEMA
                )
                parsed_stage2 = repair_and_parse_json(response_stage2_text)
                if parsed_stage2:
                    eq.name = parsed_stage2.get("name", eq.name)
                    eq.description = parsed_stage2.get("description", eq.description)
                    if tier == "T1":
                        eq.special_effect = parsed_stage2.get("special_effect", "")
                    else:
                        eq.special_effect = ""
            except Exception as e2:
                print(f"Stage2 錯誤: {e2}")

        else:
            return None

        return eq

    except Exception as e:
        print(f"generate_equipment 錯誤: {e}")
        return None
