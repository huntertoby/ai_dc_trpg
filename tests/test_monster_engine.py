import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.monster_engine import MonsterRank, MonsterEngine
from core.models import AreaSchema

class TestMonsterEngine(unittest.IsolatedAsyncioTestCase):
    def test_roll_rank(self):
        # 1. Standard roll
        rank = MonsterRank.roll_rank(threat_level=0.0)
        self.assertIn(rank["name"], ["普通", "精英", "稀有", "史詩", "頭目"])
        
        # 2. High threat roll
        rank_high = MonsterRank.roll_rank(threat_level=50.0)
        self.assertIn(rank_high["name"], ["普通", "精英", "稀有", "史詩", "頭目"])

    @patch("random.choices", return_value=[MonsterRank.COMMON])
    @patch("random.random", return_value=0.01) # Force novelty
    @patch("random.choice", return_value="狼人")
    async def test_generate_single_monster_novelty(self, mock_choice, mock_random, mock_choices):
        area = AreaSchema(
            id="1,1", name="黑森林", type="wilderness", description="森林",
            base_level=3, threat_level=1.0, dominant_species=["狼人"],
            discovered_variants=[]
        )
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value='{"name": "嗜血的狼人", "trait": "夜間攻擊力倍增"}')

        monster = await MonsterEngine._generate_single_monster(area, mock_llm, novelty_chance=0.5)
        self.assertIsNotNone(monster)
        self.assertEqual(monster["base_name"], "嗜血的狼人")
        self.assertEqual(monster["trait"], "夜間攻擊力倍增")
        self.assertEqual(monster["level"], 3)
        self.assertEqual(monster["rank"], "普通")
        
        # Check basic stats scaling
        # hp = int((60 + 3*15) * 1.0) = 105
        self.assertEqual(monster["hp"], 105)
        # Check that it got saved into discovered_variants
        self.assertEqual(len(area.discovered_variants), 1)
        self.assertEqual(area.discovered_variants[0]["name"], "嗜血的狼人")

    @patch("random.choices", return_value=[MonsterRank.COMMON])
    @patch("random.random", return_value=0.99) # Avoid novelty
    @patch("random.choice")
    async def test_generate_single_monster_existing(self, mock_choice, mock_random, mock_choices):
        area = AreaSchema(
            id="1,1", name="黑森林", type="wilderness", description="森林",
            base_level=3, threat_level=1.0, dominant_species=["狼人"],
            discovered_variants=[{"name": "殘缺的野狼", "trait": "斷肢", "rank": "普通"}]
        )
        mock_choice.side_effect = lambda x: x[0]

        monster = await MonsterEngine._generate_single_monster(area, llm_client=None, novelty_chance=0.1)
        self.assertEqual(monster["base_name"], "殘缺的野狼")
        self.assertEqual(monster["trait"], "斷肢")

    @patch("core.monster_engine.MonsterEngine._generate_single_monster")
    async def test_generate_monster_group(self, mock_generate_single):
        area = AreaSchema(
            id="1,1", name="黑森林", type="wilderness", description="森林",
            base_level=3, threat_level=1.0, dominant_species=["狼人"]
        )
        mock_generate_single.return_value = {"name": "狼"}
        
        monsters = await MonsterEngine.generate_monster_group(area, llm_client=None)
        self.assertGreaterEqual(len(monsters), 1)
        self.assertLessEqual(len(monsters), 3)
        self.assertEqual(monsters[0]["name"], "狼")
