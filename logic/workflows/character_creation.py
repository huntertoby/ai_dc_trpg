import json
import re
import asyncio
from typing import Optional, List
import discord

from core.models import CharacterSchema, Skill, Equipment
from core.character import Character
from core.constants import BASE_JOBS, BASE_RACES, SKILL_KEYWORDS
from core.skill_processor import SkillProcessor


def repair_and_parse_json(text: str) -> Optional[dict]:
    """
    強大的 JSON 提取器：支援多塊提取、Markdown 優先、自動合體與結構修復。
    """
    if not text:
        return None

    # 1. 移除 <think> 思考區塊
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # 2. 優先尋找 Markdown 代碼塊 ```json ... ```
    code_blocks = re.findall(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    clean_text = "".join(code_blocks) if code_blocks else text

    # 3. 提取所有頂層對象 (平衡大括號算法)
    blocks = []
    depth = 0
    start = -1
    for i, char in enumerate(clean_text):
        if char == '{':
            if depth == 0: start = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start != -1:
                blocks.append(clean_text[start:i+1])
    
    # 如果沒找到 {} 但有 []
    if not blocks:
        match = re.search(r'(\[.*\])', clean_text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass

    # 4. 解析與合體
    parsed_results = []
    for b in blocks:
        try:
            # 修復常見 JSON 錯誤
            b = re.sub(r',\s*\}', '}', b)
            b = re.sub(r',\s*\]', ']', b)
            parsed_results.append(json.loads(b))
        except:
            continue

    if not parsed_results:
        return None

    # 5. 根據結果類型回傳
    if len(parsed_results) == 1:
        result = parsed_results[0]
    else:
        if all(isinstance(r, dict) for r in parsed_results):
            # 檢查是否有重複的 key (例如都有 'name')，如果有，代表應該是 List
            keys_overlap = False
            seen_keys = set()
            for r in parsed_results:
                if any(k in seen_keys for k in r.keys()):
                    keys_overlap = True
                    break
                seen_keys.update(r.keys())
                
            if keys_overlap:
                result = parsed_results
            else:
                merged = {}
                for r in parsed_results: merged.update(r)
                result = merged
        else:
            result = parsed_results

    # 6. 結構修復 (針對 AI "拉平" 結構的修復邏輯)
    def fix_skill_structure(d):
        if isinstance(d, dict):
            # 1. 修復遺失的名字
            if "name" not in d:
                d["name"] = "未知技能"

            # 2. 修復 tier
            if "tier" in d and isinstance(d["tier"], int):
                d["tier"] = f"T{d['tier']}"
            if "tier" not in d:
                d["tier"] = "T5"
            
            # 3. 修復 formula 結構異常 (如 denominator)
            if "formula" in d:
                f = d["formula"]
                if isinstance(f, str):
                    d["formula"] = { "type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0 }
                elif isinstance(f, dict):
                    if "denominator" in f:
                        f["divisor"] = f.pop("denominator")
                    if "multiplier_value" in f:  # 處理 AI 自己發明的值
                        f.pop("multiplier_value")
                    if "base_stat" in f and f["base_stat"] not in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
                        f["base_stat"] = "STR"
            else:
                d["formula"] = { "type": "multiplier", "base_stat": "STR", "dice": "1d20", "divisor": 15.0 }
                
            # 4. 強制組裝成 mechanics
            if "mechanics" not in d:
                mechanics_keys = ["action_type", "formula", "cost", "keywords", "target_type", "narrative_effect", "custom_logic", "mp_cost"]
                new_mechanics = {}
                for k in list(d.keys()):
                    if k in mechanics_keys or k == "mp_cost":
                        val = d.pop(k)
                        if k == "mp_cost": new_mechanics["cost"] = {"MP": val}
                        else: new_mechanics[k] = val
                d["mechanics"] = new_mechanics
                if "description" not in d: d["description"] = d.get("name", "未命名技能")
                if "action_type" not in d["mechanics"]: d["mechanics"]["action_type"] = "damage"
        return d

    if isinstance(result, list):
        result = [fix_skill_structure(r) for r in result]
    else:
        result = fix_skill_structure(result)

    return result


def parse_bonus_points(text: str) -> dict:
    """
    解析玩家輸入的屬性點數，支援中英文與多種格式
    """
    mapping = {
        "力量": "STR", "str": "STR",
        "敏捷": "DEX", "dex": "DEX",
        "體質": "CON", "con": "CON",
        "智力": "INT", "int": "INT",
        "感知": "WIS", "wis": "WIS",
        "魅力": "CHA", "cha": "CHA"
    }
    distribution = {}
    # 尋找所有 "文字 + 數字" 的組合 (例如 "力量 3", "INT 2")
    matches = re.findall(r'([a-zA-Z]+|[\u4e00-\u9fa5]+)[\s：:]*(\d+)', text)

    for key, val in matches:
        key_lower = key.lower()
        for m_key, m_val in mapping.items():
            if m_key in key_lower:
                distribution[m_val] = distribution.get(m_val, 0) + int(val)
                break
    return distribution


from core.skill_generator import generate_starter_skills


async def generate_starter_gear(char_name: str, base_jobs: List[str], llm_client) -> List[Equipment]:
    """為新角色生成精簡的基礎 T5 裝備"""
    from core.item_generator import generate_equipment_by_ai
    from core.models import Equipment
    # 只給予最核心的三件套：武器、胸甲、腿部
    slots = ["main_hand", "chest", "legs"]
    starter_items = []

    for slot in slots:
        desc = f"一件適合 {char_name} ({'/'.join(base_jobs)}) 使用的基礎 {slot} 裝備"
        eq = await generate_equipment_by_ai(desc, 1, "T5", slot, llm_client)
        if eq:
            starter_items.append(eq)
    return starter_items



async def generate_character_json(description: str, llm_client, user_id: str, name: str = None) -> Optional[Character]:
    """
    根據玩家描述，呼叫 LLM 生成角色基本資料 (不含技能)
    """
    name_instruction = f"角色名稱必須設定為：{name}" if name else "由你根據描述生成一個帥氣的角色名稱"
    
    system_prompt = f"""
    你是一個專業的 TRPG 遊戲管理員 (GM)。請根據玩家的描述，創建一個符合系統格式的初始角色。

    **【關於角色名稱與職業種族】**
    1. {name_instruction}
    2. 你必須從以下【基準職業】清單中，挑選 **2 個** 最接近的職業，填入 "base_jobs" 列表。
    3. 你必須從以下【基準種族】清單中，選擇一個最接近的種族，填入 "base_race" 欄位。

    **【基準職業】**: {", ".join(BASE_JOBS)}
    **【基準種族】**: {", ".join(BASE_RACES)}

    **【極度重要：新手村平衡規則】**
    這是一個從零開始的冒險，所有角色初始都是 **等級 1 的新手**。
    請在「background (背景故事)」中明確體現這種「現階段還很弱」的新手處境。

    **嚴格規則：**
    回應請「只」輸出 JSON。

    **期望的 JSON 結構範例 (請嚴格遵守此精簡格式)：**
    {{
        "name": "角色名稱",
        "job_name": "創意職業",
        "base_jobs": ["職業1", "職業2"],
        "race": "創意種族",
        "base_race": "基準種族",
        "background": "背景故事...",
        "personality": {{
            "belief": "信念",
            "flaw": "缺陷",
            "fear": "恐懼"
        }}
    }}
    """

    prompt = f"玩家描述：{description}\n請生成該角色的 JSON 資料。"

    try:
        # 1. 第一步：生成角色基本資料
        response_text = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7
        )
        parsed_data = repair_and_parse_json(response_text)

        if not parsed_data: return None

        parsed_data["character_id"] = user_id
        if name: parsed_data["name"] = name

        # 2. 第二步：獨立請求生成技能
        valid_skills = await generate_starter_skills(parsed_data, llm_client)
        
        # 4. 生成初始裝備
        starter_gear = await generate_starter_gear(parsed_data["name"], parsed_data["base_jobs"], llm_client)
        
        # 5. 裝載數據並實例化角色
        schema_data = CharacterSchema(**parsed_data)
        schema_data.abilities = valid_skills
        schema_data.inventory.extend(starter_gear)
        
        char = Character(schema_data, user_id)
        
        # 6. 確保角色以全滿狀態誕生
        char.heal_all()

        def get_sheet_string():
            d = char.data
            return f"""角色名稱：{d.name} [{d.race} {d.job_name}]
生命值：{d.vitality.hp}/{char.max_hp} | 法力值：{d.vitality.mp}/{char.max_mp}
基礎屬性：力量 {d.primary_stats.STR} | 敏捷 {d.primary_stats.DEX} | 體質 {d.primary_stats.CON} | 智力 {d.primary_stats.INT} | 感知 {d.primary_stats.WIS} | 魅力 {d.primary_stats.CHA}
性格特質：信念 [{d.personality.belief}] | 缺陷 [{d.personality.flaw}] | 恐懼 [{d.personality.fear}]
目前金幣：{d.gold}G
背景故事：{d.background}"""

        char.get_sheet_string = get_sheet_string
        char.save()
        return char

    except Exception as e:
        print(f"生成角色失敗: {e}")
        return None


class StatsAllocationView(discord.ui.View):
    """視覺化屬性點分配界面"""
    def __init__(self, character_data: Character):
        super().__init__(timeout=180.0)
        self.character_data = character_data
        # 初始化為角色目前的剩餘點數
        self.points_left = character_data.data.stat_points
        self.stats = {"STR": 0, "DEX": 0, "CON": 0, "INT": 0, "WIS": 0, "CHA": 0}
        self.mapping = {
            "STR": "力量", "DEX": "敏捷", "CON": "體質",
            "INT": "智力", "WIS": "感知", "CHA": "魅力"
        }

    def get_content(self):
        stat_text = "\n".join([
            f"**{self.mapping[k]}**: {v:>2} " + ("🔹" * v if v > 0 else "▫️")
            for k, v in self.stats.items()
        ])
        return f"### 🎭 分配屬性點 (目前持有: **{self.points_left}**)\n\n{stat_text}\n\n*點擊按鈕分配點數，可一次全部分配或先分配一部分。*"

    async def _add_stat(self, interaction: discord.Interaction, stat_key: str):
        if self.points_left > 0:
            self.stats[stat_key] += 1
            self.points_left -= 1
            await self._update_message(interaction)
        else:
            await interaction.response.send_message("點數已經用完囉！", ephemeral=True)

    async def _update_message(self, interaction: discord.Interaction):
        # 只要有分配點數 (任一屬性 > 0)，就允許確認
        self.confirm_btn.disabled = (sum(self.stats.values()) == 0)
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="力量 STR", style=discord.ButtonStyle.secondary, row=0)
    async def str_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "STR")

    @discord.ui.button(label="敏捷 DEX", style=discord.ButtonStyle.secondary, row=0)
    async def dex_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "DEX")

    @discord.ui.button(label="體質 CON", style=discord.ButtonStyle.secondary, row=0)
    async def con_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "CON")

    @discord.ui.button(label="智力 INT", style=discord.ButtonStyle.secondary, row=1)
    async def int_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "INT")

    @discord.ui.button(label="感知 WIS", style=discord.ButtonStyle.secondary, row=1)
    async def wis_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "WIS")

    @discord.ui.button(label="魅力 CHA", style=discord.ButtonStyle.secondary, row=1)
    async def cha_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_stat(interaction, "CHA")

    @discord.ui.button(label="重置", style=discord.ButtonStyle.danger, row=2)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 重置為初始進入時的點數
        self.points_left = self.character_data.data.stat_points
        for k in self.stats: self.stats[k] = 0
        self.confirm_btn.disabled = True
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="確認分配", style=discord.ButtonStyle.success, row=2, disabled=True)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # 實際執行屬性點扣除與加成
            self.character_data.add_bonus_points(self.stats)
            
            # 返回角色主面板
            from ui.views import CharacterHubView
            from ui.embeds import build_character_embed
            hub_view = CharacterHubView(self.character_data, interaction.user)
            embed = build_character_embed(self.character_data, interaction.user)
            
            await interaction.response.edit_message(content=None, embed=embed, view=hub_view)
            await interaction.followup.send(f"✅ 成功分配了 {sum(self.stats.values())} 點屬性！", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"❌ 分配失敗: {e}", ephemeral=True)


