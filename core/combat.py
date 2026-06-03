import asyncio
from core.character import Character
from core.models import Skill
from core.skill_processor import SkillProcessor
import discord

async def generate_combat_narrative(
    character: Character, 
    skill: Skill, 
    mechanics_result: dict, 
    llm_client
) -> str:
    """
    將生硬的數值計算結果傳給 AI，讓 AI 生成戰鬥敘述與處理特殊邏輯。
    """
    target = mechanics_result.get("target", "假想敵")
    action_type = skill.mechanics.action_type
    
    # 組合上下文
    context = f"""
    【戰鬥事件】
    發動者: {character.data.name} (Lv.{character.data.level} {character.data.job_name})
    目標: {target}
    使用技能: {skill.name} ({skill.tier})
    - 技能描述: {skill.description}
    - 基礎動作: {action_type}
    - 特殊指令 (Custom Logic): {skill.mechanics.custom_logic or '無'}
    
    【系統結算數據】
    - 消耗: {skill.mechanics.cost}
    - 擲骰結果: 擲出 {mechanics_result['dice_roll']} (使用 {skill.mechanics.formula.dice})
    - 最終威力值: {mechanics_result['final_value']}
    - 觸發關鍵字: {', '.join(skill.mechanics.keywords) if skill.mechanics.keywords else '無'}
    """
    
    system_prompt = f"""
    你是一個專業的 TRPG 戰鬥旁白 (GM)。
    請根據提供的【戰鬥事件】與【系統結算數據】，撰寫一段生動、具畫面感的戰鬥敘述。
    
    **【撰寫規範】**
    1. 必須將擲骰結果 ({mechanics_result['dice_roll']}) 與最終威力 ({mechanics_result['final_value']}) 巧妙地融入劇情中。如果擲骰低，描述失誤或阻礙；如果高，描述爆發。
    2. 如果有【特殊指令 (Custom Logic)】，請判斷該邏輯是否觸發，並在敘述中實現它的效果。
    3. 敘述長度約 50~100 字，保持節奏緊湊。
    4. 必須使用繁體中文。
    5. 不要輸出任何 JSON，直接輸出純文字的敘事段落。
    """
    
    prompt = f"請根據以下資料生成戰鬥敘述：\n{context}"
    
    try:
        narrative = await llm_client.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.8
        )
        return narrative.strip()
    except Exception as e:
        print(f"戰鬥敘述生成失敗: {e}")
        return f"*({character.data.name} 發動了 {skill.name}，但迷霧遮蔽了戰場，無法看清具體效果。)*"

async def execute_combat_skill(
    interaction: discord.Interaction, 
    character: Character, 
    skill_name: str, 
    target_name: str, 
    llm_client
):
    """處理完整的技能使用流程"""
    await interaction.response.defer(ephemeral=False) # 戰鬥是公開的
    
    # 1. 尋找技能
    skill = next((s for s in character.data.abilities if s.name == skill_name), None)
    if not skill:
        await interaction.followup.send(f"❌ 找不到名為 `{skill_name}` 的技能。", ephemeral=True)
        return

    try:
        # 2. 系統硬核結算 (扣魔、算公式)
        mechanics_result = SkillProcessor.execute_skill(skill, character)
        mechanics_result["target"] = target_name
        
        # 3. 處理 Keyword (這裡暫時印出，未來接上怪物系統時會實際扣怪物血)
        keyword_actions = []
        for kw in skill.mechanics.keywords:
            if kw == "Execute": keyword_actions.append("試圖處決目標")
            elif kw == "Lifesteal": keyword_actions.append("吸收生命力")
            elif kw == "Pierce": keyword_actions.append("無視部分防禦")
            elif kw == "Burn": keyword_actions.append("附加灼燒狀態")
            else: keyword_actions.append(f"觸發 {kw}")
            
        # 4. 呼叫 AI 生成敘事
        narrative = await generate_combat_narrative(character, skill, mechanics_result, llm_client)
        
        # 5. 建立戰鬥面板
        embed = discord.Embed(
            title=f"⚔️ {character.data.name} 發動了 【{skill.name}】！",
            description=f"> *{narrative}*",
            color=discord.Color.brand_red() if skill.mechanics.action_type == "damage" else discord.Color.green()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        # 數值總結區塊
        action_verb = "💥 造成傷害" if skill.mechanics.action_type == "damage" else "✨ 產生效果"
        if skill.mechanics.action_type == "heal": action_verb = "💚 恢復生命"
        elif skill.mechanics.action_type == "buff": action_verb = "🛡️ 獲得增益"
        
        cost_str = ", ".join([f"{k} -{v}" for k,v in skill.mechanics.cost.items()])
        stats_text = f"**{action_verb}**: {mechanics_result['final_value']} 點\n"
        stats_text += f"**🎲 擲骰判定**: {mechanics_result['dice_roll']} ({mechanics_result['dice_type']})\n"
        if cost_str: stats_text += f"**💧 消耗**: {cost_str}\n"
        if keyword_actions: stats_text += f"**⚡ 觸發機制**: {', '.join(keyword_actions)}"
        
        embed.add_field(name="📊 系統結算", value=stats_text, inline=False)
        
        # 顯示剩餘狀態
        embed.set_footer(text=f"剩餘狀態 | HP: {character.data.vitality.hp}/{character.max_hp} | MP: {character.data.vitality.mp}/{character.max_mp}")
        
        await interaction.followup.send(embed=embed)
        
    except ValueError as e:
        # 捕捉 MP 不足等錯誤
        await interaction.followup.send(f"⚠️ 發動失敗：{e}", ephemeral=True)
