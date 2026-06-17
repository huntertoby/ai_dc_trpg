import asyncio
import sys
import os

# Add parent directory to sys.path
sys.path.append(os.path.abspath("."))

from unittest.mock import MagicMock, patch
from core.combat import CombatManager
from core.models import CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots, Equipment, StatusEffect

async def run_test():
    char = MagicMock()
    char.data = CharacterSchema(
        character_id="test_char_999",
        name="雷克斯",
        background="孤兒",
        primary_stats=PrimaryAttributes(STR=20, DEX=999, CON=15, INT=10, WIS=10, CHA=10),
        vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
        inventory=[],
        status_effects=[],
        equipment_slots=EquipmentSlots()
    )
    char.total_stats = {"STR": 20, "DEX": 999, "CON": 15, "INT": 10, "WIS": 10, "CHA": 10}
    char.max_hp = 100
    char.combat_stats = {
        "p_def": 0, "m_def": 10, "crit_rate": 0.0, "evasion_rate": 0.0,
        "accuracy": 1.0, "skill_power": 1.0, "tenacity": 100, "luck": 1
    }
    char.save = MagicMock()
    
    def mock_update_vitality(hp=None, mp=None, sanity=None, stamina=None, temp_hp=None):
        v = char.data.vitality
        if hp is not None: v.hp = max(0, min(int(hp), 100))
    char.update_vitality = MagicMock(side_effect=mock_update_vitality)

    monsters = [
        {
            "name": "幽靈",
            "base_name": "幽靈",
            "level": 5,
            "hp": 100,
            "max_hp": 100,
            "attack": 12,
            "defense": 10,
            "m_defense": 10,
            "speed": 15,
            "evasion_rate": 0.0,
            "source_id": "ghost",
            "status_effects": [],
            "executable_triggers": []
        }
    ]

    cm = CombatManager(char, monsters)
    
    # Simulate situation D setup
    # monster has "硬殼" status
    status = StatusEffect(
        name="硬殼",
        duration=2,
        executable_triggers=[
          {
            "event": "on_dice",
            "actions": [
              {
                "action_type": "modify_dice",
                "param": "roll_modifier",
                "param_value": -15
              }
            ]
          }
        ]
    )
    monsters[0]["status_effects"].append(status)
    
    cm.turn_order = [{"type": "monster", "speed": 15, "ref": monsters[0], "index": 0}]
    cm.current_turn_idx = 0
    cm._current_turn_ticked = True
    
    char.data.vitality.hp = 95
    
    with patch("random.randint", return_value=10):
        res = await cm.monster_action()
        print("Success:", res["success"])
        print("Msg:", res["msg"].encode('ascii', errors='backslashreplace').decode('ascii'))
        print("Post hp:", char.data.vitality.hp)

if __name__ == "__main__":
    asyncio.run(run_test())
