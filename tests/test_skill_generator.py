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
        mock_llm.call = AsyncMock()
        mock_llm.call.side_effect = [
            # Stage 1 Response
            '''
            {
                "skill_type": "active",
                "bonuses": null,
                "action_type": "damage",
                "target_type": "aoe",
                "base_stat": "INT",
                "is_magical": true,
                "template_choices": [{"template_id": "active_burn"}],
                "targeting_modifier": null,
                "synergy_requirement": null,
                "execution_mode": "immediate",
                "cost_preference": "standard",
                "evolution_threshold": null,
                "tags": ["Fire"],
                "reactive_trigger": null,
                "allowed_jobs": ["巫師"]
            }
            ''',
            # Stage 2 Response
            '''
            {
                "name": "烈焰風暴",
                "description": "召喚烈焰焚燒敵人",
                "narrative_effect": "烈焰沖天"
            }
            '''
        ]
        
        skill = await generate_single_skill(
            description="召喚大範圍火柱",
            tier="T3",
            llm_client=mock_llm,
            kw_count=1
        )
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "烈焰風暴")
        self.assertEqual(skill.tier, "T3")
        self.assertEqual(skill.mechanics.action_type, "damage")
        self.assertEqual(skill.mechanics.target_type, "aoe")
        self.assertIsInstance(skill, Skill)

    async def test_generate_starter_skills(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock()
        mock_llm.call.side_effect = [
            # Stage 1 Response
            '''
            {
                "skills": [
                    {
                        "skill_type": "active",
                        "bonuses": null,
                        "tier": "T5",
                        "action_type": "damage",
                        "target_type": "single",
                        "base_stat": "STR",
                        "is_magical": false,
                        "template_choices": [],
                        "targeting_modifier": null,
                        "synergy_requirement": null,
                        "execution_mode": "immediate",
                        "cost_preference": "standard",
                        "evolution_threshold": null,
                        "tags": ["Physical"],
                        "allowed_jobs": ["戰士"]
                    },
                    {
                        "skill_type": "active",
                        "bonuses": null,
                        "tier": "T5",
                        "action_type": "buff",
                        "target_type": "self",
                        "base_stat": "CON",
                        "is_magical": false,
                        "template_choices": [],
                        "targeting_modifier": null,
                        "synergy_requirement": null,
                        "execution_mode": "immediate",
                        "cost_preference": "standard",
                        "evolution_threshold": null,
                        "tags": ["Defense"],
                        "allowed_jobs": ["戰士"]
                    },
                    {
                        "skill_type": "active",
                        "bonuses": null,
                        "tier": "T4",
                        "action_type": "damage",
                        "target_type": "single",
                        "base_stat": "STR",
                        "is_magical": false,
                        "template_choices": [{"template_id": "active_bleed"}],
                        "targeting_modifier": null,
                        "synergy_requirement": null,
                        "execution_mode": "immediate",
                        "cost_preference": "heavy",
                        "evolution_threshold": null,
                        "tags": ["Physical"],
                        "allowed_jobs": ["戰士"]
                    }
                ]
            }
            ''',
            # Stage 2 Response
            '''
            {
                "skills": [
                    {
                        "name": "重擊",
                        "description": "全力的一擊",
                        "narrative_effect": "造成強力打擊"
                    },
                    {
                        "name": "格擋",
                        "description": "架起武器格擋攻擊",
                        "narrative_effect": "防禦力提升"
                    },
                    {
                        "name": "撕裂斬",
                        "description": "蓄力撕裂傷口",
                        "narrative_effect": "使目標流血"
                    }
                ]
            }
            '''
        ]
        
        char_data = {"name": "卡爾", "job_name": "戰士", "background": "雇傭兵"}
        skills = await generate_starter_skills(char_data, mock_llm, t4_kw_count=1)
        self.assertEqual(len(skills), 3)
        self.assertEqual(skills[0].name, "重擊")
        self.assertEqual(skills[0].tier, "T5")
        self.assertEqual(skills[2].name, "撕裂斬")
        self.assertEqual(skills[2].tier, "T4")
        self.assertEqual(skills[2].mechanics.keywords, ["Bleed"])

    async def test_generate_t1_skill_with_triggers(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock()
        mock_llm.call.side_effect = [
            # Stage 1 Response
            '''
            {
                "skill_type": "active",
                "bonuses": null,
                "action_type": "damage",
                "target_type": "single",
                "base_stat": "INT",
                "is_magical": true,
                "template_choices": [
                    {"template_id": "active_sacrifice"},
                    {"template_id": "active_lifesteal"},
                    {"template_id": "active_multihit"}
                ],
                "targeting_modifier": null,
                "synergy_requirement": null,
                "execution_mode": "immediate",
                "cost_preference": "heavy",
                "evolution_threshold": null,
                "tags": ["Chaos"],
                "reactive_trigger": null,
                "allowed_jobs": ["死靈法師"]
            }
            ''',
            # Stage 2 Response
            '''
            {
                "name": "末日審判",
                "description": "天基打擊",
                "narrative_effect": "世界末日"
            }
            '''
        ]

        skill = await generate_single_skill(
            description="末日審判",
            tier="T1",
            llm_client=mock_llm,
            kw_count=3
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "末日審判")
        self.assertEqual(skill.tier, "T1")
        self.assertEqual(len(skill.executable_triggers), 0)

    async def test_generate_non_t1_skill_clears_triggers(self):
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock()
        mock_llm.call.side_effect = [
            # Stage 1 Response
            '''
            {
                "skill_type": "active",
                "bonuses": null,
                "action_type": "damage",
                "target_type": "single",
                "base_stat": "INT",
                "is_magical": true,
                "template_choices": [
                    {"template_id": "active_burn"}
                ],
                "targeting_modifier": null,
                "synergy_requirement": null,
                "execution_mode": "immediate",
                "cost_preference": "standard",
                "evolution_threshold": null,
                "tags": ["Fire"],
                "reactive_trigger": null,
                "allowed_jobs": ["巫師"]
            }
            ''',
            # Stage 2 Response
            '''
            {
                "name": "火球術",
                "description": "發射火球",
                "narrative_effect": "發射一顆火球"
            }
            '''
        ]

        skill = await generate_single_skill(
            description="火球術",
            tier="T4",
            llm_client=mock_llm,
            kw_count=1
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill.tier, "T4")
        self.assertEqual(skill.executable_triggers, [])

    async def test_generate_passive_skill(self):
        # 測試被動技能的消耗、公式與屬性加成限制
        mock_llm = MagicMock()
        mock_llm.call = AsyncMock()
        mock_llm.call.side_effect = [
            # Stage 1 Response
            '''
            {
                "skill_type": "passive",
                "bonuses": {
                    "STR": 12.0,
                    "crit_rate": 0.07,
                    "p_def": 15.0
                },
                "action_type": "buff",
                "target_type": "self",
                "base_stat": "STR",
                "is_magical": false,
                "template_choices": [],
                "targeting_modifier": null,
                "synergy_requirement": null,
                "execution_mode": "immediate",
                "cost_preference": "zero",
                "evolution_threshold": null,
                "tags": ["Physical"],
                "reactive_trigger": null,
                "allowed_jobs": ["戰士"]
            }
            ''',
            # Stage 2 Response
            '''
            {
                "name": "鋼鐵巨力",
                "description": "常駐提升肉體力量與防禦",
                "narrative_effect": "常駐提升力量 10 點、爆擊率 5% 與物理防禦 10 點"
            }
            '''
        ]

        skill = await generate_single_skill(
            description="肉體硬化",
            tier="T3",
            llm_client=mock_llm,
            kw_count=0
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill.skill_type, "passive")
        self.assertEqual(skill.name, "鋼鐵巨力")
        # 被動技能無消耗
        self.assertEqual(skill.mechanics.cost, {})
        # 被動技能公式 dice 應被強制為 "0"
        self.assertEqual(skill.mechanics.formula.dice, "0")
        # 驗證屬性加成是否受到 T3 限制的 Clamp (T3 Limit: primary=10.0, rate=0.05, defense=10.0)
        self.assertEqual(skill.bonuses["STR"], 10.0)
        self.assertEqual(skill.bonuses["crit_rate"], 0.05)
        self.assertEqual(skill.bonuses["p_def"], 10.0)
