import discord
from typing import List, Optional, Any, Union

from core.character import Character
from core.models import Equipment
from ui.embeds import (
    build_character_embed, 
    build_inventory_embed
)

class InventoryView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member):
        super().__init__(timeout=180.0)
        self.character = character
        self.user = user
        self.selected_item_idx = -1
        self._update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 這不是你的背包喔！", ephemeral=True)
            return False
        return True

    def _update_components(self):
        self.clear_items()
        options = []
        for i, item in enumerate(self.character.data.inventory):
            label = f"{item.name} (x{item.quantity})"
            if isinstance(item, Equipment): label = f"[{item.tier}] {item.name} (Lv.{item.item_level})"
            options.append(discord.SelectOption(label=label, description=item.description[:50], value=str(i)))
        if not options: options.append(discord.SelectOption(label="背包空空如也", value="-1"))
        select = discord.ui.Select(placeholder="選擇一個物品查看詳情...", options=options, custom_id="inv_select", disabled=len(self.character.data.inventory) == 0)
        select.callback = self.select_callback
        self.add_item(select)
        if 0 <= self.selected_item_idx < len(self.character.data.inventory):
            item = self.character.data.inventory[self.selected_item_idx]
            if isinstance(item, Equipment):
                btn_equip = discord.ui.Button(label="✅ 裝備", style=discord.ButtonStyle.success)
                btn_equip.callback = self.equip_callback
                self.add_item(btn_equip)
            btn_discard = discord.ui.Button(label="🗑️ 丟棄", style=discord.ButtonStyle.danger)
            btn_discard.callback = self.discard_callback
            self.add_item(btn_discard)
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary, row=2)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_item_idx = int(interaction.data['values'][0])
        self._update_components()
        item = self.character.data.inventory[self.selected_item_idx]
        embed = self._build_item_detail_embed(item)
        await interaction.response.edit_message(embed=embed, view=self)

    async def equip_callback(self, interaction: discord.Interaction):
        item = self.character.data.inventory[self.selected_item_idx]
        try:
            self.character.equip_item(item.name)
            self.selected_item_idx = -1
            self._update_components()
            await interaction.response.edit_message(embed=build_inventory_embed(self.character, self.user), view=self)
            await interaction.followup.send(f"✅ 成功裝備了 **{item.name}**！", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ 裝備失敗: {e}", ephemeral=True)

    async def discard_callback(self, interaction: discord.Interaction):
        item = self.character.data.inventory.pop(self.selected_item_idx)
        self.character.save()
        self.selected_item_idx = -1
        self._update_components()
        await interaction.response.edit_message(embed=build_inventory_embed(self.character, self.user), view=self)
        await interaction.followup.send(f"🗑️ 已丟棄 **{item.name}**。", ephemeral=True)

    async def back_callback(self, interaction: discord.Interaction):
        from ui.views.hub import CharacterHubView
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(embed=build_character_embed(self.character, self.user), view=hub_view)

    def _build_item_detail_embed(self, item) -> discord.Embed:
        is_eq = isinstance(item, Equipment)
        color = 0x95a5a6
        if is_eq:
            from core.equipment import EquipmentBalancer
            color = EquipmentBalancer.get_tier_color(item.tier)
        embed = discord.Embed(title=f"📦 物品詳情：{item.name}", description=item.description, color=color)
        if is_eq:
            stats_text = "".join([f"- {s}: {v*100 if 'rate' in s else v:+.1f if 'rate' in s else '+'}\n" for s, v in item.bonuses.items()])
            embed.add_field(name="✨ 屬性加成", value=f"```md\n{stats_text or '無'}```", inline=False)
            if item.special_effect: embed.add_field(name="🔮 特殊效果", value=f"*{item.special_effect}*", inline=False)
            embed.set_footer(text=f"階級: {item.tier} | 等級需求: Lv.{item.item_level} | 部位: {item.slot_type}")
        else: embed.add_field(name="數量", value=str(item.quantity))
        return embed

class UnequipView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member):
        super().__init__(timeout=120.0)
        self.character = character
        self.user = user
        self._update_select_menu()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能操作別人的選單！", ephemeral=True)
            return False
        return True

    def _update_select_menu(self):
        self.clear_items()
        options = []
        slot_map = {"head": "頭部", "shoulders": "肩膀", "cloak": "披風", "chest": "胸甲", "hands": "手部", "legs": "腿部", "feet": "腳部", "main_hand": "主手", "off_hand": "副手", "trinket_1": "飾品1", "trinket_2": "飾品2", "ring_1": "戒指1", "ring_2": "戒指2"}
        for field in self.character.data.equipment_slots.model_fields.keys():
            item = getattr(self.character.data.equipment_slots, field)
            if item: options.append(discord.SelectOption(label=f"{slot_map.get(field, field)}: {item.name}", value=field))
        if not options: options.append(discord.SelectOption(label="目前沒有裝備任何物品", value="none"))
        select = discord.ui.Select(placeholder="選擇要卸下的部位...", options=options, custom_id="unequip_select", disabled=(len(options) == 0 or options[0].value == "none"))
        select.callback = self.unequip_callback
        self.add_item(select)
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary, row=1)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def unequip_callback(self, interaction: discord.Interaction):
        slot = interaction.data['values'][0]
        if slot == "none": return
        try:
            item = self.character.unequip_item(slot)
            if item:
                self._update_select_menu()
                await interaction.response.edit_message(embed=build_character_embed(self.character, self.user), view=self)
                await interaction.followup.send(f"👕 已卸下 **{item.name}**。", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ 卸下失敗: {e}", ephemeral=True)

    async def back_callback(self, interaction: discord.Interaction):
        from ui.views.hub import CharacterHubView
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(self.character, self.user), view=hub_view)
