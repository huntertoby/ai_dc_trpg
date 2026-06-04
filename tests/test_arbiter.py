import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.arbiter import ArbiterSystem
from core.models import AreaSchema, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots

class TestArbiter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock character schema and character instance
        self.char = MagicMock()
        self.char.data = CharacterSchema(
            character_id="test_char_123", name="卡爾", background="孤兒",
            primary_stats=PrimaryAttributes(STR=15, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], equipment_slots=EquipmentSlots(), location=[0, 0],
            gold=100, reputation=0, known_rumors=[]
        )
        self.char.total_stats = {"STR": 15, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
        
        self.area = AreaSchema(
            id="0,0", name="萬族樞紐", type="city", description="主城", base_level=1
        )
        
        self.event_data = {"prompt_action": "一扇鎖著的石門。"}

    @patch("random.randint")
    @patch("random.random", return_value=0.5)
    async def test_process_action_success_path(self, mock_random, mock_randint):
        mock_llm = MagicMock()
        # 1. DC decision: legal, STR required, DC 10
        # 2. Outcome narrative: reward gold/xp
        mock_llm.call = AsyncMock(side_effect=[
            '{"is_legal": true, "stat_required": "STR", "dc": 10, "fail_reason": ""}',
            '{"narrative": "你用力撞開了石門。", "intervention": {"type": "REWARD_GOLD_XP"}}'
        ])
        
        # roll = 15, modifier for STR = 15 // 5 = 3. Total = 18.
        # DC = 10 + 1 // 5 = 10. Success!
        mock_randint.side_effect = [
            15,  # roll
            30,  # gold reward (range 20 to 50)
            30   # exp reward (constant in formulas or random choice)
        ]
        
        res = await ArbiterSystem.process_action(
            character=self.char,
            area=self.area,
            event_data=self.event_data,
            player_text="我用力撞擊石門",
            llm_client=mock_llm
        )
        
        self.assertTrue(res["success"])
        self.assertEqual(res["res_str"], "成功")
        self.assertEqual(res["narrative"], "你用力撞開了石門。")
        self.assertEqual(res["stat_name"], "STR")
        self.assertEqual(res["roll"], 15)
        self.assertEqual(res["total"], 18)
        
        # Verify character attributes changed
        self.assertEqual(self.char.data.gold, 133)  # 100 + int(30 * 1.1)
        self.char.add_exp.assert_called_with(33)  # int(30 * 1.1)
        self.char.save.assert_called()
        self.char.add_trpg_event.assert_called_once()
        self.char.add_log.assert_called_once()

    @patch("random.randint")
    async def test_process_action_illegal_action(self, mock_randint):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value='{"is_legal": false, "stat_required": "", "dc": 0, "fail_reason": "動作太過荒謬。"}')
        
        res = await ArbiterSystem.process_action(
            character=self.char,
            area=self.area,
            event_data=self.event_data,
            player_text="我要飛上天去天界",
            llm_client=mock_llm
        )
        
        self.assertFalse(res["success"])
        self.assertFalse(res["is_legal"])
        self.assertEqual(res["fail_reason"], "動作太過荒謬。")
        self.char.save.assert_not_called()

    @patch("random.randint")
    @patch("random.random", return_value=0.5)
    async def test_process_action_failure_path(self, mock_random, mock_randint):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(side_effect=[
            '{"is_legal": true, "stat_required": "DEX", "dc": 15, "fail_reason": ""}',
            '{"narrative": "你試圖撬鎖卻折斷了鐵絲，還被陷阱刺傷。", "intervention": {"type": "COST_DEBUFF", "flavor": "手部刺傷", "details": "DEX"}}'
        ])
        
        # roll = 5, DEX = 10 -> mod = 2. Total = 7.
        # DC = 15 + 0 = 15. Fail!
        mock_randint.side_effect = [
            5,  # roll
            12  # HP loss (range 10 to 20)
        ]
        
        res = await ArbiterSystem.process_action(
            character=self.char,
            area=self.area,
            event_data=self.event_data,
            player_text="我用鐵絲撬鎖",
            llm_client=mock_llm
        )
        
        self.assertTrue(res["success"])
        self.assertEqual(res["res_str"], "失敗")
        
        # Verify character lost HP
        self.assertEqual(self.char.data.vitality.hp, 88)  # 100 - 12
        self.char.save.assert_called()
        self.char.add_trpg_event.assert_called_once()
        self.char.add_log.assert_called_once()
