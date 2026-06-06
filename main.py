import asyncio
import discord
import utils.discord_patches
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


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # 獲取原始異常
    original_error = getattr(error, "original", error)
    
    import traceback
    print(f"❌ 執行斜線指令時發生未捕獲的錯誤: {error}")
    traceback.print_exception(type(original_error), original_error, original_error.__traceback__)
    
    error_msg = f"❌ 執行指令時發生錯誤：{original_error}"
    if len(error_msg) > 2000:
        error_msg = error_msg[:1990] + "..."
        
    if interaction.response.is_done():
        try:
            # 優先嘗試編輯原始的回應 (能消除 Discord 的「正在思考...」狀態)
            await interaction.edit_original_response(content=error_msg, embed=None, view=None)
        except Exception:
            try:
                # 備用方案：如果編輯失敗，嘗試發送 followup 訊息
                await interaction.followup.send(error_msg, ephemeral=True)
            except Exception:
                pass
    else:
        try:
            # 如果還沒有回應或 defer，直接回應
            await interaction.response.send_message(error_msg, ephemeral=True)
        except Exception:
            pass


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

    # 觸發每日重置檢查
    char.check_daily_reset()

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


# --- 偵錯與測試指令組 ---
debug_group = app_commands.Group(name="debug", description="開發者偵錯與數值測試工具")

@debug_group.command(name="heal", description="完全恢復當前角色的生命、法力與體力")
async def debug_heal(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = Character.load(user_id)
    if not char:
        await interaction.response.send_message("❌ 找不到活躍角色。", ephemeral=True)
        return
    char.heal_all()
    await interaction.response.send_message(f"❤️ **{char.data.name}** 已完全恢復！", ephemeral=True)

@debug_group.command(name="combat", description="模擬生成指定數量與強度的怪物進行戰鬥測試")
async def debug_combat(
    interaction: discord.Interaction, 
    count: int = 1, 
    level: int = 1, 
    threat: float = 0.5
):
    """用法: /debug combat count:3 level:10 threat:2.0"""
    user_id = str(interaction.user.id)
    char = Character.load(user_id)
    if not char:
        await interaction.response.send_message("❌ 你還沒有建立角色，無法測試戰鬥。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    from core.monster_engine import MonsterEngine
    from ui.views.combat import CombatView
    from core.models import AreaSchema
    
    temp_area = AreaSchema(
        id="test_arena", name="🧪 數值測試場", type="wilderness",
        description="一個充滿數據流的虛擬空間，用來測試戰鬥平衡。",
        base_level=level, threat_level=threat,
        dominant_species=["測試傀儡", "數據病毒", "邏輯怪"]
    )
    
    monsters = []
    for _ in range(count):
        m = await MonsterEngine._generate_single_monster(temp_area, llm_client, novelty_chance=1.0)
        monsters.append(m)
        
    view = CombatView(char, interaction.user, monsters)
    await interaction.edit_original_response(
        content=f"🧪 **戰鬥模擬啟動！** (敵人等級: Lv.{level} | 威脅度: {threat})",
        embed=view._build_combat_embed(),
        view=view
    )

@debug_group.command(name="equipment", description="測試 AI 裝備生成與數值平衡系統")
async def debug_equipment(
    interaction: discord.Interaction, 
    description: str, 
    level: int, 
    tier: Literal["T1", "T2", "T3", "T4", "T5"],
    slot: Literal["head", "shoulders", "cloak", "chest", "hands", "legs", "feet", "main_hand", "off_hand", "trinket_1", "trinket_2", "ring"] = "main_hand"
):
    await interaction.response.defer(ephemeral=True)
    eq = await generate_equipment_by_ai(description, level, tier, slot, llm_client)
    if not eq:
        await interaction.followup.send("❌ 裝備生成失敗。", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🛠️ 測試裝備：{eq.name}",
        description=f"**[{eq.tier}] Lv.{eq.item_level} {eq.slot_type}**\n\n*{eq.description}*",
        color=EquipmentBalancer.get_tier_color(eq.tier)
    )
    stats_text = ""
    for stat, val in eq.bonuses.items():
        if "rate" in stat or "accuracy" in stat: stats_text += f"- {stat}: {val*100:.1f}%\n"
        else: stats_text += f"- {stat}: {int(val) if val == int(val) else val:+}\n"
    
    embed.add_field(name="✨ 平衡後數值", value=f"```md\n{stats_text or '*無屬性加成*'}```", inline=False)
    if eq.special_effect:
        embed.add_field(name="🔮 特殊效果", value=f"*{eq.special_effect}*", inline=False)
    if eq.executable_triggers:
        import json
        triggers_json = json.dumps(eq.executable_triggers, indent=2, ensure_ascii=False)
        embed.add_field(name="⚙️ 觸發器機制 (Triggers) (以測試通過)", value=f"```json\n{triggers_json}\n```", inline=False)
    
    user_id = str(interaction.user.id)
    char = Character.load(user_id)
    if char: char.add_item(eq)
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@debug_group.command(name="t1item", description="測試 T1 專用裝備特效 JSON 生成，直接輸出觸發器 JSON")
async def debug_t1item(
    interaction: discord.Interaction, 
    description: str
):
    await interaction.response.defer(ephemeral=True)
    eq = await generate_equipment_by_ai(
        description=description, 
        item_level=100, 
        tier="T1", 
        slot_type="main_hand", 
        llm_client=llm_client
    )
    if not eq:
        await interaction.followup.send("❌ 裝備生成失敗。", ephemeral=True)
        return

    import json
    import io
    triggers_json = json.dumps(eq.executable_triggers, indent=2, ensure_ascii=False)
    output_text = f"```json\n{triggers_json}\n```"
    if len(output_text) > 2000:
        file = discord.File(
            fp=io.BytesIO(triggers_json.encode('utf-8')),
            filename="t1item_triggers.json"
        )
        await interaction.followup.send("⚠️ 內容過長，已改用檔案發送：", file=file, ephemeral=True)
    else:
        await interaction.followup.send(output_text, ephemeral=True)

@debug_group.command(name="skill", description="測試 AI 技能生成與解析能力")
async def debug_skill(
    interaction: discord.Interaction, 
    description: str,
    tier: Literal["T1", "T2", "T3", "T4", "T5"] = "T4"
):
    await interaction.response.defer(ephemeral=True)
    skill = await generate_single_skill_test(description, tier, llm_client)
    if not skill:
        await interaction.followup.send("❌ 技能生成失敗。", ephemeral=True)
        return

    m = skill.mechanics
    embed = discord.Embed(
        title=f"⚔️ 技能測試：{skill.name}",
        description=f"**[{skill.tier}]**\n{skill.description}",
        color=discord.Color.red()
    )
    embed.add_field(name="⚙️ 機制", value=f"**消耗**: {m.cost}\n**公式**: {m.formula.base_stat}", inline=False)
    if skill.executable_triggers:
        import json
        triggers_json = json.dumps(skill.executable_triggers, indent=2, ensure_ascii=False)
        embed.add_field(name="⚙️ 觸發器機制 (Triggers)", value=f"```json\n{triggers_json}\n```", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

bot.tree.add_command(debug_group)


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
            "- 🗺️ **探索**：查看目前位置、移動或進行深度探索。\n"
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
