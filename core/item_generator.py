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

    # 獲取合法武器類型列表供 AI 參考
    from core.constants import WEAPON_TYPES
    weapon_list_str = ", ".join(WEAPON_TYPES.keys())

    # 根據稀有度動態生成特殊效果的 JSON 範例值與引導说明
    special_effect_example = "傳說特殊效果描述（例如：每次擊中敵人時，有 15% 機率觸發『餘燼爆發』，對目標造成等同於 2.0x 智力的火屬性傷害）" if tier == "T1" else ""

    system_prompt = f"""
    你是一個專業的 TRPG 數值設計師。請根據玩家的描述，設計一件裝備。
    你**必須**生成的裝備部位 (slot_type) 是：`{slot_type}`。

    **【雙軌預算規範 (務必遵守)】**
    1. 裝備等級 (ILv): {item_level} | 稀有度: {tier}
    2. 主屬性預算 (STR, DEX, CON, INT, WIS, CHA): {budgets['primary']} 點。
       - **防護具 (衣物、盔甲、盾牌)** 務必將大部分主預算分配給 `CON` (體質)，這是生存核心。
       - 請務必將預算「用好用滿」，不要保守。
    3. 附屬性預算 (戰鬥/特殊屬性): {budgets['sub']} 點。
       - 你的附屬性槽位上限為: {affix_slots} 條。
       - **你只能從以下【合法附屬性】中挑選，嚴禁自創**：
         - `crit_rate` (爆擊), `evasion_rate` (閃避), `accuracy` (命中), `skill_power` (技威力), `tenacity` (韌性), `luck` (幸運)。
       - 請確保至少提供一條符合裝備敘述的合法附屬性。

    **【傳說特效/特殊磁條規範 (僅限 T1)】**
    1. 當稀有度為 `T1` 時，你**必須**為其設計一條強大、具備戰鬥機制感或獨特敘事感的「傳說特殊效果/特殊磁條」，填入 `special_effect` 欄位。例如：
       - *「每次擊中敵人時，有 15% 機率觸發『餘燼爆發』，對目標造成等同於 2.0x 智力的火屬性傷害。」*
       - *「當生命值低於 30% 時，立即獲得一個相當於最大生命值 50% 的護盾，冷卻時間為 3 回合。」*
       - *「攻擊有機率附加『麥角灼燒』狀態，且對處於該狀態的目標，造成的傷害提高 15%。」*
    2. **非 T1 階級（T2、T3、T4、T5）的裝備，`special_effect` 欄位必須為空字串 `""`**。

    **【武器類型與持握規範 (僅限武器)】**
    1. 如果 `{slot_type}` 是 `main_hand` 或 `off_hand`，請從下表挑選一個最適合的 `weapon_type`：
       {weapon_list_str}
       **手部位置通常應強化對應的攻擊屬性 (如 STR/DEX/INT/WIS)。**
    2. **雙手屬性 (`is_two_handed`)**：
       - 若為 `巨劍`、`巨斧`、`長槍`、`長弓`、`法杖` 等重型武器，務必設為 `true`。
       - **若為雙手武器，`slot_type` 必須設為 `main_hand`**。
    3. **副手規範**：
       - 若 `{slot_type}` 為 `off_hand`，通常應選擇 `小盾`、`巨盾`、`法器`、`魔導書` 或 `副手短劍`。

    **【核心原則：極度專精】**
    挑選 1~2 個主屬性與符合數量的附屬性進行「爆發式分配」，使其威力驚人。
    
    回應請「只」輸出 JSON，不要有任何其他解釋。

    **【JSON 格式範例】**
    {{
        "name": "裝備名稱",
        "description": "一段帥氣的文字敘述",
        "special_effect": "{special_effect_example}",
        "slot_type": "{slot_type}",
        "tier": "{tier}",
        "item_level": {item_level},
        "is_two_handed": false,
        "weapon_type": "長劍", // 必須從上述合法列表中挑選，非武器則為 null
        "damage_type": "physical", // physical 或 magical
        "scaling_stat": "STR", // 該武器對應的主屬性
        "bonuses": {{
            "STR": 5,
            "crit_rate": 0.02
        }}
    }}
    """

    prompt = f"描述：{description}\n請嚴格依照部位 `{slot_type}` 生成裝備。"

    try:
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        # 使用全域的解析邏輯
        from utils.json_utils import repair_and_parse_json
        parsed_data = repair_and_parse_json(response_text)
        
        if parsed_data:
            # 1. 建立初步模型
            eq = Equipment(**parsed_data)
            # 2. 強制設定 ILv, Tier 與 Slot，防止 AI 忽視指令
            eq.item_level = item_level
            eq.tier = tier
            eq.slot_type = slot_type
            
            # 3. 額外防呆：如果 slot 是 main_hand/off_hand 但 AI 沒給 weapon_type，則給予預設
            if slot_type in ["main_hand", "off_hand"] and not eq.weapon_type:
                # 簡單判定：如果有 INT/WIS 可能是法杖/聖印，否則長劍
                if eq.bonuses.get("INT", 0) > eq.bonuses.get("STR", 0):
                    eq.weapon_type = "法杖"
                elif eq.bonuses.get("WIS", 0) > eq.bonuses.get("STR", 0):
                    eq.weapon_type = "聖印"
                else:
                    eq.weapon_type = "長劍" if slot_type == "main_hand" else "小盾"

            # 4. 通過系統過濾器進行校正
            balanced_eq = EquipmentBalancer.validate_and_clamp(eq)
            return balanced_eq
            
    except Exception as e:
        print(f"生成裝備失敗: {e}")
        return None
    return None
