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
            if self.area.type == "city":
                view = CityView(self.character, self.user, self.area)
            else:
                view = ExplorationView(self.character, self.user, self.area)
            await bi.response.edit_message(
                embed=build_area_embed(self.area, self.character), 
                view=view
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
        
        await interaction.response.defer()
        
        llm_client = LMStudioClient()
        res = await hunt_workflow(self.character, self.area, llm_client)
        
        if not res["success"]:
            await interaction.edit_original_response(content=res["message"], embed=None, view=None)
            return
            
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
        if "explore" in self.building.features:
            btn_explore = discord.ui.Button(label="👣 探索地標", style=discord.ButtonStyle.success)
            btn_explore.callback = self.explore_landmark_action
            self.add_item(btn_explore)
            
        # 萬物熔爐 (forge) 裝備製造兌換
        if self.building.id == "forge":
            btn_craft = discord.ui.Button(label="⚒️ 裝備兌換與製造", style=discord.ButtonStyle.success)
            btn_craft.callback = self.craft_equipment_action
            self.add_item(btn_craft)

        # 真理高塔 (mage_tower) 技能兌換學習
        if self.building.id == "mage_tower":
            btn_learn = discord.ui.Button(label="🔮 技能兌換與學習", style=discord.ButtonStyle.success)
            btn_learn.callback = self.learn_skill_action
            self.add_item(btn_learn)

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
        if self.area.type == "city":
            view = CityView(self.character, self.user, self.area)
        else:
            view = ExplorationView(self.character, self.user, self.area)
        await interaction.response.edit_message(embed=build_area_embed(self.area, self.character), view=view)

    async def explore_landmark_action(self, interaction: discord.Interaction):
        from services.llm_service import LMStudioClient
        from logic.workflows.exploration import explore_landmark_workflow
        
        llm_client = LMStudioClient()
        await interaction.response.defer(ephemeral=True)
        
        res = await explore_landmark_workflow(self.character, self.area, self.building, str(self.user.id), llm_client)
        if not res["success"]:
            await interaction.edit_original_response(content=res["message"])
            return
            
        txt = res["event_text"]
        btn = discord.ui.Button(label="🎬 採取行動", style=discord.ButtonStyle.primary)
        async def act_cb(bi):
            await bi.response.send_modal(ArbiterModal(self.character, self.user, self.area, {"prompt_action": txt}))
        btn.callback = act_cb
        view = discord.ui.View(timeout=120)
        view.add_item(btn)
        
        await interaction.edit_original_response(
            embed=discord.Embed(
                title=f"🔎 地標探索：{self.building.name}", 
                description=txt, 
                color=discord.Color.gold()
            ), 
            view=view
        )

    async def craft_equipment_action(self, interaction: discord.Interaction):
        # 尋找背包中的裝備製造幣
        tokens = [
            item for item in self.character.data.inventory
            if getattr(item, "item_type", "") == "crafting_token" and getattr(item, "material_type", "") == "equipment" and item.quantity > 0
        ]
        if not tokens:
            await interaction.response.send_message("❌ 你身上沒有任何「裝備製造幣」喔！快去冒險取得吧。", ephemeral=True)
            return

        view = CraftEquipmentView(self.character, self.user, tokens, self.building, self.area)
        await interaction.response.edit_message(content="⚒️ **歡迎來到萬物熔爐！請選擇你要使用的製造代幣與想要製造的部位。**", embed=None, view=view)

    async def learn_skill_action(self, interaction: discord.Interaction):
        # 尋找背包中的技能製造幣
        tokens = [
            item for item in self.character.data.inventory
            if getattr(item, "item_type", "") == "crafting_token" and getattr(item, "material_type", "") == "skill" and item.quantity > 0
        ]
        if not tokens:
            await interaction.response.send_message("❌ 你身上沒有任何「技能製造幣」喔！快去冒險取得吧。", ephemeral=True)
            return

        view = LearnSkillView(self.character, self.user, tokens, self.building, self.area)
        await interaction.response.edit_message(content="🔮 **歡迎來到真理高塔！請選擇你要使用的技能代幣。**", embed=None, view=view)


class CraftEquipmentView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, tokens: List[Item], building: BuildingSchema, area: AreaSchema):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.tokens = tokens
        self.building = building
        self.area = area
        self.selected_token_name = tokens[0].name if tokens else None
        self.selected_slot = "main_hand"  # 預設槽位
        self._add_selectors()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    def _add_selectors(self):
        # 1. 製造代幣選擇下拉選單
        token_options = []
        for t in self.tokens:
            # 檢查等級是否符合門檻
            token_lv = int(t.source_id) if t.source_id else 1
            is_locked = self.character.data.level < token_lv
            label = f"{t.name} (數量: {t.quantity})"
            if is_locked:
                label += f" 🔒 需 Lv.{token_lv}"
            
            token_options.append(
                discord.SelectOption(
                    label=label, 
                    value=t.name,
                    description=t.description[:100],
                    default=(t.name == self.selected_token_name)
                )
            )

        token_select = discord.ui.Select(
            placeholder="選擇你要消耗的製造幣...",
            options=token_options,
            custom_id="craft_token_select",
            row=0
        )
        token_select.callback = self.token_select_callback
        self.add_item(token_select)

        # 2. 部位選擇下拉選單
        slot_options = [
            discord.SelectOption(label="🗡️ 主手武器", value="main_hand", default=(self.selected_slot == "main_hand")),
            discord.SelectOption(label="🛡️ 副手裝備/盾牌", value="off_hand", default=(self.selected_slot == "off_hand")),
            discord.SelectOption(label="🪖 頭盔防具", value="head", default=(self.selected_slot == "head")),
            discord.SelectOption(label="👕 胸部防具", value="chest", default=(self.selected_slot == "chest")),
            discord.SelectOption(label="👖 腿部防具", value="legs", default=(self.selected_slot == "legs")),
            discord.SelectOption(label="🥾 鞋子防具", value="feet", default=(self.selected_slot == "feet")),
            discord.SelectOption(label="🧤 手套防具", value="hands", default=(self.selected_slot == "hands")),
            discord.SelectOption(label="🦺 肩部防具", value="shoulders", default=(self.selected_slot == "shoulders")),
            discord.SelectOption(label="🧥 披風裝備", value="cloak", default=(self.selected_slot == "cloak")),
            discord.SelectOption(label="💍 戒指裝備", value="ring_1", default=(self.selected_slot == "ring_1")),
            discord.SelectOption(label="📿 飾品裝備", value="trinket_1", default=(self.selected_slot == "trinket_1")),
        ]
        slot_select = discord.ui.Select(
            placeholder="選擇要製造的裝備部位...",
            options=slot_options,
            custom_id="craft_slot_select",
            row=1
        )
        slot_select.callback = self.slot_select_callback
        self.add_item(slot_select)

        # 3. 按鈕：開始製造、返回
        btn_start = discord.ui.Button(label="⚒️ 開始製造 (輸入設計圖)", style=discord.ButtonStyle.success, row=2)
        btn_start.callback = self.start_crafting
        self.add_item(btn_start)

        btn_back = discord.ui.Button(label="🔙 返回熔爐", style=discord.ButtonStyle.secondary, row=2)
        btn_back.callback = self.back_to_building
        self.add_item(btn_back)

    async def token_select_callback(self, interaction: discord.Interaction):
        self.selected_token_name = interaction.data['values'][0]
        self.clear_items()
        self._add_selectors()
        await interaction.response.edit_message(view=self)

    async def slot_select_callback(self, interaction: discord.Interaction):
        self.selected_slot = interaction.data['values'][0]
        self.clear_items()
        self._add_selectors()
        await interaction.response.edit_message(view=self)

    async def back_to_building(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🚪 進入：{self.building.name}", 
            description=f"你進入了{self.building.name}。\n\n*{self.building.description}*", 
            color=discord.Color.gold()
        )
        if self.building.npc_name:
            embed.add_field(name="👤 駐守人員", value=f"**{self.building.npc_name}** ({', '.join(self.building.npc_traits)})")
        view = BuildingView(self.character, self.user, self.building, self.area)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def start_crafting(self, interaction: discord.Interaction):
        token_item = next((t for t in self.tokens if t.name == self.selected_token_name), None)
        if not token_item:
            await interaction.response.send_message("❌ 選擇的代幣無效！", ephemeral=True)
            return

        token_lv = int(token_item.source_id) if token_item.source_id else 1
        if self.character.data.level < token_lv:
            await interaction.response.send_message(f"❌ 你的等級 (Lv.{self.character.data.level}) 未達到該製造幣的限制門檻 (Lv.{token_lv})！", ephemeral=True)
            return

        modal = CraftEquipmentModal(self.character, self.user, token_item, self.selected_slot, self.building, self.area)
        await interaction.response.send_modal(modal)


