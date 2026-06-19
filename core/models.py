from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Union, Literal, Any, Annotated
from core.constants import RANK_ORDER

class Item(BaseModel):
    name: str
    description: str = ""
    quantity: int = 1
    item_type: str = "material"
    material_type: Optional[str] = None
    tier: Optional[str] = None
    source_id: Optional[str] = None

class Equipment(Item):
    item_type: Literal["equipment"] = "equipment"
    slot_type: str
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T1" # 裝備稀有度
    item_level: int = 1                               # 裝備等級
    is_two_handed: bool = False                      # 是否為雙手武器
    special_effect: str = ""                         # 特殊描述/技能預留位
    bonuses: Dict[str, float] = Field(default_factory=dict)
    executable_triggers: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)      # 標籤系統
    allowed_jobs: List[str] = Field(default_factory=list) # 允許使用職業限制
    
    # --- 戰鬥系統擴充 ---
    weapon_type: Optional[str] = None                # 'sword', 'bow', 'staff', 'dagger', etc.
    damage_type: Literal["physical", "magical"] = "physical"
    scaling_stat: Literal["STR", "DEX", "INT", "WIS", "CHA", "CON"] = "STR"
    # ------------------

    @model_validator(mode='after')
    def register_custom_aliases(self) -> 'Equipment':
        for trigger in getattr(self, "executable_triggers", []) or []:
            if isinstance(trigger, dict):
                for action in trigger.get("actions", []) or []:
                    if isinstance(action, dict):
                        custom_name = action.get("custom_status_name")
                        canonical = action.get("canonical_status")
                        if custom_name and canonical:
                            from core.constants import STATUS_REGISTRY
                            if canonical in STATUS_REGISTRY:
                                aliases = STATUS_REGISTRY[canonical]["aliases"]
                                if custom_name not in aliases:
                                    aliases.append(custom_name)
                                    print(f"🔄 [Pydantic] 動態註冊狀態別名恢復：將「{custom_name}」關聯至「{canonical}」")
        return self

class StatusEffect(BaseModel):
    name: str
    description: str = ""
    duration_type: Literal["turns", "days"] = "turns" # 狀態週期：回合(行動) 或 天數
    duration: int = 0                                 # 剩餘數值
    start_date: Optional[str] = None                  # 針對天數制：開始日期 (YYYY-MM-DD)
    bonuses: Dict[str, float] = Field(default_factory=dict)
    executable_triggers: List[Dict[str, Any]] = Field(default_factory=list)
    stacks: int = 1                                   # 當前層數
    max_stacks: int = 5                               # 最大堆疊上限
    trigger_limit: int = 0                            # 最大觸發次數 (0 代表無限制)
    trigger_count: int = 0                            # 已觸發次數
    # --- DoT 傷害欄位（施加時算好，tick 直接讀取）---
    dot_damage_flat: float = 0.0                      # 每 tick 固定傷害值
    dot_scaling_stat: Optional[str] = None            # 縮放屬性 e.g. "STR"/"INT"
    dot_multiplier: float = 0.0                       # 縮放倍率
    dot_damage_type: Literal["physical", "magical", "true_damage"] = "true_damage"  # 傷害類型
    tags: List[str] = Field(default_factory=list)
    extra_data: Dict[str, Any] = Field(default_factory=dict)
    custom_status_name: Optional[str] = None          # 自訂狀態別名
    canonical_status: Optional[str] = None            # 規格狀態名

    @model_validator(mode='after')
    def register_custom_aliases(self) -> 'StatusEffect':
        custom_name = getattr(self, "custom_status_name", None)
        canonical = getattr(self, "canonical_status", None)
        if custom_name and canonical:
            from core.constants import STATUS_REGISTRY
            if canonical in STATUS_REGISTRY:
                aliases = STATUS_REGISTRY[canonical]["aliases"]
                if custom_name not in aliases:
                    aliases.append(custom_name)
                    print(f"🔄 [Pydantic] 動態註冊狀態別名恢復：將「{custom_name}」關聯至「{canonical}」")
        for trigger in getattr(self, "executable_triggers", []) or []:
            if isinstance(trigger, dict):
                for action in trigger.get("actions", []) or []:
                    if isinstance(action, dict):
                        c_name = action.get("custom_status_name")
                        canon = action.get("canonical_status")
                        if c_name and canon:
                            from core.constants import STATUS_REGISTRY
                            if canon in STATUS_REGISTRY:
                                aliases = STATUS_REGISTRY[canon]["aliases"]
                                if c_name not in aliases:
                                    aliases.append(c_name)
                                    print(f"🔄 [Pydantic] 動態註冊狀態別名恢復：將「{c_name}」關聯至「{canon}」")
        return self

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
    
    # --- 新增：大世界生態與一致性系統 ---
    ecology_tags: List[str] = []      # ["亡靈", "墓園", "寒冷"]
    dominant_species: List[str] = []  # ["骷髏兵", "食屍鬼"]
    discovered_variants: List[Dict[str, Any]] = [] # 紀錄已生成的具體怪名與特徵: [{"name": "殘缺的銀狼", "rank": "精英", "trait": "撕裂傷口"}]
    # loot_pool 紀錄物種與其掉落物的關聯: {"Skeleton": [{"name": "頭骨", "material_type": "bone", "tier": "T5"}]}
    loot_pool: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    threat_level: float = 0.0         # 區域壓力/威脅值
    # -----------------------------------

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
    skill_power: float = Field(default=0.0, ge=0.0)
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
    temp_hp: int = 0          # 新增：臨時生命（護盾）

