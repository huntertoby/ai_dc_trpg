import unittest
from unittest.mock import MagicMock, AsyncMock
from core.item_generator import generate_equipment_by_ai
from core.models import Equipment

class TestItemGenerator(unittest.IsolatedAsyncioTestCase):
    async def test_generate_equipment_by_ai_success(self):
        mock_llm = MagicMock()
        # Mock JSON response from LLM
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "灰燼之手",
            "description": "被火焰灼燒過的手套",
            "slot_type": "hands",
            "tier": "T4",
            "item_level": 5,
            "bonuses": {
                "CON": 15.0,
                "DEX": 5.0
            }
        }
        ''')

        eq = await generate_equipment_by_ai(
            description="火焰手套",
            item_level=5,
            tier="T4",
            slot_type="hands",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "灰燼之手")
        self.assertEqual(eq.slot_type, "hands")
        self.assertEqual(eq.tier, "T4")
        self.assertEqual(eq.item_level, 5)
        # Should be clamped/validated (CON / DEX should be scaled based on T4 budget)
        # Verify that it returned an Equipment object
        self.assertIsInstance(eq, Equipment)

    async def test_generate_weapon_defaults_type(self):
        mock_llm = MagicMock()
        # Return a weapon JSON but WITHOUT weapon_type
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "神秘法劍",
            "description": "蘊含奧術力量的單手劍",
            "slot_type": "main_hand",
            "tier": "T3",
            "item_level": 10,
            "bonuses": {
                "INT": 15.0
            }
        }
        ''')

        eq = await generate_equipment_by_ai(
            description="法術劍",
            item_level=10,
            tier="T3",
            slot_type="main_hand",
            llm_client=mock_llm
        )

        self.assertIsNotNone(eq)
        self.assertEqual(eq.name, "神秘法劍")
        # Since INT is higher than STR, weapon_type should fall back/default to "法杖"
        self.assertEqual(eq.weapon_type, "法杖")
