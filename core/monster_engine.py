# core/monster_engine.py
import random
import math
from typing import Dict, Any, List, Optional
from core.models import AreaSchema

class MonsterRank:
    COMMON = {"name": "普通", "multiplier": 1.0, "weight": 70, "exp_mult": 1.0, "gold_mult": 1.0}
    ELITE = {"name": "精英", "multiplier": 1.5, "weight": 20, "exp_mult": 2.5, "gold_mult": 2.0}
    RARE = {"name": "稀有", "multiplier": 2.0, "weight": 7, "exp_mult": 5.0, "gold_mult": 5.0}
    EPIC = {"name": "史詩", "multiplier": 3.5, "weight": 2, "exp_mult": 10.0, "gold_mult": 12.0}
    BOSS = {"name": "頭目", "multiplier": 6.0, "weight": 1, "exp_mult": 25.0, "gold_mult": 30.0}

    @classmethod
    def roll_rank(cls, threat_level: float = 0.0) -> Dict[str, Any]:
        """根據區域威脅值隨機決定怪物階級"""
        # 威脅值越高，高等級怪物出現機率越高
        weights = [
            cls.COMMON["weight"],
            cls.ELITE["weight"] + (threat_level * 2),
            cls.RARE["weight"] + (threat_level * 1),
            cls.EPIC["weight"] + (threat_level * 0.5),
            cls.BOSS["weight"] + (threat_level * 0.2)
        ]
        ranks = [cls.COMMON, cls.ELITE, cls.RARE, cls.EPIC, cls.BOSS]
        return random.choices(ranks, weights=weights, k=1)[0]

class MonsterEngine:
    @classmethod
    def generate_monster_group(cls, area: AreaSchema, novelty_chance: float = 0.2) -> List[Dict[str, Any]]:
        """
        根據地區生態生成怪物群體 (1~3 隻)。
        """
        import random
        # 決定怪物數量 (1-3 隻)
        # 威脅值越高，出現多隻怪物的機率微幅提升
        count_weights = [70, 20, 10] # 1隻: 70%, 2隻: 20%, 3隻: 10%
        if area.threat_level > 5: count_weights = [50, 30, 20]
        if area.threat_level > 10: count_weights = [30, 40, 30]
        
        num_monsters = random.choices([1, 2, 3], weights=count_weights, k=1)[0]
        
        monsters = []
        for _ in range(num_monsters):
            monsters.append(cls._generate_single_monster(area, novelty_chance))
        return monsters

    @classmethod
    def _generate_single_monster(cls, area: AreaSchema, novelty_chance: float = 0.2) -> Dict[str, Any]:
        """生成單隻怪物的內部邏輯"""
        import random
        is_novelty = random.random() < novelty_chance
        
        # 1. 決定物種 (強制中文)
        if is_novelty or not area.discovered_variants:
            base_species = random.choice(area.dominant_species) if area.dominant_species else "未知生物"
            # 如果 base_species 包含英文，嘗試轉換或預設
            if any(ord(c) < 128 for c in base_species): base_species = "奇異生物"
            
            adjectives = ["瘋狂的", "被污染的", "飢餓的", "巨大的", "奇異的", "虛空的", "兇猛的", "狡詐的"]
            species_name = f"{random.choice(adjectives)}{base_species}"
            
            if is_novelty and species_name not in area.discovered_variants:
                area.discovered_variants.append(species_name)
        else:
            species_name = random.choice(area.discovered_variants)

        # 2. 決定階級
        rank = MonsterRank.roll_rank(area.threat_level)
        
        # 3. 計算基礎能力 (隨 Level 縮放)
        level = area.base_level
        hp = int((100 + (level * 25)) * rank["multiplier"])
        attack = int((10 + (level * 5)) * rank["multiplier"])
        
        # 4. 獎勵計算
        base_exp = int(20 + (level * 8))
        base_gold = int(10 + (level * 5))
        
        return {
            "name": f"{rank['name']}的 {species_name}",
            "base_name": species_name,
            "level": level,
            "rank": rank["name"],
            "hp": hp,
            "max_hp": hp,
            "attack": attack,
            "exp_reward": int(base_exp * rank["exp_mult"]),
            "gold_reward": int(base_gold * rank["gold_mult"]),
            "source_id": f"boss_{species_name}" if rank["name"] == "頭目" else "common_species"
        }