class SkillFormula(BaseModel):
    type: Literal["multiplier", "additive"] = "multiplier"
    base_stat: str = "STR" 
    dice: str = "1d20"    
    divisor: float = 10.0  

class SkillMechanics(BaseModel):
    action_type: Literal["damage", "heal", "buff", "debuff"] = "damage" # 技能行為類型
    target_type: Literal["single", "aoe", "self", "allies"] = "single" # 技能目標類型
    cost: Dict[str, Union[int, str]] = Field(default_factory=dict)
    formula: SkillFormula = Field(default_factory=SkillFormula)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    narrative_effect: str = "" 
    tags: List[str] = Field(default_factory=list)      # 技能標籤系統
    # --- 新增：T1 組件化拼圖系統 ---
    targeting_modifier: Optional[str] = None          # e.g., "chain", "lowest_hp", "random_3"
    synergy_requirement: Optional[str] = None         # e.g., "requires_burn", "consumes_shields"
    execution_mode: Literal["immediate", "delayed", "stance_switch", "channeled", "reactive"] = "immediate"

    @model_validator(mode='before')
    @classmethod
    def convert_legacy_keywords(cls, data: Any) -> Any:
        if isinstance(data, dict):
            kws = data.pop("keywords", []) or []
            lk = data.pop("legendary_keyword", None)
            actions = data.get("actions", []) or []
            
            if not actions and (kws or lk):
                from core.skill_templates import assemble_skill_actions
                choices = []
                for kw in kws:
                    clean_kw = kw.replace("'", "").replace("-", "_").replace(" ", "_").lower()
                    choices.append({"template_id": f"active_{clean_kw}"})
                if lk:
                    clean_lk = lk.replace("'", "").replace("-", "_").replace(" ", "_").lower()
                    choices.append({"template_id": f"active_{clean_lk}"})
                data["actions"] = assemble_skill_actions(choices)
        return data

    @property
    def keywords(self) -> List[str]:
        # 從 actions 中還原 keywords，確保舊有測試與代碼能無縫讀取
        kws = []
        for act in self.actions:
            if act.get("action_type") == "call_special_mechanic":
                kw = act.get("keyword_name")
                if kw:
                    kws.append(kw)
            elif act.get("action_type") == "apply_status":
                status = act.get("status_name")
                if status:
                    kws.append(status)
        return list(dict.fromkeys(kws))

    @property
    def legendary_keyword(self) -> Optional[str]:
        # 從 actions 中還原傳說詞條名稱
        legendaries = {
            "Annihilate", "Soul_Drain", "Blood_Pact", "Devil's_Roll", "Last_Rites", 
            "Resonance_Break", "Paradox", "Doom_Seal", "Void_Rift", "Eternal_Wound", 
            "Abyssal_Mark", "Fate_Seal", "Soul_Shatter", "Time_Warp",
            "Phoenix_Rebirth", "Fate_Swap", "Mind_Control", "Apocalypse"
        }
        for act in self.actions:
            if act.get("action_type") == "call_special_mechanic":
                kw = act.get("keyword_name")
                if kw in legendaries:
                    return kw
        return None

