import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.drop_engine import DropEngine
from core.models import AreaSchema, Item

class TestDropEngine(unittest.IsolatedAsyncioTestCase):
    def test_get_tier_by_dist(self):
        self.assertEqual(DropEngine.get_tier_by_dist(0, 0), "T5")
        self.assertEqual(DropEngine.get_tier_by_dist(3, 4), "T5")
        self.assertEqual(DropEngine.get_tier_by_dist(8, -2), "T4")
        self.assertEqual(DropEngine.get_tier_by_dist(15, 15), "T3")
        self.assertEqual(DropEngine.get_tier_by_dist(25, 0), "T2")
        self.assertEqual(DropEngine.get_tier_by_dist(35, 10), "T1")

    @patch("core.world.WorldManager")
    @patch("random.random", return_value=0.5)
    @patch("random.choice")
    async def test_generate_loot_from_pool(self, mock_choice, mock_random, mock_world_manager):
        area = AreaSchema(
            id="0,0", name="萬族樞紐", type="city", description="主城",
            dominant_species=["野狼"],
            loot_pool={"野狼": [{"name": "狼皮", "description": "粗糙的狼皮", "material_type": "皮革"}]}
        )
        monster = {"name": "野狼", "base_name": "野狼", "level": 1, "source_id": "test_monster"}
        
        mock_choice.side_effect = lambda x: x[0]
        
        # 1. Test from existing pool
        # novelty_chance = 0.2, random.random() = 0.5 > 0.2 -> load from pool
        loot = await DropEngine.generate_loot(area, monster, llm_client=None, novelty_chance=0.2)
        self.assertIsNotNone(loot)
        self.assertEqual(loot.name, "狼皮")
        self.assertEqual(loot.tier, "T5")
        self.assertEqual(loot.source_id, "test_monster")

    @patch("core.world.WorldManager")
    @patch("random.random", return_value=0.1)
    async def test_generate_loot_from_ai(self, mock_random, mock_world_manager):
        # novelty_chance = 0.2, random.random() = 0.1 <= 0.2 -> AI generation
        area = AreaSchema(
            id="0,0", name="萬族樞紐", type="city", description="主城",
            dominant_species=["野狼"], loot_pool={}
        )
        monster = {"name": "野狼", "base_name": "野狼", "level": 1, "source_id": "test_monster"}
        
        mock_llm_client = MagicMock()
        mock_llm_client.call = AsyncMock(return_value='{"name": "狼牙", "description": "鋒利的狼牙", "material_type": "骨骼"}')
        
        loot = await DropEngine.generate_loot(area, monster, llm_client=mock_llm_client, novelty_chance=0.2)
        
        self.assertIsNotNone(loot)
        self.assertEqual(loot.name, "狼牙")
        self.assertEqual(loot.material_type, "骨骼")
        self.assertEqual(loot.tier, "T5")
        
        # Verify it was added to area's loot pool
        self.assertIn("野狼", area.loot_pool)
        self.assertEqual(area.loot_pool["野狼"][0]["name"], "狼牙")
        mock_world_manager.save_area.assert_called_with(area)
