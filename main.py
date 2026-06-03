import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

from logic.workflows.character_creation import handle_character_creation_workflow
import services.llm_service as llm_service
from core.character import Character
from ui.embeds import build_character_embed
from db.storage import CharacterRepository
from core.item_generator import generate_equipment_by_ai
from core.skill_generator import generate_single_skill_test
from core.equipment import EquipmentBalancer
from ui.views import InventoryView
from core.constants import KEYWORD_TRANSLATIONS
from typing import Literal

# 1. 環境設定
load_dotenv()
os.environ["PATH"] += os.pathsep + os.getcwd()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 避免跟 llm 模組撞名，變數名改為 llm_client
llm_client = llm_service.LMStudioClient(model="local-model")


@bot.event
async def on_ready():
    print(f'🤖 Bot 已登入為：{bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"🔄 成功同步了 {len(synced)} 個斜線指令！")
    except Exception as e:
        print(f"❌ 同步指令時發生錯誤: {e}")


@bot.tree.command(name="生成角色", description="創建一個新角色 (僅自己可見)")
async def create_character(interaction: discord.Interaction, description: str, name: str = None):
    """用法: /生成角色 description:一個能秒殺一切的龍帝魔導師 [name:影之強者]"""
    print(f"收到生成請求: {description} (名稱: {name if name else 'AI 生成'})")
    
    # 傳入重命名的 llm_client 與可選的名稱
    await handle_character_creation_workflow(interaction, description, llm_client, name=name)


@bot.tree.command(name="設定", description="調整你的個人偏好設定")
@app_commands.describe(public_mode="是否預設將角色面板、背包等訊息公開給頻道所有人看？")
async def change_settings(interaction: discord.Interaction, public_mode: bool):
    user_id = str(interaction.user.id)
    settings = CharacterRepository.get_user_settings(user_id)
    settings["public_mode"] = public_mode
    CharacterRepository.save_user_settings(user_id, settings)
    
    status = "【公開】" if public_mode else "【私有】"
    await interaction.response.send_message(f"✅ 設定已更新！你現在的預設顯示模式為：**{status}**", ephemeral=True)


@bot.tree.command(name="角色面板", description="顯示你目前的超帥氣角色詳細資訊！")
async def show_character(interaction: discord.Interaction):
    """用法: /角色面板"""
    user_id = str(interaction.user.id)
    print('查詢' + user_id)

    # 從資料庫拉取角色核心邏輯模型
    char = Character.load(user_id)

    if not char:
        await interaction.response.send_message("❌ 你還沒有建立角色喔！請先使用 `/生成角色` 踏上旅程。", ephemeral=True)
        return

    # 獲取使用者設定
    settings = CharacterRepository.get_user_settings(user_id)
    is_ephemeral = not settings.get("public_mode", False)

    # 使用新的 Hub 視圖
    from ui.views import CharacterHubView
    view = CharacterHubView(char, interaction.user)
    embed = build_character_embed(char, interaction.user)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=is_ephemeral)


@bot.tree.command(name="背包", description="查看你擁有的所有物品與裝備")
async def show_inventory(interaction: discord.Interaction):
    """用法: /背包 (現在整合進角色面板中，但保留捷徑)"""
    user_id = str(interaction.user.id)
    char = Character.load(user_id)

    if not char:
        await interaction.response.send_message("❌ 你還沒有建立角色喔！", ephemeral=True)
        return

    from ui.views import InventoryView
    from ui.embeds import build_inventory_embed
    view = InventoryView(char, interaction.user)
    embed = build_inventory_embed(char, interaction.user)
    
    settings = CharacterRepository.get_user_settings(user_id)
    is_ephemeral = not settings.get("public_mode", False)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=is_ephemeral)


@bot.tree.command(name="角色列表", description="列出你擁有的所有角色")
async def list_characters(interaction: discord.Interaction):
    """用法: /角色列表 (現在可透過角色面板 -> 換角 按鈕進入)"""
    user_id = str(interaction.user.id)
    chars = CharacterRepository.list_characters(user_id)
    active_name = CharacterRepository.get_active_character_name(user_id)

    if not chars:
        await interaction.response.send_message("❌ 你目前沒有任何角色喔！", ephemeral=True)
        return

    from ui.views import CharacterSwitchView
    view = CharacterSwitchView(chars, active_name, interaction.user)
    
    list_text = "### 📜 你的角色列表\n"
    for name in chars:
        status = " (目前使用中) ✨" if name == active_name else ""
        list_text += f"- **{name}**{status}\n"
    
    await interaction.response.send_message(list_text, view=view, ephemeral=True)


