from typing import Any, Optional, Dict

class ActionContext:
    def __init__(
        self,
        accuracy: float = 0.95,
        evasion_rate: float = 0.05,
        crit_rate: float = 0.05,
        damage_multiplier: float = 1.0,
        defense_ignore_ratio: float = 0.0,
        is_absolute_hit: bool = False,
        is_crit: bool = False,
        raw_damage: float = 0.0,
        final_damage: float = 0.0,
        damage_type: str = "physical",
        combat_context: Optional[Any] = None
    ):
        self.accuracy = accuracy
        self.evasion_rate = evasion_rate
        self.crit_rate = crit_rate
        self.damage_multiplier = damage_multiplier
        self.defense_ignore_ratio = defense_ignore_ratio
        self.is_absolute_hit = is_absolute_hit
        self.is_crit = is_crit
        self.raw_damage = raw_damage
        self.final_damage = final_damage
        self.damage_type = damage_type
        self.combat_context = combat_context
        # Extra custom flags or properties can be stored here
        self.extra_flags: Dict[str, Any] = {}

class DiceContext:
    def __init__(
        self,
        dice_str: str,
        roll_value: Optional[int] = None,
        roll_modifier: int = 0,
        floor_value: Optional[int] = None,
        reroll_threshold: Optional[int] = None,
        caster: Optional[Any] = None,
        combat_context: Optional[Any] = None
    ):
        self.dice_str = dice_str
        self.roll_value = roll_value
        self.roll_modifier = roll_modifier
        self.floor_value = floor_value
        self.reroll_threshold = reroll_threshold
        self.caster = caster
        self.combat_context = combat_context
        self.extra_flags: Dict[str, Any] = {}
