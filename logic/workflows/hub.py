from typing import Optional
from db.storage import CharacterRepository
from core.character import Character

def switch_character_workflow(user_id: str, character_name: str) -> Optional[Character]:
    """
    切換活躍角色，並載入切換後的 Character 物件。
    """
    CharacterRepository.set_active_character(str(user_id), character_name)
    return Character.load(str(user_id))

def delete_character_workflow(user_id: str, character_name: str) -> bool:
    """
    刪除玩家名下的指定角色檔案。
    """
    return CharacterRepository.delete_character(str(user_id), character_name)
