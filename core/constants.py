# core/constants.py

# 冒險者階級順序與數值 (用於比較)
RANK_ORDER = {
    "E": 0,
    "D": 1,
    "C": 2,
    "B": 3,
    "A": 4,
    "S": 5
}

# 階級對應顏色 (用於 UI)
RANK_COLORS = {
    "E": 0x95a5a6, # 灰色
    "D": 0x2ecc71, # 綠色
    "C": 0x3498db, # 藍色
    "B": 0x9b59b6, # 紫色
    "A": 0xe67e22, # 橙色
    "S": 0xf1c40f  # 金色
}

VALID_TAGS = ["Fire", "Cold", "Shadow", "Lightning", "Holy", "Dark", "Wind", "Earth", "Water", "Nature", "Poison", "Acid", "Arcane", "Physical", "Chaos", "Melee", "Ranged", "Spell", "Summon", "Defense", "Gamble"]

STAMINA_RESTORE_COST = 1000  # 體力額外恢復費用 (大量金幣)

# 武器類型定義：類別 -> 主屬性 (scaling_stat)
WEAPON_TYPES = {
    # 近戰 - 力量
    "長劍": "STR", "巨劍": "STR", "長槍": "STR", "戰斧": "STR", "戰錘": "STR", 
    "巨斧": "STR", "鏈枷": "STR", "鈍器": "STR", "棍棒": "STR",
    # 近戰 - 敏捷
    "短劍": "DEX", "匕首": "DEX", "彎刀": "DEX", "拳套": "DEX", "格鬥爪": "DEX", 
    "鎖鏈": "DEX", "鐮刀": "DEX",
    # 遠程 - 敏捷
    "長弓": "DEX", "短弓": "DEX", "十字弩": "DEX", "投擲飛刀": "DEX", "火槍": "DEX",
    # 魔法 - 智力
    "法杖": "INT", "魔杖": "INT", "魔導書": "INT", "水晶球": "INT", "符文石": "INT",
    # 聖力 - 感知
    "聖印": "WIS", "十字架": "WIS", "鈴鐺": "WIS",
    # 防禦與副手 - 體質/其他
    "小盾": "CON", "巨盾": "CON", "副手短劍": "DEX", "法器": "INT"
}

BASE_JOBS = [
    "戰士", "騎士", "狂戰士", "武僧", "暗殺者", "盜賊", "遊俠",
    "巫師", "術士", "死靈法師", "召喚師", "煉金術師", "元素使",
    "祭司", "德魯伊", "吟遊詩人", "聖騎士",
    "馴獸師", "商人", "占星師",
    "獵魔人", "工匠", "神諭者", "破法者", "暗騎士"
]

SKILL_KEYWORDS = [
    # 攻擊類
    "Pierce", "Execute", "Lifesteal", "Chain", "Multi-hit", "Sacrifice", "Sunder", "Burn", "Detonate",
    # 防禦輔助類
    "Reflect", "Shield", "Immune", "Taunt", "Purge", "Bless", "Invis",
    # 控場時空類
    "Stun", "Silence", "Root", "Slow", "Quickcast", "Time_Warp",
    # 特殊混亂類
    "Charm", "Steal", "Gamble", "Copy", "Confusion", "Summon", "Banish", "Echo", "Greed", "Berserk",
    # [新增] 進階戰術與地形
    "Blind", "Terrain_Trap", "Levitate", "Wall_Break", "Counter_Stance",
    # [新增] 屬性與資源操作
    "Mana_Burn", "Overload", "Stat_Swap", "Soul_Link",
    # [新增] 極端條件與詛咒
    "Doom", "Vampiric_Aura", "Resurrect", "Martyr", "Frostbite",
    # [新增] 連擊與動態計算
    "Combo_Starter", "Combo_Finisher", "Rampage", "Adapt", "Mimicry"
]