class ConfirmCharacterView(discord.ui.View):
    def __init__(self, character_data: Character, llm_client, user: discord.Member):
        super().__init__(timeout=120.0)
        self.character_data = character_data
        self.llm_client = llm_client
        self.user = user

    def _get_preview_embeds(self) -> List[discord.Embed]:
        from ui.embeds import build_character_embed, build_skills_embed
        char_embed = build_character_embed(self.character_data, self.user)
        char_embed.title = f"📝 [設定預覽] {char_embed.title}"
        
        skill_embed = build_skills_embed(self.character_data, self.user)
        skill_embed.set_footer(text="❓ 請問這個設定符合你的期待嗎？ (確認後角色將正式誕生)")
        
        return [char_embed, skill_embed]

    @discord.ui.button(label="確認設定", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 角色正式誕生，直接存檔並引導至面板
        self.character_data.save()
        
        await interaction.response.edit_message(
            content=f"🎉 <@{interaction.user.id}> 角色建立完成，你的旅程正式開始！\n你可以使用 `/角色面板` 查看你的屬性並分配初始點數。",
            embeds=[], 
            view=None
        )
        self.stop()

    @discord.ui.button(label="重試技能", style=discord.ButtonStyle.secondary)
    async def retry_skills(self, interaction: discord.Interaction, button: discord.ui.Button):
        """僅重新生成技能"""
        # 使用 defer 避免互動過期
        await interaction.response.defer(ephemeral=True)
        await interaction.edit_original_response(content="🔄 正在重新構思技能，請稍候...", embeds=[], view=None)
        
        # 重新呼叫統一的技能生成函式
        valid_skills = await generate_starter_skills(self.character_data.data.model_dump(), self.llm_client)
        
        # 更新並存檔
        self.character_data.data.abilities = valid_skills
        self.character_data.heal_all()  # 確保重試技能後血量也是滿的
        self.character_data.save()
        
        # 刷新預覽 (使用 edit_original_response 確保穩定)
        await interaction.edit_original_response(content=None, embeds=self._get_preview_embeds(), view=self)

    @discord.ui.button(label="重新生成", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ 已取消生成。請重新使用 `/生成角色`！", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


async def handle_character_creation_workflow(interaction: discord.Interaction, description: str, llm_client, name: str = None):
    await interaction.response.defer(ephemeral=True)
    character_data = await generate_character_json(description, llm_client, str(interaction.user.id), name=name)

    if not character_data:
        await interaction.followup.send("❌ 生成失敗，AI 暫時無法回應 或 格式錯誤。請稍後再試。", ephemeral=True)
        return

    # 使用新的 View 並整合預覽 Embeds
    view = ConfirmCharacterView(character_data, llm_client, interaction.user)
    await interaction.followup.send(embeds=view._get_preview_embeds(), view=view, ephemeral=True)
