import discord
import random
from typing import List, Dict, Any, Optional
from core.character import Character
from core.combat import CombatManager
from ui.embeds import build_character_embed

class CombatView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, monsters: List[Dict[str, Any]]):
        super().__init__(timeout=600.0)
        self.character = character
        self.user = user
        self.manager = CombatManager(character, monsters)
        self.current_msg = ""
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能替別人戰鬥！", ephemeral=True)
            return False
        return True

    def _update_buttons(self):
        self.clear_items()
        curr = self.manager.get_current_entity()
        
        if self.manager.is_finished:
            btn_exit = discord.ui.Button(label="離開戰鬥", style=discord.ButtonStyle.secondary)
            btn_exit.callback = self.exit_battle
            self.add_item(btn_exit)
            return

        if curr["type"] == "player":
            # 玩家回合：顯示行動按鈕
            btn_atk = discord.ui.Button(label="⚔️ 普通攻擊", style=discord.ButtonStyle.danger)
            btn_atk.callback = self.attack_select
            self.add_item(btn_atk)
            
            btn_skill = discord.ui.Button(label="📜 使用技能", style=discord.ButtonStyle.primary)
            btn_skill.callback = self.skill_select
            self.add_item(btn_skill)
            
            btn_flee = discord.ui.Button(label="🏃 逃跑", style=discord.ButtonStyle.secondary)
            btn_flee.callback = self.flee_attempt
            self.add_item(btn_flee)
        else:
            # 怪物回合：顯示「等待對手行動」按鈕
            btn_wait = discord.ui.Button(label="⏳ 等待怪物行動...", style=discord.ButtonStyle.secondary)
            btn_wait.callback = self.monster_turn_trigger
            self.add_item(btn_wait)

    def _build_combat_embed(self) -> discord.Embed:
        color = discord.Color.red()
        if self.manager.is_finished:
            color = discord.Color.gold() if self.manager.winner == "player" else discord.Color.dark_grey()
            
        embed = discord.Embed(title="⚔️ 戰鬥進行中", description=self.manager.get_battle_summary(), color=color)
        if self.current_msg:
            embed.add_field(name="📜 最近行動", value=self.current_msg, inline=False)
        
        curr = self.manager.get_current_entity()
        footer = f"當前輪到: {'🌟 你' if curr['type'] == 'player' else f'👾 {curr['ref']['name']}'}"
        if self.manager.is_finished:
            footer = "戰鬥已結束。"
        embed.set_footer(text=footer)
        return embed

    async def attack_select(self, interaction: discord.Interaction):
        # 取得存活敵人列表
        targets = self.manager.get_valid_targets()
        if not targets:
            await interaction.response.send_message("❌ 戰場上沒有存活的目標！", ephemeral=True)
            return
        
        # 預設直接攻擊第一個存活目標
        await self.execute_attack(interaction, targets[0]["index"])

    async def execute_attack(self, interaction: discord.Interaction, target_idx: int):
        result = await self.manager.player_attack(target_idx)
        self.current_msg = result["msg"]
        
        if self.manager.is_finished and self.manager.winner == "player":
            await self._process_victory(interaction)
        else:
            self._update_buttons()
            await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

    async def monster_turn_trigger(self, interaction: discord.Interaction):
        """觸發怪物的 AI 回合，自動處理所有連續的怪物回合"""
        from logic.workflows.combat import process_monster_turns_workflow
        res = await process_monster_turns_workflow(self.manager)
        
        self.current_msg = "\n".join(res["messages"])
        self._update_buttons()
        
        if res["finished"] and res["winner"] == "monster":
            await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)
            await interaction.followup.send("💀 你被打敗了... 冒險暫時告一段落。", ephemeral=True)
        else:
            await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

    async def skill_select(self, interaction: discord.Interaction):
        # 1. 取得角色擁有的技能
        skills = self.character.data.abilities
        if not skills:
            await interaction.response.send_message("❌ 你目前沒有任何技能可以使用！", ephemeral=True)
            return

        # 2. 暫時清空按鈕，換成技能下拉選單與返回按鈕
        self.clear_items()

        # 建立下拉選單選項
        options = []
        for i, skill in enumerate(skills):
            cost_parts = []
            for k, v in skill.mechanics.cost.items():
                if v > 0:
                    cost_parts.append(f"{k}:{v}")
            cost_str = ", ".join(cost_parts) if cost_parts else "無消耗"
            
            desc = f"[{cost_str}] {skill.description}"
            if len(desc) > 100:
                desc = desc[:97] + "..."
                
            options.append(discord.SelectOption(
                label=skill.name,
                value=str(i),
                description=desc
            ))

        select = discord.ui.Select(placeholder="🔮 選擇要施放的技能...", options=options)

        # 選擇技能後的 Callback
        async def select_callback(select_interaction: discord.Interaction):
            chosen_idx = int(select.values[0])
            skill = skills[chosen_idx]

            targets = self.manager.get_valid_targets()
            if not targets:
                await select_interaction.response.send_message("❌ 戰場上沒有存活的目標！", ephemeral=True)
                return
            
            # 預設對第一個存活目標施放
            target_idx = targets[0]["index"]

            # 執行施放
            res = await self.manager.cast_skill(skill, target_idx)
            if not res["success"]:
                await select_interaction.response.send_message(res["msg"], ephemeral=True)
                return

            self.current_msg = res["msg"]
            self._update_buttons()

            if self.manager.is_finished and self.manager.winner == "player":
                await self._process_victory(select_interaction)
            else:
                await select_interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

        select.callback = select_callback
        self.add_item(select)

        # 建立返回按鈕
        btn_back = discord.ui.Button(label="返回", style=discord.ButtonStyle.secondary)
        async def back_callback(back_interaction: discord.Interaction):
            self._update_buttons()
            await back_interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

        btn_back.callback = back_callback
        self.add_item(btn_back)

        await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

    async def flee_attempt(self, interaction: discord.Interaction):
        from logic.workflows.combat import process_flee_workflow
        res = process_flee_workflow(self.manager)
        if res["success"]:
            await interaction.response.edit_message(content="🏃 你成功逃離了戰鬥！", embed=None, view=None)
        else:
            self.current_msg = "❌ 逃跑失敗！怪物擋住了你的去路。"
            self._update_buttons()
            await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

    async def _process_victory(self, interaction: discord.Interaction):
        from logic.workflows.combat import process_victory_workflow
        res = process_victory_workflow(self.character, self.manager.monsters)
        
        msg = f"🏆 **戰鬥勝利！**\n獲得了 {res['total_gold']}G 和 {res['total_exp']}XP。"
        if res['leveled_up']:
            msg += f"\n🎊 **等級提升至 Lv.{res['new_level']}！**"
            
        self.current_msg = msg
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_combat_embed(), view=self)

    async def exit_battle(self, interaction: discord.Interaction):
        from ui.views.hub import CharacterHubView
        from ui.embeds import build_character_embed
        view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(content="戰鬥結束，返回主面板。", embed=build_character_embed(self.character, self.user), view=view)
