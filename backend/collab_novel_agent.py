#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CollabNovelAgent - 多 Agent 协作小说创作工作流（编排入口）

参考流程（mermaid）：
    LoadContext -> PlanChapter -> ApproveCard -> WriteDraft -> CheckContinuity
    CheckContinuity -- issues found --> FixIssues -> CheckContinuity
    CheckContinuity -- clean --> StyleEdit -> HumanReview
    HumanReview -- revise --> StyleEdit
    HumanReview -- approved --> UpdateMemory -> ProposeCanon -> ApproveCanon
    ApproveCanon -- rejected --> UpdateMemory
    ApproveCanon -- approved --> Commit -> END

每个节点都是一个 Agent（角色 + 提示词），状态由 LangGraph 统一驱动。
本文件只负责：图编译、检查点持久化、对外 API（start_session / run_session /
submit_human_action / run_with_manual_review）。节点实现见 nodes.py，提示词见
prompts.py，状态/常量见 state.py，LLM/卡片工具见 llm.py（拆分详见 AGENTS.md 第 5.1 节）。
"""

import os
import pickle
import threading
import uuid
from collections import defaultdict
from typing import TypedDict, Optional, List, Dict, Any

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import InMemorySaver

import project as proj

from state import CollabNovelState, CHECKPOINT_FILE, DATA_DIR, OUTPUT_DIR
from llm import load_card_file, save_card_file, _call_llm
from nodes import (
    load_context_node,
    plan_chapter_node,
    approve_card_node,
    approve_card_router,
    write_draft_node,
    check_continuity_node,
    continuity_router,
    fix_issues_node,
    style_edit_node,
    human_review_node,
    human_review_router,
    update_memory_node,
    propose_canon_node,
    approve_canon_node,
    approve_canon_router,
    commit_node,
)


# ---------------------------------------------------------------------------
# 检查点持久化（会话持久化 / 崩溃恢复，对应 #8）
# ---------------------------------------------------------------------------
# 用落盘版 Checkpointer 替代内存级 MemorySaver：复用 InMemorySaver 的全部读写逻辑，
# 仅在每次 put / put_writes 后把 storage / writes / blobs 整体 pickle 到磁盘，
# 重启后按 thread_id（=sid）恢复；崩溃恢复时也能从最近一个检查点续跑。
def _storage_inner_factory():
    """可 pickle 的默认工厂（lambda 无法序列化，故用模块级函数）。"""
    return defaultdict(dict)


class FileCheckpointer(InMemorySaver):
    """把检查点落盘到 CHECKPOINT_FILE 的 Checkpointer。"""

    def __init__(self, path: str, *, serde=None):
        super().__init__(serde=serde)
        self._path = path
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "rb") as f:
                data = pickle.load(f)
            self.storage = defaultdict(_storage_inner_factory, data.get("storage", {}) or {})
            self.writes = defaultdict(dict, data.get("writes", {}) or {})
            self.blobs = defaultdict(dict, data.get("blobs", {}) or {})
        except Exception as e:
            print(f" 加载会话检查点失败（将新建）: {e}")

    def _save(self):
        # 转成可 pickle 的纯 dict 再写（避免 defaultdict 的 lambda 工厂无法序列化）
        storage_plain = {t: dict(ns_map) for t, ns_map in self.storage.items()}
        writes_plain = dict(self.writes)
        blobs_plain = dict(self.blobs)
        tmp = self._path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(
                {"storage": storage_plain, "writes": writes_plain, "blobs": blobs_plain},
                f, protocol=pickle.HIGHEST_PROTOCOL,
            )
        os.replace(tmp, self._path)

    def put(self, config, checkpoint, metadata, new_versions):
        with self._lock:
            ret = super().put(config, checkpoint, metadata, new_versions)
            self._save()
        return ret

    def put_writes(self, config, writes, task_id, task_path=""):
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)
            self._save()

    def delete_thread(self, thread_id):
        with self._lock:
            super().delete_thread(thread_id)
            self._save()


checkpointer = FileCheckpointer(CHECKPOINT_FILE)

graph = StateGraph(CollabNovelState)
graph.add_node("load_context", load_context_node)
graph.add_node("plan_chapter", plan_chapter_node)
graph.add_node("approve_card", approve_card_node)
graph.add_node("write_draft", write_draft_node)
graph.add_node("check_continuity", check_continuity_node)
graph.add_node("fix_issues", fix_issues_node)
graph.add_node("style_edit", style_edit_node)
graph.add_node("human_review", human_review_node)
graph.add_node("update_memory", update_memory_node)
graph.add_node("propose_canon", propose_canon_node)
graph.add_node("approve_canon", approve_canon_node)
graph.add_node("commit", commit_node)

graph.add_edge(START, "load_context")
graph.add_edge("load_context", "plan_chapter")
graph.add_edge("plan_chapter", "approve_card")
graph.add_conditional_edges(
    "approve_card",
    approve_card_router,
    {"approved": "write_draft", "rejected": "plan_chapter"},
)
graph.add_edge("write_draft", "check_continuity")
graph.add_conditional_edges(
    "check_continuity",
    continuity_router,
    {"issues_found": "fix_issues", "clean": "style_edit"},
)
graph.add_edge("fix_issues", "check_continuity")
graph.add_edge("style_edit", "human_review")
graph.add_conditional_edges(
    "human_review",
    human_review_router,
    {"revise": "style_edit", "approved": "update_memory"},
)
graph.add_edge("update_memory", "propose_canon")
graph.add_edge("propose_canon", "approve_canon")
graph.add_conditional_edges(
    "approve_canon",
    approve_canon_router,
    {"approved": "commit", "rejected": "update_memory"},
)
graph.add_edge("commit", END)

# 在 human_review 前暂停，等待用户反馈
app = graph.compile(checkpointer=checkpointer, interrupt_before=["human_review"])


# ---------------------------------------------------------------------------
# 对外 API（供 TUI / 测试脚本调用）
# ---------------------------------------------------------------------------
def start_session(
    session_id: Optional[str] = None,
    chapter_title: str = "",
    chapter_outline: str = "",
    previous_summary: str = "",
    character_ids: Optional[List[str]] = None,
    plot_ids: Optional[List[str]] = None,
    style_ids: Optional[List[str]] = None,
    foreshadowing_ids: Optional[List[str]] = None,
    worldview_ids: Optional[List[str]] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """初始化一章创作会话。

    project_dir 为项目工作区目录时，从 <project>/cards/ 读取素材卡，章节写回 <project>/chapters/；
    省略则沿用全局 DATA_DIR / OUTPUT_DIR（演示模式）。未指定 id 则加载全部卡片。
    """
    sid = session_id or f"collab_{uuid.uuid4().hex[:12]}"

    # 项目模式：卡片与章节都落在项目目录内
    if project_dir:
        cards_dir = os.path.join(project_dir, "cards")
        chapters_dir = os.path.join(project_dir, "chapters")
    else:
        cards_dir = DATA_DIR
        chapters_dir = OUTPUT_DIR

    # —— 跨章节上下文（#1）——
    # prior_chapters：近期章节截断前情片段，给写作/规划/连续性检查节点当检索上下文；
    # previous_summary：用户没给时，自动取【上一章全文】（而非截断摘要），
    #   让写作节点以 One Shot 方式直接模仿上一章文风与行文节奏（仅项目模式有效）。
    prior_chapters = ""
    if project_dir:
        prior_chapters = proj.get_recent_chapter_excerpts(project_dir, recent_n=2, tail_chars=900)
        if not previous_summary:
            previous_summary = proj.get_recent_chapter_full(project_dir)

    # —— 全书大纲/结构圣经（#2）——
    # 项目模式加载 outline.md，供规划节点对齐整体走向；定稿后再把本章进展追加回去。
    book_outline = proj.load_outline(project_dir) if project_dir else ""

    initial_state: CollabNovelState = {
        "session_id": sid,
        "chapter_title": chapter_title,
        "chapter_outline": chapter_outline,
        "previous_summary": previous_summary,
        "prior_chapters": prior_chapters,
        "book_outline": book_outline,
        "character_cards": load_card_file("characters.json", character_ids, cards_dir),
        "plot_cards": load_card_file("stories.json", plot_ids, cards_dir) or load_card_file("plots.json", plot_ids, cards_dir),
        "style_cards": load_card_file("styles.json", style_ids, cards_dir),
        "foreshadowing_cards": load_card_file("foreshadowing.json", foreshadowing_ids, cards_dir),
        "worldview_cards": load_card_file("wordviews.json", worldview_ids, cards_dir),
        "chapter_plan": "",
        "plan_approved": False,
        "draft": "",
        "continuity_report": "",
        "continuity_has_issue": False,
        "style_edited_draft": "",
        "human_feedback": "",
        "human_action": "",
        "update_memory_report": "",
        "canon_proposal": "",
        "canon_approved": False,
        "final_chapter": "",
        "current_stage": "start",
        "step_logs": [],
        "error_msg": None,
        "plan_retry_count": 0,
        "continuity_fix_count": 0,
        "style_revise_count": 0,
        "canon_retry_count": 0,
        "waiting_for_human": False,
        "is_terminated": False,
        "project_dir": project_dir or "",
        "cards_dir": cards_dir,
        "chapters_dir": chapters_dir,
    }

    return {"session_id": sid, "state": initial_state}


def run_session(state: CollabNovelState, auto_approve_human: bool = False) -> CollabNovelState:
    """运行完整工作流。若 auto_approve_human=True，则自动通过人工审核（用于无 TUI 测试）。"""
    sid = state.get("session_id", uuid.uuid4().hex)
    config = {"configurable": {"thread_id": sid}}

    # 第一次 invoke，会停在 human_review 前
    app.invoke(state, config)
    graph_state = app.get_state(config)
    current_state = graph_state.values

    # 自动通过人工审核（测试模式）
    if auto_approve_human and "human_review" in graph_state.next:
        app.update_state(config, {"human_action": "approved", "waiting_for_human": False})
        app.invoke(None, config)
        graph_state = app.get_state(config)
        current_state = graph_state.values

    return current_state


def submit_human_action(
    session_id: str,
    action: str,
    feedback: str = "",
    edited_draft: str = "",
) -> Dict[str, Any]:
    """提交人工审核结果并继续运行。"""
    config = {"configurable": {"thread_id": session_id}}

    updates: Dict[str, Any] = {
        "waiting_for_human": False,
        "human_action": action,
        "human_feedback": feedback,
    }

    if action == "revise":
        if feedback:
            updates["feedback"] = feedback
    elif action == "edit":
        updates["style_edited_draft"] = edited_draft or feedback
    elif action == "approved":
        pass
    else:
        raise ValueError(f"未知人工操作: {action}")

    app.update_state(config, updates)
    app.invoke(None, config)
    graph_state = app.get_state(config)

    return {
        "session_id": session_id,
        "status": graph_state.values.get("current_stage", "unknown"),
        "state": graph_state.values,
    }


def run_with_manual_review(
    state: CollabNovelState,
    reviews: List[Dict[str, Any]],
) -> CollabNovelState:
    """
    带真实暂停的运行方式：每次流程停在 human_review 前，就取一条 review 应用后继续。

    reviews 是人工动作列表，每个元素形如：
        {"action": "approved"}
        {"action": "revise", "feedback": "……修改意见……"}
        {"action": "edit", "edited_draft": "……人工改后的全文……"}
    列表用完仍未结束时，后续暂停一律按 approved 处理。
    返回最终状态。
    """
    sid = state.get("session_id", uuid.uuid4().hex)
    config = {"configurable": {"thread_id": sid}}

    print("\n 开始执行（将在人工审核处真实暂停）")
    app.invoke(state, config)

    idx = 0
    while True:
        gs = app.get_state(config)
        if not gs.next:
            print(" 工作流结束")
            break
        if "human_review" not in gs.next:
            print(f" 停在非预期节点 {gs.next}，停止")
            break

        # —— 这里是真实的暂停点，模拟人工介入 ——
        review = reviews[idx] if idx < len(reviews) else {"action": "approved"}
        idx += 1
        print(f"\n 已暂停在人工审核，应用第 {idx} 次人工动作：{review}")

        updates: Dict[str, Any] = {
            "waiting_for_human": False,
            "human_action": review.get("action", "approved"),
            "human_feedback": review.get("feedback", ""),
        }
        if review.get("action") == "edit":
            updates["style_edited_draft"] = review.get("edited_draft", "")

        app.update_state(config, updates)
        app.invoke(None, config)

    return app.get_state(config).values


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 创建一些测试素材卡（仅首次运行用于演示）
    test_chars = [{
        "id": "hero",
        "name": "陆青崖",
        "gender": "男",
        "appearance": "青色长袍，眉间有一道旧疤",
        "personality": "沉稳、重情义，遇到不公会挺身而出",
        "identity": "青云宗外门弟子",
        "ability": "剑术初入门槛，体内封印未解",
    }]
    test_plots = [{
        "id": "main_1",
        "title": "入门考核",
        "status": "in_progress",
        "description": "陆青崖参加青云宗外门考核，需在秘境中存活三日",
    }]
    test_styles = [{
        "id": "style_1",
        "title": "古风仙侠",
        "style_overall": "古风/热血/细腻",
        "sentence_feature": "长短句交错，打斗场景短促，心理描写绵长",
        "word_preference": "常用“剑光”“灵气”“眸子”等词汇",
    }]
    test_foreshadowing = [{
        "id": "fore_1",
        "content": "陆青崖眉间旧疤与秘境中的古剑有神秘联系",
        "status": "pending",
    }]
    test_worldviews = [{
        "id": "world_1",
        "world_theme": "低魔仙侠宗门世界",
        "power_system": "炼气、筑基、金丹、元婴",
        "world_rule": "灵气稀薄，功法传承严苛",
    }]

    save_card_file("characters.json", test_chars)
    save_card_file("plots.json", test_plots)
    save_card_file("styles.json", test_styles)
    save_card_file("foreshadowing.json", test_foreshadowing)
    save_card_file("wordviews.json", test_worldviews)

    result = start_session(
        chapter_title="第一章 入门考核",
        chapter_outline="陆青崖进入青云宗秘境参加考核，遭遇妖兽围攻，在危急时刻发现眉间旧疤与一把古剑产生共鸣。",
        previous_summary="陆青崖自幼被青云宗长老收养，今日迎来外门考核。",
    )

    # 演示【真实暂停】：第一次停在人工审核时提修改意见（流程回到文风润色重排后再停），
    # 第二次停在人工审核时点通过，流程继续到提交定稿。
    # 若想跳过人工介入快速跑完，可改用 run_session(result["state"], auto_approve_human=True)
    final_state = run_with_manual_review(result["state"], reviews=[
        {"action": "revise",
         "feedback": "开头环境描写太满，压缩成两三句，尽快让妖兽冲突出现。"},
        {"action": "approved"},
    ])

    print("\n=== 最终状态 ===")
    print(f"阶段：{final_state.get('current_stage')}")
    print(f"计划通过：{final_state.get('plan_approved')}")
    print(f"正典通过：{final_state.get('canon_approved')}")
    print(f"输出文件：{final_state.get('final_chapter', '')[:200]}...")
