# core/skill_processor.py
import random
import re
from typing import Dict, Any, Tuple
from core.models import Skill, CharacterSchema

class SkillProcessor:
    @staticmethod
    def roll_dice(dice_str: str) -> int:
        """解析 NdM±X 格式並回傳隨機結果 (例如: 1d20, 2d6+3, 1d10-1)"""
        # 使用正則表達式捕捉：數量(d)面數(±加成)
        match = re.match(r"(\d+)d(\d+)(?:([+-])(\d+))?", dice_str.lower().strip())
        if not match:
            return 0
        
        num_str, sides_str, sign, modifier_str = match.groups()
        num = int(num_str)
        sides = int(sides_str)
        
        # 基礎擲骰
        total = sum(random.randint(1, sides) for _ in range(num))
        
        # 處理加減值
        if sign and modifier_str:
            modifier = int(modifier_str)
            if sign == '+':
                total += modifier
            elif sign == '-':
                total -= modifier
                
        return max(0, total)  # 確保擲骰結果不會是負數

    @classmethod
    def validate_and_clamp_skill(cls, skill: Skill) -> Skill:
        """
        技能平衡器：根據階級 (Tier) 與目標類型 (AoE) 強制校正分母 (Divisor)。
        """
        # 1. 定義階級對應的基礎最小分母 (T1 最稀有，T5 最普通)
        tier_min_divisors = {
            "T1": 5.0,  # 傳說：最高 4.0x
            "T2": 8.0,  # 史詩：最高 2.5x
            "T3": 10.0, # 稀有：最高 2.0x
            "T4": 12.0, # 精良：最高 1.6x
            "T5": 15.0  # 普通：最高 1.3x
        }
        
        base_min = tier_min_divisors.get(skill.tier, 15.0)
        
        # 2. 應用「範圍稅 (AoE Tax)」
        # 如果是 AoE，分母下限乘以 1.5 (代表傷害降低 33%)
        if skill.mechanics.target_type == "aoe":
            base_min *= 1.5
            
        # 3. 強制執行校正
        formula = skill.mechanics.formula
        if formula.type == "multiplier":
            original = formula.divisor
            formula.divisor = max(base_min, formula.divisor)
            if formula.divisor > original:
                print(f"⚖️ 技能 {skill.name} ({skill.tier}) 分母已從 {original} 校正為 {formula.divisor} (AoE: {skill.mechanics.target_type == 'aoe'})")
        
        return skill

    @classmethod
    def calculate_base_value(cls, skill: Skill, total_stats: Dict[str, int]) -> Tuple[float, int]:
        """
        計算技能的基礎數值（傷害或治療）。
        回傳: (最終數值, 骰子點數)
        """
        formula = skill.mechanics.formula
        dice_roll = cls.roll_dice(formula.dice)
        stat_val = total_stats.get(formula.base_stat, 5)

        if formula.type == "multiplier":
            # 乘法骰：Stat * (Dice / Divisor)
            multiplier = dice_roll / formula.divisor
            final_val = stat_val * multiplier
        else:
            # 加法骰：Dice + Stat (傳統模式，可保留備用)
            final_val = dice_roll + stat_val
            
        return final_val, dice_roll

    @classmethod
    def execute_skill(cls, skill: Skill, character: Any) -> Dict[str, Any]:
        """
        執行技能的預運算邏輯。
        """
        # 1. 檢查並扣除消耗
        costs = skill.mechanics.cost
        if character.data.vitality.mp < costs.get("MP", 0):
            raise ValueError("法力值不足")
        if character.data.vitality.sanity < costs.get("SAN", 0):
            raise ValueError("理智值不足")
        
        character.data.vitality.mp -= costs.get("MP", 0)
        character.data.vitality.sanity -= costs.get("SAN", 0)

        # 2. 計算核心數值
        final_val, dice_roll = cls.calculate_base_value(skill, character.total_stats)

        # 3. 回傳運算結果，準備交給 AI 敘事
        return {
            "skill_name": skill.name,
            "final_value": round(final_val, 1),
            "dice_roll": dice_roll,
            "dice_type": skill.mechanics.formula.dice,
            "keywords": skill.mechanics.keywords,
            "narrative_effect": skill.mechanics.narrative_effect
        }
