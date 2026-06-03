# ui/views.py
import discord
from core.character import Character
from core.models import Equipment, Item
from core.constants import RANK_COLORS
from ui.embeds import (
    build_character_embed, 
    build_inventory_embed, 
    build_skills_embed, 
    build_location_embed
)

class CharacterHubView(discord.ui.View):
    """角色主控制面板 (The Hub)"""
    def __init__(self, character: Character, user: discord.Member):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        # 初始化時動態添加屬性分配按鈕
        self._add_stats_button()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 這不是你的面板喔！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚜️ 面板", style=discord.ButtonStyle.primary)
    async def show_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_character_embed(self.character, self.user)
        # 重新初始化 Hub 以更新按鈕狀態 (例如點數變化)
        view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="🛡️ 裝備", style=discord.ButtonStyle.secondary)
    async def show_equipment(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.embeds import build_equipment_embed
        embed = build_equipment_embed(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="📖 傳記", style=discord.ButtonStyle.secondary)
    async def show_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        from ui.embeds import build_profile_embed
        embed = build_profile_embed(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    def _add_stats_button(self):
        """動態添加屬性分配按鈕"""
        pts = self.character.data.stat_points
        if pts > 0:
            # 只有有點數時才顯示
            btn = discord.ui.Button(
                label=f"🧬 分配屬性 ({pts})", 
                style=discord.ButtonStyle.success,
                custom_id="hub_allocate_stats"
            )
            btn.callback = self.show_allocation
            self.add_item(btn)

    async def show_allocation(self, interaction: discord.Interaction):
        from logic.workflows.character_creation import StatsAllocationView
        view = StatsAllocationView(self.character)
        # 修改返回邏輯：分配完後回到 Hub
        original_stop = view.stop
        def new_stop():
            original_stop()
        view.stop = new_stop
        
        await interaction.response.edit_message(content=view.get_content(), embed=None, view=view)

    @discord.ui.button(label="🎒 背包", style=discord.ButtonStyle.secondary)
    async def show_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = InventoryView(self.character, self.user)
        embed = build_inventory_embed(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="📜 技能", style=discord.ButtonStyle.secondary)
    async def show_skills(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_skills_embed(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="👕 脫裝", style=discord.ButtonStyle.secondary)
    async def show_unequip(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = UnequipView(self.character, self.user)
        embed = build_character_embed(self.character, self.user)
        embed.title = f"👕 {self.character.data.name} - 卸下裝備"
        embed.description = "請選擇要卸下的裝備部位。"
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="🗺️ 探索", style=discord.ButtonStyle.secondary)
    async def show_location(self, interaction: discord.Interaction, button: discord.ui.Button):
        from core.world import WorldManager
        loc = self.character.data.location
        area = WorldManager.load_area(loc[0], loc[1])
        
        if area and area.type == "city":
            # 如果在城市，顯示城市導覽視圖
            view = CityView(self.character, self.user, area)
            from ui.embeds import build_area_embed
            await interaction.response.edit_message(content=None, embed=build_area_embed(area, self.character), view=view)
        else:
            # 如果在野外，顯示移動視圖 (待實作)
            embed = build_location_embed(self.character, self.user)
            await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="🎭 換角", style=discord.ButtonStyle.secondary)
    async def show_switch(self, interaction: discord.Interaction, button: discord.ui.Button):
        from db.storage import CharacterRepository
        chars = CharacterRepository.list_characters(str(self.user.id))
        active_name = CharacterRepository.get_active_character_name(str(self.user.id))
        
        view = CharacterSwitchView(chars, active_name, self.user)
        await interaction.response.edit_message(content="🎭 請選擇要切換的角色：", embed=None, view=view)


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
        
        # 1. 物品下拉選單
        options = []
        for i, item in enumerate(self.character.data.inventory):
            from core.models import Equipment
            label = f"{item.name} (x{item.quantity})"
            if isinstance(item, Equipment):
                label = f"[{item.tier}] {item.name} (Lv.{item.item_level})"
            
            options.append(discord.SelectOption(
                label=label,
                description=item.description[:50],
                value=str(i)
            ))

        if not options:
            options.append(discord.SelectOption(label="背包空空如也", value="-1"))

        select = discord.ui.Select(
            placeholder="選擇一個物品查看詳情...",
            options=options,
            custom_id="inv_select",
            disabled=len(self.character.data.inventory) == 0
        )
        select.callback = self.select_callback
        self.add_item(select)

        # 2. 動作按鈕
        if 0 <= self.selected_item_idx < len(self.character.data.inventory):
            item = self.character.data.inventory[self.selected_item_idx]
            from core.models import Equipment
            
            if isinstance(item, Equipment):
                btn_equip = discord.ui.Button(label="✅ 裝備", style=discord.ButtonStyle.success)
                btn_equip.callback = self.equip_callback
                self.add_item(btn_equip)
            
            btn_discard = discord.ui.Button(label="🗑️ 丟棄", style=discord.ButtonStyle.danger)
            btn_discard.callback = self.discard_callback
            self.add_item(btn_discard)

        # 3. 返回按鈕
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
            
            # 使用 edit_message 更新 UI，使用 followup 發送成功提示
            await interaction.response.edit_message(embed=build_inventory_embed(self.character, self.user), view=self)
            await interaction.followup.send(f"✅ 成功裝備了 **{item.name}**！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 裝備失敗: {e}", ephemeral=True)

    async def discard_callback(self, interaction: discord.Interaction):
        item = self.character.data.inventory.pop(self.selected_item_idx)
        self.character.save()
        
        self.selected_item_idx = -1
        self._update_components()
        
        await interaction.response.edit_message(embed=build_inventory_embed(self.character, self.user), view=self)
        await interaction.followup.send(f"🗑️ 已丟棄 **{item.name}**。", ephemeral=True)

    async def back_callback(self, interaction: discord.Interaction):
        hub_view = CharacterHubView(self.character, self.user)
        embed = build_character_embed(self.character, self.user)
        await interaction.response.edit_message(embed=embed, view=hub_view)

    def _build_item_detail_embed(self, item) -> discord.Embed:
        from core.models import Equipment
        is_eq = isinstance(item, Equipment)
        color = 0x95a5a6
        if is_eq:
            from core.equipment import EquipmentBalancer
            color = EquipmentBalancer.get_tier_color(item.tier)

        embed = discord.Embed(
            title=f"📦 物品詳情：{item.name}",
            description=item.description,
            color=color
        )
        if is_eq:
            stats_text = ""
            for stat, val in item.bonuses.items():
                if "rate" in stat or "accuracy" in stat:
                    stats_text += f"- {stat}: {val*100:.1f}%\n"
                else:
                    stats_text += f"- {stat}: {int(val) if val==int(val) else val:+}\n"
            embed.add_field(name="✨ 屬性加成", value=f"```md\n{stats_text or '無'}```", inline=False)
            if item.special_effect:
                embed.add_field(name="🔮 特殊效果", value=f"*{item.special_effect}*", inline=False)
            embed.set_footer(text=f"階級: {item.tier} | 等級需求: Lv.{item.item_level} | 部位: {item.slot_type}")
        else:
            embed.add_field(name="數量", value=str(item.quantity))
        return embed


class CharacterSwitchView(discord.ui.View):
    def __init__(self, characters: list[str], active_name: str, user: discord.Member):
        super().__init__(timeout=60.0)
        self.user = user

        options = []
        for name in characters:
            status = " (目前活躍)" if name == active_name else ""
            options.append(discord.SelectOption(label=f"{name}{status}", value=name, default=(name == active_name)))
        
        select = discord.ui.Select(
            placeholder="選擇要切換的角色...",
            options=options,
            custom_id="switch_select"
        )
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
        selected_name = interaction.data['values'][0]
        from db.storage import CharacterRepository
        CharacterRepository.set_active_character(str(self.user.id), selected_name)
        
        # 重新載入角色
        char = Character.load(str(self.user.id))
        hub_view = CharacterHubView(char, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(char, self.user), view=hub_view)

    async def back_callback(self, interaction: discord.Interaction):
        char = Character.load(str(self.user.id))
        hub_view = CharacterHubView(char, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(char, self.user), view=hub_view)


class CharacterDeleteView(discord.ui.View):
    def __init__(self, characters: list[str], user: discord.Member):
        super().__init__(timeout=60.0)
        self.user = user
        self.selected_name = None

        options = [discord.SelectOption(label=name, value=name) for name in characters]

        select = discord.ui.Select(
            placeholder="選擇要刪除的角色...",
            options=options,
            custom_id="delete_select"
        )
        select.callback = self.select_callback
        self.add_item(select)

        self.confirm_btn = discord.ui.Button(label="確認刪除", style=discord.ButtonStyle.danger, disabled=True)
        self.confirm_btn.callback = self.confirm_callback
        self.add_item(self.confirm_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 你不能操作別人的選單！", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_name = interaction.data['values'][0]
        self.confirm_btn.disabled = False
        self.confirm_btn.label = f"確認刪除 {self.selected_name}"
        await interaction.response.edit_message(view=self)

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_name: return
        from db.storage import CharacterRepository
        success = CharacterRepository.delete_character(str(self.user.id), self.selected_name)
        if success:
            await interaction.response.edit_message(content=f"🗑️ 角色 **{self.selected_name}** 已成功刪除。", view=None)
        else:
            await interaction.response.edit_message(content=f"❌ 刪除 **{self.selected_name}** 時發生錯誤。", view=None)
        self.stop()

class UnequipView(discord.ui.View):
    """卸下裝備視圖"""
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
        
        # 獲取所有已裝備的部位
        options = []
        eq_slots = self.character.data.equipment_slots
        for field in eq_slots.model_fields.keys():
            item = getattr(eq_slots, field)
            if item:
                # 這裡需要一個部位對應中文的映射，為了方便先直接顯示 field 名稱或簡單轉換
                slot_name_map = {
                    "head": "頭部", "shoulders": "肩膀", "cloak": "披風", "chest": "胸甲",
                    "hands": "手部", "legs": "腿部", "feet": "腳部",
                    "main_hand": "主手", "off_hand": "副手",
                    "trinket_1": "飾品1", "trinket_2": "飾品2",
                    "ring_1": "戒指1", "ring_2": "戒指2"
                }
                options.append(discord.SelectOption(
                    label=f"{slot_name_map.get(field, field)}: {item.name}",
                    value=field
                ))

        if not options:
            options.append(discord.SelectOption(label="目前沒有裝備任何物品", value="none"))

        select = discord.ui.Select(
            placeholder="選擇要卸下的部位...",
            options=options,
            custom_id="unequip_select",
            disabled=(len(options) == 0 or options[0].value == "none")
        )
        select.callback = self.unequip_callback
        self.add_item(select)

        # 返回按鈕
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary, row=1)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def unequip_callback(self, interaction: discord.Interaction):
        slot = interaction.data['values'][0]
        if slot == "none": return
        
        try:
            item = self.character.unequip_item(slot)
            if item:
                # 1. 刷新選單狀態
                self._update_select_menu()
                # 2. 更新原始訊息 (Embed 和 View)
                await interaction.response.edit_message(embed=build_character_embed(self.character, self.user), view=self)
                # 3. 發送非同步提示
                await interaction.followup.send(f"👕 已卸下 **{item.name}** 並放入背包。", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ 該部位沒有裝備物品。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 卸下失敗: {e}", ephemeral=True)

    async def back_callback(self, interaction: discord.Interaction):
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(content=None, embed=build_character_embed(self.character, self.user), view=hub_view)

class CityView(discord.ui.View):
    """城市導覽視圖"""
    def __init__(self, character: Character, user: discord.Member, area: 'AreaSchema'):
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
        options = []
        for b in self.area.buildings:
            options.append(discord.SelectOption(
                label=b.name,
                description=b.description[:50],
                value=b.id
            ))
        
        select = discord.ui.Select(
            placeholder="前往建築物...",
            options=options,
            custom_id="city_building_select"
        )
        select.callback = self.building_callback
        self.add_item(select)

        # 添加離開城市的按鈕 (方向鍵)
        directions = [("⬆️ 北", [0, 1]), ("⬇️ 南", [0, -1]), ("⬅️ 西", [-1, 0]), ("➡️ 東", [1, 0])]
        for label, move in directions:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=1)
            # 這裡需要一個移動的回調，先預留
            # btn.callback = self.move_callback 
            self.add_item(btn)
        
        # 返回面板
        btn_back = discord.ui.Button(label="🔙 返回面板", style=discord.ButtonStyle.primary, row=2)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def building_callback(self, interaction: discord.Interaction):
        building_id = interaction.data['values'][0]
        building = next((b for b in self.area.buildings if b.id == building_id), None)
        
        if not building: return
        
        # 這裡未來會接 AI 生成進入建築的描述
        embed = discord.Embed(
            title=f"🚪 進入：{building.name}",
            description=f"你推開了大門，進入了{building.name}。\n\n*{building.description}*",
            color=discord.Color.gold()
        )
        if building.npc_name:
            npc_info = f"**{building.npc_name}** ({', '.join(building.npc_traits)})"
            talk_info = f"💬 交談花費: `{building.talk_cost}` 體力 (情報率: {int(building.rumor_rate*100)}%)"
            embed.add_field(name="👤 駐守人員", value=f"{npc_info}\n{talk_info}")
            
        # 根據建築 features 顯示功能按鈕
        view = BuildingView(self.character, self.user, building, self.area)
        await interaction.response.edit_message(embed=embed, view=view)

    async def back_callback(self, interaction: discord.Interaction):
        hub_view = CharacterHubView(self.character, self.user)
        await interaction.response.edit_message(embed=build_character_embed(self.character, self.user), view=hub_view)

class BuildingView(discord.ui.View):
    """建築物內部互動視圖"""
    def __init__(self, character: Character, user: discord.Member, building: 'BuildingSchema', area: 'AreaSchema'):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.building = building
        self.area = area
        self._add_feature_buttons()

    def _add_feature_buttons(self):
        # 根據 building.features 動態添加功能按鈕
        if "quest" in self.building.features:
            btn_take = discord.ui.Button(label="📜 領取委託", style=discord.ButtonStyle.success)
            btn_take.callback = self.open_quest_board
            self.add_item(btn_take)
            
            btn_report = discord.ui.Button(label="✅ 任務回報", style=discord.ButtonStyle.primary)
            btn_report.callback = self.report_quests
            self.add_item(btn_report)

        # [新增] 如果有 NPC，添加聊天按鈕
        if self.building.npc_name:
            btn_talk = discord.ui.Button(label=f"💬 與 {self.building.npc_name} 交談", style=discord.ButtonStyle.secondary)
            btn_talk.callback = self.talk_to_npc
            self.add_item(btn_talk)

        if "rank" in self.building.features:
            btn_rank = discord.ui.Button(label="🎖️ 階級提升", style=discord.ButtonStyle.secondary)
            btn_rank.callback = self.rank_up_action
            self.add_item(btn_rank)

        if "storage" in self.building.features:
            btn = discord.ui.Button(label="🌀 開啟虛空倉庫", style=discord.ButtonStyle.success)
            btn.callback = self.open_warehouse
            self.add_item(btn)
            
        if "rest" in self.building.features:
            btn = discord.ui.Button(label="🍺 休息 (恢復體力)", style=discord.ButtonStyle.success)
            btn.callback = self.rest_action
            self.add_item(btn)

        btn_back = discord.ui.Button(label="🔙 走出建築", style=discord.ButtonStyle.secondary)
        btn_back.callback = self.back_to_city
        self.add_item(btn_back)

    async def talk_to_npc(self, interaction: discord.Interaction):
        """與 NPC 交談 (消耗建築專屬體力，包含動態情報獲取與持久化儲存)"""
        # 1. 檢查體力 (使用建築物專屬消耗)
        COST = self.building.talk_cost
        if self.character.data.vitality.stamina < COST:
            await interaction.response.send_message(f"❌ 你太累了，連話都說不清楚... (需要 {COST} 體力)", ephemeral=True)
            return

        # 2. 扣除體力並儲存
        self.character.data.vitality.stamina -= COST
        self.character.save()

        await interaction.response.defer(ephemeral=True)
        
        from services.llm_service import LMStudioClient
        llm_client = LMStudioClient()
        
        # 3. 定義地區專屬情報池
        area_rumors = {
            "0,0": [ # 萬族樞紐
                "據說在北方 (0, 3) 的沼澤地帶，有人發現了生鏽的古代寶箱。",
                "小心 (2, -2) 的陰影森林，那裡的哥布林比平常更兇暴。",
                "如果你想提升實力，聽說 (1, 1) 的老戰士願意指導新手。",
                "最近城外的史萊姆異常聚集，似乎是因為 (-1, -1) 出現了能量波動。"
            ],
        }
        
        current_pool = area_rumors.get(self.area.id, ["聽說遠方有一片未被發掘的荒野，藏著失落的文明。"])
        
        # 4. 判定是否生成情報 (使用建築物專屬機率)
        import random
        is_rumor = random.random() < self.building.rumor_rate
        target_rumor = random.choice(current_pool) if is_rumor else None
        
        # 5. 構建系統提示詞
        system_prompt = f"""
        你現在扮演 TRPG 中的 NPC：{self.building.npc_name}。
        性格特質：{', '.join(self.building.npc_traits)}
        目前位置：{self.area.name} - {self.building.name}
        
        **【對話規範】**
        1. 嚴禁使用第三人稱敘事、括號動作或旁白。只輸出說出口的話。
        2. 語氣要親切、符合性格。玩家可以一直找你聊天，只要他們有體力。
        3. 如果【情報標記】為 True，你必須在閒聊中自然地嵌入這條傳聞：{target_rumor}
        4. 如果【情報標記】為 False，則進行普通的日常閒聊，或是對當前地區的感慨。
        5. 語言：繁體中文。長度限制 70 字以內。
        """
        
        prompt = f"冒險者 {self.character.data.name} 湊過來找你聊天。【情報標記】：{is_rumor}"
        
        try:
            content = await llm_client.call(prompt, system_prompt)
            content = content.replace("「", "").replace("」", "").replace("『", "").replace("』", "")
            
            # 6. 如果獲取了情報，儲存到角色的已知情報清單中
            if is_rumor and target_rumor not in self.character.data.known_rumors:
                self.character.data.known_rumors.append(target_rumor)
                self.character.save()
            
            embed = discord.Embed(
                title=f"💬 與 {self.building.npc_name} 的對話",
                description=f"**{self.building.npc_name}**：\n「{content.strip()}」",
                color=discord.Color.blue()
            )
            
            footer_text = f"消耗體力: {COST} | 剩餘體力: {self.character.data.vitality.stamina}"
            if is_rumor:
                footer_text += " | ✨ 獲得新情報！"
            
            embed.set_footer(text=footer_text)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 交談失敗: {e}", ephemeral=True)

    async def report_quests(self, interaction: discord.Interaction):
        """[開發中] 檢查任務目標並回報獎勵"""
        # 這裡未來會接邏輯：遍歷 character.data.active_quests，檢查 objectives 是否完成
        await interaction.response.send_message("🔍 執法官·瓦爾肯正在檢查你的任務紀錄... (回報功能開發中)", ephemeral=True)

    async def rank_up_action(self, interaction: discord.Interaction):
        """[開發中] 冒險者階級提升邏輯"""
        # 這裡未來會接邏輯：檢查等級、聲望、金幣，並開啟 AI 生成的升階試煉
        current_rank = self.character.data.rank
        await interaction.response.send_message(f"🎖️ 你目前是 **Rank {current_rank}**。升階試煉需要達到 Lv.10 且擁有 100 點聲望。(功能開發中)", ephemeral=True)

    async def open_warehouse(self, interaction: discord.Interaction):
        # 這裡將實作倉庫介面
        await interaction.response.send_message("🌀 虛空倉庫功能開發中...", ephemeral=True)

    async def open_quest_board(self, interaction: discord.Interaction):
        from core.guild import GuildManager
        quests = GuildManager.load_board()
        if not quests:
            # 嘗試刷新一次
            from services.llm_service import LMStudioClient
            llm_client = LMStudioClient()
            quests = await GuildManager.refresh_board_if_needed(llm_client)
            
        view = QuestBoardView(self.character, self.user, quests, self.building, self.area)
        await interaction.response.edit_message(content="📜 公會公告欄：這裡貼滿了各地的委託。", embed=None, view=view)

    async def rest_action(self, interaction: discord.Interaction):
        from datetime import datetime
        from core.constants import STAMINA_RESTORE_COST
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 1. 優先使用免費次數
        if self.character.data.last_free_rest_date != today:
            self.character.data.last_free_rest_date = today
            self.character.data.vitality.stamina = self.character.max_stamina
            self.character.save()
            
            await interaction.response.send_message(
                "🍺 你在大口喝下美酒後，感到精力充沛！\n*(今日首份體力免費補滿)*", 
                ephemeral=True
            )
        # 2. 如果免費次數已用，檢查付費次數
        elif self.character.data.last_paid_rest_date != today:
            if self.character.data.gold < STAMINA_RESTORE_COST:
                await interaction.response.send_message(
                    f"❌ 今天的免費體力補給已用完。額外購買需要 **{STAMINA_RESTORE_COST}** 金幣，你的金幣不足！", 
                    ephemeral=True
                )
                return
            
            # 扣除金幣並恢復
            self.character.data.gold -= STAMINA_RESTORE_COST
            self.character.data.last_paid_rest_date = today
            self.character.data.vitality.stamina = self.character.max_stamina
            self.character.save()
            
            await interaction.response.send_message(
                f"💰 你支付了 **{STAMINA_RESTORE_COST}** 金幣，再次感到精力充沛！\n*(今日額外體力補給已完成)*", 
                ephemeral=True
            )
        # 3. 如果兩次都用完
        else:
            await interaction.response.send_message(
                "❌ 今天的體力補給次數(免費1次 + 付費1次)已達上限。請明天再來吧！", 
                ephemeral=True
            )
            return
            
        # 更新背景 Embed
        await interaction.message.edit(embed=interaction.message.embeds[0])

    async def back_to_city(self, interaction: discord.Interaction):
        from ui.embeds import build_area_embed
        view = CityView(self.character, self.user, self.area)
        await interaction.response.edit_message(embed=build_area_embed(self.area, self.character), view=view)

class QuestBoardView(discord.ui.View):
    """公會任務佈告欄視圖"""
    def __init__(self, character: Character, user: discord.Member, quests: List['QuestSchema'], building: 'BuildingSchema' = None, area: 'AreaSchema' = None):
        super().__init__(timeout=300.0)
        self.character = character
        self.user = user
        self.quests = quests
        self.building = building
        self.area = area
        self.page = 0
        self._update_select()

    def _update_select(self):
        self.clear_items()
        
        # 1. 獲取角色目前已接取的任務 ID 列表，用於過濾
        active_quest_ids = [q.id for q in self.character.data.active_quests]
        
        # 2. 過濾掉已接取的任務
        available_quests = [q for q in self.quests if q.id not in active_quest_ids]
        
        # 每次顯示 25 個任務 (Discord 限制)
        options = []
        for i, q in enumerate(available_quests):
            # 檢查階級是否符合
            status = "✅" if q.rank_value <= self.character.rank_value else "🔒"
            options.append(discord.SelectOption(
                label=f"{status} [{q.rank_required}] {q.title}",
                description=f"獎勵: {q.rewards['gold']}G | {q.description[:50]}",
                value=str(i)
            ))

        if not options:
            options.append(discord.SelectOption(label="目前沒有可接取的委託", value="-1"))

        select = discord.ui.Select(
            placeholder="點擊查看任務詳情...",
            options=options,
            disabled=(len(available_quests) == 0)
        )
        select.callback = self.quest_callback
        self.add_item(select)

        # 返回公會按鈕
        btn_back = discord.ui.Button(label="🔙 返回公會", style=discord.ButtonStyle.primary)
        btn_back.callback = self.back_to_guild
        self.add_item(btn_back)

    async def quest_callback(self, interaction: discord.Interaction):
        idx = int(interaction.data['values'][0])
        if idx == -1: return
        
        # 重新計算 available_quests 以取得正確的 index
        active_quest_ids = [q.id for q in self.character.data.active_quests]
        available_quests = [q for q in self.quests if q.id not in active_quest_ids]
        
        quest = available_quests[idx]
        embed = self._build_quest_embed(quest)
        
        # 顯示接受任務按鈕的 View
        view = QuestDetailView(self.character, self.user, quest, self.quests, self.building, self.area)
        await interaction.response.edit_message(embed=embed, view=view)

    async def back_to_guild(self, interaction: discord.Interaction):
        if self.building and self.area:
            # 返回正確的建築物介面
            embed = discord.Embed(
                title=f"🚪 進入：{self.building.name}",
                description=f"你推開了大門，進入了{self.building.name}。\n\n*{self.building.description}*",
                color=discord.Color.gold()
            )
            if self.building.npc_name:
                embed.add_field(name="👤 駐守人員", value=f"**{self.building.npc_name}** ({', '.join(self.building.npc_traits)})")
            
            view = BuildingView(self.character, self.user, self.building, self.area)
            await interaction.response.edit_message(content=None, embed=embed, view=view)
        else:
            # 備援方案：返回城市導覽
            from core.world import WorldManager
            area = WorldManager.load_area(0, 0)
            view = CityView(self.character, self.user, area)
            from ui.embeds import build_area_embed
            await interaction.response.edit_message(content=None, embed=build_area_embed(area, self.character), view=view)

    def _build_quest_embed(self, quest: QuestSchema) -> discord.Embed:
        color = RANK_COLORS.get(quest.rank_required, discord.Color.blue())
        
        embed = discord.Embed(
            title=f"📜 委託：{quest.title}",
            description=quest.description,
            color=color
        )
        embed.add_field(name="🎖️ 階級要求", value=f"Rank {quest.rank_required}", inline=True)
        embed.add_field(name="💰 報酬", value=f"{quest.rewards['gold']} G / {quest.rewards['exp']} XP", inline=True)
        
        obj_text = ""
        type_map = {"kill": "⚔️ 擊殺", "collect": "📦 蒐集", "visit": "👣 拜訪", "talk": "💬 對話", "explore": "🔍 探索"}
        
        for ob in quest.objectives:
            loc_str = f" **📍 座標: ({ob.location[0]}, {ob.location[1]})**" if ob.location else ""
            type_display = type_map.get(ob.type, ob.type.capitalize())
            obj_text += f"- {type_display} {ob.target_id} x{ob.count}{loc_str}\n"
        
        embed.add_field(name="🎯 任務目標", value=obj_text or "無具體目標", inline=False)
        embed.set_footer(text=f"委託 ID: {quest.id} | 請確保體力充足再出發")
        return embed

class QuestDetailView(discord.ui.View):
    """任務詳情與接受視圖"""
    def __init__(self, character: Character, user: discord.Member, quest: 'QuestSchema', all_quests: List['QuestSchema'], building: 'BuildingSchema' = None, area: 'AreaSchema' = None):
        super().__init__(timeout=120.0)
        self.character = character
        self.user = user
        self.quest = quest
        self.all_quests = all_quests
        self.building = building
        self.area = area

    @discord.ui.button(label="✅ 接受委託", style=discord.ButtonStyle.success)
    async def accept_quest(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. 檢查階級
        if self.quest.rank_value > self.character.rank_value:
            await interaction.response.send_message("❌ 你的冒險者階級不足，無法承接此委託！", ephemeral=True)
            return
            
        # 2. 檢查是否已接過
        if any(q.id == self.quest.id for q in self.character.data.active_quests):
            await interaction.response.send_message("⚠️ 你已經在執行這個任務了喔。", ephemeral=True)
            return

        # 3. 邏輯處理
        from core.guild import GuildManager
        if GuildManager.accept_quest(str(self.user.id), self.quest.id):
            self.character.data.active_quests.append(self.quest)
            self.character.save()
            await interaction.response.send_message(f"✅ 已成功領取委託：**{self.quest.title}**！請前往目標地點執行。", ephemeral=True)
            # 返回列表
            view = QuestBoardView(self.character, self.user, self.all_quests, self.building, self.area)
            await interaction.message.edit(content="📜 公會公告欄：這裡貼滿了各地的委託。", embed=None, view=view)
        else:
            await interaction.response.send_message("❌ 領取失敗，該任務名額可能已滿。", ephemeral=True)

    @discord.ui.button(label="🔙 返回列表", style=discord.ButtonStyle.secondary)
    async def back_to_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = QuestBoardView(self.character, self.user, self.all_quests, self.building, self.area)
        await interaction.response.edit_message(content="📜 公會公告欄：這裡貼滿了各地的委託。", embed=None, view=view)

