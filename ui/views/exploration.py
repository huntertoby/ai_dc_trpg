import discord
import random
from typing import List, Optional, Any, Union
from datetime import datetime

from core.character import Character
from core.models import AreaSchema, BuildingSchema, Item, StatusEffect
from core.world import WorldManager
from core.constants import STAT_TRANSLATIONS
from ui.embeds import (
    build_character_embed, 
    build_location_embed,
    build_area_embed
)

class ArbiterModal(discord.ui.Modal):
    action_input = discord.ui.TextInput(
        label="你的行動策略", 
        placeholder="例如：我利用幻影術變出一頭更大的巨魔嚇跑他...", 
        style=discord.TextStyle.paragraph, 
        min_length=5, 
        max_length=200
    )
    
    def __init__(self, character: Character, user: discord.Member, area: AreaSchema, event_data: dict):
        super().__init__(title="🎬 事件應對：自由行動")
        self.character = character
        self.user = user
        self.area = area
        self.event_data = event_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from services.llm_service import LMStudioClient
        from core.arbiter import ArbiterSystem
        
        llm_client = LMStudioClient()
        player_text = self.action_input.value
        
        # 呼叫核心邏輯模組
        result = await ArbiterSystem.process_action(
            self.character, 
            self.area, 
            self.event_data, 
            player_text, 
            llm_client
        )
        
        if not result["success"]:
            embed = discord.Embed(
                title="⚠️ 行動無效", 
                description=result["fail_reason"], 
                color=discord.Color.orange()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        # 根據結果建立 Embed
        color = discord.Color.gold() if result["is_critical_success"] else (
            discord.Color.green() if "成功" in result["res_str"] else discord.Color.red()
        )
        
        # 屬性中文化
        translated_stat = STAT_TRANSLATIONS.get(result['stat_name'], result['stat_name'])
        
        embed = discord.Embed(
            title=f"🎬 行動結果：{result['res_str']}", 
            description=f"**{self.character.data.name}** 嘗試：\n> {player_text}\n\n**{result['narrative']}**", 
            color=color
        )
        
        embed.add_field(
            name="🎲 檢定數據", 
            value=f"**難度**: {result['final_dc']} (基{result['base_dc']}+修{self.area.base_level//5})\n"
                  f"**表現**: {result['total']} ({result['roll']}+{result['modifier']} [{translated_stat} {result['stat_val']}/5])", 
            inline=False
        )
        
        if result["rewards"]:
            embed.add_field(name="🏆 探索收益", value="\n".join(result["rewards"]))
        
        if result["penalties"]:
            embed.add_field(name="💢 挫敗代價", value="\n".join(result["penalties"]))
        
        # 建立返回按鈕
        back_view = discord.ui.View(timeout=120)
        btn_back = discord.ui.Button(label="🔙 返回探索", style=discord.ButtonStyle.primary)
        
        async def back_to_explore(bi):
            await bi.response.edit_message(
                embed=build_area_embed(self.area, self.character), 
                view=ExplorationView(self.character, self.user, self.area)
            )
        
        btn_back.callback = back_to_explore
        back_view.add_item(btn_back)
        
        await interaction.edit_original_response(embed=embed, view=back_view)

class CityView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, area: AreaSchema):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.area = area
        self._add_building_select()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能替別人導覽城市！", ephemeral=True)
            return False
        return True

    def _add_building_select(self):
        if self.area.landmarks:
            options = [discord.SelectOption(label=b.name, description=b.description[:50], value=b.id) for b in self.area.landmarks]
            select = discord.ui.Select(placeholder="前往建築物...", options=options, custom_id="city_building_select")
            select.callback = self.building_callback
            self.add_item(select)
        directions = [("⬆️ 北", [0, 1]), ("⬇️ 南", [0, -1]), ("⬅️ 西", [-1, 0]), ("➡️ 東", [1, 0])]
        for label, move in directions:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=1)
            def make_callback(m):
                async def callback(interaction): await self.move_callback(interaction, m[0], m[1])
                return callback
            btn.callback = make_callback(move)
            self.add_item(btn)
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary, row=2)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def move_callback(self, interaction: discord.Interaction, dx: int, dy: int):
        from services.llm_service import LMStudioClient
        llm_client = LMStudioClient()
        await interaction.response.defer()
        await interaction.edit_original_response(content="🚀 **正在趕路中...** (穿越荒野中)", embed=None, view=None)
        
        result_msg = await WorldManager.move_character(self.character, dx, dy, llm_client)
        self.character.tick_status()
        loc = self.character.data.location
        new_area = WorldManager.load_area(loc[0], loc[1])
        embed = build_area_embed(new_area, self.character)
        if new_area.type == "city": view = CityView(self.character, self.user, new_area)
        else: view = ExplorationView(self.character, self.user, new_area)
        await interaction.edit_original_response(content=result_msg, embed=embed, view=view)

    async def building_callback(self, interaction: discord.Interaction):
        building_id = interaction.data['values'][0]
        building = next((b for b in self.area.landmarks if b.id == building_id), None)
        if not building: return
        embed = discord.Embed(title=f"🚪 進入：{building.name}", description=f"你進入了{building.name}。\n\n*{building.description}*", color=discord.Color.gold())
        if building.npc_name: embed.add_field(name="👤 駐守人員", value=f"**{building.npc_name}** ({', '.join(building.npc_traits)})")
        view = BuildingView(self.character, self.user, building, self.area)
        await interaction.response.edit_message(embed=embed, view=view)

    async def back_callback(self, interaction: discord.Interaction):
        from ui.views.hub import CharacterHubView
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(embed=build_character_embed(self.character, self.user), view=hub_view)

