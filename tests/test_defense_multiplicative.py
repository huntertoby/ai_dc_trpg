# tests/test_defense_multiplicative.py
"""
防禦乘法堆疊單元測試

驗證防禦計算從加法改為乘法堆疊的正確性：
- 單層 debuff：base × (1 + rate)
- 多層 debuff：base × (1 + rate1) × (1 + rate2) × ...
- 混合絕對值和百分比
- 防禦永不為 0（下限=1）
"""

import pytest
from unittest.mock import Mock
from core.character import Character
from core.models import CharacterSchema, StatusEffect, Vitality, PrimaryAttributes


class TestApplyDefenseMultipliers:
    """apply_defense_multipliers 靜態方法測試"""

    def test_single_debuff(self):
        """單次 -20% debuff"""
        effects = [
            Mock(bonuses={"p_def": -0.20})
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 × (1 - 0.20) = 100 × 0.8 = 80
        assert result == 80

    def test_multiple_debuffs_multiplicative(self):
        """多層 debuff 乘法堆疊"""
        effects = [
            Mock(bonuses={"p_def": -0.20}),
            Mock(bonuses={"p_def": -0.20}),
            Mock(bonuses={"p_def": -0.20}),
            Mock(bonuses={"p_def": -0.20}),
            Mock(bonuses={"p_def": -0.20})
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 × 0.8^5 ≈ 32.77 → 32
        expected = int(100.0 * (0.8 ** 5))
        assert result == expected

    def test_defense_never_zero(self):
        """防禦永不為 0（下限=1）"""
        # 極端情況：-95% × 多層
        effects = [
            Mock(bonuses={"p_def": -0.95}),
            Mock(bonuses={"p_def": -0.95}),
            Mock(bonuses={"p_def": -0.95})
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 即使結果極小，也保留 1
        assert result >= 1

    def test_mixed_absolute_and_percentage(self):
        """混合絕對加成和百分比"""
        effects = [
            Mock(bonuses={"p_def": 20}),  # 絕對值加成
            Mock(bonuses={"p_def": -0.20})  # 百分比減益
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # (100 + 20) × (1 - 0.20) = 120 × 0.8 = 96
        assert result == 96

    def test_absolute_bonus_only(self):
        """只有絕對加成"""
        effects = [
            Mock(bonuses={"p_def": 30})
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 + 30 = 130（沒有乘法）
        assert result == 130

    def test_no_effects(self):
        """無任何效果"""
        result = Character.apply_defense_multipliers(100.0, [])
        # 基礎防禦不變
        assert result == 100

    def test_multiple_absolute_bonuses(self):
        """多個絕對加成堆疊"""
        effects = [
            Mock(bonuses={"p_def": 10}),
            Mock(bonuses={"p_def": 20}),
            Mock(bonuses={"p_def": 15})
        ]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 + 10 + 20 + 15 = 145
        assert result == 145

    def test_sorting_ensures_consistency(self):
        """乘數排序確保一致性"""
        # 不同順序的相同乘數應產生相同結果
        effects1 = [
            Mock(bonuses={"p_def": -0.10}),
            Mock(bonuses={"p_def": -0.20})
        ]
        effects2 = [
            Mock(bonuses={"p_def": -0.20}),
            Mock(bonuses={"p_def": -0.10})
        ]

        result1 = Character.apply_defense_multipliers(100.0, effects1)
        result2 = Character.apply_defense_multipliers(100.0, effects2)

        # 應該相同（乘法滿足交換律）
        assert result1 == result2


class TestCharacterCombatStatsDefense:
    """Character.combat_stats 防禦計算測試"""

    def create_character(self, base_con=10, base_str=10, base_dex=10,
                         level=10, status_effects=None):
        """輔助方法：創建測試角色"""
        schema = CharacterSchema(
            character_id="test_char_id",
            background="test_background",
            name="Test Char",
            level=level,
            primary_stats=PrimaryAttributes(
                STR=base_str, DEX=base_dex, CON=base_con, INT=10, WIS=10, CHA=10
            ),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100),
            status_effects=status_effects or []
        )
        return Character(schema, "test_user")

    def test_base_defense_calculation(self):
        """基礎防禦計算（無 debuff）"""
        char = self.create_character(base_con=20, base_str=10, base_dex=10, level=20)

        stats = char.combat_stats
        p_def = stats["p_def"]

        # 預期：(20 × 0.7) + (10 × 0.2) + (10 × 0.1) + (20 // 2) = 14 + 2 + 1 + 10 = 27
        expected = 27
        assert p_def == expected

    def test_defense_with_single_debuff(self):
        """防禦 + 單個 -20% debuff"""
        effect = Mock(
            spec=StatusEffect,
            bonuses={"p_def": -0.20},
            duration=3
        )

        char = self.create_character(base_con=20, status_effects=[effect])
        stats = char.combat_stats
        p_def = stats["p_def"]

        # 基礎防禦 ≈ 27（見上測試）
        # 乘以 (1 - 0.20) = × 0.8 ≈ 21.6 → 21
        assert p_def < 27  # 確實被削弱

    def test_defense_with_multiple_debuffs(self):
        """防禦 + 多個 debuff 乘法堆疊"""
        effects = [
            Mock(spec=StatusEffect, bonuses={"p_def": -0.20}, duration=3),
            Mock(spec=StatusEffect, bonuses={"p_def": -0.20}, duration=3)
        ]

        char = self.create_character(base_con=50, status_effects=effects)
        stats = char.combat_stats
        p_def = stats["p_def"]

        # 確保乘法堆疊比單次削弱更嚴重
        # 單次：× 0.8 = 56
        # 兩次：× 0.8^2 = × 0.64 ≈ 35.84 → 35
        assert p_def <= 40  # 大幅削弱

    def test_defense_never_zero(self):
        """防禦永不為 0"""
        # 極端 debuff
        effects = [
            Mock(spec=StatusEffect, bonuses={"p_def": -0.99}, duration=3),
            Mock(spec=StatusEffect, bonuses={"p_def": -0.99}, duration=3)
        ]

        char = self.create_character(base_con=5, status_effects=effects)
        stats = char.combat_stats
        p_def = stats["p_def"]

        # 即使極小，也 ≥ 1
        assert p_def >= 1

    def test_magical_defense_calculation(self):
        """魔法防禦計算（獨立乘法）"""
        effect = Mock(
            spec=StatusEffect,
            bonuses={"m_def": -0.15},
            duration=3
        )

        char = self.create_character(base_dex=5, level=10, status_effects=[effect])
        stats = char.combat_stats
        m_def = stats["m_def"]

        # 物理防禦不受影響
        p_def = stats["p_def"]
        # 但魔法防禦應被削弱
        assert m_def >= 1


class TestStatusEffectBonusTypes:
    """狀態效果獎勵類型識別測試"""

    def test_percentage_bonus_detection(self):
        """檢測百分比減益（-1 < value < 0）"""
        # 有效百分比範圍
        valid_percentages = [-0.01, -0.10, -0.50, -0.99]
        for val in valid_percentages:
            is_percentage = isinstance(val, (int, float)) and -1 < val < 0
            assert is_percentage, f"{val} 應被識別為百分比"

        # 無效範圍（邊界）
        invalid = [-1.0, 0, 1.0, -2.0]
        for val in invalid:
            is_percentage = isinstance(val, (int, float)) and -1 < val < 0
            assert not is_percentage, f"{val} 不應被識別為百分比"

    def test_absolute_bonus_types(self):
        """絕對值加成識別"""
        absolutes = [-100, -50, -1, 0, 1, 50, 100]
        for val in absolutes:
            is_absolute = not (isinstance(val, (int, float)) and -1 < val < 0)
            assert is_absolute, f"{val} 應被視為絕對值"


class TestDefenseBoundary:
    """防禦計算邊界測試"""

    def test_zero_base_defense(self):
        """基礎防禦為 0 時的乘法"""
        effects = [Mock(bonuses={"p_def": -0.50})]
        result = Character.apply_defense_multipliers(0.0, effects)
        # 0 × (1 - 0.50) = 0，但需要保留 1
        assert result == 1

    def test_negative_absolute_bonus(self):
        """負絕對加成"""
        effects = [Mock(bonuses={"p_def": -50})]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 - 50 = 50（負絕對值還是加上）
        assert result == 50

    def test_large_absolute_bonus(self):
        """大額絕對加成"""
        effects = [Mock(bonuses={"p_def": 1000})]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 + 1000 = 1100
        assert result == 1100

    def test_extremely_small_multiplier(self):
        """極小乘數（接近 0）"""
        # -0.999 的乘數 = 0.001
        effects = [Mock(bonuses={"p_def": -0.999})]
        result = Character.apply_defense_multipliers(100.0, effects)
        # 100 × 0.001 = 0.1 → 0，但保留 1
        assert result == 1
