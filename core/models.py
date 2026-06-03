from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Union, Literal, Any
from core.constants import RANK_ORDER

class Item(BaseModel):
    name: str
    description: str = ""
    quantity: int = 1
    item_type: str = "material"

class Equipment(Item):
    item_type: Literal["equipment"] = "equipment"
    slot_type: str
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T1" # 裝備稀有度
    item_level: int = 1                               # 裝備等級
    is_two_handed: bool = False                      # 是否為雙手武器
    special_effect: str = ""                         # 特殊描述/技能預留位
    bonuses: Dict[str, float] = Field(default_factory=dict)

class StatusEffect(BaseModel):
    name: str
    description: str = ""
    duration: int = 0
    bonuses: Dict[str, float] = Field(default_factory=dict)

class BuildingSchema(BaseModel):
    id: str
    name: str
    description: str
    features: List[str] = [] # 功能標籤：['rest', 'trade', 'quest', 'bank', 'training']
    npc_name: Optional[str] = None
    npc_traits: List[str] = []
    talk_cost: int = 5         # 交談消耗體力
    rumor_rate: float = 0.3    # 獲取情報機率 (0.0 ~ 1.0)

class AreaSchema(BaseModel):
    id: str                   # 格式 "x,y"
    name: str
    type: str                 # 'city', 'wilderness', 'dungeon'
    description: str
    landmarks: List[BuildingSchema] = [] # 地標或興趣點 (原名 buildings)
    base_level: int = 1
    connections: List[str] = [] # 相鄰地區的 ID
    discovered_by: Optional[str] = None
    interacted_users: List[str] = [] # 紀錄哪些玩家已經在這裡執行過「深入探索」

    @model_validator(mode='before')
    @classmethod
    def fix_landmarks_rename(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "buildings" in data and "landmarks" not in data:
                data["landmarks"] = data.pop("buildings")
        return data

class WarehouseSchema(BaseModel):
    user_id: str
    gold: int = 0
    items: List[Union[Equipment, Item]] = []
    max_slots: int = 50       # 倉庫初始格數較大
    upgrade_level: int = 0    # 擴充等級

class QuestObjective(BaseModel):
    type: Literal["kill", "collect", "visit", "talk", "explore"]
    target_id: str            # 怪物 ID, 物品 ID, 或 NPC 名稱
    count: int = 1
    current_count: int = 0
    location: Optional[List[int]] = None

class QuestSchema(BaseModel):
    id: str
    title: str
    description: str
    rank_required: str        # 'E', 'D', 'C', 'B', 'A', 'S'
    level_required: int = 1
    objectives: List[QuestObjective] = []
    rewards: Dict[str, int] = Field(default_factory=dict) # {"gold": 100, "exp": 200}
    is_global: bool = False   # 是否為全服競爭任務
    slots_left: int = 999
    deadline: Optional[float] = None

    @property
    def rank_value(self) -> int:
        return RANK_ORDER.get(self.rank_required, 0)

class PrimaryAttributes(BaseModel):
    STR: int = Field(default=5, ge=5)
    DEX: int = Field(default=5, ge=5)
    CON: int = Field(default=5, ge=5)
    INT: int = Field(default=5, ge=5)
    WIS: int = Field(default=5, ge=5)
    CHA: int = Field(default=5, ge=5)

class CombatAttributes(BaseModel):
    crit_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    evasion_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    accuracy: float = Field(default=0.95, ge=0.0, le=1.0)
    cast_speed: float = Field(default=1.0, ge=0.0)
    tenacity: int = Field(default=0, ge=0)
    luck: int = Field(default=1, ge=0)

class EquipmentSlots(BaseModel):
    head: Optional[Equipment] = None
    shoulders: Optional[Equipment] = None
    cloak: Optional[Equipment] = None                # 新增：披風槽位
    chest: Optional[Equipment] = None
    hands: Optional[Equipment] = None
    legs: Optional[Equipment] = None
    feet: Optional[Equipment] = None
    main_hand: Optional[Equipment] = None
    off_hand: Optional[Equipment] = None
    trinket_1: Optional[Equipment] = None
    trinket_2: Optional[Equipment] = None
    ring_1: Optional[Equipment] = None
    ring_2: Optional[Equipment] = None

class Personality(BaseModel):
    belief: str = "無"
    flaw: str = "無"
    fear: str = "無"

class Vitality(BaseModel):
    hp: int = 100
    max_hp: int = 100
    mp: int = 50
    max_mp: int = 50
    stamina: int = 100        # 新增：當前精力
    max_stamina: int = 100    # 新增：最大精力
    sanity: int = 100
    max_sanity: int = 100

class SkillFormula(BaseModel):
    type: Literal["multiplier", "additive"] = "multiplier"
    base_stat: str = "STR" 
    dice: str = "1d20"    
    divisor: float = 10.0  

class SkillMechanics(BaseModel):
    action_type: Literal["damage", "heal", "buff", "debuff"] = "damage" # 技能行為類型
    target_type: Literal["single", "aoe", "self", "allies"] = "single" # 技能目標類型
    cost: Dict[str, int] = Field(default_factory=dict)
    formula: SkillFormula = Field(default_factory=SkillFormula)
    keywords: List[str] = [] 
    custom_logic: str = ""   
    narrative_effect: str = "" 

class Skill(BaseModel):
    name: str
    description: str
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T5" # 技能階級 (T5 為最基礎)
    mechanics: SkillMechanics

class CharacterSchema(BaseModel):
    character_id: str
    name: str
    job_name: str = "冒險者"
    base_jobs: List[str] = Field(default_factory=lambda: ["戰士"]) 
    race: str = "人類"         
    base_race: str = "人類"    
    level: int = 1            
    exp: int = 0
    gold: int = 0
    background: str
    primary_stats: PrimaryAttributes = Field(default_factory=PrimaryAttributes)
    equipment_slots: EquipmentSlots = Field(default_factory=EquipmentSlots)
    bonus_points_spent: int = 0
    stat_points: int = 5      # 新增：可用屬性點，初始為 5 點
    abilities: List[Skill] = []
    personality: Personality = Field(default_factory=Personality)
    vitality: Vitality = Field(default_factory=Vitality)
    inventory: List[Union[Equipment, Item]] = []
    status_effects: List[StatusEffect] = []
    location: List[int] = Field(default_factory=lambda: [0, 0]) # 新增：當前座標 [x, y]
    last_regen: float = 0.0                                     # 新增：上次體力恢復時間戳記
    max_inventory_slots: int = 20                               # 新增：背包格數上限，初始 20
    rank: str = "E"                                             # 新增：冒險者階級 (E, D, C, B, A, S)
    reputation: int = 0                                         # 新增：名聲值
    active_quests: List[QuestSchema] = []                        # 新增：進行中的任務
    known_rumors: List[str] = []                                # 新增：已獲取的情報/傳聞
    last_free_rest_date: Optional[str] = None                   # 新增：上次免費休息日期 (YYYY-MM-DD)
    last_paid_rest_date: Optional[str] = None                   # 新增：上次付費休息日期 (YYYY-MM-DD)


