import unittest
import os
import shutil
from unittest.mock import MagicMock, AsyncMock, patch
from core.guild import GuildManager
from core.models import QuestSchema, QuestObjective, PrimaryAttributes, CharacterSchema, Vitality, EquipmentSlots

class TestGuild(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Override the board path to a test location
        self.original_board_path = GuildManager.BOARD_PATH
        GuildManager.BOARD_PATH = "world_db/test_guild_board.json"
        
        # Ensure world_db directory exists
        os.makedirs("world_db", exist_ok=True)

    def tearDown(self):
        # Clean up test file
        if os.path.exists(GuildManager.BOARD_PATH):
            os.remove(GuildManager.BOARD_PATH)
        GuildManager.BOARD_PATH = self.original_board_path

    def test_save_and_load_board(self):
        quests = [
            QuestSchema(
                id="Q-test-1", title="擊退哥布林", description="打倒 3 隻哥布林",
                rank_required="E", level_required=1,
                objectives=[QuestObjective(type="kill", target_id="goblin", count=3)],
                rewards={"gold": 50, "exp": 100}
            )
        ]
        GuildManager.save_board(quests)
        
        loaded = GuildManager.load_board()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "Q-test-1")
        self.assertEqual(loaded[0].title, "擊退哥布林")

    @patch("core.guild.GuildManager.generate_daily_quests")
    async def test_refresh_board_if_needed(self, mock_generate):
        # When board file is empty/non-existent
        mock_quests = [QuestSchema(id="Q-mock", title="Mock", description="Mock", rank_required="E")]
        mock_generate.return_value = mock_quests
        
        refreshed = await GuildManager.refresh_board_if_needed(llm_client=None)
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0].id, "Q-mock")

    async def test_generate_daily_quests_ai(self):
        mock_llm = MagicMock()
        # Return a list of 2 quests in JSON so repair_and_parse_json parses it as a list
        mock_llm.call = AsyncMock(return_value='''
        [
            {
                "title": "採集魔光草",
                "description": "採集 5 株魔光草",
                "rank_required": "D",
                "objectives": [{"type": "collect", "target_id": "glow_herb", "count": 5, "location": [2, 2]}],
                "rewards": {}
            },
            {
                "title": "討伐史萊姆",
                "description": "擊殺 3 隻史萊姆",
                "rank_required": "E",
                "objectives": [{"type": "kill", "target_id": "slime", "count": 3, "location": [1, 1]}],
                "rewards": {}
            }
        ]
        ''')
        
        quests = await GuildManager.generate_daily_quests(mock_llm)
        self.assertEqual(len(quests), 2)
        self.assertEqual(quests[0].title, "採集魔光草")
        self.assertEqual(quests[0].rank_required, "D")
        self.assertIn("gold", quests[0].rewards)
        self.assertIn("exp", quests[0].rewards)

    def test_accept_quest(self):
        quest = QuestSchema(
            id="Q-accept", title="Accept Me", description="Desc",
            rank_required="E", slots_left=2
        )
        GuildManager.save_board([quest])
        
        # Accept quest
        success = GuildManager.accept_quest("user1", "Q-accept")
        self.assertTrue(success)
        
        # Load board and check slots_left
        board = GuildManager.load_board()
        self.assertEqual(board[0].slots_left, 1)

        # Accept again (slots = 1)
        success = GuildManager.accept_quest("user1", "Q-accept")
        self.assertTrue(success)
        
        # Accept again (slots = 0) -> Should fail
        success = GuildManager.accept_quest("user1", "Q-accept")
        self.assertFalse(success)

    @patch("core.world.WorldManager.get_difficulty_settings")
    async def test_generate_rumor(self, mock_diff):
        mock_diff.return_value = {"base_level": 5, "tier_name": "文明邊緣"}
        
        character = MagicMock()
        character.total_stats = {"CHA": 12, "WIS": 10}
        
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value="聽說東邊的廢墟裡有巨大的寶箱，但有邪惡的幽靈在守護...")
        
        rumor = await GuildManager.generate_rumor(character, 0, 0, mock_llm)
        self.assertEqual(rumor, "聽說東邊的廢墟裡有巨大的寶箱，但有邪惡的幽靈在守護...")