@bot.tree.command(name="切換角色", description="切換到你的另一個角色")
async def switch_character(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    chars = CharacterRepository.list_characters(user_id)
    active_name = CharacterRepository.get_active_character_name(user_id)

    if not chars:
        await interaction.response.send_message("❌ 你目前沒有任何角色可以切換。", ephemeral=True)
        return

    # 建立切換選單 View
    from ui.views import CharacterSwitchView
    view = CharacterSwitchView(chars, active_name, interaction.user)
    await interaction.response.send_message("🎭 請選擇你想要切換的角色：", view=view, ephemeral=True)


@bot.tree.command(name="刪除角色", description="刪除一個指定的角色 (此操作無法復原！)")
async def delete_character(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    chars = CharacterRepository.list_characters(user_id)

    if not chars:
        await interaction.response.send_message("❌ 你目前沒有任何角色可以刪除。", ephemeral=True)
        return

    # 建立下拉選單 View
    from ui.views import CharacterDeleteView
    view = CharacterDeleteView(chars, interaction.user)
    await interaction.response.send_message("🗑️ 請選擇你想要刪除的角色：\n*警告：一旦刪除將無法復原。*", view=view, ephemeral=True)


@bot.tree.command(name="測試裝備", description="測試 AI 裝備生成與數值平衡系統")
async def test_equipment(
    interaction: discord.Interaction, 
    description: str, 
    level: int, 
    tier: Literal["T1", "T2", "T3", "T4", "T5"],
    slot: str = "main_hand"
):
    """用法: /測試裝備 description:龍王的斷劍 level:50 tier:T5 slot:main_hand"""
    await interaction.response.defer(ephemeral=True)
    
    print(f"🛠️ 測試裝備生成: {description} (Lv.{level}, {tier})")
    
    eq = await generate_equipment_by_ai(description, level, tier, slot, llm_client)
    
    if not eq:
        await interaction.followup.send("❌ 裝備生成失敗，請檢查 LLM 回應或重試。", ephemeral=True)
        return

    # 建立一個漂亮的預覽 Embed
    embed = discord.Embed(
        title=f"🛠️ 測試裝備：{eq.name}",
        description=f"**[{eq.tier}] Lv.{eq.item_level} {eq.slot_type}**\n\n*{eq.description}*",
        color=EquipmentBalancer.get_tier_color(eq.tier)
    )
    
    # 格式化數值顯示
    stats_text = ""
    for stat, val in eq.bonuses.items():
        if "rate" in stat or "accuracy" in stat:
            stats_text += f"- {stat}: {val*100:.1f}%\n"
        else:
            # 如果是整數，去掉 .0
            display_val = int(val) if val == int(val) else val
            stats_text += f"- {stat}: {display_val:+}\n"
    
    if not stats_text:
        stats_text = "*無屬性加成*"
        
    embed.add_field(name="✨ 平衡後數值", value=f"```md\n{stats_text}```", inline=False)
    
    # 新增：顯示特殊描述
    if eq.special_effect:
        embed.add_field(name="🔮 特殊效果 (預留位)", value=f"*{eq.special_effect}*", inline=False)
    
    # 新增：將裝備加入活躍角色背包
    user_id = str(interaction.user.id)
    char = Character.load(user_id)
    if char:
        char.add_item(eq)
        embed.set_author(name=f"{interaction.user.display_name} 的新獲取裝備", icon_url=interaction.user.display_avatar.url)
    else:
        embed.set_footer(text="⚠️ 找不到活躍角色，裝備僅供預覽 (未存檔)")

    budget_info = EquipmentBalancer.calculate_budgets(level, tier)
    footer_text = f"主預算: {budget_info['primary']:.1f} | 附預算: {budget_info['sub']:.1f} | 數值已通過雙軌平衡器"
    embed.set_footer(text=footer_text)
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="技能生成測試", description="測試 AI 技能生成與解析能力")
async def test_skill_generation(
    interaction: discord.Interaction, 
    description: str,
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T4"
):
    """用法: /技能生成測試 description:時空撕裂斬 tier:T1"""
    await interaction.response.defer(ephemeral=True)
    
    print(f"🛠️ 測試技能生成: {description} ({tier})")
    
    skill = await generate_single_skill_test(description, tier, llm_client)
    
    if not skill:
        await interaction.followup.send("❌ 技能生成失敗，請檢查 LLM 回應或解析日誌。", ephemeral=True)
        return

    m = skill.mechanics
    cost_str = ", ".join([f"{k}:{v}" for k, v in m.cost.items()])
    f = m.formula
    formula_str = f"{f.base_stat} * ({f.dice} / {f.divisor})"
    
    target_map = {
        "single": "單體",
        "aoe": "群體",
        "self": "自身",
        "allies": "友軍"
    }
    target_display = target_map.get(m.target_type, m.target_type)
    
    embed = discord.Embed(
        title=f"⚔️ 技能測試：{skill.name}",
        description=f"**[{skill.tier} | {target_display}]**\n{skill.description}",
        color=discord.Color.red()
    )
    
    # 翻譯關鍵字
    translated_kws = [KEYWORD_TRANSLATIONS.get(kw, kw) for kw in m.keywords]
    kws_str = ", ".join(translated_kws) if translated_kws else "無"
    
    embed.add_field(name="⚙️ 機制", value=f"**消耗**: {cost_str}\n**公式**: {formula_str}\n**關鍵字**: {kws_str}", inline=False)
    
    if m.custom_logic:
        embed.add_field(name="⚠️ 自訂破壞邏輯", value=f"*{m.custom_logic}*", inline=False)
        
    if m.narrative_effect:
        embed.add_field(name="📖 敘事特效", value=f"*{m.narrative_effect}*", inline=False)
        
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="使用技能", description="在戰鬥中使用你的技能")
async def use_skill(interaction: discord.Interaction, skill_name: str, target: str = "怪物"):
    """用法: /使用技能 skill_name:火球術 target:哥布林"""
    from core.combat import execute_combat_skill
    user_id = str(interaction.user.id)
    char = Character.load(user_id)

    if not char:
        await interaction.response.send_message("❌ 你還沒有建立角色喔！", ephemeral=True)
        return

    await execute_combat_skill(interaction, char, skill_name, target, llm_client)


