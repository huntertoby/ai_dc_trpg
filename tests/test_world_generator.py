import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.world_generator import WorldGenerator
from core.models import AreaSchema

class TestWorldGenerator(unittest.IsolatedAsyncioTestCase):
    @patch("random.random", return_value=0.1) # has_landmark = True
    async def test_generate_area_success(self, mock_random):
        mock_llm = MagicMock()
        # Mock json response containing buildings instead of landmarks to test normalization
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "螢光森林",
            "description": "充滿會發光的真菌與植物",
            "ecology_tags": ["發光", "奇幻"],
            "dominant_species": ["螢光精靈", "孢子獸"],
            "buildings": [
                {
                    "name": "真菌小屋",
                    "description": "小屋頂部覆蓋著巨大的螢光蕈",
                    "npc_name": "老學者",
                    "npc_traits": "博學"
                }
            ]
        }
        ''')

        # WorldManager difficulty settings mock via patch
        with patch("core.world.WorldManager.get_difficulty_settings", return_value={
            "base_level": 5, "tier": 1, "tier_name": "文明邊緣", "dist": 4
        }):
            area = await WorldGenerator.generate_area(x=1, y=2, llm_client=mock_llm)
            
            self.assertIsNotNone(area)
            self.assertEqual(area.id, "1,2")
            self.assertEqual(area.name, "螢光森林")
            self.assertEqual(area.base_level, 5)
            self.assertEqual(area.type, "wilderness")
            
            # Connections should be correctly formatted: [x,y+1], [x,y-1], [x-1,y], [x+1,y]
            self.assertEqual(area.connections, ["1,3", "1,1", "0,2", "2,2"])
            
            # Check buildings -> landmarks conversion
            self.assertEqual(len(area.landmarks), 1)
            self.assertEqual(area.landmarks[0].name, "真菌小屋")
            self.assertEqual(area.landmarks[0].id, "landmark_1_2_0")
            self.assertEqual(area.landmarks[0].features, ["explore"])
            self.assertEqual(area.landmarks[0].npc_name, "老學者")
            self.assertEqual(area.landmarks[0].npc_traits, ["博學"])  # converted from string to list

    async def test_generate_area_failure_returns_none(self):
        mock_llm = MagicMock()
        # Returns invalid response
        mock_llm.call = AsyncMock(return_value="Internal Server Error")
        
        area = await WorldGenerator.generate_area(x=1, y=2, llm_client=mock_llm)
        self.assertIsNone(area)
