import discord
from typing import List, Optional, Any, Union

from core.character import Character
from db.storage import CharacterRepository
from ui.embeds import (
    build_character_embed, 
    build_inventory_embed, 
    build_skills_embed, 
    build_location_embed
)

class CharacterHubView(discord.ui.View):
    """角色主控制面板 (The Hub)"""
    def __init__(self, character: Character, user: discord.Member, active_tab: str = "panel"):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.active_tab = active_tab
        self._update_button_styles()
        self._add_stats_button()

    def _update_button_styles(self):
        tab_map = {
            "panel": "⚜️ 面板",
            "equipment": "🛡️ 裝備",
            "profile": "📖 傳記",
            "inventory": "🎒 背包",
            "skills": "📜 技能",
            "unequip": "👕 脫裝",
            "location": "🗺️ 探索"
        }
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                btn_tab = next((k for k, v in tab_map.items() if v == child.label), None)
                if btn_tab:
                    child.style = discord.ButtonStyle.primary if btn_tab == self.active_tab else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 這不是你的面板喔！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚜️ 面板", style=discord.ButtonStyle.primary)
    async def show_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_character_embed(self.character, self.user)
        view = CharacterHubView(self.character, self.user, active_tab="panel")
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="🛡️ 裝備", style=discord.ButtonStyle.secondary)
    async def show_equipment(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.embeds import build_equipment_embed
        embed = build_equipment_embed(self.character, self.user)
        view = CharacterHubView(self.character, self.user, active_tab="equipment")
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="📖 傳記", style=discord.ButtonStyle.secondary)
    async def show_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.embeds import build_profile_embed
        embed = build_profile_embed(self.character, self.user)
        view = CharacterHubView(self.character, self.user, active_tab="profile")
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    def _add_stats_button(self):
        pts = self.character.data.stat_points
        if pts > 0:
            btn = discord.ui.Button(label=f"🧬 分配屬性 ({pts})", style=discord.ButtonStyle.success, custom_id="hub_allocate_stats")
            btn.callback = self.show_allocation
            self.add_item(btn)

    async def show_allocation(self, interaction: discord.Interaction):
        from logic.workflows.character_creation import StatsAllocationView
        view = StatsAllocationView(self.character)
        await interaction.response.edit_message(content=view.get_content(), embed=None, view=view)

    @discord.ui.button(label="🎒 背包", style=discord.ButtonStyle.secondary)
    async def show_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.views.inventory import InventoryView
        view = InventoryView(self.character, self.user)
        embed = build_inventory_embed(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="📜 技能", style=discord.ButtonStyle.secondary)
    async def show_skills(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_skills_embed(self.character, self.user)
        view = CharacterHubView(self.character, self.user, active_tab="skills")
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="👕 脫裝", style=discord.ButtonStyle.secondary)
    async def show_unequip(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.views.inventory import UnequipView
        view = UnequipView(self.character, self.user)
        embed = build_character_embed(self.character, self.user)
        embed.title = f"👕 {self.character.data.name} - 卸下裝備"
        embed.description = "請選擇要卸下的裝備部位。"
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="🗺️ 探索", style=discord.ButtonStyle.secondary)
    async def show_location(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        from core.world import WorldManager
        loc = self.character.data.location
        area = WorldManager.load_area(loc[0], loc[1])
        if not area:
            from core.world_generator import WorldGenerator
            from services.llm_service import LMStudioClient
            llm_client = LMStudioClient()
            area = await WorldGenerator.generate_area(loc[0], loc[1], llm_client)
            if area: WorldManager.save_area(area)
            else:
                embed = build_location_embed(self.character, self.user)
                view = CharacterHubView(self.character, self.user, active_tab="location")
                await interaction.edit_original_response(content="⚠️ 區域資料讀取失敗。", embed=embed, view=view)
                return
        from ui.embeds import build_area_embed
        from ui.views.exploration import CityView, ExplorationView
        embed = build_area_embed(area, self.character)
        if area.type == "city": view = CityView(self.character, self.user, area)
        else: view = ExplorationView(self.character, self.user, area)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

    @discord.ui.button(label="🎭 換角", style=discord.ButtonStyle.secondary)
    async def show_switch(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = CharacterRepository.list_characters(str(self.user.id))
        active_name = CharacterRepository.get_active_character_name(str(self.user.id))
        view = CharacterSwitchView(chars, active_name, self.user)
        await interaction.response.edit_message(content="🎭 請選擇要切換的角色：", embed=None, view=view)

class CharacterSwitchView(discord.ui.View):
    def __init__(self, characters: List[str], active_name: str, user: discord.Member):
        super().__init__(timeout=60.0)
        self.user = user
        options = [discord.SelectOption(label=f"{name}{' (目前活躍)' if name == active_name else ''}", value=name, default=(name == active_name)) for name in characters]
        select = discord.ui.Select(placeholder="選擇要切換的角色...", options=options, custom_id="switch_select")
        select.callback = self.select_callback
        self.add_item(select)
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能操作別人的選單！", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        from logic.workflows.hub import switch_character_workflow
        char = switch_character_workflow(str(self.user.id), interaction.data['values'][0])
        if char:
            hub_view = CharacterHubView(char, self.user)
            await interaction.response.edit_message(content=None, embed=build_character_embed(char, self.user), view=hub_view)
        else:
            await interaction.response.send_message("❌ 無法載入角色資料。", ephemeral=True)

    async def back_callback(self, interaction: discord.Interaction):
        char = Character.load(str(self.user.id))
        hub_view = CharacterHubView(char, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(char, self.user), view=hub_view)

class CharacterDeleteView(discord.ui.View):
    def __init__(self, characters: List[str], user: discord.Member):
        super().__init__(timeout=60.0)
        self.user = user
        self.selected_char = None
        
        options = [discord.SelectOption(label=name, value=name) for name in characters]
        select = discord.ui.Select(placeholder="選擇要刪除的角色...", options=options, custom_id="delete_select")
        select.callback = self.select_callback
        self.add_item(select)
        
        self.confirm_button = discord.ui.Button(label="確認刪除", style=discord.ButtonStyle.danger, disabled=True)
        self.confirm_button.callback = self.confirm_callback
        self.add_item(self.confirm_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能操作別人的選單！", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_char = interaction.data['values'][0]
        self.confirm_button.disabled = False
        # 更新選單的預設選項
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                for option in child.options:
                    option.default = (option.value == self.selected_char)
            
        await interaction.response.edit_message(content=f"⚠️ 你選擇了要刪除：**{self.selected_char}**\n請點擊下方的「確認刪除」按鈕來完成操作。", view=self)

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_char:
            await interaction.response.send_message("❌ 請先選擇一個角色！", ephemeral=True)
            return
            
        from logic.workflows.hub import delete_character_workflow
        success = delete_character_workflow(str(self.user.id), self.selected_char)
        if success:
            await interaction.response.edit_message(content=f"✅ 角色 **{self.selected_char}** 已成功刪除。", view=None)
        else:
            await interaction.response.edit_message(content=f"❌ 刪除角色 **{self.selected_char}** 失敗。", view=None)
