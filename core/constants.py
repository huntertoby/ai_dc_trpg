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
    "Pierce", "Execute", "Lifesteal", "Chain", "Multi-hit", "Sacrifice", "Sunder", "Burn",
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
    "Multi-hit": "多重打擊", "Sacrifice": "犧牲", "Sunder": "破甲", "Burn": "灼燒",
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
    "Combo_Starter": "連擊起手", "Combo_Finisher": "連擊終結", "Rampage": "殺戮盛宴", "Adapt": "適應", "Mimicry": "擬態"
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
