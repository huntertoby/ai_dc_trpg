# core/item_generator.py
import asyncio
from typing import Optional, Literal
from core.models import Equipment
from core.equipment import EquipmentBalancer
from core.character import Character
from core.compiler import TriggerCompiler
import json
import re

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
            elif act_type == "call_special_mechanic":
                actions.append(f"觸發系統核心特殊機制【{act.get('keyword_name')}】對象為 {target}")
            elif act_type == "modify_dice":
                actions.append(f"修改擲骰結果 [{act.get('param')}] 為 [{act.get('param_value')}]")
            elif act_type == "set_value":
                actions.append(f"設置計算數值 [{act.get('param')}] 為 [{act.get('param_value')}]")
        
        info += " ➔ 行動：" + "、".join(actions)
        lines.append(info)
    return "\n".join(lines)

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

    # 獲取合法武器類型列表與分類關鍵字供 AI 參考
    from core.constants import WEAPON_TYPES, EQUIPMENT_KEYWORDS
    weapon_list_str = ", ".join(WEAPON_TYPES.keys())
    
    # 格式化主題分類引導
    theme_guide = ""
    for k, v in EQUIPMENT_KEYWORDS.items():
        theme_guide += f"- **{k}** ({v['description']}):\n"
        theme_guide += f"  * 事件: {', '.join(v['events'])}\n"
        theme_guide += f"  * 行為: {', '.join(v['actions'])}\n"
        theme_guide += f"  * 內建狀態: {', '.join(v['statuses'])}\n"

    # --- 階段 1 System Prompt (僅設計裝備基礎數值與扁平參數) ---
    system_prompt_stage1 = f"""
    你是一個專業的 TRPG 數值設計師。請根據玩家的描述，設計一件裝備。
    你**必須**生成的裝備部位 (slot_type) 是：`{slot_type}`。

    **【雙軌預算規範 (務必遵守)】**
    1. 裝備等級 (ILv): {item_level} | 稀有度: {tier}
    2. 主屬性預算 (STR, DEX, CON, INT, WIS, CHA): {budgets['primary']} 點。
       - 防護具務必將大部分主預算分配給 `CON`。請務必用滿主屬性預算。
    3. 附屬性預算 (戰鬥/特殊屬性): {budgets['sub']} 點.
       - 你的附屬性槽位上限為: {affix_slots} 條。
       - 合法附屬性限制在：`crit_rate`, `evasion_rate`, `accuracy`, `skill_power`, `tenacity`, `luck`。
    
    **【傳說特效樂高零件規範 (僅限 T1)】**
    當稀有度為 `T1` 時，你**必須**在 `executable_triggers` 中為其設計 1~2 條傳說特效。
    為了防錯，你**只能**使用以下「平鋪樂高零件」，嚴禁使用任何巢狀 trigger 或 flag 設定：

    1. **合法事件 (Event)**：
       - `on_battle_start` (戰鬥開始時)
       - `on_turn_start` (每回合開始時)
       - `on_turn_end` (每回合結束時)
       - `on_cast` (施放主動技能時)
       - `on_hit` (擊中目標後)
       - `on_damaged` (自身受到傷害後)
       - `on_kill` (擊殺敵人時)
       - `on_crit` (造成爆擊時)
       - `on_miss` (攻擊未命中時)
       - `on_dodge` (閃避攻擊時)
       - `on_fatal_damage` (瀕死致命傷前)
       - `on_health_below` (自身生命值低於指定百分比後，必須附帶 hp_below)
       - `on_dice` (擲骰計算前)
       - `on_calculate_damage` (傷害防禦減免計算前)

    2. **合法行動 (Action)**：
       - `inflict_damage`: `flat_value`, `scaling_stat` (僅限 STR, DEX, CON, INT, WIS, CHA, MAX_HP, DAMAGE_TAKEN), `multiplier` (屬性倍率。無係數則全設為 null)
       - `gain_shield`: `flat_value`, `scaling_stat`, `multiplier`, `target` (caster)
       - `heal`: `flat_value`, `scaling_stat`, `multiplier`, `target` (caster), `target_resource` (hp/mp/sanity)
       - `apply_status`: `status_name`, `duration`, `stat_bonuses` (限 p_def, m_def, crit_rate, evasion_rate, accuracy, skill_power, tenacity, luck)
       - `apply_debuff`: `debuff_name`, `duration`, `stat_bonuses`, `target` (target)
       - `remove_status`: `status_name`, `target`
       - `purge_debuffs`: 清除所有負面狀態，支援 `target` (預設為 caster)（⚠️ 注意：僅當描述明確提及『清除狀態/驅散/淨化/解控』時才可使用，未提及時嚴禁填寫！）
       - `apply_shield`: `shield_name` (預設 Shield), `con_multiplier` (體質倍率), `duration`, `target` (預設為 caster)（⚠️ 注意：僅當描述明確提及『獲得護盾』時才可使用，未提及時嚴禁填寫！）
       - `call_special`: `keyword_name` (限定為 Time_Warp 或 Prevent_Death)
       - `modify_dice`: `param` (floor_value 或 roll_modifier), `param_value` (整數)
       - `set_value`: `param` (damage_multiplier 或 defense_ignore_ratio), `param_value` (浮點數)

    **【🚨 觸發事件與行為的隔離鐵律 (嚴禁違反)】**
    - 數值攔截事件（`on_cast`, `on_dice`, `on_calculate_damage`）**只能**觸發 `set_value`, `modify_dice` 行為！
    - 普通戰鬥事件（`on_hit`, `on_turn_start`, `on_health_below` 等其他所有事件）**只能**觸發 `inflict_damage`, `heal`, `gain_shield`, `apply_status`, `apply_debuff`, `remove_status`, `purge_debuffs`, `apply_shield`, `call_special` 等行為！

    **【🚨 瀕死救急/生命百分比觸發鐵律 (防錯與體積縮小 90%)】**
    - 當效果為「當生命值低於 XX% 時觸發」的緊急防禦/救急效果，**你必須使用 `on_health_below` 事件**，並配合填寫限制條件 `hp_below`（百分比必須是 1-100 的整數，如 40，嚴禁寫成 0.4！）。嚴禁使用 `on_turn_start` 來做生命值百分比觸發！
    - 此類生命值低於門檻觸發的救急防禦，**必須強制設置冷卻時間 `cooldown: 99`**（表示每場戰鬥限一次），防止無限重複觸發。
    - **【⚠️ 嚴禁加戲】你必須嚴格遵循玩家描述的功能，嚴禁自行添加玩家沒有要求的機制**：
      - **只有當玩家描述中白紙黑字明確提及『清除所有負面狀態/驅散/淨化/解控』等字眼時**，才可以使用 `purge_debuffs`。**嚴禁**因為看到『無敵護盾』、『絕對領域』、『庇佑』等詞彙就自行演繹、腦補加上 `purge_debuffs`！若無提及，嚴禁填寫！
      - **只有當玩家描述中明確提及『獲得護盾』時**，才可以使用 `apply_shield`。若無提及，嚴禁填寫！
      - 當需要使用清除狀態與護盾時，**你必須優先且僅能使用複合行動 `purge_debuffs` 與 `apply_shield`**。嚴禁將其拆解為多個 `remove_status` 或 `gain_shield` 行動，這可以讓 JSON 體積縮小 90% 以上！

    **【條件限制 (非必填，僅限以下欄位，無則不填)】**
    - `hp_below` (小於指定血量百分比，必須是 1-100 的整數，如 40), `hp_above` (大於指定血量百分比，必須是 1-100 的整數)
    - `caster_has_status` / `caster_not_status` (自身狀態判定)
    - `target_has_status` / `target_not_status` (目標狀態判定)
    - `cooldown` (整數冷卻), `chance` (浮點數機率，例如 0.3)

    **【裝備主題分類參考 (⚠️ 僅在描述有提及時才可搭配)】**
    以下分類關鍵字僅供你挑選零件的『靈感』。即使主題中推薦了某個零件，若玩家的描述中沒有提及該功能，**你依然嚴禁填寫該零件**！例如：描述未提到清除狀態/解控，即使主題推薦了 `purge_debuffs`，你也絕對不准填寫！
    {theme_guide}

    回應請「只」輸出 JSON，不要有任何其他解釋。

    **【JSON 格式範例 (以 T1 王者之劍為例)】**
    {{
        "slot_type": "{slot_type}",
        "tier": "{tier}",
        "item_level": {item_level},
        "is_two_handed": false,
        "weapon_type": "長劍", 
        "damage_type": "physical", 
        "scaling_stat": "STR", 
        "bonuses": {{
            "STR": 20.0,
            "crit_rate": 0.05
        }},
        "executable_triggers": [
            {{
                "event": "on_hit",
                "chance": 0.3,
                "cooldown": 2,
                "actions": [
                    {{
                        "action_type": "inflict_damage",
                        "flat_value": 15.0
                    }},
                    {{
                        "action_type": "apply_debuff",
                        "debuff_name": "Burn",
                        "duration": 3
                    }}
                ]
            }}
        ]
    }}
    """

    prompt = f"描述：{description}\n請嚴格依照部位 `{slot_type}` 生成裝備。"

    # --- 階段 2 System Prompt (故事包裝與外觀描寫) ---
    system_prompt_stage2 = """
    你是一個優秀的奇幻 TRPG 故事設計師。請根據給定的裝備基礎數值以及經過編譯的戰鬥邏輯，為裝備撰寫一個超帥氣、令人驚嘆的中文名稱、背景故事以及寫實的效果說明。

    **【🚨 故事與寫實效果包裝規則】**
    1. **中文名稱 (name)**：必須具備高級感與詩意（例如：不要寫「火焰手套」，改寫「余燼灰滅之擁」）。
    2. **背景描述 (description)**：深入描寫其外觀、質感與歷史淵源，字數 100 字左右，富有畫面感。
    3. **特殊效果敘述 (special_effect)**：
       - **自然語言轉換**：請將技術術語翻譯為符合遊戲說明的自然中文（例如：將 `caster` 翻譯為「自身」、「穿戴者」或「裝備者」；將 `target` 翻譯為「目標」或「敵方」），嚴禁在最終說明中直接出現 `caster` 或 `target` 等代碼英文。
       - **寫實約束**：你必須**嚴格且誠實地**將傳入的「編譯後邏輯偽代碼」翻譯為自然語言，**嚴禁加入任何機制上不符合的詞彙**（例如：不能寫「秒殺神明」或「造成無敵」，除非偽代碼中包含 Prevent_Death 且數值真的能秒殺）。
       - **數值 100% 吻合**：描述中提及的傷害數值、屬性倍率、狀態名稱與持續回合，**必須與偽代碼中的資料完全一致**。
       - **特別約束**：若包含額外追加傷害 (inflict_damage)，請在描述中明確寫出「此額外傷害無視防禦力（真實傷害）」。
    4. **非 T1 階級（T2、T3、T4、T5）的裝備，`special_effect` 欄位必須為空字串 `""`**。

    回應請「只」輸出 JSON，不要有任何其他解釋。

    **【JSON 格式範例】**
    {
        "name": "余燼灰滅之擁",
        "description": "這副手套的邊緣已被無光之火熏得焦黑，當穿戴者握緊雙拳時，手套內部會隱隱流動起暗淡的橘紅熔岩，散發著硫磺與落敗王朝的餘溫。",
        "special_effect": "神聖裁決：擊中敵人時有 30% 機率額外造成 15 點無視防禦力的真實傷害，且有 30% 機率對目標附加灼燒狀態，持續 3 回合；冷卻 2 回合。"
    }
    """

    try:
        # --- 階段 1：生成基礎裝備與扁平觸發器 ---
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt_stage1,
            temperature=0.3
        )
        
        from utils.json_utils import repair_and_parse_json
        parsed_data = repair_and_parse_json(response_text)
        
        if parsed_data:
            # 建立初步模型前的欄位防呆（Pydantic 驗證必填 name）
            if "name" not in parsed_data:
                parsed_data["name"] = "未命名"
            if "description" not in parsed_data:
                parsed_data["description"] = ""
            if parsed_data.get("damage_type") is None:
                parsed_data["damage_type"] = "physical"
            if parsed_data.get("scaling_stat") is None:
                parsed_data["scaling_stat"] = "STR"
                
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

            # 運行 Python 編譯層進行 T1 觸發器編譯與優化
            if tier == "T1":
                flat_triggers = parsed_data.get("executable_triggers", [])
                compiled_triggers = TriggerCompiler.compile_flat_triggers(flat_triggers)
                eq.executable_triggers = compiled_triggers
            else:
                eq.executable_triggers = []

            # 套用主/附屬性預算雙軌制過濾器進行數值裁決與修正
            eq = EquipmentBalancer.validate_and_clamp(eq)

            # --- 階段 2：故事背景、自然語言特效包裝 ---
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
                    temperature=0.2
                )
                parsed_stage2 = repair_and_parse_json(response_stage2_text)
                if parsed_stage2:
                    eq.name = parsed_stage2.get("name", eq.name)
                    eq.description = parsed_stage2.get("description", eq.description)
                    if tier == "T1":
                        eq.special_effect = parsed_stage2.get("special_effect", "")
                    else:
                        eq.special_effect = ""
            except Exception as e_stage2:
                print(f"階段 2 故事包裝失敗，保持預設或空白: {e_stage2}")
                if not eq.name:
                    eq.name = "未命名傳奇裝備"

            return eq
        else:
            print(f"JSON 解析失敗或為空。原始回應內容:\n{response_text}")
            
    except Exception as e:
        print(f"生成裝備失敗: {e}")
        try:
            print(f"原始回應內容: {response_text}")
        except NameError:
            pass
        return None
    return None