class ExplorationView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, area: AreaSchema):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.area = area
        self._add_exploration_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    def _add_exploration_buttons(self):
        self.clear_items()
        directions = [("⬆️ 北", [0, 1]), ("⬇️ 南", [0, -1]), ("⬅️ 西", [-1, 0]), ("➡️ 東", [1, 0])]
        for label, move in directions:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=0)
            def make_callback(m):
                async def callback(interaction): await self.move_callback(interaction, m[0], m[1])
                return callback
            btn.callback = make_callback(move)
            self.add_item(btn)
        for b in self.area.landmarks:
            btn = discord.ui.Button(label=f"🔍 進入 {b.name}", style=discord.ButtonStyle.success, row=1)
            def make_building_callback(building):
                async def callback(interaction):
                    view = BuildingView(self.character, self.user, building, self.area)
                    await interaction.response.edit_message(embed=discord.Embed(title=f"📍 抵達：{building.name}", description=building.description, color=discord.Color.green()), view=view)
                return callback
            btn.callback = make_building_callback(b)
            self.add_item(btn)
        btn_hunt = discord.ui.Button(label="⚔️ 進行狩獵", style=discord.ButtonStyle.danger, row=2)
        btn_hunt.callback = self.handle_hunt
        self.add_item(btn_hunt)
        is_explored = str(self.user.id) in self.area.interacted_users
        btn_deep = discord.ui.Button(label="👣 深入探索" if not is_explored else "✅ 已探索", style=discord.ButtonStyle.success if not is_explored else discord.ButtonStyle.secondary, row=3, disabled=is_explored)
        btn_deep.callback = self.handle_deep_exploration
        self.add_item(btn_deep)
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.secondary, row=4)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def handle_hunt(self, interaction: discord.Interaction):
        from services.llm_service import LMStudioClient
        from logic.workflows.exploration import hunt_workflow
        from ui.views.combat import CombatView
        
        llm_client = LMStudioClient()
        res = await hunt_workflow(self.character, self.area, llm_client)
        
        if not res["success"]:
            await interaction.response.send_message(res["message"], ephemeral=True)
            return
            
        await interaction.response.defer()
        view = CombatView(self.character, self.user, res["monsters"])
        embed = view._build_combat_embed()
        
        await interaction.edit_original_response(
            content=f"⚔️ **在 {self.area.name} 遭遇了敵人！**",
            embed=embed,
            view=view
        )

    async def handle_deep_exploration(self, interaction: discord.Interaction):
        from services.llm_service import LMStudioClient
        from logic.workflows.exploration import deep_exploration_workflow
        
        llm_client = LMStudioClient()
        await interaction.response.defer(ephemeral=True)
        
        res = await deep_exploration_workflow(self.character, self.area, str(self.user.id), llm_client)
        if not res["success"]:
            await interaction.edit_original_response(content=res["message"])
            return
            
        txt = res["event_text"]
        btn = discord.ui.Button(label="🎬 採取行動", style=discord.ButtonStyle.primary)
        async def act_cb(bi): await bi.response.send_modal(ArbiterModal(self.character, self.user, self.area, {"prompt_action": txt}))
        btn.callback = act_cb
        view = discord.ui.View(timeout=120)
        view.add_item(btn)
        await interaction.edit_original_response(embed=discord.Embed(title=f"🔎 探索發現：{self.area.name}", description=txt, color=discord.Color.gold()), view=view)

    async def move_callback(self, interaction: discord.Interaction, dx: int, dy: int):
        from services.llm_service import LMStudioClient
        llm = LMStudioClient()
        await interaction.response.defer()
        msg = await WorldManager.move_character(self.character, dx, dy, llm)
        self.character.tick_status()
        loc = self.character.data.location
        new_area = WorldManager.load_area(loc[0], loc[1])
        embed = build_area_embed(new_area, self.character)
        if new_area.type == "city": view = CityView(self.character, self.user, new_area)
        else: view = ExplorationView(self.character, self.user, new_area)
        await interaction.edit_original_response(content=msg, embed=embed, view=view)

    async def back_callback(self, interaction: discord.Interaction):
        from ui.views.hub import CharacterHubView
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(self.character, self.user), view=hub_view)

