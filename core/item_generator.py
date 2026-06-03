# core/item_generator.py
import asyncio
from typing import Optional, Literal
from core.models import Equipment
from core.equipment import EquipmentBalancer
from core.character import Character
import json
import re

async def generate_equipment_by_ai(
    description: str, 
    item_level: int, 
    tier: Literal["T1", "T2", "T3", "T4", "T5"],
    slot_type: str,
    llm_client
) -> Optional[Equipment]:
    """
    呼叫 AI 生成裝備敘述與初始數值，並通過系統雙軌過濾器校正。
    """
    budgets = EquipmentBalancer.calculate_budgets(item_level, tier)
    affix_slots = EquipmentBalancer.AFFIX_SLOTS.get(tier, 0)

    system_prompt = f"""
    你是一個專業的 TRPG 數值設計師。請根據玩家的描述，設計一件裝備。
    
    **【雙軌預算規範 (務必遵守)】**
    1. 裝備等級 (ILv): {item_level} | 稀有度: {tier}
    2. 主屬性預算 (STR, DEX, CON, INT, WIS, CHA): {budgets['primary']} 點。
       - 請務必將預算「用好用滿」，不要保守。
    3. 附屬性預算 (戰鬥/特殊屬性): {budgets['sub']} 點。
       - 你的附屬性槽位上限為: {affix_slots} 條。
       - **你只能從以下【合法附屬性】中挑選，嚴禁自創**：
         - `crit_rate` (爆擊), `evasion_rate` (閃避), `accuracy` (命中), `cast_speed` (施法速度), `tenacity` (韌性), `luck` (幸運)。
       - 請確保至少提供一條符合裝備敘述的合法附屬性。

    
    **【核心原則：極度專精】**
    挑選 1~2 個主屬性與符合數量的附屬性進行「爆發式分配」，使其威力驚人。
    
    回應請「只」輸出 JSON，不要有任何其他解釋。

    **【JSON 格式範例】**
    {{
        "name": "裝備名稱",
        "description": "一段帥氣的文字敘述",
        "special_effect": "如果是 T1 裝備，請在此寫下一個獨特的傳說特效描述",
        "slot_type": "{slot_type}",
        "tier": "{tier}",
        "item_level": {item_level},
        "is_two_handed": false,
        "bonuses": {{
            "STR": 5,
            "crit_rate": 0.02
        }}
    }}
    """

    prompt = f"描述：{description}\n請根據以上條件生成裝備。"

    try:
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        # 借用 character_creation 的解析邏輯
        from logic.workflows.character_creation import repair_and_parse_json
        parsed_data = repair_and_parse_json(response_text)
        
        if parsed_data:
            # 1. 建立初步模型
            eq = Equipment(**parsed_data)
            # 2. 強制設定 ILv 與 Tier，防止 AI 亂改
            eq.item_level = item_level
            eq.tier = tier
            # 3. 通過系統過濾器進行校正
            balanced_eq = EquipmentBalancer.validate_and_clamp(eq)
            return balanced_eq
            
    except Exception as e:
        print(f"生成裝備失敗: {e}")
        return None
    return None