KEYWORD_TRANSLATIONS = {
    "Pierce": "穿透", "Execute": "處決", "Lifesteal": "吸血", "Chain": "連鎖", 
    "Multi-hit": "多重打擊", "Sacrifice": "犧牲", "Sunder": "破甲", "Burn": "灼燒", "Detonate": "引爆",
    "Reflect": "反射", "Shield": "護盾", "Immune": "免疫", "Taunt": "嘲諷", 
    "Purge": "淨化", "Bless": "祝福", "Invis": "隱身",
    "Stun": "暈眩", "Silence": "沉默", "Root": "定身", "Slow": "減速", 
    "Quickcast": "瞬發", "Time_Warp": "時光回溯",
    "Charm": "魅惑", "Steal": "竊取", "Gamble": "豪賭", "Copy": "鏡像", 
    "Confusion": "混亂", "Summon": "召喚", "Banish": "放逐", "Echo": "殘響", 
    "Greed": "貪婪", "Berserk": "狂暴",
    # [新增]
    "Blind": "盲目", "Terrain_Trap": "地形陷阱", "Levitate": "浮空", "Wall_Break": "碎垣", "Counter_Stance": "反擊架勢",
    "Mana_Burn": "燃魔", "Overload": "超載", "Stat_Swap": "屬性反轉", "Soul_Link": "靈魂連結",
    "Doom": "厄運宣告", "Vampiric_Aura": "吸血光環", "Resurrect": "復甦", "Martyr": "殉道", "Frostbite": "凍傷",
    "Combo_Starter": "連擊起手", "Combo_Finisher": "連擊終結", "Rampage": "殺戮盛宴", "Adapt": "適應", "Mimicry": "擬態",
    "Focus": "專注", "Siphon": "屬性汲取", "Bleed": "流血", "Ward": "魔防護盾", "Desperation": "絕境怒火", "Fade": "仇恨消退",
    "Phoenix_Rebirth": "涅槃重燃", "Fate_Swap": "因果互換", "Mind_Control": "心靈傀儡", "Apocalypse": "天劫降臨"
}

# 傳說技能專屬詞條
LEGENDARY_KEYWORDS = [
    "Annihilate", "Soul_Drain", "Doom_Seal", "Blood_Pact", "Epoch_Break",
    "Void_Rift", "Last_Rites", "Paradox", "Eternal_Wound", "Abyssal_Mark",
    "Resonance_Break", "Soul_Shatter", "Fate_Seal", "Devil's_Roll",
    "Phoenix_Rebirth", "Fate_Swap", "Mind_Control", "Apocalypse"
]

LEGENDARY_KEYWORD_TRANSLATIONS = {
    "Annihilate": "虛滅",
    "Soul_Drain": "靈魂汲取",
    "Doom_Seal": "厄印強化",
    "Blood_Pact": "血誓契約",
    "Epoch_Break": "時代終結",
    "Void_Rift": "虛空裂隙",
    "Last_Rites": "終焉禮讚",
    "Paradox": "矛盾法則",
    "Eternal_Wound": "永恆創傷",
    "Abyssal_Mark": "深淵印記",
    "Resonance_Break": "共鳴破碎",
    "Soul_Shatter": "靈魂粉碎",
    "Fate_Seal": "命運封印",
    "Devil's_Roll": "惡魔骰",
    "Phoenix_Rebirth": "涅槃重燃",
    "Fate_Swap": "因果互換",
    "Mind_Control": "心靈傀儡",
    "Apocalypse": "天劫降臨"
}

BASE_RACES = [
    # 經典族群
    "人類", "精靈", "矮人", "半身人", "半獸人", "地精", "高精靈", "暗夜精靈", "草原精靈", "蠻族人",
    # 獸人與亞人
    "貓人", "狼人", "蜥蜴人", "龍裔", "鳥人", "半人馬", "米諾陶", "兔人", "熊人", "狐人",
    # 魔性與亡靈
    "惡魔", "吸血鬼", "幽靈", "骷髏", "魅魔", "食屍鬼", "提夫林", "無頭騎士", "影魔", "蛇人",
    # 元素、自然與構造
    "火靈", "水精", "土偶", "風妖", "樹人", "史萊姆", "機巧人", "發條生物", "妖精", "石像鬼",
    # 神聖與珍稀
    "天使", "星之子", "古神後裔", "幻影", "納迦", "塞壬", "泰坦血裔", "天狗", "麒麟裔", "鳳凰血裔"
]

# 屬性中文化映射
STAT_TRANSLATIONS = {
    "STR": "力量",
    "DEX": "敏捷",
    "CON": "體質",
    "INT": "智力",
    "WIS": "感知",
    "CHA": "魅力"
}

