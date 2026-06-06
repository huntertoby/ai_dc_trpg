import sys
import json
from core.models import Equipment

item_json = """
{
    "name": "殉祭之契·雙生項鍊",
    "description": "這枚項鍊由兩枚交錯的暗銀墜飾組成，表面刻滿細密如血管般的古符文。當穿戴者握拳時，墜飾會隨呼吸明滅交替，彷彿在低語著古老祭壇上的血誓與恩賜，散發著沉靜而堅韌的氣息。",
    "quantity": 1,
    "item_type": "equipment",
    "material_type": null,
    "tier": "T1",
    "source_id": null,
    "slot_type": "trinket_1",
    "item_level": 100,
    "is_two_handed": true,
    "special_effect": "命中觸發：命中敵人時有 60% 機率發動，冷卻 1 回合。對目標造成 25 + 自身力量×1.2 點傷害，此額外傷害無視防禦力（真實傷害）；並對自身施加【Sacrifice_Blight】狀態，持續 3 回合（技能威力 -10）。\\n血誓護盾：當生命值低於 45% 時觸發，冷卻 99 回合。為自身獲得 60 + 自身力量×1.5 點護盾；並對自身施加【Sacrifice_Blessing】狀態，持續 4 回合（技能威力 +20、暴擊率 +15%）。",
    "bonuses": {
        "STR": 195.0,
        "skill_power": 0.04,
        "crit_rate": 0.03,
        "accuracy": 0.03
    },
    "executable_triggers": [
        {
            "event": "on_hit",
            "actions": [
                {
                    "action_type": "inflict_damage",
                    "target": "target",
                    "flat_value": 25.0,
                    "scaling_stat": "STR",
                    "value_multiplier": 1.2,
                    "dice": null,
                    "divisor": 1.0,
                    "damage_type": "true_damage"
                },
                {
                    "action_type": "apply_status",
                    "target": "caster",
                    "status_name": "Sacrifice_Blight",
                    "duration": 3,
                    "bonuses": {
                        "skill_power": -10.0
                    }
                }
            ],
            "cooldown": 1,
            "chance": 0.6
        },
        {
            "event": "on_health_below",
            "actions": [
                {
                    "action_type": "gain_shield",
                    "target": "caster",
                    "flat_value": 60.0,
                    "scaling_stat": "STR",
                    "value_multiplier": 1.5,
                    "dice": null,
                    "divisor": 1.0
                },
                {
                    "action_type": "apply_status",
                    "target": "caster",
                    "status_name": "Sacrifice_Blessing",
                    "duration": 4,
                    "bonuses": {
                        "skill_power": 20.0,
                        "crit_rate": 15.0
                    }
                }
            ],
            "cooldown": 99,
            "condition": "health_below(45)",
            "health_threshold": 45.0
        }
    ],
    "weapon_type": null,
    "damage_type": "physical",
    "scaling_stat": "STR"
}
"""

try:
    data = json.loads(item_json)
    eq = Equipment(**data)
    print("SUCCESS: JSON is fully valid and loads successfully!")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
