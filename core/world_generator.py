# core/world_generator.py
import random
from typing import Optional, List, Dict
from core.models import AreaSchema, BuildingSchema
from utils.json_utils import repair_and_parse_json

class WorldGenerator:
    @classmethod
    async def generate_area(cls, x: int, y: int, llm_client) -> Optional[AreaSchema]:
        """
        呼叫 AI 生成指定座標的地區資料
        """
        from core.world import WorldManager
        diff_settings = WorldManager.get_difficulty_settings(x, y)
        base_level = diff_settings["base_level"]
        tier = diff_settings["tier"]
        tier_name = diff_settings["tier_name"]
        dist = diff_settings["dist"]

        # 目前強制只生成 wilderness 類型，確保野外的一致性
        area_type = "wilderness"

        # 決定是否有地標 (40% 機率)
        has_landmark = random.random() < 0.40

        system_prompt = f"""
        你是一個專業的 TRPG 世界觀設計師。請為座標 ({x}, {y}) 生成一個獨特的地區設定。

        **【地理階級：{tier_name} (Tier {tier})】**
        - 此地區距離主城 {dist} 單位，基礎難度 Lv.{base_level}。
        - **地貌演化指引**：
            - Tier 1 (文明邊緣)：地貌相對正常（森林、平原），氣氛較和平，威脅多為野獸。
            - Tier 2 (異變荒野)：地貌開始出現魔力異變（如：發光的植物、懸浮石塊、色彩異常的河流），環境充滿神祕感。
            - Tier 3 (禁忌區域)：極端且詭異的景觀（如：破碎的時空、永恆之火、機械遺蹟），氣氛壓抑且致命。

        **【生成規範】**
        1. **地區名稱**：需符合 Tier {tier} 的風格。
        2. **敘事描述**：描述環境氣氛、視覺細節。
        3. **生態系 (Ecology)**：
           - **ecology_tags**: 賦予 2~3 個環境標籤 (如: ["亡靈", "陰暗", "腐敗"])。
           - **dominant_species**: 賦予此地區的主要核心物種 (如: ["Skeleton"])。
        4. **地標 (Landmark)**：
           - 此座標是否包含可互動地標：{has_landmark}

        **【JSON 格式範例】**
        {{
            "name": "地區名稱",
            "type": "wilderness",
            "description": "地區的詳細描述...",
            "ecology_tags": ["標籤1", "標籤2"],
            "dominant_species": ["物種1"],
            "landmarks": [
                {{
                    "id": "landmark_{x}_{y}",
                    "name": "地標名稱",
                    "description": "關於此地標的視覺描述與神祕感...",
                    "features": ["explore"],
                    "npc_name": "守護者或奇遇 NPC 名稱 (選填)",
                    "npc_traits": ["性格 1", "性格 2"]
                }}
            ]
        }}

        回應請「只」輸出 JSON。
        """

        prompt = f"請生成座標 ({x}, {y}) 的地區資料。包含地標：{has_landmark}"

        try:
            response_text = await llm_client.call(prompt, system_prompt)
            parsed_data = repair_and_parse_json(response_text)

            if not parsed_data:
                return None

            # 強制寫入/校正系統欄位
            parsed_data["id"] = f"{x},{y}"
            parsed_data["base_level"] = base_level
            parsed_data["type"] = area_type
            parsed_data["connections"] = [
                f"{x},{y+1}", f"{x},{y-1}", f"{x-1},{y}", f"{x+1},{y}"
            ]
            
            # 確保生態欄位存在
            if "ecology_tags" not in parsed_data: parsed_data["ecology_tags"] = []
            if "dominant_species" not in parsed_data: parsed_data["dominant_species"] = ["Unknown"]

            # 相容性處理：如果 AI 回傳 buildings 則轉為 landmarks
            if "buildings" in parsed_data and "landmarks" not in parsed_data:
                parsed_data["landmarks"] = parsed_data.pop("buildings")

            # 確保 landmarks 是列表且包含必要的 id 與欄位正規化
            if "landmarks" in parsed_data and isinstance(parsed_data["landmarks"], list):
                for i, landmark in enumerate(parsed_data["landmarks"]):
                    if not isinstance(landmark, dict): continue
                    if "id" not in landmark or not landmark["id"]:
                        landmark["id"] = f"landmark_{x}_{y}_{i}"
                    
                    # 補全 BuildingSchema 預期欄位與型別修正
                    if "features" not in landmark or not isinstance(landmark["features"], list):
                        landmark["features"] = ["explore"]
                    if "talk_cost" not in landmark: landmark["talk_cost"] = 5
                    if "rumor_rate" not in landmark: landmark["rumor_rate"] = 0.3
                    if "npc_traits" in landmark and isinstance(landmark["npc_traits"], str):
                        landmark["npc_traits"] = [landmark["npc_traits"]]
                    elif "npc_traits" not in landmark:
                        landmark["npc_traits"] = []
            else:
                parsed_data["landmarks"] = []

            return AreaSchema(**parsed_data)

        except Exception as e:
            print(f"生成地區 ({x}, {y}) 失敗: {e}")
            import traceback
            traceback.print_exc()
            return None
