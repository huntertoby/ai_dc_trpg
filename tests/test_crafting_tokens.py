# ai_dc_trpg/tests/test_crafting_tokens.py
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json

from core.character import Character
from core.models import CharacterSchema, Item, Equipment, Skill, Vitality, PrimaryAttributes, EquipmentSlots
from logic.workflows.character_creation import generate_character_json, create_equipment_token, create_skill_token


class TestCraftingTokens(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Setup mock CharacterRepository save to prevent actual filesystem write in tests
        self.repo_patcher = patch("core.character.CharacterRepository")
        self.mock_repo = self.repo_patcher.start()

        self.schema = CharacterSchema(
            character_id="test_user_1",
            name="雷恩",
            background="鐵匠學徒",
            primary_stats=PrimaryAttributes(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots(),
            stat_points=5
        )

    def tearDown(self):
        self.repo_patcher.stop()

    async def test_starter_character_creation_gets_tokens(self):
        """測試初始角色生成是否正確獲得製造代幣，且無初始技能與裝備"""
        mock_llm = MagicMock()
        
        # Mock LLM 回應角色的基本設定
        llm_response = json.dumps({
            "name": "雷恩",
            "job_name": "符文工匠",
            "base_jobs": ["戰士", "工匠"],
            "race": "矮人",
            "base_race": "矮人",
            "background": "在萬物熔爐敲打鐵砧的學徒。",
            "personality": {
                "belief": "追求極致",
                "flaw": "頑固",
                "fear": "失去鍛錘"
            }
        })
        mock_llm.call = AsyncMock(return_value=llm_response)

        char = await generate_character_json(
            description="矮人鐵匠學徒", 
            llm_client=mock_llm, 
            user_id="user_1", 
            name="雷恩"
        )

        self.assertIsNotNone(char)
        # 初始技能與穿戴裝備皆應為空
        self.assertEqual(len(char.data.abilities), 0)
        self.assertIsNone(char.data.equipment_slots.main_hand)
        self.assertIsNone(char.data.equipment_slots.chest)

        # 初始背包中應包含各 3 枚製造幣
        eq_tokens = [i for i in char.data.inventory if i.name == "T5裝備製造幣 (新手套裝卷) (Lv.1)"]
        sk_tokens = [i for i in char.data.inventory if i.name == "T5技能製造幣 (新手技能卷)"]

        self.assertEqual(len(eq_tokens), 1)
        self.assertEqual(eq_tokens[0].quantity, 3)
        self.assertEqual(eq_tokens[0].item_type, "crafting_token")
        self.assertEqual(eq_tokens[0].material_type, "equipment")

        self.assertEqual(len(sk_tokens), 1)
        self.assertEqual(sk_tokens[0].quantity, 3)
        self.assertEqual(sk_tokens[0].item_type, "crafting_token")
        self.assertEqual(sk_tokens[0].material_type, "skill")

    async def test_equipment_token_exchanged(self):
        """測試消耗一個裝備製造幣並生成對應的裝備"""
        char = Character(self.schema, "test_user_1")
        # 給予 3 個製造代幣
        char.add_item(create_equipment_token("T5", 1, 3))
        
        self.assertEqual(len(char.data.inventory), 1)
        self.assertEqual(char.data.inventory[0].quantity, 3)

        # Mock 生成的裝備
        generated_eq = Equipment(
            name="學徒之錘",
            slot_type="main_hand",
            tier="T5",
            item_level=1,
            bonuses={"STR": 2.0}
        )

        # 模擬 Modal on_submit 的扣除與兌換邏輯
        # 1. 尋找代幣
        token_name = "T5裝備製造幣 (新手套裝卷) (Lv.1)"
        found_token = None
        for item in char.data.inventory:
            if item.name == token_name and getattr(item, "item_type", "") == "crafting_token":
                found_token = item
                break

        self.assertIsNotNone(found_token)

        # 2. 扣除代幣並加入新裝備
        found_token.quantity -= 1
        if found_token.quantity <= 0:
            char.data.inventory.remove(found_token)
        char.add_item(generated_eq)
        char.save()

        # 驗證代幣數量變為 2
        self.assertEqual(len([i for i in char.data.inventory if i.name == token_name]), 1)
        updated_token = next(i for i in char.data.inventory if i.name == token_name)
        self.assertEqual(updated_token.quantity, 2)

        # 驗證裝備已存入背包
        self.assertEqual(len([i for i in char.data.inventory if i.name == "學徒之錘"]), 1)
        eq_in_bag = next(i for i in char.data.inventory if i.name == "學徒之錘")
        self.assertEqual(eq_in_bag.slot_type, "main_hand")
        self.assertEqual(eq_in_bag.bonuses["STR"], 2.0)

    async def test_skill_token_exchanged(self):
        """測試消耗一個技能製造代幣並學會對應的技能"""
        char = Character(self.schema, "test_user_1")
        # 給予 3 個技能製造幣
        char.add_item(create_skill_token("T5", 3))

        self.assertEqual(len(char.data.inventory), 1)
        self.assertEqual(char.data.inventory[0].quantity, 3)
        self.assertEqual(len(char.data.abilities), 0)

        # Mock 生成的技能
        generated_sk = Skill(
            name="重擊",
            description="矮人工匠基礎重擊技巧。",
            tier="T5",
            skill_type="active"
        )

        # 模擬 Modal on_submit 的扣除與技能學習邏輯
        token_name = "T5技能製造幣 (新手技能卷)"
        found_token = None
        for item in char.data.inventory:
            if item.name == token_name and getattr(item, "item_type", "") == "crafting_token":
                found_token = item
                break

        self.assertIsNotNone(found_token)

        # 扣除代幣並學會技能
        found_token.quantity -= 1
        if found_token.quantity <= 0:
            char.data.inventory.remove(found_token)
        char.data.abilities.append(generated_sk)
        char.save()

        # 驗證技能幣數量變為 2
        updated_token = next(i for i in char.data.inventory if i.name == token_name)
        self.assertEqual(updated_token.quantity, 2)

        # 驗證已成功學會該技能
        self.assertEqual(len(char.data.abilities), 1)
        self.assertEqual(char.data.abilities[0].name, "重擊")
        self.assertEqual(char.data.abilities[0].tier, "T5")

    def test_token_level_locks(self):
        """測試製造幣的使用門檻限制"""
        char = Character(self.schema, "test_user_1")
        char.data.level = 1

        # 1. 測試等級 20 的裝備幣門檻 (玩家 Lv.1) -> 應為 Locked
        eq_token_20 = create_equipment_token("T4", 20, 1)
        token_lv = int(eq_token_20.source_id)
        self.assertTrue(char.data.level < token_lv)  # Locked

        # 提升等級至 20 -> 應為 Unlocked
        char.data.level = 20
        self.assertFalse(char.data.level < token_lv)  # Unlocked

        # 2. 測試技能幣固定門檻 (玩家回復 Lv.1，使用 T4 技能幣需 20 等)
        char.data.level = 1
        sk_token_t4 = create_skill_token("T4", 1)  # T4 -> source_id="20"
        sk_level_req = int(sk_token_t4.source_id)
        self.assertEqual(sk_level_req, 20)
        self.assertTrue(char.data.level < sk_level_req)  # Locked

        # 玩家升級至 20 -> 應為 Unlocked
        char.data.level = 20
        self.assertFalse(char.data.level < sk_level_req)  # Unlocked

        # 玩家等級為 20 欲使用 T3 技能幣 (需 40 等) -> 應為 Locked
        sk_token_t3 = create_skill_token("T3", 1)  # T3 -> source_id="40"
        self.assertTrue(char.data.level < int(sk_token_t3.source_id))  # Locked

    def test_token_theme_extraction(self):
        """測試是否能正確從製造幣名稱中解析出客製化主題"""
        import re
        def extract_theme(token_name):
            matches = re.findall(r'\(([^)]+)\)', token_name)
            for m in matches:
                if not m.startswith("Lv."):
                    return m
            return None

        # 驗證各種格式
        self.assertEqual(extract_theme("T5裝備製造幣 (新手套裝卷) (Lv.1)"), "新手套裝卷")
        self.assertEqual(extract_theme("T3裝備製造幣 (熔炎之地) (Lv.45)"), "熔炎之地")
        self.assertEqual(extract_theme("T1裝備製造幣 (冰霜龍BOSS) (Lv.80)"), "冰霜龍BOSS")
        self.assertEqual(extract_theme("T5技能製造幣 (新手技能卷)"), "新手技能卷")
        self.assertEqual(extract_theme("T2技能製造幣 (雷霆神殿)"), "雷霆神殿")
        self.assertIsNone(extract_theme("T5裝備製造幣 (Lv.1)"))
