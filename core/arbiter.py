import random
from typing import Optional, Dict, Any
from core.character import Character
from core.models import AreaSchema, Item, StatusEffect
from utils.json_utils import repair_and_parse_json

class ArbiterSystem:
    @staticmethod
    async def process_action(
        character: Character, 
        area: AreaSchema, 
        event_data: Dict[str, Any], 
        player_text: str, 
        llm_client: Any
    ) -> Dict[str, Any]:
        """
        處理玩家在探索中的自由行動。
        包含：AI 裁決、屬性檢定、結果生成、獎勵/代價發放。
        回傳結果字典供 UI 顯示。
        """
        context = {
            "job": character.data.job_name,
            "skills": [s.name for s in character.data.abilities],
            "items": [i.name for i in character.data.inventory],
            "stats": character.total_stats
        }
        
        # 1. AI 裁決行動合法性與精確難度 (DC)
        sys_prompt = f"""
        你是一個精通 TRPG 規則的仲裁者。角色資訊：{context}。環境：{area.name}。
        當前事件：{event_data['prompt_action']}。
        
        **【難度 (DC) 裁決指引】**
        請根據玩家描述的「具體行動策略」給予一個 1 到 25 之間的難度等級 (Difficulty Class)：
        - **DC 1-5 (極簡單)**: 幾乎不需要檢定，除非角色完全外行。
        - **DC 6-10 (簡單)**: 稍有訓練的人都能輕鬆完成，如觀察環境、謹慎退避。
        - **DC 11-15 (普通)**: 需要一定的屬性支持或技巧，如翻越障礙、說服普通衛兵。
        - **DC 16-20 (困難)**: 具有風險的冒險行動，或對抗強大生物。
        - **DC 21-25 (極困難/英雄級)**: 幾乎不可能完成的神技，或在極端劣勢下的反擊。
        
        請判定玩家行動是否合法，並輸出對應的屬性與精確 DC。
        只輸出 JSON: {{"is_legal":bool, "stat_required":"INT", "dc":int, "fail_reason":"..."}}
        """
        
        arb_resp = await llm_client.call(player_text, sys_prompt)
        decision = repair_and_parse_json(arb_resp)
        
        if not decision or not decision.get("is_legal"):
            return {
                "success": False,
                "is_legal": False,
                "fail_reason": decision.get("fail_reason", "超出能力範圍。") if decision else "AI 響應錯誤"
            }

        # 2. 進行屬性檢定
        stat_name = decision.get("stat_required", "STR").upper()
        stat_val = character.total_stats.get(stat_name, 10)
        modifier = stat_val // 5
        base_dc = decision.get("dc", 12)
        final_dc = base_dc + (area.base_level // 5)
        
        roll = random.randint(1, 20)
        total = roll + modifier
        is_success = total >= final_dc
        
        res_str = "大獲全勝" if is_success and roll == 20 else ("成功" if is_success else ("大失敗" if not is_success and roll == 1 else "失敗"))
        
        # 3. AI 生成故事結局與干預類型
        con_prompt = f"玩家行動：{player_text}。屬性：{stat_name}(DC:{final_dc}, 骰出:{roll}+{modifier}={total})。結果：{res_str}。請寫下結局與干預類型(REWARD_ITEM,REWARD_BUFF,REWARD_GOLD_XP,COST_DEBUFF,COST_GOLD,TRIGGER_COMBAT,DISCOVERY)。JSON: {{\"narrative\":\"...\", \"intervention\":{{\"type\":\"...\", \"flavor\":\"...\", \"details\":\"...\"}}}}"
        con_resp = await llm_client.call("執行結算", con_prompt)
        outcome = repair_and_parse_json(con_resp) or {"narrative": f"行動{res_str}。", "intervention": {"type": "REWARD_GOLD_XP"}}
        
        itv = outcome.get("intervention", {})
        itype = itv.get("type", "REWARD_GOLD_XP")
        
        # 4. 結算獎勵與代價
        rewards = []
        penalties = []
        
        if is_success:
            gold = int(random.randint(20, 50) * (1 + area.base_level/10))
            exp = int(30 * (1 + area.base_level/10))
            character.data.gold += gold
            character.add_exp(exp)
            rewards.append(f"💰 {gold}G")
            rewards.append(f"✨ {exp}XP")
            
            if random.random() < 0.4:
                if itype == "REWARD_ITEM":
                    loot = itv.get("flavor", "神祕材料")
                    from core.drop_engine import DropEngine
                    tier = DropEngine.get_tier_by_dist(*character.data.location)
                    character.add_item(Item(name=loot, description=f"發現於探索", material_type="雜物", tier=tier, source_id="exploration"))
                    rewards.append(f"🎁 獲得：{loot}")
                elif itype == "REWARD_BUFF":
                    bname = itv.get("flavor", "啟發")
                    bstat = itv.get("details", stat_name).upper()
                    if bstat not in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]: bstat = stat_name
                    character.data.status_effects.append(StatusEffect(name=bname, description="探索加成", duration_type="turns", duration=3, bonuses={bstat.lower(): 5}))
                    rewards.append(f"🌟 獲得：【{bname}】 (+5 {bstat})")
            
            if itype == "DISCOVERY":
                clue = itv.get("flavor", "一條線索")
                if clue not in character.data.known_rumors:
                    character.data.known_rumors.append(clue)
                rewards.append(f"📜 發現：{clue}")
        else:
            loss = random.randint(10, 20) * (2 if "大失敗" in res_str else 1)
            character.data.vitality.hp -= loss
            penalties.append(f"💔 生命值 -{loss}")
            
            if (itype == "COST_DEBUFF" and random.random() < 0.4) or "大失敗" in res_str:
                dname = itv.get("flavor", "受挫")
                dstat = itv.get("details", "LUCK" if "大失敗" in res_str else stat_name).upper()
                if dstat not in ["STR", "DEX", "CON", "INT", "WIS", "CHA", "LUCK"]: dstat = "LUCK"
                character.data.status_effects.append(StatusEffect(name=dname, description="探索減益", duration_type="turns", duration=3, bonuses={dstat.lower(): -5}))
                penalties.append(f"💀 附加：【{dname}】 (-5 {dstat})")
            elif itype == "COST_GOLD":
                glost = min(character.data.gold, 50)
                character.data.gold -= glost
                penalties.append(f"💰 損失：{glost}G")
            elif itype == "TRIGGER_COMBAT":
                penalties.append("⚔️ **驚動了生物，戰鬥開始！**")
        
        character.save()
        
        # 5. 紀錄日誌並增加事件計數
        character.add_trpg_event()
        log_type = "LEGEND" if ("大獲" in res_str) else ("ORDEAL" if "大失敗" in res_str else "TRIFLE")
        character.add_log(log_type, f"在 {area.name} 執行行動：{player_text}。結果：{res_str}。")

        return {
            "success": True,
            "is_legal": True,
            "res_str": res_str,
            "narrative": outcome.get("narrative", f"行動{res_str}。"),
            "stat_name": stat_name,
            "stat_val": stat_val,
            "modifier": modifier,
            "base_dc": base_dc,
            "final_dc": final_dc,
            "roll": roll,
            "total": total,
            "rewards": rewards,
            "penalties": penalties,
            "is_critical_fail": "大失敗" in res_str,
            "is_critical_success": "大獲" in res_str
        }