class CraftEquipmentModal(discord.ui.Modal):
    concept_input = discord.ui.TextInput(
        label="請輸入這件裝備的設計概念/主題",
        placeholder="例如：一把散發著冰霜寒氣的雙手大劍，或是能增加防禦力與力量的重甲...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=150
    )

    def __init__(self, character: Character, user: discord.Member, token_item: Item, slot: str, building: BuildingSchema, area: AreaSchema):
        super().__init__(title="⚒️ 熔爐製造：輸入設計概念")
        self.character = character
        self.user = user
        self.token_item = token_item
        self.slot = slot
        self.building = building
        self.area = area

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.edit_original_response(content="🔥 **熔爐運轉中... 大工匠托比昂正在根據你的概念鍛造裝備，請稍候...**", view=None)

        from services.llm_service import LMStudioClient
        from core.item_generator import generate_equipment_by_ai
        import re
        
        # 提取括號中的主題（排除 Lv. 格式）
        theme = None
        matches = re.findall(r'\(([^)]+)\)', self.token_item.name)
        for m in matches:
            if not m.startswith("Lv."):
                theme = m
                break
                
        llm_client = LMStudioClient()
        description = self.concept_input.value
        if theme:
            description = f"{description} (製造代幣主題/來源：{theme})"
            
        token_tier = self.token_item.tier or "T5"
        token_level = int(self.token_item.source_id) if self.token_item.source_id else 1

        found_token = None
        for item in self.character.data.inventory:
            if item.name == self.token_item.name and getattr(item, "item_type", "") == "crafting_token":
                found_token = item
                break

        if not found_token or found_token.quantity <= 0:
            await interaction.edit_original_response(content="❌ 你的背包裡已經沒有對應的製造幣了！", view=None)
            return

        eq = await generate_equipment_by_ai(description, token_level, token_tier, self.slot, llm_client)

        if not eq:
            await interaction.edit_original_response(
                content="❌ 熔煉失敗，AI 無法回應或格式錯誤，已保留你的製造幣。請稍候重試！", 
                view=None
            )
            return

        found_token.quantity -= 1
        if found_token.quantity <= 0:
            self.character.data.inventory.remove(found_token)

        self.character.add_item(eq)
        self.character.save()

        embed = discord.Embed(
            title=f"⚒️ 成功鍛造出：{eq.name}",
            description=f"**品質/等階**: [{eq.tier}] | **裝備等級**: Lv.{eq.item_level}\n\n*{eq.description}*",
            color=discord.Color.green()
        )
        embed.add_field(name="裝備部位", value=eq.slot_type)
        if eq.bonuses:
            stat_strs = [f"{k}: +{v}" for k, v in eq.bonuses.items()]
            embed.add_field(name="📊 屬性加成", value="\n".join(stat_strs))
        if eq.special_effect:
            embed.add_field(name="🔮 特殊效果", value=eq.special_effect, inline=False)
            
        embed.set_footer(text="裝備已存入你的背包。您可以返回主城面板穿戴它！")

        back_view = discord.ui.View(timeout=120)
        btn_back = discord.ui.Button(label="🔙 返回熔爐", style=discord.ButtonStyle.primary)
        
        async def back_to_forge(bi):
            embed_building = discord.Embed(
                title=f"🚪 進入：{self.building.name}", 
                description=f"你進入了{self.building.name}。\n\n*{self.building.description}*", 
                color=discord.Color.gold()
            )
            if self.building.npc_name:
                embed_building.add_field(name="👤 駐守人員", value=f"**{self.building.npc_name}** ({', '.join(self.building.npc_traits)})")
            view = BuildingView(self.character, self.user, self.building, self.area)
            await bi.response.edit_message(content=None, embed=embed_building, view=view)
            
        btn_back.callback = back_to_forge
        back_view.add_item(btn_back)

        await interaction.edit_original_response(
            content=f"🎉 **恭喜！你成功消耗了 {self.token_item.name} 並鍛造出一件神兵！**", 
            embed=embed, 
            view=back_view
        )


