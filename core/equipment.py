# core/equipment.py
from typing import Dict, Any
from core.models import Equipment

class EquipmentBalancer:
    # 稀有度倍率配置 (T1 最稀有, T5 最普通)
    TIER_SUB_MULTIPLIERS = {
        "T5": 0.0,   # 普通：無附屬性
        "T4": 0.8,   # 精良：調降係數
        "T3": 1.5,   # 稀有
        "T2": 2.5,   # 史詩
        "T1": 4.0    # 傳說
    }

    # 附屬性數量限制 (T5:0, T4:1, T3:2, T2:3, T1:3+特殊)
    AFFIX_SLOTS = {
        "T5": 0, "T4": 1, "T3": 2, "T2": 3, "T1": 3
    }

    # 屬性權重 (權重越高，佔用的預算越多)
    STAT_WEIGHTS = {
        "STR": 1.0, "DEX": 1.0, "CON": 1.0, "INT": 1.0, "WIS": 1.0, "CHA": 1.0,
        "crit_rate": 1000.0,    # 1% = 10 點
        "evasion_rate": 1000.0, # 1% = 10 點
        "accuracy": 1000.0,     # 1% = 10 點
        "skill_power": 1000.0,  # 1% = 10 點
        "tenacity": 1.0,        # 1 點 = 1 點
        "luck": 5.0             # 1 點 = 5 點
    }

    @classmethod
    def calculate_budgets(cls, item_level: int, tier: str) -> dict:
        """分別計算主屬性與附屬性的預算"""
        # 主屬性：縮減預算 (*0.75)
        primary_budget = (10 + (item_level * 2.5)) * 0.75
        # 附屬性：基礎值再砍半 (從 0.5 降至 0.25)
        sub_base = (item_level * 0.25) 
        multiplier = cls.TIER_SUB_MULTIPLIERS.get(tier, 0.0)
        sub_budget = sub_base * multiplier
        return {"primary": primary_budget, "sub": sub_budget}

    @classmethod
    def validate_and_clamp(cls, equipment: Equipment) -> Equipment:
        """
        雙軌制過濾器：確保主屬性存在且附屬性數量/強度正確。
        """
        budgets = cls.calculate_budgets(equipment.item_level, equipment.tier)
        
        # 0. 移除負數或零
        equipment.bonuses = {k: v for k, v in equipment.bonuses.items() if v > 0}
        
        # 分類屬性
        primary_list = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        proposed_primary = {k: v for k, v in equipment.bonuses.items() if k in primary_list}
        proposed_sub = {k: v for k, v in equipment.bonuses.items() if k not in primary_list}

        # 1. 處理主屬性 (Primary)
        if not proposed_primary:
            # 根據部位給予預設主屬性 (防具現在統一強化 CON 作為生存核心)
            proposed_primary = {"CON": budgets["primary"]}
        
        p_cost = sum(proposed_primary.values())
        if p_cost > 0:
            ratio = budgets["primary"] / p_cost
            # 確保主屬性至少有 1 點且取整
            proposed_primary = {k: float(max(1, round(v * ratio))) for k, v in proposed_primary.items()}
        
        # 2. 處理附屬性 (Sub)
        max_slots = cls.AFFIX_SLOTS.get(equipment.tier, 0)
        if max_slots > 0:
            if not proposed_sub:
                proposed_sub = {"luck": 1.0} 
            
            # 只保留權重成本最高的前 N 條
            sorted_subs = sorted(
                proposed_sub.items(), 
                key=lambda x: x[1] * cls.STAT_WEIGHTS.get(x[0], 1.0), 
                reverse=True
            )
            proposed_sub = dict(sorted_subs[:max_slots])

            s_cost = sum(abs(v) * cls.STAT_WEIGHTS.get(k, 1.0) for k, v in proposed_sub.items())
            if s_cost > 0 and budgets["sub"] > 0:
                ratio = budgets["sub"] / s_cost
                new_sub = {}
                for k, v in proposed_sub.items():
                    w = cls.STAT_WEIGHTS.get(k, 1.0)
                    final_v = v * ratio
                    # 確保不因捨入歸零
                    if w < 10:
                        new_sub[k] = float(max(1, round(final_v)))
                    else:
                        new_sub[k] = float(max(0.01, round(final_v, 2)))
                proposed_sub = new_sub
        else:
            proposed_sub = {}

        # 3. 最終清理：合併並徹底移除所有值為 0 的項
        final_bonuses = {**proposed_primary, **proposed_sub}
        
        # 針對武器動態加入 ATK 屬性，針對盾牌動態加入 p_def 屬性
        if equipment.slot_type in ["main_hand", "off_hand"]:
            is_shield = equipment.weapon_type in ["小盾", "巨盾"]
            is_focus = equipment.weapon_type in ["法器", "魔導書"]
            
            if equipment.slot_type == "main_hand" or (equipment.slot_type == "off_hand" and not is_shield and not is_focus):
                # 計算武器基礎 ATK
                ilvl = equipment.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(equipment.tier, 1.0)
                
                if equipment.is_two_handed:
                    atk_val = (15.0 + ilvl * 3.0) * mult
                else:
                    atk_val = (5.0 + ilvl * 1.5) * mult
                final_bonuses["ATK"] = float(round(atk_val, 1))
            elif is_shield:
                # 計算盾牌基礎物理防禦
                ilvl = equipment.item_level
                tier_mults = {"T5": 1.0, "T4": 1.2, "T3": 1.5, "T2": 1.8, "T1": 2.2}
                mult = tier_mults.get(equipment.tier, 1.0)
                if equipment.weapon_type == "巨盾":
                    def_val = (10.0 + ilvl * 2.0) * mult
                else:
                    def_val = (5.0 + ilvl * 1.0) * mult
                final_bonuses["p_def"] = float(round(def_val, 1))

        equipment.bonuses = {k: v for k, v in final_bonuses.items() if v > 0}
        
        # 4. 特殊效果過濾：僅 T1 (傳說) 允許擁有特殊效果描述
        if equipment.tier != "T1":
            equipment.special_effect = ""
            
        return equipment

    @classmethod
    def get_tier_color(cls, tier: str) -> int:
        colors = {"T1": 0xf1c40f, "T2": 0x9b59b6, "T3": 0x3498db, "T4": 0x2ecc71, "T5": 0x95a5a6}
        return colors.get(tier, 0xffffff)
