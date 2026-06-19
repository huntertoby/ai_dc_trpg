import unittest
from unittest.mock import MagicMock, AsyncMock
from core.models import CharacterSchema, AreaSchema, BuildingSchema, Vitality, PrimaryAttributes, EquipmentSlots
from core.character import Character
from logic.workflows.exploration import explore_landmark_workflow

class TestLandmarkExploration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock character schema and character instance
        self.char_data = CharacterSchema(
            character_id="test_char_999",
            name="泰瑞斯",
            background="學者",
            primary_stats=PrimaryAttributes(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[],
            status_effects=[],
            equipment_slots=EquipmentSlots()
        )
        self.character = Character(self.char_data, "user_123")
        # Mock the save method of Character to prevent writing to disk
        self.character.save = MagicMock()

        self.area = AreaSchema(
            id="0,1",
            name="微光森林",
            type="wilderness",
            description="一片被魔法微光籠罩的古老森林。",
            ecology_tags=["木系", "神祕"],
            dominant_species=["妖精", "林狼"],
            threat_level=1.0
        )

        self.building = BuildingSchema(
            id="landmark_0_1_0",
            name="荒廢的德魯伊祭壇",
            description="祭壇上長滿了藤蔓，隱約散發著自然法術的殘留共鳴。",
            features=["explore"]
        )

        # Mock LLM Client
        self.mock_llm = MagicMock()
        self.mock_llm.call = AsyncMock(return_value="你在祭壇上發現了一枚刻滿古老符文的石板，微弱的光芒在符文間流轉。你是否要嘗試解讀它？")

    async def test_explore_landmark_workflow_insufficient_stamina(self):
        # Set stamina to 5 (needs 10)
        self.character.data.vitality.stamina = 5
        res = await explore_landmark_workflow(
            character=self.character,
            area=self.area,
            building=self.building,
            user_id="user_123",
            llm_client=self.mock_llm
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "stamina")
        self.assertEqual(self.character.data.vitality.stamina, 5) # Check no deduction
        self.character.save.assert_not_called()

    async def test_explore_landmark_workflow_success(self):
        # Set stamina to 100
        self.character.data.vitality.stamina = 100
        res = await explore_landmark_workflow(
            character=self.character,
            area=self.area,
            building=self.building,
            user_id="user_123",
            llm_client=self.mock_llm
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["event_text"], "你在祭壇上發現了一枚刻滿古老符文的石板，微弱的光芒在符文間流轉。你是否要嘗試解讀它？")
        self.assertEqual(self.character.data.vitality.stamina, 90) # Deducted 10 stamina
        self.character.save.assert_called_once()
        self.mock_llm.call.assert_called_once()
