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
        """呼叫 AI 生成每日任務，並根據座標距離調整獎勵"""
        system_prompt = f"""
        你是一個 TRPG 冒險者公會的任務秘書。請為佈告欄生成 10 個多樣化的任務。
        
        **【任務階級與區域指引】**
        - E/D 級 (新手/正式): 目標範圍 (0,0) 周邊 0-7 格。
        - C/B 級 (精英/英雄): 目標範圍 8-15 格。
        - A/S 級 (傳奇/神話): 目標範圍 16 格以外。
        
        **【結構規則】**
        1. 每個任務必須包含：標題、敘事描述、階級(E/D/C/B/A/S)、目標類型(kill/collect/explore)。
        2. 任務目標要有具體的座標(x,y)，請嚴格遵守上述【區域指引】分配座標。
        3. 越高階級的任務，敘事應越具備地區特色（參考：Tier 1 平常, Tier 2 異變, Tier 3 禁忌）。
        
        回應請「只」輸出 JSON 列表。
        """
        
        prompt = "請根據區域指引生成 10 個涵蓋不同難度的冒險公會委託任務。"
        
        try:
            response = await llm_client.call(prompt, system_prompt)

            from utils.json_utils import repair_and_parse_json
            parsed = repair_and_parse_json(response)

            
            if not isinstance(parsed, list): return []
            
            final_quests = []
            for i, q_data in enumerate(parsed):
                rank = q_data.get("rank_required", "E")
                table = RANK_REWARD_TABLE.get(rank, RANK_REWARD_TABLE["E"])
                
                # 計算座標距離加成
                objs = q_data.get("objectives", [])
                max_dist = 0
                for obj in objs:
                    loc = obj.get("location", [0, 0])
                    dist = max(abs(loc[0]), abs(loc[1]))
                    max_dist = max(max_dist, dist)
                
                # 距離紅利係數 (每 10 單位增加 50% 獎勵)
                dist_bonus = 1 + (max_dist / 20)
                
                q_data["id"] = f"Q-{int(time.time())}-{i}"
                q_data["rewards"] = {
                    "gold": int(((table["gold"][0] + table["gold"][1]) // 2) * dist_bonus),
                    "exp": int(((table["exp"][0] + table["exp"][1]) // 2) * dist_bonus),
                    "reputation": int(((table["reputation"][0] + table["reputation"][1]) // 2) * dist_bonus)
                }
                final_quests.append(QuestSchema(**q_data))
                
            return final_quests
        except Exception as e:
            print(f"任務生成失敗: {e}")
            return []

    @classmethod
    async def generate_rumor(cls, character, x: int, y: int, llm_client) -> Optional[str]:
        """
        根據玩家座標、等級與屬性生成傳聞。
        """
        import random
        from core.world import WorldManager
        
        # 1. 判定距離階級 (70% 近, 20% 中, 10% 遠)
        roll = random.random()
        if roll < 0.70:
            target_dist = random.randint(1, 7)
        elif roll < 0.90:
            target_dist = random.randint(8, 15)
        else:
            target_dist = random.randint(16, 25)
            
        # 2. 隨機選定目標座標
        tx = x + random.choice([-target_dist, target_dist])
        ty = y + random.randint(-target_dist, target_dist)
        if random.random() > 0.5: tx, ty = ty, tx
        
        diff = WorldManager.get_difficulty_settings(tx, ty)
        
        # 3. 屬性影響判定 (CHA/WIS)
        stats = character.total_stats
        cha = stats["CHA"]
        wis = stats["WIS"]
        
        system_prompt = f"""
        你是一個 TRPG 的酒館流言家。請為座標 ({tx}, {ty}) 生成一條傳聞。
        
        **【環境背景】**
        - 地區等級: Lv.{diff['base_level']} | 階級: {diff['tier_name']}
        - 玩家目前所在: ({x}, {y})
        
        # **【資訊完整度 (受魅力 {cha} 影響)】**
        # - 如果魅力 >= 15，請給出精確座標 ({tx}, {ty})。
        # - 如果魅力 < 15，請模糊描述方向。
        # 
        # **【資訊深度 (受智慧 {wis} 影響)】**
        # - 如果智慧 >= 15，請提到怪物的弱點或隱藏的獎勵類型。
        # - 如果智慧 < 15，只提到一些表面的傳聞。
        
        回應請直接輸出傳聞敘事，長度 50 字內，不要括號。
        """
        
        prompt = f"生成一條關於座標 ({tx}, {ty}) 的流言。"
        
        try:
            rumor = await llm_client.call(prompt, system_prompt)
            return rumor.strip()
        except Exception as e:
            print(f"流言生成失敗: {e}")
            return None

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
