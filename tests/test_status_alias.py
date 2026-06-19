import unittest
from unittest.mock import MagicMock
from core.constants import STATUS_REGISTRY, normalize_status_name
from core.models import Equipment, StatusEffect, Skill, CharacterSchema, Vitality
from core.combat_utils import add_entity_status_effect, has_status, get_status_effect
from core.combat import CombatManager

class TestStatusAlias(unittest.TestCase):
    def setUp(self):
        # Ensure Void_Burn is cleared from aliases before each test
        if "Void_Burn" in STATUS_REGISTRY["Bleed"]["aliases"]:
            STATUS_REGISTRY["Bleed"]["aliases"].remove("Void_Burn")

    def tearDown(self):
        # Clean up Void_Burn from aliases
        if "Void_Burn" in STATUS_REGISTRY["Bleed"]["aliases"]:
            STATUS_REGISTRY["Bleed"]["aliases"].remove("Void_Burn")

    def test_pydantic_dynamic_registration_via_equipment(self):
        # 1. Verify initially "Void_Burn" does not normalize to "Bleed"
        self.assertNotEqual(normalize_status_name("Void_Burn"), "Bleed")

        # 2. Instantiate Equipment with a custom status trigger
        eq_json = {
            "name": "裂魂斬擊之刃",
            "slot_type": "main_hand",
            "tier": "T1",
            "executable_triggers": [
                {
                    "event": "on_hit",
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "target": "target",
                            "status_name": "Void_Burn",
                            "custom_status_name": "Void_Burn",
                            "canonical_status": "Bleed",
                            "duration": 3,
                            "dot_damage_flat": 25.0
                        }
                    ]
                }
            ]
        }
        
        eq = Equipment.model_validate(eq_json)

        # 3. Verify that after parsing, "Void_Burn" is registered to "Bleed" aliases
        self.assertIn("Void_Burn", STATUS_REGISTRY["Bleed"]["aliases"])
        self.assertEqual(normalize_status_name("Void_Burn"), "Bleed")

    def test_add_entity_status_effect_preserves_custom_name(self):
        # Ensure registered
        if "Void_Burn" not in STATUS_REGISTRY["Bleed"]["aliases"]:
            STATUS_REGISTRY["Bleed"]["aliases"].append("Void_Burn")

        target = {"status_effects": [], "name": "敵對目標", "hp": 100, "max_hp": 100}
        
        # Add the effect with the custom name
        add_entity_status_effect(
            target,
            "Void_Burn",
            "虛空燃燒 Dot",
            3,
            dot_damage_flat=25.0,
            custom_status_name="Void_Burn",
            canonical_status="Bleed"
        )

        # The status effect name must remain "Void_Burn"
        self.assertEqual(target["status_effects"][0]["name"], "Void_Burn")
        
        # It must be detected as Bleed (canonical checks)
        self.assertTrue(has_status(target, "Bleed"))
        self.assertTrue(has_status(target, "Void_Burn"))
        
        effect = get_status_effect(target, "Bleed")
        self.assertIsNotNone(effect)
        self.assertEqual(effect["name"], "Void_Burn")

    def test_dot_tick_uses_custom_name_in_logs(self):
        if "Void_Burn" not in STATUS_REGISTRY["Bleed"]["aliases"]:
            STATUS_REGISTRY["Bleed"]["aliases"].append("Void_Burn")

        # Create dummy character schemas wrapped in MagicMock
        caster = MagicMock()
        caster.data = CharacterSchema(
            character_id="c1", name="冒險者", background="背景",
            vitality=Vitality(hp=100, max_hp=100, mp=50, max_mp=50)
        )
        caster.total_stats = {"DEX": 10}
        
        target = {
            "name": "哥布林",
            "hp": 100,
            "max_hp": 100,
            "status_effects": [],
            "speed": 10
        }

        # Apply Void_Burn to target
        add_entity_status_effect(
            target,
            "Void_Burn",
            "虛空燃燒 Dot",
            3,
            dot_damage_flat=25.0,
            custom_status_name="Void_Burn",
            canonical_status="Bleed"
        )

        # Run combat turn tick and check logs
        combat = CombatManager(caster, [target])
        
        # Process tick for target
        finished, logs_str = combat._process_entity_status_tick(target, is_player=False)
        
        # The logs should say "Void_Burn DoT" instead of "流血 DoT"
        self.assertIn("受到Void_Burn DoT，扣除 25 點生命值！", logs_str)
        self.assertNotIn("受到流血 DoT", logs_str)
