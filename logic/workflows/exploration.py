import random
from datetime import datetime
from typing import Dict, Any
from core.character import Character
from core.models import AreaSchema, BuildingSchema
from core.constants import STAMINA_RESTORE_COST
from core.world import WorldManager
from core.guild import GuildManager
from core.monster_engine import MonsterEngine

def rest_character_workflow(character: Character) -> Dict[str, Any]:
    """
    處理旅店/酒館休息邏輯。補滿體力，並處理付費或免費次數限制。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if character.data.last_free_rest_date != today:
        character.data.last_free_rest_date = today
        character.data.vitality.stamina = character.max_stamina
        character.save()
        return {"success": True, "type": "free", "message": "🍺 體力已補滿(今日免費)！"}
    elif character.data.gold >= STAMINA_RESTORE_COST:
        character.data.gold -= STAMINA_RESTORE_COST
        character.data.last_paid_rest_date = today
        character.data.vitality.stamina = character.max_stamina
        character.save()
        return {"success": True, "type": "paid", "cost": STAMINA_RESTORE_COST, "message": f"💰 支付 {STAMINA_RESTORE_COST}G，體力已補滿！"}
    else:
        return {"success": False, "reason": "gold", "message": "❌ 金幣不足或次數上限。"}

async def npc_talk_workflow(character: Character, building: BuildingSchema, llm_client) -> Dict[str, Any]:
    """
    處理與 NPC 的交談邏輯。扣體力、生成傳聞、與 LLM 取得對話，並存檔。
    """
    cost = building.talk_cost
    if character.data.vitality.stamina < cost:
        return {"success": False, "reason": "stamina", "message": "❌ 體力不足。"}
    
    character.data.vitality.stamina -= cost
    character.save()
    
    is_rumor = random.random() < building.rumor_rate
    target_rumor = await GuildManager.generate_rumor(character, *character.data.location, llm_client) if is_rumor else None
    
    sys_prompt = f"扮演 NPC：{building.npc_name}。特質：{building.npc_traits}。資訊：{target_rumor if is_rumor else '無'}。70字內對話，只輸出說的話。"
    
    try:
        content = await llm_client.call("聊天", sys_prompt)
        if is_rumor and target_rumor and target_rumor not in character.data.known_rumors:
            character.data.known_rumors.append(target_rumor)
            character.save()
        return {
            "success": True,
            "dialogue": content.strip(),
            "is_rumor": is_rumor,
            "rumor": target_rumor
        }
    except Exception as e:
        return {"success": False, "reason": "error", "message": f"❌ 錯誤: {e}"}

async def deep_exploration_workflow(character: Character, area: AreaSchema, user_id: str, llm_client) -> Dict[str, Any]:
    """
    處理深入探索邏輯。扣體力、增加探索紀錄、呼叫 LLM 生成情境描述，並存檔。
    """
    if character.data.vitality.stamina < 10:
        return {"success": False, "reason": "stamina", "message": "❌ 體力不足。"}
    
    character.data.vitality.stamina -= 10
    if str(user_id) not in area.interacted_users:
        area.interacted_users.append(str(user_id))
    character.save()
    WorldManager.save_area(area)
    
    p = character.data.personality
    char_traits = f"背景：{character.data.background}\n信仰：{p.belief} | 缺點：{p.flaw} | 恐懼：{p.fear}"
    char_status = f"{character.data.job_name}(Lv.{character.data.level})"
    hp_pct = (character.data.vitality.hp / character.data.vitality.max_hp) * 100
    health_desc = "受傷嚴重" if hp_pct < 30 else ("略顯疲態" if hp_pct < 70 else "狀態良好")
    
    area_info = f"區域：{area.name} ({area.type})\n描述：{area.description}\n生態標籤：{', '.join(area.ecology_tags)}\n威脅等級：{area.threat_level}"
    
    sys_prompt = f"""
    你是一個充滿想像力的 TRPG GM。
    
    【環境資訊】
    {area_info}
    
    【角色資訊】
    角色：{character.data.name} ({char_status})
    狀態：{health_desc}
    特質：{char_traits}
    
    請根據以上資訊生成一個即時發生的「探索困境」或「奇遇事件」。
    要求：
    1. 敘事風格要有代入感，能夠體現該區域的生態特色。
    2. **特別注意**：嘗試將角色的背景、恐懼或缺點融入事件中，讓事件對該角色具有個人意義。
    3. 字數控制在 100 字以內。
    4. 只輸出故事敘事，不要有 GM 的開場白（如「好的，...」）。
    """
    
    try:
        txt = await llm_client.call("生成探索事件", sys_prompt)
        return {"success": True, "event_text": txt}
    except Exception as e:
        return {"success": False, "reason": "error", "message": f"❌ 錯誤: {e}"}

async def hunt_workflow(character: Character, area: AreaSchema, llm_client) -> Dict[str, Any]:
    """
    處理狩獵邏輯。扣體力、增加區域威脅度，並生成怪物群。
    """
    COST = 15
    if character.data.vitality.stamina < COST:
        return {"success": False, "reason": "stamina", "message": "❌ 體力不足。"}
        
    character.data.vitality.stamina -= COST
    area.threat_level += 0.5
    character.save()
    WorldManager.save_area(area)
    
    try:
        m_group = await MonsterEngine.generate_monster_group(area, llm_client)
        return {"success": True, "monsters": m_group}
    except Exception as e:
        return {"success": False, "reason": "error", "message": f"❌ 生成怪物失敗: {e}"}
