#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 协作创作工作流 —— 各节点的提示词模板。

把每个 Agent 节点的 prompt 抽取为 build_*_prompt(state) 函数，节点函数只保留
「取状态 → 调 LLM → 写回」的逻辑，便于单独审阅与调整提示词（对应 AGENTS.md 第 5.1 节）。
"""

from typing import Any, Dict, List

from llm import format_cards
from state import CollabNovelState


def build_planner_prompt(state: CollabNovelState) -> str:
    """规划节点：根据大纲、素材、前文、全书大纲生成本章详细计划。"""
    return f"""你是一位资深小说大纲规划师。请根据以下信息，为即将撰写的章节生成一份详细的写作计划。

【上一章概括】
{state.get('previous_summary', '无')}

【本章大纲】
{state.get('chapter_outline', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('plot_cards', []), '剧情卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

{f"【前文片段（近期章节，用于保持连续性）】\n" + state["prior_chapters"] if state.get("prior_chapters") else ""}

{f"【全书大纲 / 结构圣经（本章规划需与之对齐）】\n" + state["book_outline"] if state.get("book_outline") else ""}

请输出：
1. 本章核心目标（本章要解决什么问题、推动哪条剧情线）
2. 出场人物及在本章的任务/状态
3. 关键场景列表（场景地点、人物、核心动作）
4. 需要回收或新埋下的伏笔
5. 节奏与情绪控制建议
6. 预计字数与分段建议

直接输出计划文本，不要额外寒暄。
"""


def build_approve_card_prompt(state: CollabNovelState) -> str:
    """大纲审批节点：判断本章计划是否可执行。"""
    return f"""你是一位严格的小说责编，负责判断本章计划是否可执行。

【本章大纲】
{state.get('chapter_outline', '无')}

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('plot_cards', []), '剧情卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}

请从以下维度判断：
1. 计划是否符合本章大纲目标；
2. 人物行为是否与人设一致；
3. 伏笔回收/铺设是否合理；
4. 节奏是否可行。

请在第一行明确输出：APPROVED 或 REJECTED
第二行起给出理由（若是 REJECTED，请给出具体修改建议）。
"""


def build_writer_prompt(state: CollabNovelState) -> str:
    """写作节点：根据计划与素材撰写本章正文。"""
    style_text = format_cards(state.get("style_cards", []), "文风卡")
    return f"""你是一位经验丰富的专业网文作家。请严格根据以下材料撰写本章正文。

【上一章概括】
{state.get('previous_summary', '无')}

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('plot_cards', []), '剧情卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}
{style_text}

{f"【前文片段（近期章节，用于保持连续性）】\n" + state["prior_chapters"] if state.get("prior_chapters") else ""}

### 输出要求
1. 直接输出完整正文，不要解释、不要开场白、不要结尾总结。
2. 严格按【本章计划】展开，不要偏离大纲。
3. 人物言行符合人设，伏笔铺设自然。
4. 文风完全贴合【文风卡】要求。
5. 段落紧凑，段首缩进两个字符，段与段之间不留空行。
6. 不要刻意埋钩子或升华。
"""


def build_continuity_prompt(state: CollabNovelState) -> str:
    """连续性检查节点：检查草稿与前文、人设、伏笔是否一致。"""
    return f"""你是一位小说设定管理员，专门检查草稿是否与已有设定保持一致。

【上一章概括】
{state.get('previous_summary', '无')}

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

【当前草稿】
{state.get('draft', '')}

{f"【前文片段（近期章节，用于保持连续性）】\n" + state["prior_chapters"] if state.get("prior_chapters") else ""}

请检查：
1. 人物行为、能力、关系是否与前文/人设冲突；
2. 世界观规则是否被违反；
3. 伏笔是否被正确回收或铺设；
4. 时间线、地点、状态是否连续。

请在第一行输出：CLEAN 或 ISSUES_FOUND
第二行起输出具体问题与修改建议（CLEAN 时简要说明即可）。
"""


def build_fixer_prompt(state: CollabNovelState) -> str:
    """连续性修复节点：根据检查报告修改草稿。"""
    return f"""你是一位小说修改专家。请根据连续性检查报告修改草稿，只修正问题，保留原有精彩内容。

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

【当前草稿】
{state.get('draft', '')}

【连续性检查报告】
{state.get('continuity_report', '')}

请输出修改后的完整正文。不要只输出修改片段。
"""


def build_style_edit_prompt(state: CollabNovelState) -> str:
    """文风润色节点：根据文风卡润色正文，若有前一轮润色稿则在其上改。"""
    # 若上一轮已润色过，则基于已润色稿再改；否则基于原始草稿。
    # 这样人工提出「revise」后重排，不会丢掉之前的润色成果。
    base_draft = state.get("style_edited_draft") or state.get("draft", "")
    feedback = state.get("human_feedback", "")
    feedback_block = ""
    if feedback:
        feedback_block = f"\n【人工修改意见（必须逐条落实）】\n{feedback}\n"

    return f"""你是一位小说文风编辑。请根据文风卡对当前草稿进行润色，使风格统一、语言精炼。

{format_cards(state.get('style_cards', []), '文风卡')}

【本章计划】
{state.get('chapter_plan', '无')}

【当前草稿】
{base_draft}
{feedback_block}
要求：
1. 保留情节和人物行为不变；
2. 调整句式、用词、节奏，使其符合文风卡要求；
3. 若存在人工修改意见，必须优先、逐条落实；
4. 直接输出修改后的完整正文。
"""


def build_update_memory_prompt(state: CollabNovelState) -> str:
    """素材记忆更新节点：根据正文本章更新伏笔卡、剧情卡等。"""
    return f"""你是一位小说资料管理员。请根据本章正文，更新伏笔卡与剧情卡的状态。

【本章计划】
{state.get('chapter_plan', '无')}

【最终正文】
{state.get('style_edited_draft', state.get('draft', ''))}

{format_cards(state.get('foreshadowing_cards', []), '当前伏笔卡')}
{format_cards(state.get('plot_cards', []), '当前剧情卡')}

请输出更新后的内容：
1. 已回收的伏笔（状态改为 resolved）；
2. 新埋下的伏笔（新增条目，状态为 pending）；
3. 剧情卡进度更新（状态改为 completed/in_progress）；
4. 新出场人物（若本章出现了此前没有的角色，给出 id、name 与一句设定，status 为 new）；
5. 新补充的世界观（若本章补充了设定，给出 id、world_theme 与要点）。

请严格输出 JSON：
{{"foreshadowing_updates": [...], "plot_updates": [...], "new_characters": [...], "new_worldviews": [...]}}
"""


def build_canon_proposer_prompt(state: CollabNovelState) -> str:
    """正典提案节点：总结本章加入官方设定的关键事实。"""
    final_text = state.get("style_edited_draft") or state.get("draft", "")
    return f"""你是一位小说正典管理员。请根据本章正文生成一份正典提案，记录本章加入官方设定的关键事实。

【本章计划】
{state.get('chapter_plan', '无')}

【最终正文】
{final_text}

请输出：
1. 已确认的人物状态变化；
2. 已确认的剧情推进；
3. 已确认的世界观补充；
4. 已回收/新埋下的伏笔清单。

直接输出提案文本。
"""


def build_canon_approver_prompt(state: CollabNovelState) -> str:
    """正典审批节点：判断正典提案是否可入库。"""
    return f"""你是一位总编，负责审批本章正典提案是否可以写入小说官方设定。

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

【正典提案】
{state.get('canon_proposal', '')}

请判断：
1. 提案中的人物状态变化是否与人设一致；
2. 剧情推进是否逻辑自洽；
3. 世界观补充是否与已有设定冲突。

请在第一行输出：APPROVED 或 REJECTED
第二行起给出理由（REJECTED 时说明需要修改的地方）。
"""
