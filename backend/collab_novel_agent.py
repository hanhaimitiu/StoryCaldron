#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CollabNovelAgent - 多 Agent 协作小说创作工作流

参考流程（mermaid）：
    LoadContext -> PlanChapter -> ApproveCard -> WriteDraft -> CheckContinuity
    CheckContinuity -- issues found --> FixIssues -> CheckContinuity
    CheckContinuity -- clean --> StyleEdit -> HumanReview
    HumanReview -- revise --> StyleEdit
    HumanReview -- approved --> UpdateMemory -> ProposeCanon -> ApproveCanon
    ApproveCanon -- rejected --> UpdateMemory
    ApproveCanon -- approved --> Commit -> END

每个节点都是一个 Agent（角色 + 提示词），状态由 LangGraph 统一驱动。
"""

import json
import os
import time
import uuid
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime
from functools import wraps

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

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

_llm_cache: Dict[float, ChatOpenAI] = {}

# 默认指向本地 llama.cpp 模型（可用环境变量覆盖）
DEFAULT_LLM_MODEL = r"F:\llm_model\Qwen3.6-35B-A3B-UD-Q3_K_M.gguf"
DEFAULT_LLM_BASE_URL = "http://localhost:8080/v1"
DEFAULT_LLM_API_KEY = "dummy"

# 本地 llama.cpp 服务在 keep-alive 连接复用时会每隔一次返回 404（服务端连接复用 bug），
# 加 Connection: close 让每次请求都新建连接即可规避。接正常服务可置 False。
LLM_FORCE_CONNECTION_CLOSE = True
LLM_MAX_RETRIES = 3


def get_llm(temperature: float = 0.6) -> ChatOpenAI:
    """按温度取 LLM 实例（缓存），避免导入时因缺 Key 报错，也让各角色温度不同。"""
    if temperature not in _llm_cache:
        api_key = os.environ.get("LLM_API_KEY") or DEFAULT_LLM_API_KEY
        extra = {}
        if LLM_FORCE_CONNECTION_CLOSE:
            extra["default_headers"] = {"Connection": "close"}
        _llm_cache[temperature] = ChatOpenAI(
            model=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
            temperature=temperature,
            max_tokens=16384,
            **extra,
        )
    return _llm_cache[temperature]


def _call_llm(
    prompt: str,
    system: str = "你是一位专业的小说创作助手。",
    temperature: float = 0.7,
) -> str:
    """
    调用大模型，失败时返回空字符串供上层降级处理。
    temperature 控制角色温度；失败自动重试（服务端偶发 404/超时时有用）。
    """
    messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
    last_err = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            return get_llm(temperature).invoke(messages).content.strip()
        except Exception as e:
            last_err = e
            print(f"⚠️ LLM 调用失败（第 {attempt + 1}/{LLM_MAX_RETRIES} 次）: {e}")
    print(f"❌ LLM 调用最终失败: {last_err}")
    return ""


# ---------------------------------------------------------------------------
# 工具函数：读写素材卡
# ---------------------------------------------------------------------------
def load_card_file(filename: str, ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    从 backend/data/ 读取卡片 JSON。
    支持：
      - 直接按 id 列表过滤；
      - 未传 id 时返回全部；
      - 文件不存在时返回空列表。
    """
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取 {filename} 失败: {e}")
        return []

    # 统一成列表
    if isinstance(data, dict):
        items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []

    if not ids:
        return items

    result = []
    for id_ in ids:
        id_str = str(id_)
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")) == id_str:
                result.append(item)
                break
    return result


def save_card_file(filename: str, items: List[Dict[str, Any]]):
    """以对象字典形式保存卡片（key = id），保留旧数据并覆盖同名 id。"""
    path = os.path.join(DATA_DIR, filename)
    db: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id", uuid.uuid4().hex))
        db[key] = item

    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def format_cards(cards: List[Dict[str, Any]], title: str = "卡片") -> str:
    """把卡片列表格式化成给 LLM 看的文本。"""
    if not cards:
        return f"【无{title}】"
    lines = [f"### {title}（共 {len(cards)} 条）"]
    for i, card in enumerate(cards, 1):
        name = card.get("name") or card.get("title") or card.get("id") or f"第{i}条"
        content = json.dumps(card, ensure_ascii=False)
        lines.append(f"\n--- 第 {i} 条：{name} ---\n{content}")
    return "\n".join(lines)


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

    # 加载的素材卡
    character_cards: List[Dict[str, Any]]
    plot_cards: List[Dict[str, Any]]
    style_cards: List[Dict[str, Any]]
    foreshadowing_cards: List[Dict[str, Any]]
    worldview_cards: List[Dict[str, Any]]

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


