# core/guild.py
import asyncio
import json
import os
import time
from typing import List, Optional, Dict
from core.models import QuestSchema, QuestObjective, CharacterSchema
from services import llm_service

# 1. 任務行情基準 (用於校正 AI)
RANK_REWARD_TABLE = {
    "E": {"gold": (50, 150), "exp": (100, 300), "reputation": (5, 10)},
    "D": {"gold": (200, 500), "exp": (500, 1000), "reputation": (15, 30)},
    "C": {"gold": (600, 1500), "exp": (1200, 2500), "reputation": (40, 80)},
    "B": {"gold": (2000, 5000), "exp": (3000, 6000), "reputation": (100, 200)},
    "A": {"gold": (6000, 15000), "exp": (8000, 15000), "reputation": (250, 500)},
    "S": {"gold": (20000, 100000), "exp": (20000, 50000), "reputation": (1000, 2000)},
}

class GuildManager:
    BOARD_PATH = "world_db/guild_board.json"

    @classmethod
    def load_board(cls) -> List[QuestSchema]:
        """讀取全服佈告欄"""
        if not os.path.exists(cls.BOARD_PATH):
            return []
        with open(cls.BOARD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [QuestSchema(**q) for q in data]

    @classmethod
    def save_board(cls, quests: List[QuestSchema]):
        """儲存全服佈告欄"""
        os.makedirs("world_db", exist_ok=True)
        with open(cls.BOARD_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps([q.model_dump() for q in quests], indent=4, ensure_ascii=False))

    @classmethod
    async def refresh_board_if_needed(cls, llm_client):
        """檢查是否需要刷新任務"""
        current_quests = cls.load_board()
        if not current_quests:
            new_quests = await cls.generate_daily_quests(llm_client)
            cls.save_board(new_quests)
            return new_quests
        return current_quests

    @classmethod
    async def generate_daily_quests(cls, llm_client) -> List[QuestSchema]:
        """呼叫 AI 生成每日任務"""
        system_prompt = f"""
        你是一個 TRPG 冒險者公會的任務秘書。請為佈告欄生成 10 個多樣化的任務。
        
        **【行情參考】**
        E級 (新手): 簡單雜事, D級 (正式): 野外討伐, C級: 地區威脅。
        
        **【結構規則】**
        1. 每個任務必須包含：標題、敘事描述、階級(E/D/C)、目標類型(kill/collect/explore)。
        2. 獎勵請留空或設為 0，系統會自動填入數值。
        3. 任務目標要有具體的座標(x,y)，範圍在 (0,0) 周邊 5 格內。
        
        回應請「只」輸出 JSON 列表。
        結構範例：
        [
          {{
            "id": "q_001",
            "title": "標題",
            "description": "敘事...",
            "rank_required": "E",
            "objectives": [{{ "type": "kill", "target_id": "史萊姆", "count": 5, "location": [1, 0] }}]
          }}
        ]
        """
        
        prompt = "請生成 10 個精彩的冒險公會委託任務。"
        
        try:
            response = await llm_client.call(prompt, system_prompt)

            from utils.json_utils import repair_and_parse_json
            parsed = repair_and_parse_json(response)

            
            if not isinstance(parsed, list): return []
            
            final_quests = []
            for i, q_data in enumerate(parsed):
                rank = q_data.get("rank_required", "E")
                table = RANK_REWARD_TABLE.get(rank, RANK_REWARD_TABLE["E"])
                
                q_data["id"] = f"Q-{int(time.time())}-{i}"
                q_data["rewards"] = {
                    "gold": (table["gold"][0] + table["gold"][1]) // 2,
                    "exp": (table["exp"][0] + table["exp"][1]) // 2,
                    "reputation": (table["reputation"][0] + table["reputation"][1]) // 2
                }
                final_quests.append(QuestSchema(**q_data))
                
            return final_quests
        except Exception as e:
            print(f"任務生成失敗: {e}")
            return []

    @classmethod
    def accept_quest(cls, user_id: str, quest_id: str) -> bool:
        board = cls.load_board()
        target_q = next((q for q in board if q.id == quest_id), None)
        if not target_q or target_q.slots_left <= 0:
            return False
        target_q.slots_left -= 1
        cls.save_board(board)
        return True

# --- 測試代碼 ---
if __name__ == "__main__":
    from services.llm_service import LMStudioClient
    async def test():
        client = LMStudioClient()
        print("🚀 正在測試生成 10 個任務...")
        quests = await GuildManager.generate_daily_quests(client)
        if quests:
            GuildManager.save_board(quests)
            print(f"✅ 成功生成並儲存 {len(quests)} 個任務！")
            for q in quests:
                print(f"[{q.rank_required}] {q.title} - 獎勵: {q.rewards['gold']}G")
        else:
            print("❌ 生成失敗。")
            
    asyncio.run(test())
