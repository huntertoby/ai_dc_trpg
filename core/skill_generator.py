# core/skill_generator.py
import asyncio
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from core.models import Skill
from core.skill_processor import SkillProcessor
from core.constants import SKILL_KEYWORDS
from utils.json_utils import repair_and_parse_json

# 定義互斥關鍵字組合
CONFLICTING_GROUPS = [
    ({"Invis", "Taunt"}, "隱身 (Invis) 與 嘲諷 (Taunt) 不能同時存在"),
    ({"Combo_Starter", "Combo_Finisher"}, "連擊起手 (Combo_Starter) 與 連擊終結 (Combo_Finisher) 不能同時存在"),
    ({"Levitate", "Root"}, "浮空 (Levitate) 與 定身 (Root) 不能同時存在"),
    ({"Banish", "Chain"}, "放逐 (Banish) 與 連鎖 (Chain) 不能同時存在"),
    ({"Banish", "Multi-hit"}, "放逐 (Banish) 與 多重打擊 (Multi-hit) 不能同時存在"),
    ({"Doom", "Execute"}, "厄運宣告 (Doom) 與 處決 (Execute) 不能同時存在"),
    ({"Stun", "Silence"}, "暈眩 (Stun) 已包含沉默效果，兩者不應共存"),
    ({"Stun", "Root"}, "暈眩 (Stun) 已包含定身效果，兩者不應共存"),
    ({"Silence", "Root"}, "沉默 (Silence) 與 定身 (Root) 同時存在代表極端的限制，應避免冗餘"),
    ({"Vampiric_Aura", "Lifesteal"}, "吸血光環 (Vampiric_Aura) 與 個人吸血 (Lifesteal) 重複，請二選一"),
    ({"Stat_Swap", "Overload"}, "屬性反轉 (Stat_Swap) 與 超載 (Overload) 機制衝突"),
    ({"Mimicry", "Copy"}, "擬態 (Mimicry) 與 鏡像 (Copy) 同時存在會導致複製邏輯混亂"),
]

def validate_keywords_safety(keywords: List[str]) -> Optional[str]:
    """
    檢查關鍵字中是否有衝突，若有，回傳第一個找到的衝突說明；否則回傳 None。
    """
    kw_set = set(keywords)
    for group, error_msg in CONFLICTING_GROUPS:
        if group.issubset(kw_set):
            return error_msg
    return None

