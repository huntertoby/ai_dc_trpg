import unittest
import os
import shutil
from unittest.mock import MagicMock, patch
from core.world import WorldManager, init_main_city
from core.models import AreaSchema, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots

class TestWorld(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Override the area db path
        self.original_path = WorldManager.AREA_DB_PATH
        WorldManager.AREA_DB_PATH = "area_db_test"
        os.makedirs(WorldManager.AREA_DB_PATH, exist_ok=True)

    def tearDown(self):
        # Remove test area db path
        if os.path.exists(WorldManager.AREA_DB_PATH):
            shutil.rmtree(WorldManager.AREA_DB_PATH)
        WorldManager.AREA_DB_PATH = self.original_path

    def test_get_area_id(self):
        self.assertEqual(WorldManager.get_area_id(3, -5), "3,-5")

    def test_get_difficulty_settings(self):
        # Center (0, 0)
        c = WorldManager.get_difficulty_settings(0, 0)
        self.assertEqual(c["base_level"], 1)
        self.assertEqual(c["tier_name"], "文明樞紐")

        # Civilization border (dist <= 5)
        border = WorldManager.get_difficulty_settings(3, 4)  # dist = 4
        self.assertEqual(border["tier"], 1)
        self.assertEqual(border["tier_name"], "文明邊緣")
        
        # Wilderness (dist = 10)
        wild = WorldManager.get_difficulty_settings(10, 0)
        self.assertEqual(wild["tier"], 2)
        self.assertEqual(wild["tier_name"], "異變荒野")

    def test_save_and_load_area(self):
        area = AreaSchema(
            id="2,2", name="妖精之森", type="wilderness", description="美麗的森林"
        )
        WorldManager.save_area(area)
        
        loaded = WorldManager.load_area(2, 2)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "妖精之森")

    def test_load_main_city_auto_initializes(self):
        # 0,0 doesn't exist initially in our temp path
        # Loading (0,0) should auto-initialize main city
        area = WorldManager.load_area(0, 0)
        self.assertIsNotNone(area)
        self.assertEqual(area.id, "0,0")
        self.assertEqual(area.name, "阿卡西亞·萬徑之城")
        
        # Verify it was saved
        self.assertTrue(os.path.exists(os.path.join(WorldManager.AREA_DB_PATH, "0,0.json")))

    @patch("core.world_generator.WorldGenerator.generate_area")
    async def test_move_character_success_existing_area(self, mock_generate_area):
        # Setup existing target area (1, 0)
        target = AreaSchema(id="1,0", name="荒地", type="wilderness", description="荒地")
        WorldManager.save_area(target)

        # Mock Character
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], equipment_slots=EquipmentSlots(), location=[0, 0]
        )

        res = await WorldManager.move_character(char, dx=1, dy=0, llm_client=None)
        self.assertIn("🚶 你向著目標前行，來到了 **荒地**。", res)
        self.assertEqual(char.data.location, [1, 0])
        self.assertEqual(char.data.vitality.stamina, 95)  # 100 - 5 cost
        char.save.assert_called_once()
        mock_generate_area.assert_not_called()

    async def test_move_character_insufficient_stamina(self):
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=2, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], equipment_slots=EquipmentSlots(), location=[0, 0]
        )
        res = await WorldManager.move_character(char, dx=1, dy=0, llm_client=None)
        self.assertIn("❌ 體力不足！", res)
        self.assertEqual(char.data.location, [0, 0])

    @patch("core.world_generator.WorldGenerator.generate_area")
    async def test_move_character_generates_new_area(self, mock_generate_area):
        # Target area (0, 1) does not exist.
        # It should trigger generate_area
        char = MagicMock()
        char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], equipment_slots=EquipmentSlots(), location=[0, 0]
        )

        generated = AreaSchema(id="0,1", name="迷霧森林", type="wilderness", description="大霧迷漫")
        mock_generate_area.return_value = generated

        mock_llm = MagicMock()

        res = await WorldManager.move_character(char, dx=0, dy=1, llm_client=mock_llm)
        self.assertIn("🚶 你向著目標前行，來到了 **迷霧森林**。", res)
        self.assertEqual(char.data.location, [0, 1])
        mock_generate_area.assert_called_with(0, 1, mock_llm)
        
        # Check area was saved
        self.assertTrue(os.path.exists(os.path.join(WorldManager.AREA_DB_PATH, "0,1.json")))
