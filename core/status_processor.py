# core/status_processor.py
from datetime import datetime
from typing import List
from core.models import StatusEffect, CharacterSchema

class StatusProcessor:
    @classmethod
    def tick_turns(cls, character: CharacterSchema):
        """扣除回合制狀態的持續時間 (在每次行動後執行)"""
        remaining_effects = []
        for effect in character.status_effects:
            if effect.duration_type == "turns":
                effect.duration -= 1
                if effect.duration > 0:
                    remaining_effects.append(effect)
            else:
                # 天數制的狀態不在此處處理
                remaining_effects.append(effect)
        character.status_effects = remaining_effects

    @classmethod
    def update_days(cls, character: CharacterSchema):
        """更新天數制狀態 (在每日重置時執行)"""
        today = datetime.now().strftime("%Y-%m-%d")
        remaining_effects = []
        for effect in character.status_effects:
            if effect.duration_type == "days":
                # 這裡的邏輯可以根據需求調整
                # 簡單方案：如果 start_date + duration < today 則過期
                # 或者簡單扣除 duration
                effect.duration -= 1
                if effect.duration > 0:
                    remaining_effects.append(effect)
            else:
                remaining_effects.append(effect)
        character.status_effects = remaining_effects

class DailyResetManager:
    @classmethod
    def check_and_reset(cls, character: CharacterSchema) -> bool:
        """
        檢查是否跨越了午夜 12 點。
        支援補算天數 (如果玩家幾天沒上線)。
        """
        today_dt = datetime.now()
        today_str = today_dt.strftime("%Y-%m-%d")
        
        if character.last_daily_reset_date == today_str:
            return False
            
        # 如果是第一次紀錄 (新角色)，直接設定日期不執行重置
        if not character.last_daily_reset_date:
            character.last_daily_reset_date = today_str
            return False

        # 計算日期差
        last_date = datetime.strptime(character.last_daily_reset_date, "%Y-%m-%d")
        delta = (today_dt.date() - last_date.date()).days
        
        if delta <= 0:
            return False

        # --- 執行每日重置邏輯 ---
        
        # 1. 補算天數制狀態 (如果斷開 2 天，就扣 2 天持續時間)
        for _ in range(delta):
            StatusProcessor.update_days(character)
        
        # 2. 恢復體力 (每日登入獎勵)
        character.vitality.stamina = character.vitality.max_stamina
        
        # 3. 更新重置日期
        character.last_daily_reset_date = today_str
        
        # 4. 同步更新 Tavern 的檢查日期 (確保 tavern 邏輯與系統重置同步)
        # 這裡不清除，而是讓 tavern 比對當前日期，系統重置確保了體力補滿
        
        return True
