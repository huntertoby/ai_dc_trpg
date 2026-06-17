import unittest
from core.compiler import TriggerCompiler
from core.trigger_templates import assemble_trigger
from core.contexts import DiceContext, ActionContext
from core.trigger_engine import TriggerEngine
from unittest.mock import MagicMock

class TestNewTemplates(unittest.TestCase):
    def test_on_dice_modify_compilation(self):
        # 1. Test assemble_trigger
        raw_trig = assemble_trigger("on_dice_modify", {
            "param": "roll_modifier",
            "param_value": 5
        })
        self.assertEqual(raw_trig["event"], "on_dice")
        self.assertEqual(raw_trig["actions"][0]["action_type"], "modify_dice")
        self.assertEqual(raw_trig["actions"][0]["param"], "roll_modifier")
        self.assertEqual(raw_trig["actions"][0]["param_value"], 5)

        # 2. Test TriggerCompiler
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_dice")
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "modify_dice")
        self.assertEqual(compiled[0]["actions"][0]["param"], "roll_modifier")
        self.assertEqual(compiled[0]["actions"][0]["param_value"], 5)

    def test_on_dice_reroll_compilation(self):
        raw_trig = assemble_trigger("on_dice_reroll", {
            "param_value": 3
        })
        self.assertEqual(raw_trig["event"], "on_dice")
        self.assertEqual(raw_trig["actions"][0]["action_type"], "modify_dice")
        self.assertEqual(raw_trig["actions"][0]["param"], "reroll_threshold")
        self.assertEqual(raw_trig["actions"][0]["param_value"], 3)

        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["actions"][0]["param"], "reroll_threshold")
        self.assertEqual(compiled[0]["actions"][0]["param_value"], 3)

    def test_on_calc_dmg_multiplier_compilation(self):
        raw_trig = assemble_trigger("on_calc_dmg_multiplier", {
            "param_value": 1.5,
            "chance": 0.5,
            "cooldown": 3
        })
        self.assertEqual(raw_trig["event"], "on_calculate_damage")
        self.assertEqual(raw_trig["chance"], 0.5)
        self.assertEqual(raw_trig["cooldown"], 3)
        self.assertEqual(raw_trig["actions"][0]["action_type"], "set_value")
        self.assertEqual(raw_trig["actions"][0]["param"], "damage_multiplier")
        self.assertEqual(raw_trig["actions"][0]["param_value"], 1.5)

        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["actions"][0]["param_value"], 1.5)

    def test_on_calc_ignore_defense_compilation(self):
        raw_trig = assemble_trigger("on_calc_ignore_defense", {
            "param_value": 0.45
        })
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["actions"][0]["param"], "defense_ignore_ratio")
        self.assertEqual(compiled[0]["actions"][0]["param_value"], 0.45)

    def test_on_calc_absolute_hit_compilation(self):
        raw_trig = assemble_trigger("on_calc_absolute_hit", {})
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["actions"][0]["param"], "is_absolute_hit")
        self.assertTrue(compiled[0]["actions"][0]["param_value"])

    def test_on_calc_guaranteed_crit_compilation(self):
        raw_trig = assemble_trigger("on_calc_guaranteed_crit", {})
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["actions"][0]["param"], "is_crit")
        self.assertTrue(compiled[0]["actions"][0]["param_value"])

    def test_on_crit_time_warp_compilation(self):
        raw_trig = assemble_trigger("on_crit_time_warp", {})
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_crit")
        self.assertEqual(compiled[0]["actions"][0]["action_type"], "call_special_mechanic")
        self.assertEqual(compiled[0]["actions"][0]["keyword_name"], "Time_Warp")

    def test_on_fatal_prevent_death_compilation(self):
        raw_trig = assemble_trigger("on_fatal_prevent_death", {})
        compiled = TriggerCompiler.compile_flat_triggers([raw_trig])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["event"], "on_fatal_damage")
        self.assertEqual(compiled[0]["actions"][0]["keyword_name"], "Prevent_Death")

    def test_trigger_engine_interceptor_execution(self):
        # Create a mock character with our compiled trigger
        char = MagicMock()
        
        # Let's compile a dice modify trigger
        raw_trig = assemble_trigger("on_dice_modify", {"param": "roll_modifier", "param_value": 5})
        compiled_trig = TriggerCompiler.compile_flat_triggers([raw_trig])[0]
        
        # Mock equipment slot retrieval
        mock_equipment = MagicMock()
        mock_equipment.executable_triggers = [compiled_trig]
        
        char.data = MagicMock()
        char.data.equipment_slots = MagicMock()
        char.data.equipment_slots.model_fields = {"main_hand": None}
        char.data.status_effects = []
        char.data.abilities = []
        
        setattr(char.data.equipment_slots, "main_hand", mock_equipment)
        
        # Test DiceContext modification
        dice_ctx = DiceContext(dice_str="1d20", roll_modifier=0)
        TriggerEngine.dispatch_interceptor("on_dice", dice_ctx, char)
        
        # Should be modified by +5
        self.assertEqual(dice_ctx.roll_modifier, 5)

        # Test ActionContext modification (guaranteed crit)
        crit_raw = assemble_trigger("on_calc_guaranteed_crit", {})
        crit_compiled = TriggerCompiler.compile_flat_triggers([crit_raw])[0]
        mock_equipment.executable_triggers = [crit_compiled]

        act_ctx = ActionContext(crit_rate=0.05, is_crit=False)
        TriggerEngine.dispatch_interceptor("on_calculate_damage", act_ctx, char)

        # Should be modified to is_crit=True
        self.assertTrue(act_ctx.is_crit)

if __name__ == "__main__":
    unittest.main()
