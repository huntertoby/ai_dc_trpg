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

    stat_names = {
        "STR": "力量", "DEX": "敏捷", "CON": "體質", "INT": "智力", "WIS": "感知", "CHA": "魅力",
        "crit_rate": "爆擊", "evasion_rate": "閃避", "accuracy": "命中", "skill_power": "技威",
        "tenacity": "韌性", "luck": "幸運", "ATK": "攻擊", "p_def": "物防", "m_def": "魔防"
    }
    dmg_type_map = {"physical": "物理", "magical": "魔法"}
    scaling_map = {"STR": "力量", "DEX": "敏捷", "CON": "體質", "INT": "智力", "WIS": "感知", "CHA": "魅力"}
    event_names = {
        "on_hit": "命中時", "on_crit": "暴擊時", "on_kill": "擊殺時",
        "on_damaged": "受擊時", "on_dodge": "閃避時", "on_miss": "未命中時",
        "on_battle_start": "戰鬥開始", "on_battle_end": "戰鬥結束",
        "on_turn_start": "回合開始", "on_turn_end": "回合結束",
        "on_health_below": "生命過低", "on_fatal_damage": "致命傷害時"
    }

    def format_equipment_detail(slot_name: str, item) -> str:
        """為單件裝備生成詳細展示"""
        if not item:
            return f"**{slot_name}**: ─ 空 ─"
        
        # 第一行：槽位 + 稀有度 + 名稱 + 等級
        header = f"**{slot_name}**: [{item.tier}] **{item.name}** `iLv.{item.item_level}`"
        
        lines = [header]

        # 第二行：武器額外資訊 (武器類型 / 傷害類型 / 主屬性 / 雙手)
        weapon_info_parts = []
        if getattr(item, 'weapon_type', None) and item.weapon_type:
            weapon_info_parts.append(f"🗡️{item.weapon_type}")
        if item.slot_type in ['main_hand', 'off_hand']:
            weapon_info_parts.append(dmg_type_map.get(item.damage_type, item.damage_type))
            weapon_info_parts.append(f"主屬:{scaling_map.get(item.scaling_stat, item.scaling_stat)}")
            if item.is_two_handed:
                weapon_info_parts.append("⚔️雙手")
        if weapon_info_parts:
            lines.append(f"  ├ {' | '.join(weapon_info_parts)}")

        # 第三行：屬性加成
        if item.bonuses:
            bonus_strs = []
            for stat_key, val in item.bonuses.items():
                name = stat_names.get(stat_key, stat_key)
                if any(x in stat_key for x in ["rate", "accuracy", "skill_power"]):
                    bonus_strs.append(f"{name}+{val*100:.0f}%")
                else:
                    bonus_strs.append(f"{name}+{int(val) if val == int(val) else val}")
            lines.append(f"  ├ 📊 {', '.join(bonus_strs)}")

        # 第四行：標籤
        if getattr(item, 'tags', None) and item.tags:
            tag_str = ' '.join([f"`{t}`" for t in item.tags])
            lines.append(f"  ├ 🏷️ {tag_str}")

        # 職業限制
        allowed_jobs_str = ", ".join(item.allowed_jobs) if getattr(item, "allowed_jobs", None) else "通用"
        lines.append(f"  ├ 👤 允許職業: {allowed_jobs_str}")

        # 第五行：觸發器效果
        if getattr(item, 'executable_triggers', None) and item.executable_triggers:
            for trig in item.executable_triggers:
                event = trig.get('event', '?')
                event_display = event_names.get(event, event)
                chance = trig.get('chance')
                chance_str = f" ({chance*100:.0f}%機率)" if chance and chance < 1.0 else ""
                cooldown = trig.get('cooldown')
                cd_str = f" [CD:{cooldown}T]" if cooldown and cooldown > 0 else ""
                # 從 actions 提取描述
                action_descs = []
                for act in trig.get('actions', []):
                    a_type = act.get('action_type', '')
                    if a_type == 'inflict_damage':
                        flat = act.get('flat_value', 0)
                        action_descs.append(f"造成{flat:.0f}傷害" if flat else "造成傷害")
                    elif a_type == 'heal':
                        flat = act.get('flat_value', 0)
                        action_descs.append(f"回復{flat:.0f}HP" if flat else "回復生命")
                    elif a_type == 'gain_shield':
                        flat = act.get('flat_value', 0)
                        action_descs.append(f"獲得{flat:.0f}護盾" if flat else "獲得護盾")
                    elif a_type == 'apply_status':
                        sn = act.get('status_name', '增益')
                        action_descs.append(f"施加{sn}")
                    elif a_type == 'apply_debuff':
                        dn = act.get('debuff_name', '減益')
                        action_descs.append(f"施加{dn}")
                    elif a_type == 'purge_debuffs':
                        action_descs.append("淨化減益")
                    elif a_type == 'call_special':
                        action_descs.append("特殊效果")
                    else:
                        action_descs.append(a_type)
                effect_text = '、'.join(action_descs) if action_descs else '觸發效果'
                lines.append(f"  ├ ⚡ {event_display}{chance_str}：{effect_text}{cd_str}")

        # 最後一行：特殊效果描述
        if getattr(item, 'special_effect', None) and item.special_effect:
            lines.append(f"  └ 🔮 *{item.special_effect}*")
        
        return '\n'.join(lines)

    # 防具區塊
    armor_lines = [format_equipment_detail(k, v) for k, v in armor_dict.items()]
    armor_text = '\n'.join(armor_lines)
    # Discord embed field value 上限 1024 字元，若超長則分段
    if len(armor_text) <= 1024:
        embed.add_field(name="👕【 防具槽位 】", value=armor_text, inline=False)
    else:
        mid = len(armor_lines) // 2
        embed.add_field(name="👕【 防具槽位 (上) 】", value='\n'.join(armor_lines[:mid]), inline=False)
        embed.add_field(name="👕【 防具槽位 (下) 】", value='\n'.join(armor_lines[mid:]), inline=False)

    # 武器與飾品區塊
    weapon_lines = [format_equipment_detail(k, v) for k, v in weapon_dict.items()]
    weapon_text = '\n'.join(weapon_lines)
    if len(weapon_text) <= 1024:
        embed.add_field(name="⚔️【 武器與飾品 】", value=weapon_text, inline=False)
    else:
        mid = len(weapon_lines) // 2
        embed.add_field(name="⚔️【 武器與飾品 (上) 】", value='\n'.join(weapon_lines[:mid]), inline=False)
        embed.add_field(name="⚔️【 武器與飾品 (下) 】", value='\n'.join(weapon_lines[mid:]), inline=False)

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
        action_type_map = {"damage": "⚔️傷害", "heal": "💚治療", "buff": "🔰增益", "debuff": "💜減益"}
        exec_mode_map = {
            "immediate": "瞬發", "delayed": "延遲", "stance_switch": "姿態切換",
            "channeled": "引導", "reactive": "反應"
        }
        targeting_mod_map = {
            "chain": "連鎖", "lowest_hp": "最低血量", "random_3": "隨機3體",
            "random_2": "隨機2體", "highest_atk": "最高攻擊"
        }

        for s in d.abilities:
            lines = [f"*{s.description}*"]
            
            # 限制職業
            allowed_jobs_str = ", ".join(s.allowed_jobs) if getattr(s, "allowed_jobs", None) else "通用"
            lines.append(f"> 👤 限制職業: {allowed_jobs_str}")

            if getattr(s, "skill_type", "active") == "passive":
                # --- 被動技能特定顯示 ---
                lines.append(f"> 類型: 💎被動技能")
                
                # 屬性加成
                bonus_list = []
                stat_names = {
                    "STR": "力量", "DEX": "敏捷", "CON": "體質", "INT": "智力", "WIS": "感知", "CHA": "魅力",
                    "crit_rate": "爆擊", "evasion_rate": "閃避", "accuracy": "命中", "skill_power": "技威",
                    "tenacity": "韌性", "luck": "幸運", "ATK": "攻擊", "p_def": "物防", "m_def": "魔防"
                }
                for stat_key, val in getattr(s, "bonuses", {}).items():
                    name = stat_names.get(stat_key, stat_key)
                    if any(x in stat_key for x in ["rate", "accuracy", "skill_power"]):
                        bonus_list.append(f"{name}+{val*100:.0f}%")
                    else:
                        bonus_list.append(f"{name}+{int(val) if val == int(val) else val}")
                if bonus_list:
                    lines.append(f"> 📊 常駐屬性: {', '.join(bonus_list)}")
            else:
                # --- 主動技能特定顯示 ---
                m = s.mechanics
                f = m.formula
                
                # 類型 | 消耗 | 目標
                action_display = action_type_map.get(m.action_type, m.action_type)
                cost_str = ", ".join([f"{k}:{v}" for k, v in m.cost.items()]) if m.cost else "無"
                target_display = target_map.get(m.target_type, m.target_type)
                
                type_line_parts = [f"類型: {action_display}", f"消耗: {cost_str}", f"目標: {target_display}"]
                lines.append("> " + " | ".join(type_line_parts))
                
                # 公式
                translated_stat = STAT_TRANSLATIONS.get(f.base_stat, f.base_stat)
                formula_str = f"{translated_stat} × ({f.dice} / {f.divisor})"
                lines.append(f"> 📐 公式: {formula_str}")

                # 執行模式 | 瞄準修正 | 協同需求
                detail_parts = []
                exec_display = exec_mode_map.get(m.execution_mode, m.execution_mode)
                if m.execution_mode != "immediate":
                    detail_parts.append(f"🔄 模式: {exec_display}")
                if getattr(m, 'targeting_modifier', None) and m.targeting_modifier:
                    tm_display = targeting_mod_map.get(m.targeting_modifier, m.targeting_modifier)
                    detail_parts.append(f"🎯 瞄準: {tm_display}")
                if getattr(m, 'synergy_requirement', None) and m.synergy_requirement:
                    synergy = m.synergy_requirement
                    synergy_clean = synergy.replace('requires_', '需要').replace('consumes_', '消耗')
                    detail_parts.append(f"🔗 協同: {synergy_clean}")
                if detail_parts:
                    lines.append("> " + " | ".join(detail_parts))
                
                # 特性 (keywords) + 傳說詞條
                translated_kws = [KEYWORD_TRANSLATIONS.get(kw, kw) for kw in m.keywords]
                kws = ", ".join(translated_kws) if translated_kws else "無"
                keyword_line = f"> 🏷️ 特性: {kws}"
                
                if getattr(m, "legendary_keyword", None):
                    from core.constants import LEGENDARY_KEYWORD_TRANSLATIONS
                    trans_legend = LEGENDARY_KEYWORD_TRANSLATIONS.get(m.legendary_keyword, m.legendary_keyword)
                    keyword_line += f" | 🌟 **傳說: {trans_legend}**"
                lines.append(keyword_line)
                
                # 標籤
                if getattr(m, 'tags', None) and m.tags:
                    tag_str = ' '.join([f"`{t}`" for t in m.tags])
                    lines.append(f"> 🔖 標籤: {tag_str}")

            # --- 共用觸發器與進度 ---
            # 觸發器
            if getattr(s, 'executable_triggers', None) and s.executable_triggers:
                trig_descs = []
                event_names = {
                    "on_hit": "命中時", "on_crit": "暴擊時", "on_kill": "擊殺時",
                    "on_damaged": "受擊時", "on_dodge": "閃避時",
                    "on_battle_start": "戰鬥開始", "on_turn_start": "回合開始",
                    "on_health_below": "生命過低", "on_fatal_damage": "致命傷害時"
                }
                for trig in s.executable_triggers:
                    event = trig.get('event', '?')
                    event_display = event_names.get(event, event)
                    chance = trig.get('chance')
                    chance_str = f"({chance*100:.0f}%)" if chance and chance < 1.0 else ""
                    trig_descs.append(f"{event_display}{chance_str}")
                lines.append(f"> ⚡ 觸發: {', '.join(trig_descs)}")
            
            # 進化與使用次數
            if s.evolution_threshold and s.evolution_threshold > 0:
                evo_bar = f"{s.usage_count}/{s.evolution_threshold}"
                evo_status = "✅ 可進化！" if s.can_evolve else f"進度: {evo_bar}"
                evo_tier = f" (已進化{s.evolution_tier}次)" if s.evolution_tier > 0 else ""
                lines.append(f"> 🧬 {evo_status}{evo_tier}")
            elif s.usage_count > 0:
                lines.append(f"> 📊 已使用: {s.usage_count}次")

            field_val = "\n".join(lines)
            if len(field_val) > 1024:
                field_val = field_val[:1020] + "..."
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
