#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 协作创作工作流 —— 状态、类型与共享常量定义。

把 LangGraph 的状态结构（CollabNovelState / StepLog）、步骤埋点装饰器
track_step，以及全局配置常量集中在此，供 prompts / nodes / 主模块复用，
避免 collab_novel_agent.py 单文件过长（>800 行红线，见 AGENTS.md 第 5.1 节）。
"""

import os
import time
from datetime import datetime
from functools import wraps
from typing import TypedDict, Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# 全局配置（路径 / LLM / 循环上限）
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# 每个 Agent 角色的温度：判断型（规划/审批/检查/正典）求稳用低温，
# 创作型（写作/修复/润色）求变用高温。避免所有角色共用一个温度。
ROLE_TEMPERATURES = {
    "planner": 0.4,
    "card_approver": 0.2,
    "writer": 0.9,
    "continuity_checker": 0.2,
    "continuity_fixer": 0.7,
    "style_editor": 0.5,
    "memory_updater": 0.3,
    "canon_proposer": 0.4,
    "canon_approver": 0.2,
}

# LLM 实例按温度缓存，避免重复创建连接；键为温度，值延迟到 llm.py 填充。
_llm_cache: Dict[float, Any] = {}

# 默认指向本地 llama.cpp 模型（可用环境变量覆盖）
DEFAULT_LLM_MODEL = r"F:\llm_model\Qwen3.6-35B-A3B-UD-Q3_K_M.gguf"
DEFAULT_LLM_BASE_URL = "http://localhost:8080/v1"
DEFAULT_LLM_API_KEY = "dummy"

# 本地 llama.cpp 服务在 keep-alive 连接复用时会每隔一次返回 404（服务端连接复用 bug），
# 加 Connection: close 让每次请求都新建连接即可规避。接正常服务可置 False。
LLM_FORCE_CONNECTION_CLOSE = True
LLM_MAX_RETRIES = 3
# 润色回环硬上限：人工反复「修改」超过此次数后，强制通过进入收尾，
# 避免 style_edit ↔ human_review 空转（上下文规模恒定，但仍需给人工一个出口）。
STYLE_REVISE_MAX = 5

# 检查点落盘文件（会话持久化 / 崩溃恢复，对应 #8）。
CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoints.pkl")


# ---------------------------------------------------------------------------
# 状态定义
# ---------------------------------------------------------------------------
class StepLog(TypedDict):
    step_id: str
    node_name: str
    step_name: str
    description: str
    output: str
    status: str
    timestamp: str
    duration_ms: int


class CollabNovelState(TypedDict, total=False):
    # 输入与上下文
    session_id: str
    chapter_title: str
    chapter_outline: str
    previous_summary: str
    prior_chapters: str  # 跨章节检索得到的近期章节前情片段（#1）
    book_outline: str    # 全书大纲/结构圣经（#2），规划节点参考、定稿后演进

    # 加载的素材卡
    character_cards: List[Dict[str, Any]]
    plot_cards: List[Dict[str, Any]]
    style_cards: List[Dict[str, Any]]
    foreshadowing_cards: List[Dict[str, Any]]
    worldview_cards: List[Dict[str, Any]]
    anti_ai_cards: List[Dict[str, Any]]  # 去AI风卡：写作/润色节点据此规避 AI 套路文风

    # 工作流中间产物
    chapter_plan: str
    plan_approved: bool
    draft: str
    continuity_report: str
    continuity_has_issue: bool
    style_edited_draft: str
    human_feedback: str
    human_action: str
    update_memory_report: str
    canon_proposal: str
    canon_approved: bool
    final_chapter: str

    # 控制与日志
    current_stage: str
    step_logs: List[StepLog]
    error_msg: Optional[str]

    # 循环计数器，防止无限循环
    plan_retry_count: int
    continuity_fix_count: int
    style_revise_count: int
    canon_retry_count: int

    # 兼容中断恢复
    waiting_for_human: bool
    is_terminated: bool

    # 项目工作区（项目模式时由 start_session 注入；演示模式为空）
    project_dir: str
    cards_dir: str
    chapters_dir: str


# ---------------------------------------------------------------------------
# 步骤埋点装饰器
# ---------------------------------------------------------------------------
def track_step(node_name: str, step_name: str, description: str):
    """包裹节点函数，自动记录步骤日志（开始/成功/失败、耗时、简短输出）。

    日志不进 LLM prompt（仅写入 step_logs 供前端展示），因此不会撑大上下文。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(state: CollabNovelState) -> CollabNovelState:
            start = time.time()
            logs = state.get("step_logs", [])
            log: StepLog = {
                "step_id": f"{node_name}_{int(time.time() * 1000)}",
                "node_name": node_name,
                "step_name": step_name,
                "description": description,
                "output": "",
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 0,
            }
            logs.append(log)
            state = {**state, "step_logs": logs, "current_stage": step_name}

            try:
                result = func(state)
                duration_ms = int((time.time() - start) * 1000)
                result["step_logs"] = result.get("step_logs", logs)
                result["step_logs"][-1]["status"] = "success"
                result["step_logs"][-1]["duration_ms"] = duration_ms
                # 记录简短输出
                short = ""
                if result.get("draft"):
                    short = str(result["draft"])[:300]
                elif result.get("chapter_plan"):
                    short = str(result["chapter_plan"])[:300]
                result["step_logs"][-1]["output"] = short
                return result
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                logs[-1]["status"] = "failed"
                logs[-1]["description"] = f"{description} 出错: {e}"
                logs[-1]["duration_ms"] = duration_ms
                return {**state, "error_msg": str(e), "step_logs": logs}
        return wrapper
    return decorator
