import unittest
from core.models import (
    Item, Equipment, StatusEffect, BuildingSchema, AreaSchema,
    WarehouseSchema, QuestObjective, QuestSchema, PrimaryAttributes,
    CombatAttributes, EquipmentSlots, Personality, Vitality,
    SkillFormula, SkillMechanics, Skill, LogEntry, CharacterSchema
)

class TestModels(unittest.TestCase):
    def test_item_creation(self):
        item = Item(name="木棒", description="普通木棒", quantity=2, item_type="material")
        self.assertEqual(item.name, "木棒")
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.item_type, "material")

    def test_equipment_creation(self):
        eq = Equipment(
            name="鐵劍", slot_type="main_hand", tier="T4", item_level=5,
            is_two_handed=False, bonuses={"STR": 5}, weapon_type="長劍",
            damage_type="physical", scaling_stat="STR"
        )
        self.assertEqual(eq.slot_type, "main_hand")
        self.assertEqual(eq.item_type, "equipment")
        self.assertEqual(eq.bonuses["STR"], 5)

    def test_area_schema_validator(self):
        # Test model validator: fix_landmarks_rename (buildings -> landmarks)
        data = {
            "id": "1,1",
            "name": "荒野",
            "type": "wilderness",
            "description": "一片荒涼",
            "buildings": [
                {
                    "id": "b1",
                    "name": "廢墟",
                    "description": "古老的廢墟"
                }
            ]
        }
        area = AreaSchema(**data)
        self.assertEqual(len(area.landmarks), 1)
        self.assertEqual(area.landmarks[0].name, "廢墟")

    def test_quest_schema_properties(self):
        quest = QuestSchema(
            id="Q-1", title="擊殺野狼", description="擊殺 5 隻野狼",
            rank_required="D", level_required=3,
            objectives=[QuestObjective(type="kill", target_id="wolf", count=5)],
            rewards={"gold": 100}
        )
        self.assertEqual(quest.rank_value, 1)

    def test_vitality(self):
        v = Vitality()
        self.assertEqual(v.hp, 100)
        self.assertEqual(v.max_hp, 100)

    def test_primary_attributes(self):
        pa = PrimaryAttributes()
        self.assertEqual(pa.STR, 5)
        
        # Test ge=5 validation
        with self.assertRaises(ValueError):
            PrimaryAttributes(STR=4)