class LearnSkillView(discord.ui.View):
    def __init__(self, character: Character, user: discord.Member, tokens: List[Item], building: BuildingSchema, area: AreaSchema):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.tokens = tokens
        self.building = building
        self.area = area
        self.selected_token_name = tokens[0].name if tokens else None
        self._add_selectors()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 非本人操作。", ephemeral=True)
            return False
        return True

    def _add_selectors(self):
        token_options = []
        for t in self.tokens:
            token_lv = int(t.source_id) if t.source_id else 1
            is_locked = self.character.data.level < token_lv
            label = f"{t.name} (數量: {t.quantity})"
            if is_locked:
                label += f" 🔒 需 Lv.{token_lv}"
            
            token_options.append(
                discord.SelectOption(
                    label=label, 
                    value=t.name,
                    description=t.description[:100],
                    default=(t.name == self.selected_token_name)
                )
            )

        token_select = discord.ui.Select(
            placeholder="選擇你要消耗的技能代幣...",
            options=token_options,
            custom_id="learn_token_select",
            row=0
        )
        token_select.callback = self.token_select_callback
        self.add_item(token_select)

        btn_start = discord.ui.Button(label="🔮 開始領悟學習 (輸入招式概念)", style=discord.ButtonStyle.success, row=1)
        btn_start.callback = self.start_learning
        self.add_item(btn_start)

        btn_back = discord.ui.Button(label="🔙 返回高塔", style=discord.ButtonStyle.secondary, row=1)
        btn_back.callback = self.back_to_building
        self.add_item(btn_back)

    async def token_select_callback(self, interaction: discord.Interaction):
        self.selected_token_name = interaction.data['values'][0]
        self.clear_items()
        self._add_selectors()
        await interaction.response.edit_message(view=self)

    async def back_to_building(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🚪 進入：{self.building.name}", 
            description=f"你進入了{self.building.name}。\n\n*{self.building.description}*", 
            color=discord.Color.gold()
        )
        if self.building.npc_name:
            embed.add_field(name="👤 駐守人員", value=f"**{self.building.npc_name}** ({', '.join(self.building.npc_traits)})")
        view = BuildingView(self.character, self.user, self.building, self.area)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def start_learning(self, interaction: discord.Interaction):
        token_item = next((t for t in self.tokens if t.name == self.selected_token_name), None)
        if not token_item:
            await interaction.response.send_message("❌ 選擇的代幣無效！", ephemeral=True)
            return

        token_lv = int(token_item.source_id) if token_item.source_id else 1
        if self.character.data.level < token_lv:
            await interaction.response.send_message(f"❌ 你的等級 (Lv.{self.character.data.level}) 未達到該技能代幣的等階限制 (需要 Lv.{token_lv})！", ephemeral=True)
            return

        modal = LearnSkillModal(self.character, self.user, token_item, self.building, self.area)
        await interaction.response.send_modal(modal)


