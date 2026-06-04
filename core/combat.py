import random
import math
from typing import List, Dict, Any, Optional, Union
from core.character import Character
from core.models import Skill, Equipment
from core.skill_processor import SkillProcessor
from core.constants import STAT_TRANSLATIONS

class CombatManager:
    def __init__(self, character: Character, monsters: List[Dict[str, Any]]):
        self.character = character
        self.monsters = monsters
        self.turn_order = []
        self.current_turn_idx = 0
        self.battle_logs = []
        self.is_finished = False
        self.winner = None # 'player' or 'monster'
        
        self._initialize_battle()

    def _initialize_battle(self):
        """初始化戰鬥：決定行動順序"""
        entities = []
        # 玩家加入順序 (速度 + 1d10 + 基礎先攻加成 10)
        p_speed = 10 + self.character.total_stats["DEX"] + random.randint(1, 10)
        entities.append({"type": "player", "speed": p_speed, "ref": self.character})
        
        # 怪物加入順序
        for i, m in enumerate(self.monsters):
            m_speed = m["speed"] + random.randint(1, 10)
            entities.append({"type": "monster", "speed": m_speed, "ref": m, "index": i})
            
        # 排序：速度高者先行動
        self.turn_order = sorted(entities, key=lambda x: x["speed"], reverse=True)
        self.battle_logs.append("⚔️ 戰鬥開始！行動順序已決定。")

    def get_current_entity(self) -> Dict[str, Any]:
        return self.turn_order[self.current_turn_idx]

    def next_turn(self):
        """切換到下一個行動者"""
        self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
        # 如果當前行動者已死亡，遞迴跳過
        curr = self.get_current_entity()
        if curr["type"] == "monster" and curr["ref"]["hp"] <= 0:
            self.next_turn()

    async def player_attack(self, target_idx: int) -> Dict[str, Any]:
        """玩家進行普通攻擊 (TRPG 1d20 風格)"""
        target = self.monsters[target_idx]
        c_stats = self.character.combat_stats
        
        # 1. 取得屬性修正與武器加成
        main_hand = self.character.data.equipment_slots.main_hand
        scaling_stat = "STR"
        damage_type = "physical"
        weapon_power = 0
        
        if main_hand and isinstance(main_hand, Equipment):
            scaling_stat = main_hand.scaling_stat
            damage_type = main_hand.damage_type
            weapon_power = main_hand.bonuses.get("ATK", 0) 
            # 有武器時，屬性倍率較高 (1.5x)
            stat_multiplier = 1.5
        else:
            # 空手時，屬性倍率較低 (1.0x)
            stat_multiplier = 1.0
            
        stat_val = self.character.total_stats.get(scaling_stat, 10)
        
        # ... (命中判定代碼保持不變) ...

        # 3. 傷害計算 (1d20 作為威力加乘：0.55x ~ 1.5x)
        dmg_roll = random.randint(1, 20)
        roll_mult = 0.5 + (dmg_roll * 0.05)
        
        # 基礎威力 = (屬性 * 倍率) + 武器
        base_power = (stat_val * stat_multiplier) + weapon_power
        
        # 4. 判定爆擊 (1.5x)
        is_crit = random.random() < c_stats["crit_rate"]
        crit_mult = 1.5 if is_crit else 1.0
        
        # 5. 計算總威力 (基 * 效 * 爆)
        total_power = base_power * roll_mult * crit_mult
        
        # 6. 防禦力固定減免 (Flat Subtraction)
        defense = target["defense"] if damage_type == "physical" else target["m_defense"]
        
        # 最終傷害 = 總威力 - 固定防禦
        final_dmg = max(1, round(total_power - defense))
        
        # 7. 應用傷害
        target["hp"] -= final_dmg
        self._check_battle_status()
        
        crit_tag = "✨ **爆擊！** " if is_crit else ""
        crit_info = f" * 💥1.5x" if is_crit else ""
        
        # 顯示更詳細的計算過程
        stat_name = STAT_TRANSLATIONS.get(scaling_stat, scaling_stat)
        base_breakdown = f"{stat_name}:{stat_val} * {stat_multiplier}x + 攻:{weapon_power}"
        
        calc_info = (
            f"\n 🎲 **判定**: {dmg_roll} (效能 {roll_mult:.2f})"
            f"\n 📊 **威力**: ({base_breakdown}) * {roll_mult:.2f}{crit_info}"
            f"\n 🛡️ **減免**: - 敵方防禦 {defense}"
        )
        
        msg = f"{crit_tag}💥 {self.character.data.name} 對 {target['name']} 造成了 {final_dmg} 點傷害！{calc_info}"
        
        if target["hp"] <= 0:
            msg += f"\n💀 {target['name']} 倒下了！"
            
        return {"success": True, "damage": final_dmg, "is_crit": is_crit, "msg": msg}

    async def monster_action(self) -> Dict[str, Any]:
        """處理當前怪物的 AI 行動 (TRPG 風格)"""
        curr = self.get_current_entity()
        if curr["type"] != "monster": return {"success": False}
        
        monster = curr["ref"]
        c_stats = self.character.combat_stats
        
        # 1. 怪物命中判定
        hit_chance = 90 - (c_stats["evasion_rate"] * 100)
        if random.randint(1, 100) > hit_chance:
            return {"success": False, "msg": f"🛡️ {self.character.data.name} 靈巧地躲過了 {monster['name']} 的攻擊！ (迴避 {c_stats['evasion_rate']*100:.1f}%)"}
            
        # 2. 玩家減傷計算
        # 使用統一的戰鬥屬性計算
        p_def = c_stats["p_def"]
        
        # 韌性減傷 (比例減傷)
        tenacity_reduction = 1.0 - (c_stats["tenacity"] / 1000)
        tenacity_reduction = max(0.5, tenacity_reduction)
        
        # 怪物傷害：1d20 效能倍率 * (基礎攻擊力)
        m_roll = random.randint(1, 20)
        m_roll_mult = 0.5 + (m_roll * 0.05)
        total_m_power = monster["attack"] * m_roll_mult
        
        # 最終傷害 = (威力 - 固定防禦) * 韌性比例減傷
        final_dmg = max(1, round((total_m_power - p_def) * tenacity_reduction))
        
        self.character.data.vitality.hp -= final_dmg
        self.character.save()
        self._check_battle_status()
        
        # 顯示更詳細的計算過程
        lvl_bonus = self.character.data.level // 2
        ts = self.character.total_stats
        # 物理防禦：體質核心(0.7) + 力量(0.2) + 敏捷(0.1)
        stat_def = (ts["CON"] * 0.7) + (ts["STR"] * 0.2) + (ts["DEX"] * 0.1)
        def_formula = f"體質:{ts['CON']}*0.7 + 力量:{ts['STR']}*0.2 + 敏捷:{ts['DEX']}*0.1"
        
        calc_info = (
            f"\n 🎲 **判定**: {m_roll} (效能 {m_roll_mult:.2f})"
            f"\n 📊 **威力**: {monster['attack']} * {m_roll_mult:.2f}"
            f"\n 🛡️ **防禦**: -{p_def} (屬防:{stat_def:.1f} ({def_formula}) + 等級:{lvl_bonus})"
            f"\n ✨ **減傷**: 韌性免傷 {(1-tenacity_reduction)*100:.0f}%"
        )
        return {"success": True, "damage": final_dmg, "msg": f"💢 {monster['name']} 攻擊了 {self.character.data.name}，造成 {final_dmg} 點傷害！{calc_info}"}

    def _check_battle_status(self):
        """檢查戰鬥是否結束"""
        if self.character.data.vitality.hp <= 0:
            self.is_finished = True
            self.winner = "monster"
            return
            
        if all(m["hp"] <= 0 for m in self.monsters):
            self.is_finished = True
            self.winner = "player"
            return

    def get_battle_summary(self) -> str:
        status = f"👤 **{self.character.data.name}**: {self.character.data.vitality.hp}/{self.character.max_hp} HP\n"
        for i, m in enumerate(self.monsters):
            level_str = f"Lv.{m['level']}"
            hp_str = f"{max(0, m['hp'])}/{m['max_hp']} HP"
            status += f"👾 #{i} **{m['name']}** ({level_str}): {hp_str} {'(已倒下)' if m['hp'] <= 0 else ''}\n"
        return status
