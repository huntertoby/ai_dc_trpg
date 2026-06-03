# core/character.py
from core.models import CharacterSchema, Item, Equipment, StatusEffect
from db.storage import CharacterRepository
from core.constants import RANK_ORDER
from typing import Union

class Character:
    def __init__(self, data: CharacterSchema, user_id: str):
        self.data = data
        self.user_id = user_id

    @property
    def rank_value(self) -> int:
        """獲取目前階級的數值，用於比較 (E=0, D=1, C=2, B=3, A=4, S=5)"""
        return RANK_ORDER.get(self.data.rank, 0)

    @property
    def total_stats(self) -> dict:
        """計算 基礎屬性 + 裝備加成 + 狀態加成 的最終總值"""
        base = self.data.primary_stats
        bonuses = self.get_total_bonuses()
        
        status_bonuses = {}
        for effect in self.data.status_effects:
            for stat, val in effect.bonuses.items():
                status_bonuses[stat] = status_bonuses.get(stat, 0) + val

        def get_stat(name: str) -> int:
            return getattr(base, name) + int(bonuses.get(name, 0)) + int(status_bonuses.get(name, 0))

        return {
            "STR": get_stat("STR"), "DEX": get_stat("DEX"), "CON": get_stat("CON"),
            "INT": get_stat("INT"), "WIS": get_stat("WIS"), "CHA": get_stat("CHA")
        }

    @property
    def max_hp(self) -> int:
        """最大生命值：基礎 100 + 總體質 * 10"""
        return 100 + (self.total_stats["CON"] * 10)

    @property
    def max_mp(self) -> int:
        """最大法力值：基礎 50 + 總智力 * 10 + 總感知 * 5"""
        ts = self.total_stats
        return 50 + (ts["INT"] * 10) + (ts["WIS"] * 5)

    @property
    def max_sanity(self) -> int:
        """最大理智值：基礎 100 + 總感知 * 5"""
        return 100 + (self.total_stats["WIS"] * 5)

    @property
    def max_stamina(self) -> int:
        """最大精力值：基礎 100 + 總體質 * 5"""
        return 100 + (self.total_stats["CON"] * 5)

    @property
    def xp_required(self) -> int:
        """升級所需的經驗值：指數成長公式 100 * (等級^1.5)"""
        return int(100 * (self.data.level ** 1.5))

    def add_item(self, item: Union[Item, Equipment, str], description: str = "", quantity: int = 1):
        """新增物品到背包"""
        if isinstance(item, (Item, Equipment)):
            if not isinstance(item, Equipment):
                for inv_item in self.data.inventory:
                    if inv_item.name == item.name and not isinstance(inv_item, Equipment):
                        inv_item.quantity += item.quantity
                        self.save()
                        return
            self.data.inventory.append(item)
        else:
            self.data.inventory.append(Item(name=item, description=description, quantity=quantity))
        self.save()

    def equip_item(self, item_name: str):
        """從背包尋找指定物品並穿上 (支援雙手武器邏輯)"""
        found_idx = -1
        found_item = None
        for i, item in enumerate(self.data.inventory):
            if item.name == item_name and isinstance(item, Equipment):
                found_idx = i
                found_item = item
                break

        if not found_item:
            raise ValueError(f"背包裡找不到可裝備的物品: {item_name}")

        slot = found_item.slot_type
        if not hasattr(self.data.equipment_slots, slot):
            raise ValueError(f"錯誤：系統不支援 {slot} 這種裝備位置。")

        # --- 雙手武器特殊邏輯 ---
        if slot == "main_hand":
            if found_item.is_two_handed:
                # 穿上雙手武器：卸下副手
                old_off = self.data.equipment_slots.off_hand
                if old_off:
                    self.data.inventory.append(old_off)
                    self.data.equipment_slots.off_hand = None
            elif self.data.equipment_slots.off_hand and self.data.equipment_slots.off_hand.is_two_handed:
                # 雖然主手不是雙手，但如果副手是雙手（不應該發生但作防呆），也卸下副手
                old_off = self.data.equipment_slots.off_hand
                self.data.inventory.append(old_off)
                self.data.equipment_slots.off_hand = None

        if slot == "off_hand":
            # 穿上副手：若主手是雙手武器，則卸下主手
            old_main = self.data.equipment_slots.main_hand
            if old_main and old_main.is_two_handed:
                self.data.inventory.append(old_main)
                self.data.equipment_slots.main_hand = None

        # 替換目標槽位
        old_eq = getattr(self.data.equipment_slots, slot)
        if old_eq:
            self.data.inventory.append(old_eq)
        
        setattr(self.data.equipment_slots, slot, found_item)
        self.data.inventory.pop(found_idx)
        self.save()

    def unequip_item(self, slot: str):
        """卸下指定位置的裝備並放入背包"""
        if not hasattr(self.data.equipment_slots, slot):
            raise ValueError(f"無效的裝備位置: {slot}")
        
        old_eq = getattr(self.data.equipment_slots, slot)
        if old_eq:
            self.data.inventory.append(old_eq)
            setattr(self.data.equipment_slots, slot, None)
            self.save()
            return old_eq
        return None

    def add_status_effect(self, name: str, description: str, duration: int):
        self.data.status_effects.append(StatusEffect(name=name, description=description, duration=duration))
        self.save()

    def tick_status_effects(self):
        for effect in self.data.status_effects:
            effect.duration -= 1
        self.data.status_effects = [e for e in self.data.status_effects if e.duration > 0]
        self.save()

    def add_bonus_points(self, distribution: dict):
        """分配屬性點"""
        total_to_spend = sum(distribution.values())
        if total_to_spend > self.data.stat_points:
            raise ValueError(f"點數不足！剩餘點數: {self.data.stat_points}")

        for attr, amount in distribution.items():
            if hasattr(self.data.primary_stats, attr):
                setattr(self.data.primary_stats, attr, getattr(self.data.primary_stats, attr) + amount)
        
        self.data.stat_points -= total_to_spend
        self.data.bonus_points_spent += total_to_spend
        self.save()

    def heal_all(self):
        self.data.vitality.hp = self.max_hp
        self.data.vitality.mp = self.max_mp
        self.data.vitality.sanity = self.max_sanity
        self.data.vitality.stamina = self.max_stamina
        self.save()

    def get_total_bonuses(self) -> dict:
        total = {}
        for slot in self.data.equipment_slots.model_fields.keys():
            eq_item = getattr(self.data.equipment_slots, slot)
            if eq_item and isinstance(eq_item, Equipment):
                for stat, value in eq_item.bonuses.items():
                    total[stat] = total.get(stat, 0) + value
        return total

    def save(self):
        self.data.vitality.max_hp = self.max_hp
        self.data.vitality.max_mp = self.max_mp
        self.data.vitality.max_sanity = self.max_sanity
        self.data.vitality.max_stamina = self.max_stamina
        
        # 確保當前值不超過上限
        self.data.vitality.hp = min(self.data.vitality.hp, self.data.vitality.max_hp)
        self.data.vitality.mp = min(self.data.vitality.mp, self.data.vitality.max_mp)
        self.data.vitality.sanity = min(self.data.vitality.sanity, self.data.vitality.max_sanity)
        self.data.vitality.stamina = min(self.data.vitality.stamina, self.data.vitality.max_stamina)
        
        CharacterRepository.save(self.data, self.user_id)

    @property
    def combat_stats(self) -> dict:
        ts = self.total_stats
        bonuses = self.get_total_bonuses()
        def get_bonus(name: str) -> float: return bonuses.get(name, 0.0)
        main_off = max(ts["DEX"], ts["INT"], ts["WIS"])
        return {
            "crit_rate": 0.05 + (main_off * 0.005) + get_bonus("crit_rate"),
            "evasion_rate": 0.05 + (ts["DEX"] * 0.008) + get_bonus("evasion_rate"),
            "accuracy": 0.85 + (max(ts["DEX"], ts["WIS"]) * 0.01) + get_bonus("accuracy"),
            "cast_speed": 1.0 + (ts["INT"] * 0.02) + get_bonus("cast_speed"),
            "tenacity": int(ts["CON"] * 2 + get_bonus("tenacity")),
            "luck": int(1 + get_bonus("luck"))
        }

    @classmethod
    def load(cls, user_id: str):
        data = CharacterRepository.load_active(user_id)
        return cls(data, user_id) if data else None