class Skill(BaseModel):
    name: str
    description: str
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T5" # 技能階級 (T5 為最基礎)
    skill_type: Literal["active", "passive"] = "active"
    allowed_jobs: List[str] = Field(default_factory=list) # 允許使用職業限制
    mechanics: Optional[SkillMechanics] = None
    bonuses: Dict[str, float] = Field(default_factory=dict)
    executable_triggers: List[Dict[str, Any]] = Field(default_factory=list)
    # --- 新增：技能成長與進化系統 ---
    usage_count: int = 0
    evolution_threshold: int = 0      # 0 代表不可進化
    can_evolve: bool = False          # 達成次數後標示為可進化
    evolution_tier: int = 0           # 紀錄進化了幾次

    @model_validator(mode='after')
    def register_custom_aliases(self) -> 'Skill':
        mechanics = getattr(self, "mechanics", None)
        if mechanics:
            for action in getattr(mechanics, "actions", []):
                custom_name = action.get("custom_status_name")
                canonical = action.get("canonical_status")
                if custom_name and canonical:
                    from core.constants import STATUS_REGISTRY
                    if canonical in STATUS_REGISTRY:
                        aliases = STATUS_REGISTRY[canonical]["aliases"]
                        if custom_name not in aliases:
                            aliases.append(custom_name)
                            print(f"🔄 [Pydantic] 動態註冊狀態別名恢復：將「{custom_name}」關聯至「{canonical}」")
        return self

class ActiveSkill(Skill):
    skill_type: Literal["active"] = "active"

class PassiveSkill(Skill):
    skill_type: Literal["passive"] = "passive"

class LogEntry(BaseModel):
    date: str                  # YYYY-MM-DD
    type: Literal["GRIND", "LEGEND", "ORDEAL", "TRIFLE", "MILESTONE"]
    content: str               # 簡短描述

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
    row: str = "front"                                          # 戰位：front (前排) 或 back (後排)
    resistances: Dict[str, float] = Field(default_factory=dict) # 元素抗性：fire, cold, shadow 等
    primary_stats: PrimaryAttributes = Field(default_factory=PrimaryAttributes)
    equipment_slots: EquipmentSlots = Field(default_factory=EquipmentSlots)
    bonus_points_spent: int = 0
    stat_points: int = 5      # 新增：可用屬性點，初始為 5 點
    abilities: List[Skill] = Field(default_factory=list)
    personality: Personality = Field(default_factory=Personality)
    vitality: Vitality = Field(default_factory=Vitality)
    inventory: List[Union[Equipment, Item]] = Field(default_factory=list)
    status_effects: List[StatusEffect] = Field(default_factory=list)
    location: List[int] = Field(default_factory=lambda: [0, 0]) # 新增：當前座標 [x, y]
    last_regen: float = 0.0                                     # 新增：上次體力恢復時間戳記
    max_inventory_slots: int = 20                               # 新增：背包格數上限，初始 20
    rank: str = "E"                                             # 新增：冒險者階級 (E, D, C, B, A, S)
    reputation: int = 0                                         # 新增：名聲值
    active_quests: List[QuestSchema] = Field(default_factory=list)                        # 新增：進行中的任務
    known_rumors: List[str] = Field(default_factory=list)
    last_daily_reset_date: Optional[str] = None                 # 新增：上次每日重置日期 (YYYY-MM-DD)
    last_free_rest_date: Optional[str] = None                   # 新增：上次免費休息日期 (YYYY-MM-DD)
    last_paid_rest_date: Optional[str] = None                   # 新增：上次付費休息日期 (YYYY-MM-DD)

    # --- 新增：冒險生涯回溯系統 ---
    adventure_logs: List[LogEntry] = Field(default_factory=list)
    total_trpg_events: int = 0                                  # 經歷過的 AI 仲裁事件總數
    last_personality_check_level: int = 1                       # 上次進行性格檢查的等級
    last_personality_check_events: int = 0                      # 上次進行性格檢查時的事件數
    # -----------------------------


