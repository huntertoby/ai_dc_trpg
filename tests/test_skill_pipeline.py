import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.models import Skill, SkillMechanics, SkillFormula, CharacterSchema, Vitality, PrimaryAttributes, EquipmentSlots
from core.skill_processor import SkillProcessor, SkillExecutionPipeline
from core.skill_generator import validate_keywords_safety, generate_single_skill

class TestSkillPipelineAndGenerator(unittest.TestCase):
    def test_validate_keywords_safety(self):
        # 1. 無衝突
        self.assertIsNone(validate_keywords_safety(["Pierce", "Sunder"]))
        # 2. 單一衝突：隱身 + 嘲諷
        self.assertEqual(validate_keywords_safety(["Invis", "Taunt"]), "隱身 (Invis) 與 嘲諷 (Taunt) 不能同時存在")
        # 3. 連擊起手 + 終結衝突
        self.assertEqual(validate_keywords_safety(["Combo_Starter", "Combo_Finisher"]), "連擊起手 (Combo_Starter) 與 連擊終結 (Combo_Finisher) 不能同時存在")
        # 4. 多重硬控衝突：Stun + Silence
        self.assertEqual(validate_keywords_safety(["Stun", "Silence"]), "暈眩 (Stun) 已包含沉默效果，兩者不應共存")

    @patch("core.skill_generator.repair_and_parse_json")
    async def _test_generate_single_skill_retry_on_conflict_async(self, mock_repair):
        # 建立 Mock LLM client
        llm_client = MagicMock()
        
        # 第一次回傳包含衝突 (Invis + Taunt) 的 JSON，第二次回傳合法的 JSON
        response_conflict = {
            "skill_type": "active",
            "bonuses": None,
            "action_type": "buff",
            "target_type": "self",
            "base_stat": "WIS",
            "is_magical": True,
            "template_choices": [
                {"template_id": "active_invis"},
                {"template_id": "active_taunt"}
            ],
            "targeting_modifier": None,
            "synergy_requirement": None,
            "execution_mode": "immediate",
            "cost_preference": "standard",
            "evolution_threshold": None,
            "tags": ["Shadow"],
            "reactive_trigger": None,
            "allowed_jobs": ["暗殺者", "盜賊"]
        }
        
        response_clean = {
            "skill_type": "active",
            "bonuses": None,
            "action_type": "buff",
            "target_type": "self",
            "base_stat": "WIS",
            "is_magical": True,
            "template_choices": [
                {"template_id": "active_invis"}
            ],
            "targeting_modifier": None,
            "synergy_requirement": None,
            "execution_mode": "immediate",
            "cost_preference": "standard",
            "evolution_threshold": None,
            "tags": ["Shadow"],
            "reactive_trigger": None,
            "allowed_jobs": ["暗殺者", "盜賊"]
        }

        response_stage2 = {
            "name": "影遁術",
            "description": "純粹隱身",
            "narrative_effect": "暗影隱身，持續 2 回合。"
        }
        
        llm_client.call = AsyncMock()
        llm_client.call.side_effect = ["conflict_raw_text", "clean_raw_text", "stage2_raw_text"]
        
        mock_repair.side_effect = [response_conflict, response_clean, response_stage2]
        
        skill = await generate_single_skill("想隱身", "T2", llm_client, kw_count=1)
        
        # 驗證是否呼叫了三次 LLM (Stage 1 衝突, Stage 1 乾淨, Stage 2)，且最後成功返回無衝突的技能
        self.assertEqual(llm_client.call.call_count, 3)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "影遁術")
        self.assertEqual(skill.mechanics.keywords, ["Invis"])

    def test_generate_single_skill_retry_on_conflict(self):
        # 執行異步測試
        import asyncio
        asyncio.run(self._test_generate_single_skill_retry_on_conflict_async())

    def test_pipeline_execution_sacrifice_and_lifesteal(self):
        # 1. 先單獨測試 Sacrifice (犧牲) 的 HP 扣除與威力加成
        skill_sac = Skill(
            name="血魂擊", description="犧牲生命攻擊對手", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=1.0),
                keywords=["Sacrifice"]
            )
        )
        
        caster = MagicMock()
        caster.data = CharacterSchema(
            character_id="caster_123", name="施法者", background="孤兒",
            primary_stats=PrimaryAttributes(STR=20, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=20, max_mp=20, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        caster.total_stats = {"STR": 20}
        caster.max_hp = 100
        caster.combat_stats = {"accuracy": 1.0, "skill_power": 1.0, "p_def": 10, "m_def": 10, "crit_rate": 0.0}
        
        target = {
            "name": "怪物",
            "hp": 200,
            "max_hp": 200,
            "defense": 0,
            "crit_rate": 0.05,
            "evasion_rate": 0.0,
            "accuracy": 0.95
        }
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_sac, caster, target)
            self.assertTrue(res["logs"])
            # 扣除當前 HP(100) 的 20% = 20 HP
            self.assertEqual(caster.data.vitality.hp, 80)
            
        # 2. 測試 Sacrifice (犧牲) 與 Lifesteal (吸血) 協同運作 (吸血會回復 HP)
        skill_both = Skill(
            name="血魂刺", description="犧牲生命吸取對手", tier="T1",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=1.0),
                keywords=["Sacrifice", "Lifesteal"]
            )
        )
        
        caster.data.vitality.hp = 100 # 重置生命
        target["hp"] = 200 # 重置生命
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_both, caster, target)
            
            # 230 傷害 * 30% 吸血 = 69 回復。 80 + 69 = 149 -> 限制在 max_hp 100
            self.assertEqual(caster.data.vitality.hp, 100)
            self.assertEqual(caster.data.vitality.mp, 0)

    def test_pipeline_execution_stun_and_shield(self):
        # 測試 Stun (暈眩) 與 Shield (護盾) 附加
        skill = Skill(
            name="聖光震擊", description="震暈對手並加盾", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 15},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="5", divisor=10.0),
                keywords=["Stun", "Shield"]
            )
        )
        
        caster = MagicMock()
        caster.data = CharacterSchema(
            character_id="caster_123", name="施法者", background="孤兒",
            primary_stats=PrimaryAttributes(STR=10, DEX=10, CON=10, INT=10, WIS=20, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=30, max_mp=30, stamina=100, max_stamina=100, sanity=100, max_sanity=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        caster.total_stats = {"WIS": 20}
        caster.combat_stats = {"accuracy": 1.0, "skill_power": 1.0, "crit_rate": 0.0}
        
        target = {
            "name": "怪物",
            "hp": 100,
            "max_hp": 100,
            "status_effects": []
        }
        
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=5):
            res = SkillProcessor.execute_skill(skill, caster, target)
            
            # 驗證目標被附加暈眩狀態
            self.assertTrue(any(e["name"] == "Stun" for e in target["status_effects"]))
            # 注意：在我們的 Phase 6 邏輯中，Shield 施加在 target 上。如果是防守關鍵字，通常作用於 caster 本身。
            # 我們的 Phase 6 實現：add_entity_status_effect(target, "Shield", ...)，此處也是施加在 target 上。
            self.assertTrue(any(e["name"] == "Shield" for e in target["status_effects"]))

    def test_pipeline_additional_keywords(self):
        # 1. 測試 Pierce (穿透)
        skill_pierce = Skill(
            name="穿透箭", description="穿透防禦", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="DEX", dice="10", divisor=2.0),
                keywords=["Pierce"]
            )
        )
        caster = MagicMock()
        caster.data = CharacterSchema(
            character_id="c1", name="Caster", background="孤兒",
            primary_stats=PrimaryAttributes(STR=10, DEX=20, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100),
            inventory=[], status_effects=[], equipment_slots=EquipmentSlots()
        )
        caster.total_stats = {"DEX": 20}
        caster.combat_stats = {"accuracy": 1.0, "skill_power": 1.0, "crit_rate": 0.0}
        
        target = {
            "name": "防禦怪",
            "hp": 200,
            "max_hp": 200,
            "defense": 100,
            "crit_rate": 0.0,
            "evasion_rate": 0.0,
            "accuracy": 1.0,
            "status_effects": []
        }
        
        # Base value = 20 * (10 / 2.0) = 100.
        # Pierce: Target def = 100 * 0.5 = 50.
        # Final dmg = 100 - 50 = 50.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_pierce, caster, target)
            self.assertEqual(res["final_value"], 50)
            
        # 2. 測試 Execute (處決)
        skill_exec = Skill(
            name="處決斬", description="低血量斬殺", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=10.0),
                keywords=["Execute"]
            )
        )
        caster.total_stats = {"STR": 20}
        
        # Case A: target HP >= 20%
        target["hp"] = 50 # 50 / 200 = 25%
        target["defense"] = 0
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_exec, caster, target)
            self.assertEqual(res["final_value"], 20)
            
        # Case B: target HP < 20%
        target["hp"] = 30 # 30 / 200 = 15%
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_exec, caster, target)
            # 20 * 3 = 60
            self.assertEqual(res["final_value"], 60)

        # 3. 測試 Gamble (豪賭)
        skill_gamble = Skill(
            name="豪賭之槍", description="拚死一搏", tier="T3",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=10.0),
                keywords=["Gamble"]
            )
        )
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        # Gamble roll = 1 -> 3x damage
        with patch("random.randint", return_value=1), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_gamble, caster, target)
            self.assertEqual(res["final_value"], 60) # 20 * 3 = 60
            
        # Gamble roll = 2 -> backlash, self takes damage, target takes 0 damage
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        target["hp"] = 200
        with patch("random.randint", return_value=2), patch("core.skill_processor.SkillProcessor.roll_dice", return_value=10):
            res = SkillProcessor.execute_skill(skill_gamble, caster, target)
            self.assertEqual(res["final_value"], 0)
            # HP should be reduced by base_val (20) -> 80
            self.assertEqual(caster.data.vitality.hp, 80)

        # 4. 測試 Purge (淨化)
        skill_purge = Skill(
            name="淨化術", description="清除負面效果", tier="T4",
            mechanics=SkillMechanics(
                action_type="buff", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1", divisor=1.0),
                keywords=["Purge"]
            )
        )
        from core.models import StatusEffect
        target_entity = MagicMock()
        target_entity.data = CharacterSchema(
            character_id="t1", name="Target", background="孤兒",
            primary_stats=PrimaryAttributes(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            vitality=Vitality(hp=100, max_hp=100, mp=100, max_mp=100),
            inventory=[],
            status_effects=[
                StatusEffect(name="Stun", description="暈眩", duration=1),
                StatusEffect(name="Bless", description="祝福", duration=3)
            ],
            equipment_slots=EquipmentSlots()
        )
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        SkillProcessor.execute_skill(skill_purge, caster, target_entity)
        # Stun (debuff) should be removed, Bless (buff) should be kept
        names = [e.name for e in target_entity.data.status_effects]
        self.assertNotIn("Stun", names)
        self.assertIn("Bless", names)

        # 5. 測試 Bless (祝福)
        skill_blessed_attack = Skill(
            name="幸運擊", description="幸運擲骰", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="1d20", divisor=10.0),
                keywords=[]
            )
        )
        caster.data.status_effects = [StatusEffect(name="Bless", description="祝福", duration=3)]
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        # roll_dice returns 3 (<= 5). Because of Bless, it should be treated as 10.
        # Base value = STR (20) * (10 / 10.0) = 20.
        with patch("core.skill_processor.SkillProcessor.roll_dice", return_value=3):
            res = SkillProcessor.execute_skill(skill_blessed_attack, caster, target)
            self.assertEqual(res["final_value"], 20)

        # 6. 測試 Immune (免疫)
        skill_stun = Skill(
            name="重擊", description="暈眩對手", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="STR", dice="10", divisor=10.0),
                keywords=["Stun"]
            )
        )
        target_entity.data.status_effects = [StatusEffect(name="Immune", description="免疫", duration=2)]
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        SkillProcessor.execute_skill(skill_stun, caster, target_entity)
        # Should NOT get Stun status effect because of Immune
        names = [e.name for e in target_entity.data.status_effects]
        self.assertNotIn("Stun", names)

        # 7. 測試 Time_Warp (時光回溯)
        skill_warp = Skill(
            name="時光倒流", description="回溯狀態", tier="T3",
            mechanics=SkillMechanics(
                action_type="buff", target_type="self", cost={"MP": 0},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1", divisor=1.0),
                keywords=["Time_Warp"]
            )
        )
        caster.data.vitality.hp = 50
        caster.data.vitality.mp = 5
        caster._hp_snapshot = 85
        caster._mp_snapshot = 25
        SkillProcessor.execute_skill(skill_warp, caster, caster)
        # HP/MP should be restored to 85 and 25
        self.assertEqual(caster.data.vitality.hp, 85)
        self.assertEqual(caster.data.vitality.mp, 25)

        # 8. 測試 Steal (竊取)
        skill_steal = Skill(
            name="妙手空空", description="竊取金幣", tier="T4",
            mechanics=SkillMechanics(
                action_type="buff", target_type="single", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="DEX", dice="1", divisor=1.0),
                keywords=["Steal"]
            )
        )
        caster.data.gold = 100
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        res = SkillProcessor.execute_skill(skill_steal, caster, target)
        self.assertTrue(res["control_flags"].get("steal_active"))
        self.assertGreater(caster.data.gold, 100)

        # 9. 測試 Copy (鏡像)
        skill_copy = Skill(
            name="鏡像術", description="複製技能", tier="T3",
            mechanics=SkillMechanics(
                action_type="buff", target_type="self", cost={"MP": 5},
                formula=SkillFormula(type="multiplier", base_stat="WIS", dice="1", divisor=1.0),
                keywords=["Copy"]
            )
        )
        # Cast standard attack skill first
        skill_std = Skill(
            name="火焰球", description="火焰傷害", tier="T4",
            mechanics=SkillMechanics(
                action_type="damage", target_type="single", cost={"MP": 10},
                formula=SkillFormula(type="multiplier", base_stat="INT", dice="10", divisor=2.0),
                keywords=["Burn"]
            )
        )
        # This will set caster._last_skill_cast = skill_std
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        SkillProcessor.execute_skill(skill_std, caster, target)
        
        # Now cast mirror copy
        caster.data.vitality.mp = 100
        caster.data.vitality.hp = 100
        res = SkillProcessor.execute_skill(skill_copy, caster, target)
        # Verify that the original skill was NOT mutated in-place (no database corruption)
        self.assertEqual(skill_copy.mechanics.formula.base_stat, "WIS")
        
        # Verify that the executed result reflects the copied mechanics
        self.assertIn("Burn", res["keywords"])

    def test_new_skill_generator_features(self):
        # 1. 測試物理與魔法消耗類型路由 (Stamina vs MP)
        from core.skill_generator import calculate_skill_cost
        
        # 魔法技能 -> 消耗 MP
        cost_magical = calculate_skill_cost(
            tier="T3", target_type="single", is_magical=True,
            template_choices=[], cost_pref="standard", description="魔法火球"
        )
        self.assertIn("MP", cost_magical)
        self.assertNotIn("STAMINA", cost_magical)
        
        # 物理技能 -> 消耗 STAMINA
        cost_physical = calculate_skill_cost(
            tier="T3", target_type="single", is_magical=False,
            template_choices=[], cost_pref="standard", description="物理斬擊"
        )
        self.assertIn("STAMINA", cost_physical)
        self.assertNotIn("MP", cost_physical)
        
        # 無消耗偏好
        cost_zero = calculate_skill_cost(
            tier="T3", target_type="single", is_magical=True,
            template_choices=[], cost_pref="zero", description="無消耗"
        )
        self.assertEqual(cost_zero, {})

        # 2. 測試 assemble_skill_actions 的 Tier & Intensity 數值縮放
        from core.skill_templates import assemble_skill_actions
        
        # T3 Standard Shield
        actions_t3_std = assemble_skill_actions([{"template_id": "active_shield", "intensity": "standard"}], tier="T3")
        shield_t3_std = actions_t3_std[0]["flat_value"]
        
        # T1 Extreme Shield (should be much higher)
        actions_t1_ext = assemble_skill_actions([{"template_id": "active_shield", "intensity": "extreme"}], tier="T1")
        shield_t1_ext = actions_t1_ext[0]["flat_value"]
        
        self.assertGreater(shield_t1_ext, shield_t3_std)
        
        # 3. 測試 Pydantic 載入時動態註冊自訂狀態別名
        from core.constants import STATUS_REGISTRY, normalize_status_name
        from core.models import Skill
        
        # 建立帶有 custom_status_name 與 canonical_status 的技能數據
        skill_json = {
            "name": "地獄黑炎",
            "description": "召喚極致黑火",
            "tier": "T2",
            "mechanics": {
                "action_type": "damage",
                "target_type": "single",
                "cost": {"MP": 20},
                "formula": {"type": "multiplier", "base_stat": "INT", "dice": "1d10", "divisor": 8.0},
                "actions": [
                    {
                        "action_type": "apply_status",
                        "target": "target",
                        "status_name": "地獄黑焰",
                        "duration": 3,
                        "custom_status_name": "地獄黑焰",
                        "canonical_status": "Burn"
                    }
                ]
            }
        }
        
        # 驗證在反序列化前，"地獄黑焰" 還不是 "Burn" 的別名
        if "地獄黑焰" in STATUS_REGISTRY["Burn"]["aliases"]:
            STATUS_REGISTRY["Burn"]["aliases"].remove("地獄黑焰")
            
        self.assertNotEqual(normalize_status_name("地獄黑焰"), "Burn")
        
        # 使用 Pydantic 反序列化實例化模型
        loaded_skill = Skill.model_validate(skill_json)
        
        # 驗證別名已成功自動註冊回 STATUS_REGISTRY，且 normalize_status_name 能成功標準化
        self.assertIn("地獄黑焰", STATUS_REGISTRY["Burn"]["aliases"])
        self.assertEqual(normalize_status_name("地獄黑焰"), "Burn")
