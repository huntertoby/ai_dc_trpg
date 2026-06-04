import discord
from typing import List, Optional, Any, Union

from core.character import Character
from core.models import AreaSchema, BuildingSchema, QuestSchema
from core.constants import RANK_COLORS
from core.guild import GuildManager

class QuestBoardView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, quests: List[QuestSchema], building: BuildingSchema = None, area: AreaSchema = None):
        super().__init__(timeout=300.0)
        self.character, self.user, self.quests, self.building, self.area = character, user, quests, building, area
        self._update_select()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    def _update_select(self):
        self.clear_items()
        active_ids = [q.id for q in self.character.data.active_quests]
        avail = [q for q in self.quests if q.id not in active_ids]
        options = [discord.SelectOption(label=f"{'✅' if q.rank_value <= self.character.rank_value else '🔒'} [{q.rank_required}] {q.title}", description=f"{q.rewards['gold']}G | {q.description[:50]}", value=str(i)) for i, q in enumerate(avail)]
        if not options: options.append(discord.SelectOption(label="無可用委託", value="-1"))
        select = discord.ui.Select(placeholder="點擊查看任務...", options=options, disabled=(len(avail) == 0))
        async def cb(i):
            idx = int(i.data['values'][0])
            if idx == -1: return
            q = avail[idx]
            await i.response.edit_message(embed=self._build_quest_embed(q), view=QuestDetailView(self.character, self.user, q, self.quests, self.building, self.area))
        select.callback = cb
        self.add_item(select)
        btn_back = discord.ui.Button(label="🔙 返回", style=discord.ButtonStyle.primary)
        async def back_cb(i):
            from ui.views.exploration import BuildingView
            await i.response.edit_message(embed=discord.Embed(title=f"🚪 進入：{self.building.name}"), view=BuildingView(self.character, self.user, self.building, self.area))
        btn_back.callback = back_cb
        self.add_item(btn_back)

    def _build_quest_embed(self, quest: QuestSchema) -> discord.Embed:
        embed = discord.Embed(title=f"📜 委託：{quest.title}", description=quest.description, color=RANK_COLORS.get(quest.rank_required, discord.Color.blue()))
        embed.add_field(name="💰 報酬", value=f"{quest.rewards['gold']} G / {quest.rewards['exp']} XP")
        obj_text = "\n".join([f"- {ob.type} {ob.target_id} x{ob.count}" for ob in quest.objectives])
        embed.add_field(name="🎯 目標", value=obj_text or "無", inline=False)
        return embed

class QuestDetailView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, quest: QuestSchema, all_quests: List[QuestSchema], building: BuildingSchema = None, area: AreaSchema = None):
        super().__init__(timeout=120.0)
        self.character, self.user, self.quest, self.all_quests, self.building, self.area = character, user, quest, all_quests, building, area

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ 接受委託", style=discord.ButtonStyle.success)
    async def accept_quest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.quest.rank_value > self.character.rank_value:
            await interaction.response.send_message("❌ 階級不足。", ephemeral=True)
            return
        if GuildManager.accept_quest(str(self.user.id), self.quest.id):
            self.character.data.active_quests.append(self.quest); self.character.save()
            await interaction.response.send_message(f"✅ 已領取：{self.quest.title}", ephemeral=True)
            await interaction.message.edit(view=QuestBoardView(self.character, self.user, self.all_quests, self.building, self.area))
        else: await interaction.response.send_message("❌ 領取失敗。", ephemeral=True)

    @discord.ui.button(label="🔙 返回列表", style=discord.ButtonStyle.secondary)
    async def back_to_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=QuestBoardView(self.character, self.user, self.all_quests, self.building, self.area))
