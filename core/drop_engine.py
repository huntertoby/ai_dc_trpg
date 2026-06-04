# core/drop_engine.py
import random
from typing import Dict, Any, List, Optional
from core.models import AreaSchema, Item

class DropEngine:
    @classmethod
    def get_tier_by_dist(cls, x: int, y: int) -> str:
        """根據座標距離決定掉落品質 (Tier)"""
        dist = max(abs(x), abs(y))
        if dist <= 5: return "T5"
        elif dist <= 12: return "T4"
        elif dist <= 20: return "T3"
        elif dist <= 30: return "T2"
        else: return "T1"

    @classmethod
    async def generate_loot(
        cls, 
        area: AreaSchema, 
        monster: Dict[str, Any], 
        llm_client,
        novelty_chance: float = 0.2
    ) -> Optional[Item]:
        """
        生成掉落材料。
        - 80% 從地區已發現的 loot_pool 中抽選。
        - 20% 呼叫 AI 生成新材料並紀錄。
        """
        species = monster["base_name"]
        tier = cls.get_tier_by_dist(*[int(c) for c in area.id.split(",")])
        
        # 1. 決定是否從已有的池子中抽
        if species in area.loot_pool and random.random() > novelty_chance:
            loot_data = random.choice(area.loot_pool[species])
            return Item(
                name=loot_data["name"],
                description=loot_data.get("description", ""),
                material_type=loot_data["material_type"],
                tier=tier,
                source_id=monster["source_id"]
            )
        
        # 2. 呼叫 AI 生成新材料 (20% 機率)
        material_types = ["骨骼", "皮革", "金屬", "藥草", "血液", "靈魂", "雜物"]
        
        system_prompt = f"""
        你是一個 TRPG 掉落物設計師。
        玩家剛擊敗了：{monster['name']} (Lv.{monster['level']})
        地區環境：{area.name} ({', '.join(area.ecology_tags)})
        
        請為該怪物設計 **1 個** 獨特的掉落材料。
        
        **【規範】**
        1. **名稱 (name)**：具備敘事感的名稱 (如: 骷髏王的斷裂肋骨)。
        2. **描述 (description)**：一段帥氣的視覺描述。
        3. **核心類別 (material_type)**：必須從以下列表中選一：{material_types}。
        
        回應請「只」輸出 JSON。
        """
        
        prompt = f"請生成 {monster['name']} 的掉落物。"
        
        try:
            from utils.json_utils import repair_and_parse_json
            response_text = await llm_client.call(prompt, system_prompt)
            parsed_data = repair_and_parse_json(response_text)
            
            if parsed_data:
                # 補全系統欄位
                parsed_data["tier"] = tier
                parsed_data["source_id"] = monster["source_id"]
                
                # 紀錄到地區的 loot_pool (排除 source_id 因為 source_id 是戰鬥時動態決定的)
                if species not in area.loot_pool:
                    area.loot_pool[species] = []
                
                pool_entry = {
                    "name": parsed_data["name"],
                    "description": parsed_data["description"],
                    "material_type": parsed_data["material_type"]
                }
                if pool_entry not in area.loot_pool[species]:
                    area.loot_pool[species].append(pool_entry)
                
                # 持久化地區資料
                from core.world import WorldManager
                WorldManager.save_area(area)
                
                return Item(**parsed_data)
        except Exception as e:
            print(f"掉落物生成失敗: {e}")
            
        return None
