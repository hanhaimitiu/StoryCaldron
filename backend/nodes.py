#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 协作创作工作流 —— LangGraph 节点函数与路由。

每个节点就是「取状态 → 调 LLM（用 prompts 里的模板）→ 写回状态」；
路由负责在分支处决定下一步走向。状态结构见 state.py，提示词见 prompts.py，
LLM/卡片工具见 llm.py。拆分自 collab_novel_agent.py（见 AGENTS.md 第 5.1 节）。
"""

import os
import sys
import json
import uuid

# 让同目录下的 project 模块可 import（commit 节点写章节、自动前情检索、正典落盘都会用到）
sys.path.insert(0, os.path.dirname(__file__))
import project as proj

from state import (
    CollabNovelState,
    track_step,
    DATA_DIR,
    OUTPUT_DIR,
    ROLE_TEMPERATURES,
    STYLE_REVISE_MAX,
)
from llm import _call_llm, load_card_file, save_card_file
from prompts import (
    build_planner_prompt,
    build_approve_card_prompt,
    build_writer_prompt,
    build_continuity_prompt,
    build_fixer_prompt,
    build_style_edit_prompt,
    build_update_memory_prompt,
    build_canon_proposer_prompt,
    build_canon_approver_prompt,
)


@track_step("loader", "加载素材上下文", "读取人物卡、剧情卡、文风卡、伏笔卡、世界观卡")
def load_context_node(state: CollabNovelState) -> CollabNovelState:
    """加载外部素材卡到状态，供下游 Agent 使用。"""
    print("\n--- 📚 加载素材上下文 ---")

    # 回退读取必须限定在本项目 cards_dir（演示模式为 DATA_DIR）；
    # 绝不能落到默认 DATA_DIR，否则空项目/删光某类卡时会错误混入全局演示卡，破坏项目隔离。
    cards_dir = state.get("cards_dir") or DATA_DIR

    # 优先用 start_session 已注入的卡片；为空也保持空（不要回落到全局演示卡）
    characters = state.get("character_cards") or load_card_file("characters.json", base_dir=cards_dir)
    plots = (state.get("plot_cards")
             or load_card_file("stories.json", base_dir=cards_dir)
             or load_card_file("plots.json", base_dir=cards_dir))
    styles = state.get("style_cards") or load_card_file("styles.json", base_dir=cards_dir)
    foreshadowing = state.get("foreshadowing_cards") or load_card_file("foreshadowing.json", base_dir=cards_dir)
    worldviews = state.get("worldview_cards") or load_card_file("wordviews.json", base_dir=cards_dir)

    print(f"   人物卡 {len(characters)} 条，剧情卡 {len(plots)} 条，文风卡 {len(styles)} 条，"
          f"伏笔卡 {len(foreshadowing)} 条，世界观卡 {len(worldviews)} 条")

    return {
        **state,
        "character_cards": characters,
        "plot_cards": plots,
        "style_cards": styles,
        "foreshadowing_cards": foreshadowing,
        "worldview_cards": worldviews,
        "current_stage": "context_loaded",
    }


@track_step("planner", "规划本章", "根据大纲和素材生成本章详细计划")
def plan_chapter_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🗺️ 规划本章 ---")

    prompt = build_planner_prompt(state)
    plan = _call_llm(prompt, system="你是一位擅长拆解网文章节结构的大纲规划师。",
                     temperature=ROLE_TEMPERATURES["planner"])

    if not plan:
        plan = f"【默认计划】\n本章目标：{state.get('chapter_outline', '')[:80]}...\n" \
               f"按大纲逐步展开，注意保持人物设定与文风一致。"

    return {
        **state,
        "chapter_plan": plan,
        "plan_retry_count": state.get("plan_retry_count", 0),
        "current_stage": "plan_done",
    }


@track_step("card_approver", "审批大纲卡", "判断本章计划是否可行，是否通过或驳回")
def approve_card_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🧾 审批大纲卡 ---")

    prompt = build_approve_card_prompt(state)
    result = _call_llm(prompt, system="你是一位严格但务实的网文编辑。",
                       temperature=ROLE_TEMPERATURES["card_approver"])
    approved = "APPROVED" in result.upper() or "通过" in result

    if not result:
        # 无模型时按轮数兜底
        approved = state.get("plan_retry_count", 0) >= 2
        result = "【兜底】计划可执行。" if approved else "计划细节不够充分，请补充场景与伏笔安排。"

    print(f"   审批结果：{'通过' if approved else '驳回'}")

    return {
        **state,
        "plan_approved": approved,
        "plan_retry_count": state.get("plan_retry_count", 0) + 1,
        "current_stage": "card_approved" if approved else "card_rejected",
    }


def approve_card_router(state: CollabNovelState) -> str:
    if state.get("plan_approved"):
        return "approved"
    if state.get("plan_retry_count", 0) >= 3:
        print("⚠️ 规划反复被驳回，已达上限，强制通过。")
        state["plan_approved"] = True
        return "approved"
    return "rejected"


@track_step("writer", "撰写草稿", "根据计划与素材撰写本章正文")
def write_draft_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- ✍️ 撰写草稿 ---")

    prompt = build_writer_prompt(state)
    draft = _call_llm(prompt, system="你是一位高产且注重细节的网文作家。",
                      temperature=ROLE_TEMPERATURES["writer"])

    if not draft:
        draft = f"【模拟草稿】\n根据计划「{state.get('chapter_plan', '')[:60]}...」展开：\n\n"
        draft += "    月光洒在青石板上，主角站在窗前，望着远处的灯火。"

    return {
        **state,
        "draft": draft,
        "style_edited_draft": "",
        "current_stage": "draft_done",
    }


@track_step("continuity_checker", "连续性检查", "检查草稿与前文、人设、伏笔的连续性")
def check_continuity_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🔍 连续性检查 ---")

    prompt = build_continuity_prompt(state)
    result = _call_llm(prompt, system="你是一位注重细节的小说设定管理员。",
                       temperature=ROLE_TEMPERATURES["continuity_checker"])
    has_issue = "ISSUES_FOUND" in result.upper() or "问题" in result

    if not result:
        # 无模型时，前两次可能模拟发现问题，第三次强制通过
        fix_count = state.get("continuity_fix_count", 0)
        if fix_count < 2:
            has_issue = True
            result = "【模拟】部分人物情绪转折稍显突兀，建议补充过渡。"
        else:
            has_issue = False
            result = "【兜底】连续性问题已修正。"

    print(f"   连续性：{'通过' if not has_issue else '发现问题'}")

    return {
        **state,
        "continuity_report": result,
        "continuity_has_issue": has_issue,
        "current_stage": "continuity_checked",
    }


def continuity_router(state: CollabNovelState) -> str:
    if not state.get("continuity_has_issue"):
        return "clean"
    if state.get("continuity_fix_count", 0) >= 3:
        print("⚠️ 连续性问题修复已达上限，强制进入润色。")
        return "clean"
    return "issues_found"


@track_step("continuity_fixer", "修复连续性问题", "根据检查报告修改草稿")
def fix_issues_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🔧 修复连续性问题 ---")

    prompt = build_fixer_prompt(state)
    fixed = _call_llm(prompt, system="你是一位擅长无痕修改的网文编辑。",
                      temperature=ROLE_TEMPERATURES["continuity_fixer"])

    if not fixed:
        fixed = state.get("draft", "") + "\n\n    【模拟修复】已根据检查报告调整人物反应，使过渡更自然。"

    return {
        **state,
        "draft": fixed,
        "continuity_fix_count": state.get("continuity_fix_count", 0) + 1,
        "current_stage": "issues_fixed",
    }


@track_step("style_editor", "文风润色", "根据文风卡润色正文")
def style_edit_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🎨 文风润色 ---")

    prompt = build_style_edit_prompt(state)
    edited = _call_llm(prompt, system="你是一位对文字敏感的文风编辑。",
                       temperature=ROLE_TEMPERATURES["style_editor"])

    if not edited:
        edited = state.get("style_edited_draft") or state.get("draft", "")

    return {
        **state,
        "style_edited_draft": edited,
        "style_revise_count": state.get("style_revise_count", 0) + 1,
        "current_stage": "style_edited",
    }


@track_step("human_review", "人工审核", "暂停等待用户审核与反馈")
def human_review_node(state: CollabNovelState) -> CollabNovelState:
    """人工审核节点，实际由 LangGraph 的 interrupt_before 触发暂停。"""
    print("\n--- 👤 人工审核 ---")
    print("当前草稿已就绪，等待人工采纳/修改/提出建议。")

    action = state.get("human_action", "")
    if action == "revise" and state.get("human_feedback"):
        print(f"收到修改意见：{state['human_feedback'][:80]}...")
    elif action == "approved":
        print("人工审核通过。")

    return {
        **state,
        "waiting_for_human": True,
        "current_stage": "human_review",
    }


def human_review_router(state: CollabNovelState) -> str:
    action = state.get("human_action", "")
    # 润色回环硬上限：人工反复「修改」超过 STYLE_REVISE_MAX 次，强制通过进入收尾，
    # 避免 style_edit ↔ human_review 无限空转。
    if state.get("style_revise_count", 0) >= STYLE_REVISE_MAX:
        print(f"⚠️ 人工润色修改已达上限（{STYLE_REVISE_MAX} 次），强制通过进入收尾。")
        return "approved"
    if action == "revise":
        return "revise"
    return "approved"


@track_step("memory_updater", "更新素材记忆", "更新伏笔卡、剧情卡等长期记忆")
def update_memory_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🧠 更新素材记忆 ---")

    prompt = build_update_memory_prompt(state)
    raw = _call_llm(prompt, system="你是一位负责维护小说世界观的资料管理员。",
                    temperature=ROLE_TEMPERATURES["memory_updater"])

    # 简单解析
    try:
        match = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        foreshadowing_updates = match.get("foreshadowing_updates", [])
        plot_updates = match.get("plot_updates", [])
        new_characters = match.get("new_characters", [])
        new_worldviews = match.get("new_worldviews", [])
    except Exception:
        foreshadowing_updates = []
        plot_updates = []
        new_characters = []
        new_worldviews = []

    # 合并回卡片（简单按 id 覆盖）
    existing_foreshadowing = {str(item.get("id", i)): item for i, item in enumerate(state.get("foreshadowing_cards", []))}
    for upd in foreshadowing_updates:
        key = str(upd.get("id", uuid.uuid4().hex))
        existing_foreshadowing[key] = upd

    existing_plots = {str(item.get("id", i)): item for i, item in enumerate(state.get("plot_cards", []))}
    for upd in plot_updates:
        key = str(upd.get("id", uuid.uuid4().hex))
        existing_plots[key] = upd

    # 合并新出场人物 / 新世界观到已有卡片（按 id 覆写，避免重复）
    cards_dir = state.get("cards_dir") or DATA_DIR
    existing_characters = {str(item.get("id", i)): item
                           for i, item in enumerate(state.get("character_cards", []))}
    existing_names = {str(v.get("name", "")).strip()
                      for v in existing_characters.values() if v.get("name")}
    for nc in new_characters:
        if not isinstance(nc, dict):
            continue
        nc_name = str(nc.get("name", "")).strip()
        if nc_name and nc_name in existing_names:
            continue  # 与已有同名人物，跳过避免重复建卡
        key = str(nc.get("id") or f"char_{uuid.uuid4().hex[:6]}")
        existing_characters[key] = nc
        existing_names.add(nc_name)
    existing_worldviews = {str(item.get("id", i)): item
                           for i, item in enumerate(state.get("worldview_cards", []))}
    for nw in new_worldviews:
        if not isinstance(nw, dict):
            continue
        key = str(nw.get("id") or f"world_{uuid.uuid4().hex[:6]}")
        existing_worldviews[key] = nw

    # 写回项目 / 全局 cards 目录
    plot_file = "stories.json" if os.path.exists(os.path.join(cards_dir, "stories.json")) else "plots.json"
    save_card_file("foreshadowing.json", list(existing_foreshadowing.values()), base_dir=cards_dir)
    save_card_file(plot_file, list(existing_plots.values()), base_dir=cards_dir)
    save_card_file("characters.json", list(existing_characters.values()), base_dir=cards_dir)
    save_card_file("wordviews.json", list(existing_worldviews.values()), base_dir=cards_dir)

    new_bits = []
    if new_characters:
        new_bits.append(f"新人物 {len(new_characters)} 个")
    if new_worldviews:
        new_bits.append(f"新世界观 {len(new_worldviews)} 条")
    report = f"更新伏笔 {len(foreshadowing_updates)} 条，剧情 {len(plot_updates)} 条"
    if new_bits:
        report += "，" + "、".join(new_bits)
    print(f"   {report}")

    return {
        **state,
        "foreshadowing_cards": list(existing_foreshadowing.values()),
        "plot_cards": list(existing_plots.values()),
        "character_cards": list(existing_characters.values()),
        "worldview_cards": list(existing_worldviews.values()),
        "update_memory_report": report,
        "current_stage": "memory_updated",
    }


@track_step("canon_proposer", "提出正典提案", "总结本章正典信息")
def propose_canon_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 📜 提出正典提案 ---")

    prompt = build_canon_proposer_prompt(state)
    proposal = _call_llm(prompt, system="你是一位负责维护小说正典的管理员。",
                         temperature=ROLE_TEMPERATURES["canon_proposer"])

    if not proposal:
        proposal = "【默认正典提案】\n本章情节已加入正典，伏笔与剧情已更新。"

    return {
        **state,
        "canon_proposal": proposal,
        "current_stage": "canon_proposed",
    }


@track_step("canon_approver", "审批正典", "判断正典提案是否可入库")
def approve_canon_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- ✅ 审批正典 ---")

    prompt = build_canon_approver_prompt(state)
    result = _call_llm(prompt, system="你是一位把控全书走向的总编。",
                       temperature=ROLE_TEMPERATURES["canon_approver"])
    approved = "APPROVED" in result.upper() or "通过" in result

    if not result:
        approved = state.get("canon_retry_count", 0) >= 2
        result = "【兜底】正典提案通过。" if approved else "提案中的世界观补充需要更具体依据。"

    print(f"   正典审批：{'通过' if approved else '驳回'}")

    return {
        **state,
        "canon_approved": approved,
        "canon_retry_count": state.get("canon_retry_count", 0) + 1,
        "current_stage": "canon_approved" if approved else "canon_rejected",
    }


def approve_canon_router(state: CollabNovelState) -> str:
    if state.get("canon_approved"):
        return "approved"
    if state.get("canon_retry_count", 0) >= 3:
        print("⚠️ 正典反复被驳回，已达上限，强制通过。")
        return "approved"
    return "rejected"


@track_step("committer", "提交定稿", "保存最终章节并结束工作流")
def commit_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 💾 提交定稿 ---")

    final_text = state.get("style_edited_draft") or state.get("draft", "")

    # 项目模式：章节写入 <project>/chapters/ 并记录到 project.json；
    # 演示模式：写入全局 backend/output/。
    project_dir = state.get("project_dir")
    if project_dir:
        path = proj.add_chapter(
            project_dir,
            state.get("chapter_title", "未命名章节"),
            final_text,
        )
    else:
        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        filename = f"chapter_{state.get('session_id', uuid.uuid4().hex)[:8]}.txt"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {state.get('chapter_title', '未命名章节')}\n\n")
            f.write(final_text)

    # #4 正典落盘：审批通过的正典提案追加写入项目的 canon.md（演示模式写 OUTPUT_DIR/canon.md），
    # 形成持续累积的「小说圣经」，供后续章节作为权威事实源。
    if state.get("canon_proposal") and state.get("canon_approved"):
        canon_root = project_dir or OUTPUT_DIR
        try:
            canon_path = proj.append_canon(
                canon_root, state.get("chapter_title", "未命名章节"), state["canon_proposal"]
            )
            print(f"   正典已追加：{canon_path}")
        except Exception as e:
            print(f"⚠️ 正典落盘失败: {e}")

    # #2 结构圣经：定稿后把本章进展追加进全书大纲（outline.md），形成持续演进的结构圣经。
    if state.get("chapter_plan"):
        brief = ""
        for ln in state["chapter_plan"].splitlines():
            if ln.strip():
                brief = ln.strip()[:140]
                break
        if not brief:
            brief = (state.get("previous_summary") or state.get("chapter_title", ""))[:140]
        outline_root = project_dir or OUTPUT_DIR
        no = 0
        if project_dir:
            try:
                no = len(proj.read_meta(project_dir).get("chapters", []))
            except Exception:
                no = 0
        try:
            outline_path = proj.append_outline_entry(
                outline_root, state.get("chapter_title", "未命名章节"), brief, no
            )
            print(f"   大纲已演进：{outline_path}")
        except Exception as e:
            print(f"⚠️ 大纲落盘失败: {e}")

    print(f"   定稿已保存：{path}")

    return {
        **state,
        "final_chapter": final_text,
        "current_stage": "committed",
    }