# ---------------------------------------------------------------------------
# 步骤埋点装饰器
# ---------------------------------------------------------------------------
def track_step(node_name: str, step_name: str, description: str):
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


# ---------------------------------------------------------------------------
# Agent 节点
# ---------------------------------------------------------------------------
@track_step("loader", "加载素材上下文", "读取人物卡、剧情卡、文风卡、伏笔卡、世界观卡")
def load_context_node(state: CollabNovelState) -> CollabNovelState:
    """加载外部素材卡到状态，供下游 Agent 使用。"""
    print("\n--- 📚 加载素材上下文 ---")

    # 若调用方已经注入卡片，则不再重复读取
    characters = state.get("character_cards") or load_card_file("characters.json")
    plots = state.get("plot_cards") or load_card_file("stories.json") or load_card_file("plots.json")
    styles = state.get("style_cards") or load_card_file("styles.json")
    foreshadowing = state.get("foreshadowing_cards") or load_card_file("foreshadowing.json")
    worldviews = state.get("worldview_cards") or load_card_file("wordviews.json")

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

    prompt = f"""你是一位资深小说大纲规划师。请根据以下信息，为即将撰写的章节生成一份详细的写作计划。

【上一章概括】
{state.get('previous_summary', '无')}

【本章大纲】
{state.get('chapter_outline', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('plot_cards', []), '剧情卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

请输出：
1. 本章核心目标（本章要解决什么问题、推动哪条剧情线）
2. 出场人物及在本章的任务/状态
3. 关键场景列表（场景地点、人物、核心动作）
4. 需要回收或新埋下的伏笔
5. 节奏与情绪控制建议
6. 预计字数与分段建议

直接输出计划文本，不要额外寒暄。
"""

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

    prompt = f"""你是一位严格的小说责编，负责判断本章计划是否可执行。

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

    style_text = format_cards(state.get("style_cards", []), "文风卡")

    prompt = f"""你是一位经验丰富的专业网文作家。请严格根据以下材料撰写本章正文。

【上一章概括】
{state.get('previous_summary', '无')}

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('plot_cards', []), '剧情卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}
{style_text}

### 输出要求
1. 直接输出完整正文，不要解释、不要开场白、不要结尾总结。
2. 严格按【本章计划】展开，不要偏离大纲。
3. 人物言行符合人设，伏笔铺设自然。
4. 文风完全贴合【文风卡】要求。
5. 段落紧凑，段首缩进两个字符，段与段之间不留空行。
6. 不要刻意埋钩子或升华。
"""

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

    prompt = f"""你是一位小说设定管理员，专门检查草稿是否与已有设定保持一致。

【上一章概括】
{state.get('previous_summary', '无')}

【本章计划】
{state.get('chapter_plan', '无')}

{format_cards(state.get('character_cards', []), '人物卡')}
{format_cards(state.get('foreshadowing_cards', []), '伏笔卡')}
{format_cards(state.get('worldview_cards', []), '世界观卡')}

【当前草稿】
{state.get('draft', '')}

请检查：
1. 人物行为、能力、关系是否与前文/人设冲突；
2. 世界观规则是否被违反；
3. 伏笔是否被正确回收或铺设；
4. 时间线、地点、状态是否连续。

