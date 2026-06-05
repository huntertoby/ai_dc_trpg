import unittest
from unittest.mock import MagicMock, AsyncMock
from core.skill_generator import fix_skill_structure, get_tier_rules, generate_single_skill, generate_starter_skills
from core.models import Skill

class TestSkillGenerator(unittest.IsolatedAsyncioTestCase):
    def test_fix_skill_structure(self):
        raw = {
            "name": "火球術",
            "tier": 4,
            "action_type": "damage",
            "target_type": "single",
            "cost": {"MP": 10},
            "formula": {"type": "multiplier", "base_stat": "INT", "dice": "1d10", "divisor": 12.0}
        }
        fixed = fix_skill_structure(raw)
        self.assertEqual(fixed["name"], "火球術")
        self.assertEqual(fixed["tier"], "T4")
        self.assertIn("mechanics", fixed)
        self.assertEqual(fixed["mechanics"]["action_type"], "damage")
        self.assertEqual(fixed["mechanics"]["formula"]["base_stat"], "INT")

    def test_get_tier_rules(self):
        rules_t1 = get_tier_rules("T1")
        self.assertIn("T1 傳說", rules_t1)
        rules_t5 = get_tier_rules("T5")
        self.assertIn("T5 基礎招式", rules_t5)

    async def test_generate_single_skill(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "烈焰風暴",
            "description": "召喚烈焰焚燒敵人",
            "tier": "T3",
            "action_type": "damage",
            "target_type": "aoe",
            "cost": {"MP": 20},
            "formula": { "type": "multiplier", "base_stat": "INT", "dice": "1d20", "divisor": 15.0 },
            "keywords": ["Burn"],
            "custom_logic": "",
            "narrative_effect": "烈焰沖天"
        }
        ''')
        
        skill = await generate_single_skill(
            description="召喚大範圍火柱",
            tier="T3",
            llm_client=mock_llm
        )
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "烈焰風暴")
        self.assertEqual(skill.tier, "T3")
        self.assertEqual(skill.mechanics.action_type, "damage")
        self.assertEqual(skill.mechanics.target_type, "aoe")
        self.assertIsInstance(skill, Skill)

    async def test_generate_starter_skills(self):
        mock_llm = MagicMock()
        # Generates a list of 3 skills
        mock_llm.call = AsyncMock(return_value='''
        [
            {
                "name": "重擊",
                "description": "全力的一擊",
                "tier": "T5",
                "action_type": "damage",
                "target_type": "single",
                "cost": {"MP": 5},
                "formula": { "type": "multiplier", "base_stat": "STR", "dice": "1d6", "divisor": 15.0 }
            },
            {
                "name": "格擋",
                "description": "架起武器格擋攻擊",
                "tier": "T5",
                "action_type": "buff",
                "target_type": "self",
                "cost": {"MP": 5},
                "formula": { "type": "multiplier", "base_stat": "CON", "dice": "1d6", "divisor": 15.0 }
            },
            {
                "name": "破甲擊",
                "description": "蓄力擊破防禦",
                "tier": "T4",
                "action_type": "damage",
                "target_type": "single",
                "cost": {"MP": 15},
                "formula": { "type": "multiplier", "base_stat": "STR", "dice": "2d6", "divisor": 12.0 },
                "keywords": ["Sunder"]
            }
        ]
        ''')
        
        char_data = {"name": "卡爾", "job_name": "戰士", "background": "雇傭兵"}
        skills = await generate_starter_skills(char_data, mock_llm)
        self.assertEqual(len(skills), 3)
        self.assertEqual(skills[0].name, "重擊")
        self.assertEqual(skills[0].tier, "T5")
        self.assertEqual(skills[2].name, "破甲擊")
        self.assertEqual(skills[2].tier, "T4")
        self.assertEqual(skills[2].mechanics.keywords, ["Sunder"])

    async def test_generate_t1_skill_with_triggers(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "末日審判",
            "description": "天基打擊",
            "tier": "T1",
            "action_type": "damage",
            "target_type": "single",
            "cost": {"MP": 100},
            "formula": { "type": "multiplier", "base_stat": "INT", "dice": "2d10", "divisor": 5.0 },
            "keywords": ["Sacrifice", "Lifesteal", "Multi-hit"],
            "custom_logic": "造成毀滅性打擊",
            "narrative_effect": "世界末日",
            "executable_triggers": [
                {
                    "event": "on_prepare",
                    "actions": [
                        {
                            "action_type": "set_flag",
                            "param": "is_absolute_hit",
                            "param_value": true
                        }
                    ]
                }
            ]
        }
        ''')

        skill = await generate_single_skill(
            description="末日審判",
            tier="T1",
            llm_client=mock_llm
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "末日審判")
        self.assertEqual(skill.tier, "T1")
        self.assertEqual(len(skill.executable_triggers), 1)
        self.assertEqual(skill.executable_triggers[0]["event"], "on_prepare")
        self.assertEqual(skill.executable_triggers[0]["actions"][0]["action_type"], "set_flag")
        self.assertEqual(skill.executable_triggers[0]["actions"][0]["param_value"], True)

    async def test_generate_non_t1_skill_clears_triggers(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock(return_value='''
        {
            "name": "火球術",
            "description": "發射火球",
            "tier": "T4",
            "action_type": "damage",
            "target_type": "single",
            "cost": {"MP": 15},
            "formula": { "type": "multiplier", "base_stat": "INT", "dice": "1d10", "divisor": 12.0 },
            "keywords": ["Burn"],
            "custom_logic": "",
            "narrative_effect": "",
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [{"action_type": "inflict_damage"}]
                }
            ]
        }
        ''')

        skill = await generate_single_skill(
            description="火球術",
            tier="T4",
            llm_client=mock_llm
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill.tier, "T4")
        self.assertEqual(skill.executable_triggers, [])