# 裝備主題分類關鍵字，用於 Stage 1 LLM 生成池導引
EQUIPMENT_KEYWORDS = {
    "fire": {
        "events": ["on_hit", "on_damaged", "on_crit"],
        "actions": ["inflict_damage", "apply_debuff"],
        "statuses": ["Burn"],
        "description": "與火焰、灼燒、爆裂相關的主題"
    },
    "ice": {
        "events": ["on_hit", "on_damaged", "on_miss", "on_dodge"],
        "actions": ["apply_debuff", "gain_shield"],
        "statuses": ["Slow", "Frostbite"],
        "description": "與冰霜、減速、凍傷、護盾相關的主題"
    },
    "holy": {
        "events": ["on_battle_start", "on_turn_start", "on_health_below", "on_fatal_damage"],
        "actions": ["heal", "gain_shield", "purge_debuffs", "call_special"],
        "statuses": ["Bless", "Shield", "Immune"],
        "description": "與神聖、治療、淨化、免死、祝福相關的主題"
    },
    "shadow": {
        "events": ["on_hit", "on_crit", "on_kill", "on_dodge"],
        "actions": ["inflict_damage", "apply_debuff", "remove_status"],
        "statuses": ["Blind", "Doom", "Slow"],
        "description": "與暗影、詛咒、盲目、處決、即死相關的主題"
    },
    "lightning": {
        "events": ["on_hit", "on_crit", "on_dodge"],
        "actions": ["inflict_damage", "apply_debuff", "set_value"],
        "statuses": ["Stun", "Slow"],
        "description": "與雷電、眩暈、高額爆擊、無視防禦相關的主題"
    },
    "wind": {
        "events": ["on_turn_start", "on_dodge", "on_miss"],
        "actions": ["gain_shield", "apply_status", "modify_dice"],
        "statuses": ["Invis", "Slow"],
        "description": "與疾風、迴避、隱身、行動點骰子修正相關的主題"
    }
}

