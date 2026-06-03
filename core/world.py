# core/world.py
import os
import json
from typing import Optional, List, Dict
from core.models import AreaSchema, BuildingSchema

class WorldManager:
    AREA_DB_PATH = "area_db"
    
    @classmethod
    def get_area_id(cls, x: int, y: int) -> str:
        return f"{x},{y}"

    @classmethod
    def load_area(cls, x: int, y: int) -> Optional[AreaSchema]:
        """讀取指定座標的地區資料"""
        area_id = cls.get_area_id(x, y)
        file_path = os.path.join(cls.AREA_DB_PATH, f"{area_id}.json")
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return AreaSchema(**data)
        return None

    @classmethod
    def save_area(cls, area: AreaSchema):
        """儲存地區資料"""
        if not os.path.exists(cls.AREA_DB_PATH):
            os.makedirs(cls.AREA_DB_PATH)
            
        file_path = os.path.join(cls.AREA_DB_PATH, f"{area.id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(area.model_dump_json(indent=4))

    @classmethod
    def get_base_level(cls, x: int, y: int) -> int:
        """根據座標計算該地區的基礎等級"""
        dist = max(abs(x), abs(y))
        if dist == 0: return 1
        return dist * 2

def init_main_city():
    """初始化萬族樞紐主城 (0,0)"""
    buildings = [
        BuildingSchema(
            id="guild", name="📜 冒險者公會", 
            description="萬族共同維護的公會，是接取委託與回報功績的中心。", 
            features=["quest", "rank"],
            npc_name="執法官·瓦爾肯", npc_traits=["冷靜", "公正"]
        ),
        BuildingSchema(
            id="tavern", name="🍻 諸神酒館", 
            description="這裡提供世界各地的美酒，是恢復精力與聽取冒險傳聞的最佳去處。", 
            features=["rest", "rumor"],
            npc_name="老闆娘·瑪拉", npc_traits=["熱情", "看人很準"]
        ),
        BuildingSchema(
            id="plaza", name="⛲ 星辰中央廣場", 
            description="城市的中心點，設有古老的遠距離傳送矩陣。", 
            features=["warp", "news"]
        ),
        BuildingSchema(
            id="forge", name="⚒️ 萬物熔爐", 
            description="融合了矮人鍛造、精靈附魔與人族工藝的頂尖鐵匠鋪。", 
            features=["upgrade", "repair"],
            npc_name="大工匠·托比昂", npc_traits=["頑固", "視技術如生命"]
        ),
        BuildingSchema(
            id="market", name="⚖️ 跨位面市集", 
            description="匯集了來自各個大陸與位面的貿易商隊，販售各類物資。", 
            features=["trade", "sell"],
            npc_name="貿易官·斯卡卡", npc_traits=["狡黠", "極致精明"]
        ),
        BuildingSchema(
            id="warehouse", name="🌀 虛空倉庫", 
            description="由空間魔法維護的保險庫，你名下的所有冒險者都能在此共享物資與金幣。", 
            features=["storage", "shared_bank", "upgrade_bag"],
            npc_name="監管者·零", npc_traits=["機械化", "絕對精準"]
        ),
        BuildingSchema(
            id="mage_tower", name="🔮 真理高塔", 
            description="法術研究與神祕學交流的中心，也提供神祕物品的鑑定服務。", 
            features=["identify", "skill_learn"],
            npc_name="導師·埃隆", npc_traits=["睿智", "嚴謹"]
        ),
        BuildingSchema(
            id="sanctuary", name="🌿 生命神殿", 
            description="一處寧靜的中立庇護所，提供治癒與靈魂重塑（洗點）服務。", 
            features=["heal", "respec"],
            npc_name="祭司·伊蓮娜", npc_traits=["溫柔", "慈悲"]
        ),
        BuildingSchema(
            id="training_ground", name="⚔️ 英靈修練場", 
            description="供各族冒險者切磋武藝、測試技能強度的開放式靶場。", 
            features=["training", "test_dummy"]
        )
    ]
    
    main_city = AreaSchema(
        id="0,0",
        name="阿卡西亞·萬徑之城",
        type="city",
        description="這是一座坐落於世界地理樞紐的宏偉巨城，建立在四個大陸交匯的廣袤盆地中。城市由古老的黑曜石與白大理石築成，無數條穿越森林、荒漠與高山的貿易古道最終都匯聚於此。它是文明與野蠻的分界線，也是冒險者們最堅實的後盾。",
        buildings=buildings,
        base_level=1,
        connections=["0,1", "0,-1", "-1,0", "1,0"]
    )
    
    WorldManager.save_area(main_city)
    return main_city

if __name__ == "__main__":
    init_main_city()
    print("萬族樞紐主城 (0,0) 已成功初始化！")
