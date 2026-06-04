import unittest
from core import constants

class TestConstants(unittest.TestCase):
    def test_rank_order(self):
        self.assertIn("E", constants.RANK_ORDER)
        self.assertIn("S", constants.RANK_ORDER)
        self.assertEqual(constants.RANK_ORDER["E"], 0)
        self.assertEqual(constants.RANK_ORDER["S"], 5)

    def test_rank_colors(self):
        self.assertEqual(len(constants.RANK_COLORS), len(constants.RANK_ORDER))
        self.assertIn("E", constants.RANK_COLORS)

    def test_weapon_types(self):
        self.assertIn("長劍", constants.WEAPON_TYPES)
        self.assertEqual(constants.WEAPON_TYPES["長劍"], "STR")
        self.assertEqual(constants.WEAPON_TYPES["法杖"], "INT")

    def test_base_jobs(self):
        self.assertIn("戰士", constants.BASE_JOBS)
        self.assertGreater(len(constants.BASE_JOBS), 10)

    def test_skill_keywords(self):
        self.assertIn("Pierce", constants.SKILL_KEYWORDS)
        self.assertIn("Shield", constants.SKILL_KEYWORDS)

    def test_keyword_translations(self):
        self.assertEqual(constants.KEYWORD_TRANSLATIONS["Pierce"], "穿透")
        self.assertEqual(constants.KEYWORD_TRANSLATIONS["Shield"], "護盾")

    def test_base_races(self):
        self.assertIn("人類", constants.BASE_RACES)

    def test_stat_translations(self):
        self.assertEqual(constants.STAT_TRANSLATIONS["STR"], "力量")
        self.assertEqual(constants.STAT_TRANSLATIONS["CON"], "體質")
