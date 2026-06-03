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
        dist = max(abs(x), abs(y))
        base_level = dist * 2 if dist > 0 else 1
        
        # 目前強制只生成 wilderness 類型，確保野外的一致性
        area_type = "wilderness"

        # 決定是否有地標 (40% 機率)
        has_landmark = random.random() < 0.40

        system_prompt = f"""
        你是一個專業的 TRPG 世界觀設計師。請為座標 ({x}, {y}) 生成一個獨特的荒野地區設定。

        **【環境背景】**
        - 此地區距離主城 {dist} 單位，基礎難度 Lv.{base_level}。
        - 地貌應根據座標距離呈現演化（近處較和平，遠處越荒涼或詭異）。

        **【生成規範】**
        1. **地區名稱**：例如「月光森林」、「焦土原野」。
        2. **敘事描述**：描述環境氣氛、視覺細節（植物、光線、風向）。
        3. **地標 (Landmark)**：
           - 此座標是否包含可互動地標：{has_landmark}
           - 如果為 True，請在 landmarks 列表中生成一個「獨特的興趣點」（如：遠古祭壇、廢棄營地、奇異巨石）。
           - 如果為 False，請將 landmarks 列表保持為空 []。

        回應請「只」輸出 JSON。

        **【JSON 格式範例】**
        {{
            "name": "地區名稱",
            "type": "wilderness",
            "description": "地區的詳細描述...",
            "landmarks": [
                {{
                    "id": "landmark_{x}_{y}",
                    "name": "地標名稱",
                    "description": "關於此地標的視覺描述與神祕感...",
                    "features": ["explore"]
                }}
            ]
        }}
        """

        prompt = f"請生成座標 ({x}, {y}) 的地區資料。包含地標：{has_landmark}"

        try:
            response_text = await llm_client.call(prompt, system_prompt)
            parsed_data = repair_and_parse_json(response_text)

            if not parsed_data:
                return None

            parsed_data["id"] = f"{x},{y}"
            parsed_data["base_level"] = base_level
            parsed_data["connections"] = [
                f"{x},{y+1}", f"{x},{y-1}", f"{x-1},{y}", f"{x+1},{y}"
            ]

            # 相容性處理：如果 AI 回傳 buildings 則轉為 landmarks
            if "buildings" in parsed_data and "landmarks" not in parsed_data:
                parsed_data["landmarks"] = parsed_data.pop("buildings")

            return AreaSchema(**parsed_data)

        except Exception as e:
            print(f"生成地區 ({x}, {y}) 失敗: {e}")
            return None