@bot.tree.command(name="說明", description="查看冒險指南，了解如何遊玩此 TRPG 系統")
async def help_command(interaction: discord.Interaction):
    """顯示遊戲完整說明指南"""
    embed = discord.Embed(
        title="⚔️ AI DC TRPG 冒險者指南",
        description="歡迎來到這個由 AI 驅動的 Discord TRPG 世界！在這裡，你的文字就是力量，AI 將根據你的描述為你量身打造專屬的角色與冒險。",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🌟 踏出第一步：創建角色",
        value=(
            "使用指令：`/生成角色 description:[你的敘述] [name:選填名字]`\n"
            "> **範例**：`/生成角色 description:一個操縱星辰之力的精靈占星術師`\n"
            "- AI 會生成背景、性格、技能與基礎裝備。\n"
            "- **屬性分配**：生成後可點擊按鈕分配 5 點初始屬性。"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🕹️ 核心中心：角色面板",
        value=(
            "使用指令：`/角色面板` (這是你最常用的指令)\n"
            "這是一個全方位的互動中心，透過下方的**按鈕**即可進行所有操作：\n"
            "- ⚜️ **面板**：查看角色詳情、屬性、狀態效果。\n"
            "- 🎒 **背包**：查看物品、穿戴/更換裝備、丟棄廢物。\n"
            "- 📜 **技能**：查看你的技能倍率與詳細機制。\n"
            "- 👕 **脫裝**：快速卸下已裝備的部位。\n"
            "- 🎭 **換角**：在多個角色之間快速切換。"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚔️ 冒險與戰鬥",
        value=(
            "目前支援基本戰鬥操作：\n"
            "- `/使用技能`：手動選擇技能並指定目標。\n"
            "> *註：戰鬥按鈕化系統正在開發中！*"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ 其他管理功能",
        value=(
            "- `/設定`：調整「公開/私有模式」，決定你的面板是否要給其他人看。\n"
            "- `/角色列表`：列出所有存檔的角色。\n"
            "- `/刪除角色`：永久告別一名戰友 (小心使用)。"
        ),
        inline=False
    )

    embed.set_footer(text="系統版本：v0.2 | 異步 AI 核心已啟動 | 作者：Gemini CLI")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if token:
        print("🚀 正在連線到 Discord...")
        bot.run(token)
    else:
        print("❌ 找不到 Token！請檢查 .env")
