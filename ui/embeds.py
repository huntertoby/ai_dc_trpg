import discord
from core.character import Character
from core.constants import KEYWORD_TRANSLATIONS, STAT_TRANSLATIONS

def build_character_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成核心狀態面板 (精簡版)"""
    d = character.data
    base_jobs_str = ", ".join(d.base_jobs)
    xp_str = f"{d.exp} / {character.xp_required}"

    embed = discord.Embed(
        title=f"⚜️ {d.name} 的核心狀態 ⚜️",
        description=(
            f"**Lv. {d.level}** (`{xp_str} XP`)\n"
            f"**[{d.race}] {d.job_name}**\n"
            f"*基準：{base_jobs_str}*"
        ),
        color=discord.Color.dark_purple()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    # 1. 狀態條 (2x2 佈局) - 使用中文標籤並優化對齊
    # 生命 (HP), 法力 (MP), 精力 (STAM), 理智 (SAN)
    hp_info = f"生命: {d.vitality.hp}/{character.max_hp}"
    mp_info = f"法力: {d.vitality.mp}/{character.max_mp}"
    stam_info = f"精力: {d.vitality.stamina}/{character.max_stamina}"
    san_info = f"理智: {d.vitality.sanity}/{character.max_sanity}"

    ansi_bars = (
        f"```ansi\n"
        f"\u001b[1;31m❤️ {hp_info:<16}\u001b[0m \u001b[1;34m✨ {mp_info:<16}\u001b[0m\n"
        f"\u001b[1;33m⚡ {stam_info:<16}\u001b[0m \u001b[1;35m🧠 {san_info:<16}\u001b[0m\n"
        f"```"
    )
    embed.add_field(name="【 當前狀態 】", value=ansi_bars, inline=False)

    # 2. 總體屬性
    ts = character.total_stats
    loc = d.location
    stats = (
        f"力量: {ts['STR']:<3} | 智力: {ts['INT']:<3}\n"
        f"敏捷: {ts['DEX']:<3} | 感知: {ts['WIS']:<3}\n"
        f"體質: {ts['CON']:<3} | 魅力: {ts['CHA']:<3}\n"
        f"📍 當前座標: ({loc[0]}, {loc[1]})"
    )
    embed.add_field(name="【 基礎屬性與位置 】", value=f"```yaml\n{stats}\n```", inline=False)

    # 3. 戰鬥屬性
    c_stats = character.combat_stats
    # 獲取總防禦 (僅由屬性衍生得出)
    p_def = c_stats["p_def"]
    m_def = c_stats["m_def"]

    combat = (
        f"物理防禦: {p_def:<5} | 魔法防禦: {m_def:<5}\n"
        f"爆擊率: {c_stats['crit_rate'] * 100:>4.1f}% | 閃避率: {c_stats['evasion_rate'] * 100:>4.1f}%\n"
        f"命中率: {c_stats['accuracy'] * 100:>4.1f}% | 技威力: {c_stats['skill_power'] * 100:>4.1f}%\n"
        f"韌  性: {c_stats['tenacity']:>5} | 幸  運: {c_stats['luck']:>5}"
    )
    embed.add_field(name="【 戰鬥詳細數值 】", value=f"```yaml\n{combat}\n```", inline=False)

    # 4. 狀態效果
    eff_text = "\n".join([f"⚠️ {e.name} ({e.duration}T)" for e in d.status_effects]) if d.status_effects else "*目前沒有異常狀態*"
    embed.add_field(name="🌀【 狀態效果 】", value=eff_text, inline=True)

    embed.set_footer(text="點擊下方按鈕切換：🛡️ 裝備 / 📖 傳記 | TRPG 系統")
    return embed

def build_equipment_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成專門的裝備資訊面板"""
    d = character.data
    embed = discord.Embed(
        title=f"🛡️ {d.name} 的武裝配備",
        description="這裡顯示你目前穿戴在身上的所有裝備與飾品。",
        color=discord.Color.blue()
    )
    
    eq = d.equipment_slots
    armor_dict = {
        '頭部': eq.head, '肩膀': eq.shoulders, '披風': eq.cloak, 
        '胸甲': eq.chest, '手部': eq.hands, '腿部': eq.legs, '腳部': eq.feet
    }
    weapon_dict = {
        '主手': eq.main_hand, '副手': eq.off_hand, 
        '飾品一': eq.trinket_1, '飾品二': eq.trinket_2, 
        '戒指一': eq.ring_1, '戒指二': eq.ring_2
    }

    def format_equipment_list(eq_group):
        lines = []
        stat_names = {
            "STR": "力量", "DEX": "敏捷", "CON": "體質", "INT": "智力", "WIS": "感知", "CHA": "魅力",
            "crit_rate": "爆擊", "evasion_rate": "閃避", "accuracy": "命中", "skill_power": "技威",
            "tenacity": "韌性", "luck": "幸運", "ATK": "攻擊", "p_def": "物防", "m_def": "魔防"
        }
        for k, v in eq_group.items():
            if v:
                bonus_strs = []
                for stat_key, val in v.bonuses.items():
                    name = stat_names.get(stat_key, stat_key)
                    if any(x in stat_key for x in ["rate", "accuracy", "skill_power"]):
                        bonus_strs.append(f"{name}+{val*100:.0f}%")
                    else:
                        bonus_strs.append(f"{name}+{int(val) if val == int(val) else val}")
                
                stats_part = f" `({', '.join(bonus_strs)})`" if bonus_strs else ""
                effect_part = f"\n  └ 🔮 *{v.special_effect}*" if getattr(v, "special_effect", None) and v.special_effect else ""
                lines.append(f"**{k}**: [{v.tier}] {v.name}{stats_part}{effect_part}")
            else:
                lines.append(f"**{k}**: ---")
        return "\n".join(lines)

    embed.add_field(name="👕【 防具槽位 】", value=format_equipment_list(armor_dict), inline=True)
    embed.add_field(name="⚔️【 武器與飾品 】", value=format_equipment_list(weapon_dict), inline=True)

    embed.set_footer(text="可使用「👕 脫裝」按鈕來卸下物品")
    return embed

