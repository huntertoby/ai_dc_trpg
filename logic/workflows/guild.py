from typing import Dict, Any
from core.character import Character
from core.models import QuestSchema
from core.guild import GuildManager

def accept_quest_workflow(character: Character, quest: QuestSchema, user_id: str) -> Dict[str, Any]:
    """
    處理接受任務的業務邏輯。檢查玩家階級、更新任務欄位剩餘空位、加載任務至角色 active 列表中，並存檔。
    """
    if quest.rank_value > character.rank_value:
        return {"success": False, "reason": "rank", "message": "❌ 階級不足。"}
        
    if GuildManager.accept_quest(str(user_id), quest.id):
        character.data.active_quests.append(quest)
        character.save()
        return {"success": True, "message": f"✅ 已領取：{quest.title}"}
    else:
        return {"success": False, "reason": "slots", "message": "❌ 領取失敗。"}
