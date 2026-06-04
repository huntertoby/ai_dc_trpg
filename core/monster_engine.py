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
    async def generate_monster_group(cls, area: AreaSchema, llm_client, novelty_chance: float = 0.2) -> List[Dict[str, Any]]:
        """
        根據地區生態生成怪物群體 (1~3 隻)。
        """
        import random
        # 決定怪物數量 (1-3 隻)
        count_weights = [70, 20, 10]
        if area.threat_level > 5: count_weights = [50, 30, 20]
        if area.threat_level > 10: count_weights = [30, 40, 30]
        
        num_monsters = random.choices([1, 2, 3], weights=count_weights, k=1)[0]
        
        monsters = []
        for _ in range(num_monsters):
            monsters.append(await cls._generate_single_monster(area, llm_client, novelty_chance))
        return monsters

    @classmethod
    async def _generate_single_monster(cls, area: AreaSchema, llm_client, novelty_chance: float = 0.2) -> Dict[str, Any]:
        """生成單隻怪物的內部邏輯"""
        import random
        from utils.json_utils import repair_and_parse_json
        
        # 1. 決定階級
        rank = MonsterRank.roll_rank(area.threat_level)
        is_high_rank = rank["name"] in ["史詩", "頭目"]

        # 2. 決定物種機率 (隨數量遞減)
        num_variants = len(area.discovered_variants)
        # 機率公式：基礎 0.4，隨種類增加而迅速遞減
        effective_novelty_chance = 0.6 / (1 + num_variants)
        is_novelty = random.random() < effective_novelty_chance
        
        # 3. 執行生成
        # 如果是新物種，或是高等級怪物，則呼叫 AI 進行精緻化生成
        if is_novelty or is_high_rank or not area.discovered_variants:
            base_species = random.choice(area.dominant_species) if area.dominant_species else "未知生物"
            
            system_prompt = f"""
            你是一個專業的 TRPG 數值設計師。
            請為地區「{area.name}」(標籤: {area.ecology_tags}) 的物種「{base_species}」生成一個變體。
            
            **【要求】**
            1. **名稱**：不使用死板的前綴，而是富有敘事感的命名 (如: 「焦渴的食屍鬼」、「被虛空侵蝕的銀狼」)。
            2. **特徵 (Trait)**：賦予一個獨特的戰鬥特徵或被動能力描述 (如: 「每次攻擊會造成流血」、「死亡時爆發毒霧」)。
            3. **階級**：{rank["name"]}。
            
            回應格式為 JSON:
            {{
                "name": "變體名稱",
                "trait": "特徵描述"
            }}
            """
            
            try:
                res = await llm_client.call(f"生成{rank['name']}怪物: {base_species}", system_prompt)
                data = repair_and_parse_json(res)
                species_name = data.get("name", f"{rank['name']}的{base_species}")
                trait = data.get("trait", "無特殊特徵")
            except:
                species_name = f"{rank['name']}的{base_species}"
                trait = "強大的存在"

            # 紀錄到生態系統 (如果是新物種)
            if is_novelty and not any(v["name"] == species_name for v in area.discovered_variants):
                area.discovered_variants.append({"name": species_name, "trait": trait, "rank": rank["name"]})
        else:
            # 從已發現的物種中挑選 (偏好階級相近的)
            variant = random.choice(area.discovered_variants)
            species_name = variant["name"]
            trait = variant.get("trait", "無特殊特徵")

        # 4. 計算基礎能力 (隨 Level 縮放) - 平衡性調整
        level = area.base_level
        mult = rank["multiplier"]
        
        # 基礎值設定
        hp = int((60 + (level * 15)) * mult)
        mp = int((30 + (level * 5)) * mult)
        attack = int((5 + (level * 3)) * mult)
        
        # 防禦與功能性數值
        defense = int((2 + (level * 1.5)) * mult)
        m_defense = int((1 + (level * 1)) * mult)
        speed = int((5 + (level * 0.5)) * mult)
        evasion = 0.02 + (level * 0.002)
        
        # 獎勵計算
        base_exp = int(20 + (level * 8))
        base_gold = int(10 + (level * 5))
        
        return {
            "name": f"{rank['name']}的 {species_name}",
            "base_name": species_name,
            "trait": trait,                          # 加入 AI 生成的特徵描述
            "level": level,
            "rank": rank["name"],
            "hp": hp,
            "max_hp": hp,
            "mp": mp,
            "max_mp": mp,
            "attack": attack,
            "defense": defense,
            "m_defense": m_defense,
            "speed": speed,
            "evasion": min(evasion, 0.4),
            "skills": [],
            "exp_reward": int(base_exp * rank["exp_mult"]),
            "gold_reward": int(base_gold * rank["gold_mult"]),
            "source_id": f"boss_{species_name}" if rank["name"] == "頭目" else "common_species"
        }