def build_profile_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成專門的人物傳記面板"""
    d = character.data
    embed = discord.Embed(
        title=f"📖 {d.name} 的人物檔案",
        description=d.background,
        color=discord.Color.green()
    )
    
    pers = d.personality
    traits_text = (
        f"**✨ 信念**: {pers.belief}\n"
        f"**🌑 缺陷**: {pers.flaw}\n"
        f"**😨 恐懼**: {pers.fear}"
    )
    embed.add_field(name="🎭【 人格特質 】", value=traits_text, inline=False)

    xp_progress = f"{d.exp} / {character.xp_required}"
    growth_text = (
        f"💰 **持有金幣**: {d.gold} G\n"
        f"🌟 **冒險經驗**: {xp_progress}\n"
        f"🎖️ **冒險階級**: Rank {d.rank} ({d.reputation} 名聲)"
    )
    embed.add_field(name="📈【 財富與成長 】", value=growth_text, inline=False)

    if d.active_quests:
        quests_text = "\n".join([f"- {q.title}" for q in d.active_quests])
        embed.add_field(name="📜【 進行中委託 】", value=quests_text, inline=False)

    return embed

def build_inventory_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成精簡的背包視圖"""
    d = character.data
    embed = discord.Embed(
        title=f"🎒 {user.display_name} 的背包",
        description=f"目前持有物品: **{len(d.inventory)}/{d.max_inventory_slots}**",
        color=discord.Color.blue()
    )
    
    if d.inventory:
        inv_text = ""
        for i, item in enumerate(d.inventory):
            from core.models import Equipment
            is_eq = isinstance(item, Equipment)
            prefix = f"[{item.tier}] " if is_eq else ""
            inv_text += f"{i+1}. {prefix}**{item.name}** x{item.quantity}\n"
        embed.add_field(name="內容物", value=inv_text, inline=False)
    else:
        embed.description = "你的背包目前空空如也..."

    return embed

def build_skills_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成詳細的技能清單視圖"""
    d = character.data
    embed = discord.Embed(
        title=f"📜 {d.name} 的技能集",
        description=f"目前掌握了 {len(d.abilities)} 個技能。",
        color=discord.Color.red()
    )
    
    if d.abilities:
        target_map = {"single": "單體", "aoe": "群體", "self": "自身", "allies": "友軍"}
        for s in d.abilities:
            m = s.mechanics
            cost_str = ", ".join([f"{k}:{v}" for k, v in m.cost.items()])
            f = m.formula
            target_display = target_map.get(m.target_type, m.target_type)
            
            # 屬性中文化
            translated_stat = STAT_TRANSLATIONS.get(f.base_stat, f.base_stat)
            formula_str = f"{translated_stat} * ({f.dice} / {f.divisor})"
            
            translated_kws = [KEYWORD_TRANSLATIONS.get(kw, kw) for kw in m.keywords]
            kws = ", ".join(translated_kws) if translated_kws else "無"
            
            field_val = f"*{s.description}*\n> 消耗: {cost_str} | 公式: {formula_str}\n> 目標: {target_display} | 特性: {kws}"
            embed.add_field(name=f"🔹 {s.name} `[{s.tier}]`", value=field_val, inline=False)
    else:
        embed.description = "尚未學習任何技能。"

    return embed

def build_area_embed(area: 'AreaSchema', character: Character) -> discord.Embed:
    """生成地區/城市詳細視圖"""
    from core.world import WorldManager
    diff = WorldManager.get_difficulty_settings(int(area.id.split(",")[0]), int(area.id.split(",")[1]))
    
    embed = discord.Embed(
        title=f"🏙️ {area.name} (Lv.{diff['base_level']})",
        description=f"**地理階級：{diff['tier_name']} (Tier {diff['tier']})**\n\n{area.description}",
        color=discord.Color.gold() if area.type == "city" else discord.Color.green()
    )
    
    if area.landmarks:
        l_list = "\n".join([f"- **{b.name}**" for b in area.landmarks])
        field_name = "🏢 城市設施" if area.type == "city" else "📍 地標興趣點"
        embed.add_field(name=field_name, value=l_list, inline=False)
        
    loc = character.data.location
    embed.set_footer(text=f"📍 座標: ({loc[0]}, {loc[1]}) | ⚡ 精力: {character.data.vitality.stamina}/{character.max_stamina}")
    return embed

def build_location_embed(character: Character, user: discord.Member) -> discord.Embed:
    """生成當前位置的環境視圖"""
    embed = discord.Embed(
        title=f"🗺️ 探索：荒野",
        description="你正處於未知的荒野中。四周雜草叢生，遠方隱約傳來野獸的吼叫聲。",
        color=discord.Color.green()
    )
    loc = character.data.location
    embed.add_field(name="📍 當前座標", value=f"X: {loc[0]}, Y: {loc[1]}")
    embed.set_footer(text="使用方向按鈕進行移動 (需消耗 10 點精力)")
    return embed
