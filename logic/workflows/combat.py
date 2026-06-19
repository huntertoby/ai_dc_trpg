import random
from typing import List, Dict, Any
from core.character import Character

def process_victory_workflow(character: Character, monsters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    計算戰鬥勝利的獎勵，將其加給角色，並存檔。
    """
    total_gold = sum(m["gold_reward"] for m in monsters)
    total_exp = sum(m["exp_reward"] for m in monsters)
    
    character.data.gold += total_gold
    leveled_up = character.add_exp(total_exp)
    character.save()
    
    return {
        "total_gold": total_gold,
        "total_exp": total_exp,
        "leveled_up": leveled_up,
        "new_level": character.data.level
    }

def process_flee_workflow(combat_manager) -> Dict[str, Any]:
    """
    計算逃跑機率。如果成功，結束戰鬥；如果失敗，切換回合。
    """
    if random.random() < 0.4:
        combat_manager.is_finished = True
        return {"success": True}
    else:
        combat_manager.next_turn()
        return {"success": False}

async def process_monster_turns_workflow(combat_manager) -> Dict[str, Any]:
    """
    處理怪物的 AI 回合，直到輪到玩家或戰鬥結束。
    """
    msgs = []
    
    while not combat_manager.is_finished:
        curr = combat_manager.get_current_entity()
        # 如果是玩家的召喚物，且主人存活，暫停自動循環，由玩家進行手動控制
        is_player_summon = curr["type"] == "monster" and curr["ref"].get("is_summon") and curr["ref"].get("master_id") == str(id(combat_manager.character))
        if is_player_summon and combat_manager.character.data.vitality.hp > 0:
            break
            
        if curr["type"] != "monster":
            break  # 輪到玩家了，停止自動循環
            
        result = await combat_manager.monster_action()
        msgs.append(result["msg"])
        
        if combat_manager.is_finished:
            break
            
        combat_manager.next_turn()
        
    return {
        "finished": combat_manager.is_finished,
        "winner": combat_manager.winner,
        "messages": msgs
    }