def fix_skill_structure(d):
    if isinstance(d, dict):
        # 1. 修復遺失的名字
        if "name" not in d:
            d["name"] = "未知技能"

        # 2. 修復 tier
        if "tier" in d and isinstance(d["tier"], int):
            d["tier"] = f"T{d['tier']}"
        if "tier" not in d:
            d["tier"] = "T5"
        
        # 3. 修復 formula 結構異常 (如 denominator)
        if "formula" in d:
            f = d["formula"]
            if isinstance(f, str):
                d["formula"] = { "type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0 }
            elif isinstance(f, dict):
                if "denominator" in f:
                    f["divisor"] = f.pop("denominator")
                if "multiplier_value" in f:  # 處理 AI 自己發明的值
                    f.pop("multiplier_value")
                if "base_stat" in f and f["base_stat"] not in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
                    f["base_stat"] = "STR"
        else:
            d["formula"] = { "type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0 }
            
        # 4. 強制組裝成 mechanics
        if "mechanics" not in d:
            mechanics_keys = ["action_type", "formula", "cost", "keywords", "target_type", "narrative_effect", "custom_logic", "mp_cost"]
            new_mechanics = {}
            for k in list(d.keys()):
                if k in mechanics_keys or k == "mp_cost":
                    val = d.pop(k)
                    if k == "mp_cost": new_mechanics["cost"] = {"MP": val}
                    else: new_mechanics[k] = val
            d["mechanics"] = new_mechanics
            if "description" not in d: d["description"] = d.get("name", "未命名技能")
            if "action_type" not in d["mechanics"]: d["mechanics"]["action_type"] = "damage"
            if "target_type" not in d["mechanics"]: d["mechanics"]["target_type"] = "single"
            if "cost" not in d["mechanics"]: d["mechanics"]["cost"] = {}
            if "keywords" not in d["mechanics"]: d["mechanics"]["keywords"] = []
            if "custom_logic" not in d["mechanics"]: d["mechanics"]["custom_logic"] = ""
            if "narrative_effect" not in d["mechanics"]: d["mechanics"]["narrative_effect"] = ""
            
        # 確保 mechanics 內的字段完整
        m = d["mechanics"]
        if "action_type" not in m: m["action_type"] = "damage"
        if "target_type" not in m: m["target_type"] = "single"
        if "cost" not in m: m["cost"] = {}
        if "keywords" not in m: m["keywords"] = []
        if "custom_logic" not in m: m["custom_logic"] = ""
        if "narrative_effect" not in m: m["narrative_effect"] = ""
        if "formula" not in m: m["formula"] = d["formula"]

        # 5. 修復 executable_triggers
        if "executable_triggers" not in d:
            d["executable_triggers"] = []
        
    return d

def get_tier_rules(tier: str) -> str:
    """獲取不同階級的生成規則"""
    if tier == "T1":
        return """
        - **這是 T1 傳說禁咒！**
        - **公式分母**：單體至少 5.0，AoE 至少 7.5 (極致倍率)。
        - **關鍵字**：挑選 3 個關鍵字形成變態連段 (如 Sacrifice + Lifesteal + Multi-hit)。
        - **消耗**：極端代價。除了至少 100 MP，還必須消耗巨量 SAN (理智) 或加上自殘代價。
        - **自訂邏輯 (custom_logic)**：必須填寫！寫下一個破壞遊戲規則的機制。
        - **傳說級觸發器 (executable_triggers)**：你必須為這個技能設計 1~2 個結構化被動觸發器，填入 `executable_triggers` 欄位（見下方說明）。
        """
    elif tier == "T2":
        return """
        - **這是 T2 史詩絕學！**
        - **公式分母**：單體至少 8.0，AoE 至少 12.0。
        - **關鍵字**：挑選 2 個關鍵字。
        - **消耗**：高消耗 (50~80 MP)。
        - **自訂邏輯 (custom_logic)**：必須留空 ("")。
        """
    elif tier == "T3":
        return """
        - **這是 T3 專家奧義！**
        - **公式分母**：單體至少 10.0，AoE 至少 15.0。
        - **關鍵字**：挑選 1~2 個關鍵字。
        - **消耗**：中高消耗 (30~50 MP)。
        - **自訂邏輯 (custom_logic)**：必須留空 ("")。
        """
    elif tier == "T4":
        return """
        - **這是 T4 進階技巧！**
        - **公式分母**：單體至少 12.0，AoE 至少 18.0。
        - **關鍵字**：最多只能挑選 1 個關鍵字。
        - **消耗**：中低消耗 (15~30 MP)。
        - **自訂邏輯 (custom_logic)**：必須留空 ("")。
        """
    else: # T5
        return """
        - **這是 T5 基礎招式！**
        - **公式分母**：單體至少 15.0，AoE 至少 22.5。
        - **關鍵字**：不可挑選任何關鍵字 (必須為空列表 [])。
        - **消耗**：極低 (5~10 MP)。
        - **自訂邏輯 (custom_logic)**：必須留空 ("")。
        """

async def generate_single_skill(description: str, tier: str, llm_client) -> Optional[Skill]:
    """生成單一技能"""
    tier_rules = get_tier_rules(tier)
    conflict_instructions = "嚴禁同時挑選互斥的關鍵字組，包括：\n" + "\n".join([f"- {msg}" for _, msg in CONFLICTING_GROUPS])
    
    triggers_guide = ""
    triggers_json_example = "[]"
    if tier == "T1":
        triggers_guide = """
    **【傳說技能被動觸發器規範 (僅限 T1)】**
    當階級為 `T1` 時，你**必須**在 `executable_triggers` 欄位提供該技能附帶的被動觸發器 JSON 列表（當角色學會此技能時在戰鬥中自動生效）。
    結構規範如下：
    - `event` (觸發事件名，必須是下列之一)：
      - `'on_prepare'` (命中判定前，用於修改命中、爆擊等 flags)
      - `'on_dice'` (擲骰計算前，用於修改點數或補底)
      - `'on_calculate_damage'` (傷害減免計算前，用於修改無視防禦比例或傷害加倍)
      - `'on_hit'` (擊中目標後，在此時目標血量已被扣減)
      - `'on_damaged'` (受到任何傷害後，自身或目標)
      - `'on_kill'` (擊殺目標後)
      - `'on_health_below'` (自身血量低於指定百分比後，必須附帶 `health_threshold`)
      - `'on_health_up'` (自身或目標獲得治療後)
      - `'on_turn_start'` (回合開始時)
      - `'on_turn_end'` (回合結束時)
    - 條件過濾器 (選擇性填寫)：
      - `health_threshold` (浮點數，僅當 event 為 'on_health_below' 時): 觸發血量百分比門檻 (如 30.0 代表 30%)
      - `target_health_below` (浮點數): 擊中時目標血量百分比必須小於或等於此值才觸發 (如 30.0)
      - `target_health_above` (浮點數): 擊中時目標血量百分比必須大於或等於此值才觸發 (如 70.0)
    - `actions` (觸發行為列表，每個對象包含)：
      - `action_type` (必須是下列之一)：
        - `'inflict_damage'`: 造成額外傷害 (可設定 `flat_value`, `scaling_stat` 如 "STR" 或 "MAX_HP", `value_multiplier` 如 3.5, `damage_type` 通常為 "true_damage")
        - `'gain_shield'`: 獲得臨時護盾 (可設定 `flat_value`, `scaling_stat`, `value_multiplier`，會增加 temp_hp 並賦予 Shield 狀態)
        - `'heal'`: 恢復生命/法力/理智 (可設定 `flat_value`, `scaling_stat`, `value_multiplier`, `target_resource` 為 "hp"/"mp"/"sanity")
        - `'apply_status'`: 施加狀態。必須設定 `status_name`。如果施加的是系統內建狀態（如 'Burn', 'Stun', 'Slow' 等），可直接填入；如果是自定義狀態（如『魔神烙印』），請將 `status_name` 設為自定義名稱，並在本 Action 對象內提供額外的 `executable_triggers` 列表，用於定義該自定義狀態在目標身上生效時的被動觸發器（例如在 `on_calculate_damage` 時將 `damage_multiplier` 設為 1.15，並在 `on_damaged` 時執行 `remove_status` 移除自身，以實現單次傷害增幅）。
        - `'remove_status'`: 清除狀態 (必須設定 `status_name`)
        - `'call_special_mechanic'`: 特殊機制 (必須設定 `keyword_name` 為 'Time_Warp')
        - `'set_flag'`: 攔截器標記 (僅適用於 on_prepare/on_dice/on_calculate_damage，`param` 為 "is_absolute_hit"/"is_crit"，`param_value` 為 true/false)
        - `'set_value'`: 攔截器數值 (僅適用於 on_prepare/on_calculate_damage，`param` 為 "defense_ignore_ratio"/"damage_multiplier"，`param_value` 為浮點數如 0.5)
        - `'modify_dice'`: 攔截器骰子修正 (僅適用於 on_dice，`param` 為 "floor_value"/"roll_modifier"，`param_value` 為整數如 15)
      - `target` (作用目標，必須是下列之一)：
        - `'caster'` (裝備/狀態持有者)
        - `'target'` (攻擊對象，或攻擊自身者)
        - `'random_enemy'` (隨機單一敵人)
      - `chance` (浮點數，觸發機率，0.0 到 1.0，預設 1.0)
        """
        triggers_json_example = """[
            {
                "event": "on_hit",
                "actions": [
                    {
                        "action_type": "apply_status",
                        "target": "target",
                        "status_name": "魔神烙印",
                        "duration": 2,
                        "chance": 0.3,
                        "executable_triggers": [
                            {
                                "event": "on_calculate_damage",
                                "actions": [
                                    {
                                        "action_type": "set_value",
                                        "param": "damage_multiplier",
                                        "param_value": 1.15
                                    }
                                ]
                            },
                            {
                                "event": "on_damaged",
                                "actions": [
                                    {
                                        "action_type": "remove_status",
                                        "target": "caster",
                                        "status_name": "魔神烙印"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]"""

    system_prompt = f"""
    你是一個專業的 TRPG 技能設計師。請根據玩家的描述，設計 **1 個** 技能。
    
    **【階級差異化設計規範】**
    {tier_rules}

    **【關鍵字互斥規則】**
    {conflict_instructions}
    
    **【通用規範】**
    1. **行為類型 (Action Type)**：標註 `damage`, `heal`, `buff`, `debuff`。
    2. **目標類型 (Target Type)**：`single`, `aoe`, `self`, `allies`。
    3. **敘事特效 (Narrative Effect)**：一段帥氣的劇情效果。
    {triggers_guide}

    **【合法關鍵字】**: {", ".join(SKILL_KEYWORDS)}

    **【輸出格式】**
    你必須輸出一個 JSON 對象。所有內容必須使用「繁體中文」。
    {{
        "name": "技能名稱",
        "description": "簡短描述",
        "tier": "{tier}",
        "action_type": "damage",
        "target_type": "single",
        "cost": {{"MP": 20}},
        "formula": {{ "type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 12.0 }},
        "keywords": [],
        "custom_logic": "",
        "narrative_effect": "一段特效描述...",
        "executable_triggers": {triggers_json_example}
    }}
    """

    prompt = f"描述：{description}\n請生成該技能。"
    
    for attempt in range(3):
        try:
            response_text = await llm_client.call(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7 + (attempt * 0.1)
            )
            
            parsed_data = repair_and_parse_json(response_text)
            
            if parsed_data:
                if isinstance(parsed_data, list) and len(parsed_data) > 0:
                    parsed_data = parsed_data[0]
                
                # 使用本地的修復邏輯
                parsed_data = fix_skill_structure(parsed_data)
                
                skill = Skill(**parsed_data)
                
                conflict_err = validate_keywords_safety(skill.mechanics.keywords)
                if conflict_err:
                    print(f"⚠️ 生成技能 '{skill.name}' 出現衝突 ({conflict_err})，重試中 (嘗試 {attempt + 1}/3)...")
                    prompt = f"描述：{description}\n\n【注意】上次生成出現了關鍵字衝突：{conflict_err}。請重新生成，並避開此衝突。"
                    continue
                
                SkillProcessor.validate_and_clamp_skill(skill)
                return skill
        except Exception as e:
            print(f"技能生成失敗 (嘗試 {attempt + 1}/3): {e}")
            
    return None

async def generate_starter_skills(char_data: Dict, llm_client) -> List[Skill]:
    """為新角色生成 3 個初始技能 (2個 T5, 1個 T4)"""
    t5_rules = get_tier_rules("T5")
    t4_rules = get_tier_rules("T4")
    conflict_instructions = "嚴禁同時挑選互斥的關鍵字組，包括：\n" + "\n".join([f"- {msg}" for _, msg in CONFLICTING_GROUPS])

    system_prompt = f"""
    你是一個專業的 TRPG 技能設計師。請為以下角色設計 **3 個** 初始技能。
    
    **【角色資訊】**
    名稱：{char_data.get('name')}
    職業：{char_data.get('job_name')}
    背景：{char_data.get('background')}

    **【技能設計規範】**
    你必須生成：
    1. **2 個 T5 技能 (基礎招式)**：
    {t5_rules}
    
    2. **1 個 T4 技能 (進階技巧)**：
    {t4_rules}

    **【關鍵字互斥規則】**
    {conflict_instructions}

    **【合法關鍵字】**: {", ".join(SKILL_KEYWORDS)}

    **【輸出格式】**
    必須輸出一個 JSON 列表，每個元素符合扁平結構。所有內容必須使用「繁體中文」。
    [
        {{
            "name": "技能名稱",
            "description": "簡短描述",
            "tier": "T5",
            "action_type": "damage",
            "target_type": "single",
            "cost": {{"MP": 8}},
            "formula": {{ "type": "multiplier", "base_stat": "STR", "dice": "2d6+2", "divisor": 15.0 }},
            "keywords": [],
            "narrative_effect": "..."
        }}
    ]
    """

    prompt = "請根據角色背景生成 3 個初始技能。"
    
    for attempt in range(3):
        try:
            response_text = await llm_client.call(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.8
            )
            
            skills_raw = repair_and_parse_json(response_text)
            
            valid_skills = []
            has_conflict = False
            first_conflict_msg = ""
            
            if isinstance(skills_raw, list):
                for s in skills_raw:
                    try:
                        s_fixed = fix_skill_structure(s)
                        skill = Skill(**s_fixed)
                        
                        conflict_err = validate_keywords_safety(skill.mechanics.keywords)
                        if conflict_err:
                            has_conflict = True
                            first_conflict_msg = f"技能 '{skill.name}' 存在衝突：{conflict_err}"
                            break
                            
                        SkillProcessor.validate_and_clamp_skill(skill)
                        valid_skills.append(skill)
                    except:
                        continue
                        
            if has_conflict or len(valid_skills) < 3:
                err_msg = first_conflict_msg if has_conflict else "生成的初始技能數量不足 3 個"
                print(f"⚠️ 初始技能生成未通過校驗 ({err_msg})，重試中 (嘗試 {attempt + 1}/3)...")
                prompt = f"請根據角色背景生成 3 個初始技能。\n\n【注意】上次生成失敗原因：{err_msg}。請重新生成，確保完全無衝突且數量正確。"
                continue
                
            return valid_skills
        except Exception as e:
            print(f"初始技能生成失敗 (嘗試 {attempt + 1}/3): {e}")
            
    return []

async def generate_single_skill_test(description: str, tier: str, llm_client) -> Optional[Skill]:
    return await generate_single_skill(description, tier, llm_client)