class LearnSkillModal(discord.ui.Modal):
    concept_input = discord.ui.TextInput(
        label="請輸入你想領悟的技能概念/描述",
        placeholder="例如：召喚大量烈焰隕石轟炸敵方全體的法術，或是能夠在受到致命傷時進入無敵姿態的反擊劍術...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=150
    )

    def __init__(self, character: Character, user: discord.Member, token_item: Item, building: BuildingSchema, area: AreaSchema):
        super().__init__(title="🔮 高塔領悟：輸入技能招式概念")
        self.character = character
        self.user = user
        self.token_item = token_item
        self.building = building
        self.area = area

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.edit_original_response(content="🔮 **奧術能量激盪中... 導師埃隆正在引導你的靈魂領悟技能，請稍候...**", view=None)

        from services.llm_service import LMStudioClient
        from core.skill_generator import generate_single_skill
        import re
        
        # 提取括號中的主題
        theme = None
        matches = re.findall(r'\(([^)]+)\)', self.token_item.name)
        for m in matches:
            if not m.startswith("Lv."):
                theme = m
                break
                
        llm_client = LMStudioClient()
        description = self.concept_input.value
        if theme:
            description = f"{description} (技能代幣主題/來源：{theme})"
            
        token_tier = self.token_item.tier or "T5"

        found_token = None
        for item in self.character.data.inventory:
            if item.name == self.token_item.name and getattr(item, "item_type", "") == "crafting_token":
                found_token = item
                break

        if not found_token or found_token.quantity <= 0:
            await interaction.edit_original_response(content="❌ 你的背包裡已經沒有對應的技能代幣了！", view=None)
            return

        skill = await generate_single_skill(description, token_tier, llm_client)

        if not skill:
            await interaction.edit_original_response(
                content="❌ 技能領悟失敗，AI 無法回應或格式錯誤，已保留你的技能代幣。請稍候重試！", 
                view=None
            )
            return

        found_token.quantity -= 1
        if found_token.quantity <= 0:
            self.character.data.inventory.remove(found_token)

        self.character.data.abilities.append(skill)
        self.character.save()

        embed = discord.Embed(
            title=f"🔮 成功領悟技能：{skill.name}",
            description=f"**技能等階**: {skill.tier} | **類型**: {'💎 被動技能' if skill.skill_type == 'passive' else '⚔️ 主動技能'}\n\n*{skill.description}*",
            color=discord.Color.purple()
        )
        
        if skill.skill_type == "active" and skill.mechanics:
            m = skill.mechanics
            cost_str = ", ".join([f"{k}:{v}" for k, v in m.cost.items()]) if m.cost else "無"
            embed.add_field(name="消耗", value=cost_str, inline=True)
            embed.add_field(name="目標", value=m.target_type, inline=True)
            if m.narrative_effect:
                embed.add_field(name="📖 特效說明", value=m.narrative_effect, inline=False)
        elif skill.skill_type == "passive" and skill.bonuses:
            bonus_strs = [f"{k}: +{v}" for k, v in skill.bonuses.items()]
            embed.add_field(name="📊 屬性加成", value="\n".join(bonus_strs), inline=False)
            
        embed.set_footer(text="技能已成功學會。您可以返回主城面板查看技能詳情！")

        back_view = discord.ui.View(timeout=120)
        btn_back = discord.ui.Button(label="🔙 返回高塔", style=discord.ButtonStyle.primary)
        
        async def back_to_tower(bi):
            embed_building = discord.Embed(
                title=f"🚪 進入：{self.building.name}", 
                description=f"你進入了{self.building.name}。\n\n*{self.building.description}*", 
                color=discord.Color.gold()
            )
            if self.building.npc_name:
                embed_building.add_field(name="👤 駐守人員", value=f"**{self.building.npc_name}** ({', '.join(self.building.npc_traits)})")
            view = BuildingView(self.character, self.user, self.building, self.area)
            await bi.response.edit_message(content=None, embed=embed_building, view=view)
            
        btn_back.callback = back_to_tower
        back_view.add_item(btn_back)

        await interaction.edit_original_response(
            content=f"🎉 **恭喜！你成功消耗了 {self.token_item.name} 並學會了新的絕技！**", 
            embed=embed, 
            view=back_view
        )
