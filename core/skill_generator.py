# core/skill_generator.py
import asyncio
import json
import re
from typing import Optional, List, Dict, Any
from core.models import Skill
from core.skill_processor import SkillProcessor
from core.constants import SKILL_KEYWORDS
from utils.json_utils import repair_and_parse_json

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
    
    system_prompt = f"""
    你是一個專業的 TRPG 技能設計師。請根據玩家的描述，設計 **1 個** 技能。
    
    **【階級差異化設計規範】**
    {tier_rules}
    
    **【通用規範】**
    1. **行為類型 (Action Type)**：標註 `damage`, `heal`, `buff`, `debuff`。
    2. **目標類型 (Target Type)**：`single`, `aoe`, `self`, `allies`。
    3. **敘事特效 (Narrative Effect)**：一段帥氣的劇情效果。

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
        "narrative_effect": "一段特效描述..."
    }}
    """

    prompt = f"描述：{description}\n請生成該技能。"
    
    try:
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        parsed_data = repair_and_parse_json(response_text)
        
        if parsed_data:
            if isinstance(parsed_data, list) and len(parsed_data) > 0:
                parsed_data = parsed_data[0]
            
            # 使用本地的修復邏輯
            parsed_data = fix_skill_structure(parsed_data)
            
            skill = Skill(**parsed_data)
            SkillProcessor.validate_and_clamp_skill(skill)
            return skill
    except Exception as e:
        print(f"技能生成失敗: {e}")
    return None

async def generate_starter_skills(char_data: Dict, llm_client) -> List[Skill]:
    """為新角色生成 3 個初始技能 (2個 T5, 1個 T4)"""
    
    t5_rules = get_tier_rules("T5")
    t4_rules = get_tier_rules("T4")

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
    
    try:
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.8
        )
        
        skills_raw = repair_and_parse_json(response_text)
        
        valid_skills = []
        if isinstance(skills_raw, list):
            for s in skills_raw:
                try:
                    # 修復結構
                    s_fixed = fix_skill_structure(s)
                    skill = Skill(**s_fixed)
                    SkillProcessor.validate_and_clamp_skill(skill)
                    valid_skills.append(skill)
                except:
                    continue
        return valid_skills
    except Exception as e:
        print(f"初始技能生成失敗: {e}")
        return []

# 保留舊名稱以維持相容性 (可選)
async def generate_single_skill_test(description: str, tier: str, llm_client) -> Optional[Skill]:
    return await generate_single_skill(description, tier, llm_client)