请在第一行输出：CLEAN 或 ISSUES_FOUND
第二行起输出具体问题与修改建议（CLEAN 时简要说明即可）。
"""

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

    prompt = f"""你是一位小说修改专家。请根据连续性检查报告修改草稿，只修正问题，保留原有精彩内容。

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

    prompt = f"""你是一位小说文风编辑。请根据文风卡对当前草稿进行润色，使全文风格统一、语言精炼。

{format_cards(state.get('style_cards', []), '文风卡')}

【本章计划】
{state.get('chapter_plan', '无')}

【当前草稿】
{state.get('draft', '')}

要求：
1. 保留情节和人物行为不变；
2. 仅调整句式、用词、节奏，使其符合文风卡要求；
3. 直接输出润色后的完整正文。
"""

    edited = _call_llm(prompt, system="你是一位对文字敏感的文风编辑。",
                       temperature=ROLE_TEMPERATURES["style_editor"])

    if not edited:
        edited = state.get("draft", "")

    return {
        **state,
        "style_edited_draft": edited,
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
    if action == "revise":
        return "revise"
    return "approved"


@track_step("memory_updater", "更新素材记忆", "更新伏笔卡、剧情卡等长期记忆")
def update_memory_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 🧠 更新素材记忆 ---")

    prompt = f"""你是一位小说资料管理员。请根据本章正文，更新伏笔卡与剧情卡的状态。

【本章计划】
{state.get('chapter_plan', '无')}

【最终正文】
{state.get('style_edited_draft', state.get('draft', ''))}

{format_cards(state.get('foreshadowing_cards', []), '当前伏笔卡')}
{format_cards(state.get('plot_cards', []), '当前剧情卡')}

请输出更新后的内容：
1. 已回收的伏笔（状态改为 resolved）；
2. 新埋下的伏笔（新增条目，状态为 pending）；
3. 剧情卡进度更新（状态改为 completed/in_progress）。

请严格输出 JSON：
{{"foreshadowing_updates": [...], "plot_updates": [...]}}
"""

    raw = _call_llm(prompt, system="你是一位负责维护小说世界观的资料管理员。",
                    temperature=ROLE_TEMPERATURES["memory_updater"])

    # 简单解析
    try:
        match = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        foreshadowing_updates = match.get("foreshadowing_updates", [])
        plot_updates = match.get("plot_updates", [])
    except Exception:
        foreshadowing_updates = []
        plot_updates = []

    # 合并回卡片（简单按 id 覆盖）
    existing_foreshadowing = {str(item.get("id", i)): item for i, item in enumerate(state.get("foreshadowing_cards", []))}
    for upd in foreshadowing_updates:
        key = str(upd.get("id", uuid.uuid4().hex))
        existing_foreshadowing[key] = upd

    existing_plots = {str(item.get("id", i)): item for i, item in enumerate(state.get("plot_cards", []))}
    for upd in plot_updates:
        key = str(upd.get("id", uuid.uuid4().hex))
        existing_plots[key] = upd

    # 写回文件
    save_card_file("foreshadowing.json", list(existing_foreshadowing.values()))
    save_card_file("plots.json" if os.path.exists(os.path.join(DATA_DIR, "plots.json")) else "stories.json",
                   list(existing_plots.values()))

    report = f"更新伏笔 {len(foreshadowing_updates)} 条，剧情 {len(plot_updates)} 条。"
    print(f"   {report}")

    return {
        **state,
        "foreshadowing_cards": list(existing_foreshadowing.values()),
        "plot_cards": list(existing_plots.values()),
        "update_memory_report": report,
        "current_stage": "memory_updated",
    }


@track_step("canon_proposer", "提出正典提案", "总结本章正典信息")
def propose_canon_node(state: CollabNovelState) -> CollabNovelState:
    print("\n--- 📜 提出正典提案 ---")

    final_text = state.get("style_edited_draft") or state.get("draft", "")

    prompt = f"""你是一位小说正典管理员。请根据本章正文生成一份正典提案，记录本章加入官方设定的关键事实。

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

    prompt = f"""你是一位总编，负责审批本章正典提案是否可以写入小说官方设定。

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

    # 保存到 output 目录
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"chapter_{state.get('session_id', uuid.uuid4().hex)[:8]}.txt"
    path = os.path.join(output_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {state.get('chapter_title', '未命名章节')}\n\n")
        f.write(final_text)

    print(f"   定稿已保存：{path}")

    return {
        **state,
        "final_chapter": final_text,
        "current_stage": "committed",
    }


# ---------------------------------------------------------------------------
# 构建 LangGraph
# ---------------------------------------------------------------------------
checkpointer = MemorySaver()

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
) -> Dict[str, Any]:
    """初始化一章创作会话，加载指定卡片。未指定 id 则加载全部。"""
    sid = session_id or f"collab_{uuid.uuid4().hex[:12]}"

    initial_state: CollabNovelState = {
        "session_id": sid,
        "chapter_title": chapter_title,
        "chapter_outline": chapter_outline,
        "previous_summary": previous_summary,
        "character_cards": load_card_file("characters.json", character_ids),
        "plot_cards": load_card_file("stories.json", plot_ids) or load_card_file("plots.json", plot_ids),
        "style_cards": load_card_file("styles.json", style_ids),
        "foreshadowing_cards": load_card_file("foreshadowing.json", foreshadowing_ids),
        "worldview_cards": load_card_file("wordviews.json", worldview_ids),
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

    print("\n▶️ 开始执行（将在人工审核处真实暂停）")
    app.invoke(state, config)

    idx = 0
    while True:
        gs = app.get_state(config)
        if not gs.next:
            print("🏁 工作流结束")
            break
        if "human_review" not in gs.next:
            print(f"⚠️ 停在非预期节点 {gs.next}，停止")
            break

        # —— 这里是真实的暂停点，模拟人工介入 ——
        review = reviews[idx] if idx < len(reviews) else {"action": "approved"}
        idx += 1
        print(f"\n⏸️ 已暂停在人工审核，应用第 {idx} 次人工动作：{review}")

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
