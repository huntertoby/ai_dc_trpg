from typing import Dict, Any
from core.character import Character

def equip_item_workflow(character: Character, item_name: str) -> Dict[str, Any]:
    """
    將指定裝備穿戴到角色身上，並儲存角色資料。
    """
    try:
        character.equip_item(item_name)
        character.save()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def unequip_item_workflow(character: Character, slot: str) -> Dict[str, Any]:
    """
    卸下指定部位的裝備，放回背包中，並儲存角色資料。
    """
    try:
        item = character.unequip_item(slot)
        character.save()
        return {"success": True, "item": item}
    except Exception as e:
        return {"success": False, "error": str(e)}

def discard_item_workflow(character: Character, item_idx: int) -> Dict[str, Any]:
    """
    從背包中丟棄指定索引的物品，並儲存角色資料。
    """
    if 0 <= item_idx < len(character.data.inventory):
        item = character.data.inventory.pop(item_idx)
        character.save()
        return {"success": True, "item": item}
    return {"success": False, "error": "Index out of range"}