class BuildingView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, building: BuildingSchema, area: AreaSchema):
        super().__init__(timeout=300.0)
        self.character, self.user, self.building, self.area = character, user, building, area
        self._add_feature_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    def _add_feature_buttons(self):
        if "quest" in self.building.features:
            btn_take = discord.ui.Button(label="📜 領取委託", style=discord.ButtonStyle.success)
            btn_take.callback = self.open_quest_board
            self.add_item(btn_take)
            btn_report = discord.ui.Button(label="✅ 任務回報", style=discord.ButtonStyle.primary)
            btn_report.callback = self.report_quests
            self.add_item(btn_report)
        if self.building.npc_name:
            btn_talk = discord.ui.Button(label=f"💬 與 {self.building.npc_name} 交談", style=discord.ButtonStyle.secondary)
            btn_talk.callback = self.talk_to_npc
            self.add_item(btn_talk)
        if "rank" in self.building.features:
            btn_rank = discord.ui.Button(label="🎖️ 階級提升", style=discord.ButtonStyle.secondary)
            btn_rank.callback = self.rank_up_action
            self.add_item(btn_rank)
        if "rest" in self.building.features:
            btn = discord.ui.Button(label="🍺 休息 (恢復體力)", style=discord.ButtonStyle.success)
            btn.callback = self.rest_action
            self.add_item(btn)
        btn_back = discord.ui.Button(label="🔙 走出建築", style=discord.ButtonStyle.secondary)
        btn_back.callback = self.back_to_city
        self.add_item(btn_back)

    async def talk_to_npc(self, interaction: discord.Interaction):
        from services.llm_service import LMStudioClient
        from logic.workflows.exploration import npc_talk_workflow
        
        llm_client = LMStudioClient()
        await interaction.response.defer(ephemeral=True)
        
        res = await npc_talk_workflow(self.character, self.building, llm_client)
        if not res["success"]:
            await interaction.followup.send(res["message"], ephemeral=True)
            return
            
        embed = discord.Embed(
            title=f"💬 與 {self.building.npc_name} 的對話", 
            description=f"**{self.building.npc_name}**：「{res['dialogue']}」", 
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def report_quests(self, interaction: discord.Interaction): await interaction.response.send_message("🔍 檢查任務中... (開發中)", ephemeral=True)
    async def rank_up_action(self, interaction: discord.Interaction): await interaction.response.send_message("🎖️ 階級提升功能開發中。", ephemeral=True)
    async def open_quest_board(self, interaction: discord.Interaction):
        from services.llm_service import LMStudioClient
        from core.guild import GuildManager
        from ui.views.guild import QuestBoardView
        quests = GuildManager.load_board() or await GuildManager.refresh_board_if_needed(LMStudioClient())
        view = QuestBoardView(self.character, self.user, quests, self.building, self.area)
        await interaction.response.edit_message(content="📜 公會公告欄", embed=None, view=view)

    async def rest_action(self, interaction: discord.Interaction):
        from logic.workflows.exploration import rest_character_workflow
        res = rest_character_workflow(self.character)
        await interaction.response.send_message(res["message"], ephemeral=True)

    async def back_to_city(self, interaction: discord.Interaction):
        view = CityView(self.character, self.user, self.area)
        await interaction.response.edit_message(embed=build_area_embed(self.area, self.character), view=view)