# --- 統一狀態效果註冊表 (Status Effect Registry) ---
STATUS_REGISTRY = {
    # 控制與負面狀態 (Debuffs)
    "Stun": {
        "canonical_name": "Stun",
        "aliases": ["stun", "暈眩", "眩暈", "昏迷", "Stunned"],
        "is_debuff": True,
        "emoji": "🌀",
        "translation": "暈眩"
    },
    "Silence": {
        "canonical_name": "Silence",
        "aliases": ["silence", "沉默", "禁言", "Silenced"],
        "is_debuff": True,
        "emoji": "🤐",
        "translation": "沉默"
    },
    "Root": {
        "canonical_name": "Root",
        "aliases": ["root", "定身", "纏繞", "Rooted"],
        "is_debuff": True,
        "emoji": "🕸️",
        "translation": "定身"
    },
    "Slow": {
        "canonical_name": "Slow",
        "aliases": ["slow", "減速", "緩速", "Slowed"],
        "is_debuff": True,
        "emoji": "🐢",
        "translation": "減速"
    },
    "Blind": {
        "canonical_name": "Blind",
        "aliases": ["blind", "盲目", "失明", "Blindness"],
        "is_debuff": True,
        "emoji": "🕶️",
        "translation": "盲目"
    },
    "Charm": {
        "canonical_name": "Charm",
        "aliases": ["charm", "魅惑", "誘惑", "Charmed"],
        "is_debuff": True,
        "emoji": "💖",
        "translation": "魅惑"
    },
    "Confusion": {
        "canonical_name": "Confusion",
        "aliases": ["confusion", "混亂", "Confused"],
        "is_debuff": True,
        "emoji": "🌀",
        "translation": "混亂"
    },
    "Berserk": {
        "canonical_name": "Berserk",
        "aliases": ["berserk", "狂暴", "狂怒", "Berserked"],
        "is_debuff": True,
        "emoji": "🩸",
        "translation": "狂暴"
    },
    "Mind_Control": {
        "canonical_name": "Mind_Control",
        "aliases": ["mind_control", "心靈傀儡", "精神控制", "心靈控制"],
        "is_debuff": True,
        "emoji": "🧠",
        "translation": "心靈傀儡"
    },
    "Banish": {
        "canonical_name": "Banish",
        "aliases": ["banish", "放逐", "虛無", "Banished"],
        "is_debuff": True,
        "emoji": "🌀",
        "translation": "放逐"
    },
    
    # 持續傷害狀態 (DoT Debuffs)
    "Burn": {
        "canonical_name": "Burn",
        "aliases": ["burn", "灼燒", "燃燒", "灼痕刻印", "焚痕刻印"],
        "is_debuff": True,
        "emoji": "🔥",
        "translation": "灼燒"
    },
    "Frostbite": {
        "canonical_name": "Frostbite",
        "aliases": ["frostbite", "凍傷", "冰凍", "寒霜"],
        "is_debuff": True,
        "emoji": "🥶",
        "translation": "凍傷"
    },
    "Bleed": {
        "canonical_name": "Bleed",
        "aliases": ["bleed", "流血", "撕裂流血", "撕裂"],
        "is_debuff": True,
        "emoji": "🩸",
        "translation": "流血"
    },
    "Poison": {
        "canonical_name": "Poison",
        "aliases": ["poison", "中毒", "毒素"],
        "is_debuff": True,
        "emoji": "☠️",
        "translation": "中毒"
    },
    "Sunder": {
        "canonical_name": "Sunder",
        "aliases": ["sunder", "破甲", "護甲撕裂"],
        "is_debuff": True,
        "emoji": "🛡️",
        "translation": "破甲"
    },
    "Siphon_Debuff": {
        "canonical_name": "Siphon_Debuff",
        "aliases": ["siphon_debuff", "屬性汲取", "汲取衰弱"],
        "is_debuff": True,
        "emoji": "🩸",
        "translation": "屬性汲取"
    },

    # 傳說/詛咒與特殊 Debuffs
    "Doom": {
        "canonical_name": "Doom",
        "aliases": ["doom", "厄運宣告", "厄運", "死亡宣告"],
        "is_debuff": True,
        "emoji": "💀",
        "translation": "厄運宣告"
    },
    "Doom_Seal": {
        "canonical_name": "Doom_Seal",
        "aliases": ["doom_seal", "厄印強化", "厄運印記"],
        "is_debuff": True,
        "emoji": "💀",
        "translation": "厄印強化"
    },
    "Void_Rift": {
        "canonical_name": "Void_Rift",
        "aliases": ["void_rift", "虛空裂隙"],
        "is_debuff": True,
        "emoji": "🌀",
        "translation": "虛空裂隙"
    },
    "Eternal_Wound": {
        "canonical_name": "Eternal_Wound",
        "aliases": ["eternal_wound", "永恆創傷"],
        "is_debuff": True,
        "emoji": "🩸",
        "translation": "永恆創傷"
    },
    "Abyssal_Mark": {
        "canonical_name": "Abyssal_Mark",
        "aliases": ["abyssal_mark", "深淵印記"],
        "is_debuff": True,
        "emoji": "💀",
        "translation": "深淵印記"
    },
    "Fate_Seal": {
        "canonical_name": "Fate_Seal",
        "aliases": ["fate_seal", "命運封印"],
        "is_debuff": True,
        "emoji": "⏳",
        "translation": "命運封印"
    },
    "Soul_Exhaustion": {
        "canonical_name": "Soul_Exhaustion",
        "aliases": ["soul_exhaustion", "靈魂汲取", "魂能枯竭"],
        "is_debuff": True,
        "emoji": "💀",
        "translation": "靈魂汲取"
    },
    "Overload_Lock": {
        "canonical_name": "Overload_Lock",
        "aliases": ["overload_lock", "超載鎖定", "超載限制"],
        "is_debuff": True,
        "emoji": "⚡",
        "translation": "超載鎖定"
    },

    # 增益與保護狀態 (Buffs & Shields)
    "Shield": {
        "canonical_name": "Shield",
        "aliases": ["shield", "護盾", "奧術護盾", "防護罩", "聖盾"],
        "is_debuff": False,
        "emoji": "🛡️",
        "translation": "護盾"
    },
    "Immune": {
        "canonical_name": "Immune",
        "aliases": ["immune", "霸體", "免疫", "狀態免疫"],
        "is_debuff": False,
        "emoji": "🛡️",
        "translation": "免疫"
    },
    "Invis": {
        "canonical_name": "Invis",
        "aliases": ["invis", "隱身", "潛行", "隱形"],
        "is_debuff": False,
        "emoji": "💨",
        "translation": "隱身"
    },
    "Levitate": {
        "canonical_name": "Levitate",
        "aliases": ["levitate", "浮空", "重力浮空", "漂浮"],
        "is_debuff": False,
        "emoji": "🌀",
        "translation": "浮空"
    },
    "Counter_Stance": {
        "canonical_name": "Counter_Stance",
        "aliases": ["counter_stance", "反擊架勢", "反擊架式"],
        "is_debuff": False,
        "emoji": "⚔️",
        "translation": "反擊架勢"
    },
    "Bless": {
        "canonical_name": "Bless",
        "aliases": ["bless", "祝福", "神聖祝福"],
        "is_debuff": False,
        "emoji": "✨",
        "translation": "祝福"
    },
    "Reflect": {
        "canonical_name": "Reflect",
        "aliases": ["reflect", "反射", "鏡面反射", "傷害反射"],
        "is_debuff": False,
        "emoji": "🛡️",
        "translation": "反射"
    },
    "Taunt": {
        "canonical_name": "Taunt",
        "aliases": ["taunt", "嘲諷", "野性嘲諷"],
        "is_debuff": False,
        "emoji": "⚠️",
        "translation": "嘲諷"
    },
    "Ward": {
        "canonical_name": "Ward",
        "aliases": ["ward", "魔防護盾", "負面抵抗"],
        "is_debuff": False,
        "emoji": "🛡️",
        "translation": "魔防護盾"
    },
    "Desperation": {
        "canonical_name": "Desperation",
        "aliases": ["desperation", "絕境怒火", "絕境"],
        "is_debuff": False,
        "emoji": "🔥",
        "translation": "絕境怒火"
    },
    "Phoenix_Rebirth": {
        "canonical_name": "Phoenix_Rebirth",
        "aliases": ["phoenix_rebirth", "涅槃重燃", "鳳凰涅槃", "復活預備"],
        "is_debuff": False,
        "emoji": "🔥",
        "translation": "涅槃重燃"
    },
    "Adapt": {
        "canonical_name": "Adapt",
        "aliases": ["adapt", "適應", "適應性抗性"],
        "is_debuff": False,
        "emoji": "🧬",
        "translation": "適應"
    },
    # --- Resonance Buffs ---
    "Fire_Resonance": {
        "canonical_name": "Fire_Resonance",
        "aliases": ["fire_resonance", "火焰共鳴", "火共鳴"],
        "is_debuff": False,
        "emoji": "🔥",
        "translation": "火焰共鳴"
    },
    "Cold_Resonance": {
        "canonical_name": "Cold_Resonance",
        "aliases": ["cold_resonance", "冰霜共鳴", "冰共鳴"],
        "is_debuff": False,
        "emoji": "🥶",
        "translation": "冰霜共鳴"
    },
    "Shadow_Resonance": {
        "canonical_name": "Shadow_Resonance",
        "aliases": ["shadow_resonance", "暗影共鳴", "暗共鳴"],
        "is_debuff": False,
        "emoji": "💀",
        "translation": "暗影共鳴"
    },
    "Lightning_Resonance": {
        "canonical_name": "Lightning_Resonance",
        "aliases": ["lightning_resonance", "雷電共鳴", "雷共鳴"],
        "is_debuff": False,
        "emoji": "⚡",
        "translation": "雷電共鳴"
    },
    "Holy_Resonance": {
        "canonical_name": "Holy_Resonance",
        "aliases": ["holy_resonance", "神聖共鳴", "光共鳴"],
        "is_debuff": False,
        "emoji": "✨",
        "translation": "神聖共鳴"
    },
    "Melee_Resonance": {
        "canonical_name": "Melee_Resonance",
        "aliases": ["melee_resonance", "近戰共鳴"],
        "is_debuff": False,
        "emoji": "⚔️",
        "translation": "近戰共鳴"
    },
    "Ranged_Resonance": {
        "canonical_name": "Ranged_Resonance",
        "aliases": ["ranged_resonance", "遠程共鳴"],
        "is_debuff": False,
        "emoji": "🎯",
        "translation": "遠程共鳴"
    },
    "Spell_Resonance": {
        "canonical_name": "Spell_Resonance",
        "aliases": ["spell_resonance", "法術共鳴"],
        "is_debuff": False,
        "emoji": "📖",
        "translation": "法術共鳴"
    },
    "Summon_Resonance": {
        "canonical_name": "Summon_Resonance",
        "aliases": ["summon_resonance", "召喚共鳴"],
        "is_debuff": False,
        "emoji": "🌀",
        "translation": "召喚共鳴"
    },
    "Defense_Resonance": {
        "canonical_name": "Defense_Resonance",
        "aliases": ["defense_resonance", "防禦共鳴"],
        "is_debuff": False,
        "emoji": "🛡️",
        "translation": "防禦共鳴"
    },
    "Gamble_Resonance": {
        "canonical_name": "Gamble_Resonance",
        "aliases": ["gamble_resonance", "豪賭共鳴"],
        "is_debuff": False,
        "emoji": "🎲",
        "translation": "豪賭共鳴"
    }
}

def normalize_status_name(name: str) -> str:
    """
    將傳入的狀態效果名稱（支持中英文、大小寫變體）標準化為註冊表中的 Canonical Name。
    若找不到匹配，則將底線/空格分割的部分首字母大寫後回傳（作為自定義狀態的彈性保留）。
    """
    if not name:
        return ""
    
    cleaned = name.strip().lower().replace(" ", "_")
    
    # 1. 查找註冊表
    for canonical, info in STATUS_REGISTRY.items():
        if cleaned == canonical.lower():
            return canonical
        for alias in info["aliases"]:
            if cleaned == alias.strip().lower().replace(" ", "_"):
                return canonical
                
    # 2. 自動底線首字母大寫容錯（例如 phoenix_rebirth -> Phoenix_Rebirth）
    parts = cleaned.split("_")
    return "_".join(p.capitalize() for p in parts if p)
