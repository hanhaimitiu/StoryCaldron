import json
import os
import time
from typing import TypedDict, Optional, List
from datetime import datetime
from functools import wraps

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

# 全局状态存储
agent_states = {}
checkpoint_storage = MemorySaver()

llm = ChatOpenAI(
    model="glm-5",
    api_key="sk-0a9abe3a8a2241079b881333fad52c1a",
    base_url="http://localhost:8080",
    temperature=0.6,
    max_tokens=16384
)

writer_system_prompt = """你是一个经验丰富的专业网文作家。你的任务是根据提供的资料撰写或修改小说正文。

### 【创作参考资料】
1. **上一章概括**：{prev_summary}
2. **本章大纲**：{next_outline}
3. **文风要求**：{style_requirement}
4. **涉及角色设定**：{character_profiles}
5. **相关世界观/背景**：{worldview_settings}

### 【当前工作状态】
- **上一版草稿**：{previous_draft}  <-- 如果没有则为空
- **修改意见**：{revision_feedback}  <-- 如果没有则为空

### 【核心执行准则】
1. **判断工作模式**：
   - 如果【上一版草稿】和【修改意见】为空，请根据大纲和设定**从头撰写**本章正文。
   - 如果【上一版草稿】和【修改意见】不为空，请**保留上一版草稿中符合要求的部分**，仅针对【修改意见】中指出的问题进行**定向修改和润色**。严禁全盘重写或丢失原本精彩的细节。
2. **严格遵循大纲与设定**：无论初稿还是修改稿，都必须确保剧情不偏离大纲，人设不崩坏，世界观逻辑自洽。
3. **完美承上启下**：确保开头与上一章无缝衔接，人物状态连贯。
4. **文风精准把控**：全文遣词造句必须贴合要求的文风。

### 【输出要求】
- 直接输出完整的小说正文（修改模式下，请输出修改后的完整全文，不要只输出修改的片段）。
- 不需要输出任何解释性语言、开场白或结尾总结。
- 禁止结尾埋下勾子，或者升华
- 请保持段落紧凑，段落之间不要留空行，每段开头缩进两个字符。
"""

reviewer_system_prompt = """你是一位专业的小说审稿编辑。你的任务是对提交的小说草稿进行全面审核，判断是否需要修改，并给出具体的修改意见。

### 【审核参考资料】
1. **本章大纲**：{next_outline}
2. **上一章概括**：{prev_summary}
3. **角色设定**：{character_profiles}
4. **世界观/背景**：{worldview_settings}
5. **文风要求**：{style_requirement}
6. **当前草稿**：{current_draft}
7. **上一轮修改意见**：{feedback}

### 【审核维度】
1. **情节合理性**：是否符合大纲，逻辑是否通顺，是否有明显的漏洞或不合理之处。
2. **人物塑造**：人物言行是否符合设定，性格是否鲜明，情感是否真实。
3. **文风统一**：语言风格是否符合要求，是否保持一致。
4. **内容质量**：描写是否生动，对话是否自然，节奏是否得当。
5. **字数要求**：篇幅是否适中。

### 【输出格式】
请在第一行明确输出审核结果：
- 如果通过审核，输出：PASS
- 如果需要修改，输出：REJECT

然后在下一行开始输出详细的审核意见（如果通过也可以简要说明理由）。
"""

class StepLog(TypedDict):
    step_id: str
    node_name: str
    step_name: str
    description: str
    output: str
    status: str
    timestamp: str
    duration_ms: int

class ChapterState(TypedDict):
    draft: str | None
    previous_plot: str | None
    input: str | None
    characters: Optional[list[str]]
    styles: Optional[list[str]]
    outlines: Optional[list[str]]
    world_views: str | None
    feedback: str | None
    revision_count: int
    need_revision: str | None
    human_feedback: str | None
    current_stage: str | None
    step_logs: List[StepLog]
    session_id: str | None
    is_paused: bool
    is_terminated: bool
    edited_draft: str | None
    human_suggestions: Optional[list[str]]
    human_action: str | None
    waiting_for_human: bool
    interrupt_data: dict | None

def readfrom(filename: str, ids: list) -> list:
    base_path = os.path.join(os.path.dirname(__file__), 'data')
    file_path = os.path.join(base_path, filename)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        result = []
        
        # 如果 data 是字典（键是 ID）
        if isinstance(data, dict):
            for id in ids:
                id_str = str(id)
                # 先尝试直接用 ID 作为键
                if id_str in data:
                    result.append(data[id_str])
                else:
                    # 尝试在值对象中匹配 id 字段
                    for key, value in data.items():
                        if isinstance(value, dict) and str(value.get('id', '')) == id_str:
                            result.append(value)
                            break
        
        # 如果 data 是列表
        elif isinstance(data, list):
            for id in ids:
                id_str = str(id)
                for item in data:
                    if isinstance(item, dict):
                        if str(item.get('id', '')) == id_str:
                            result.append(item)
                            break
        
        return result
    except Exception as e:
        print(f"读取文件失败: {filename}, 错误: {e}")
        return []

# ======================
# 步骤埋点装饰器（参考示例）
# ======================
def track_step(node_name: str, step_name: str, description: str):
    def decorator(func):
        @wraps(func)
        def wrapper(state: ChapterState):
            start_time = time.time()
            print(f"\n--- {'✍️' if node_name == 'writer' else '🔍' if node_name == 'reviewer' else '🧑‍💻' if node_name == 'human' else '📄'} {step_name} ---")
            
            # 添加开始日志
            step_logs = state.get("step_logs", [])
            new_log: StepLog = {
                "step_id": f"{node_name}_{int(time.time() * 1000)}",
                "node_name": node_name,
                "step_name": step_name,
                "description": description,
                "output": "",
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 0
            }
            step_logs.append(new_log)
            state = {**state, "step_logs": step_logs, "current_stage": step_name}
            
            try:
                result = func(state)
                
                # 添加成功日志
                duration_ms = int((time.time() - start_time) * 1000)
                output = result.get("draft", "") if isinstance(result, dict) else ""
                state = result
                state["step_logs"][-1]["status"] = "success"
                state["step_logs"][-1]["output"] = output[:500] if output else ""
                state["step_logs"][-1]["duration_ms"] = duration_ms
                return state
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                state["step_logs"][-1]["status"] = "failed"
                state["step_logs"][-1]["description"] = f"{description}过程中发生错误: {str(e)}"
                state["step_logs"][-1]["duration_ms"] = duration_ms
                state["error_msg"] = str(e)
                return state
        return wrapper
    return decorator

# ======================
# 业务节点
# ======================
@track_step(node_name="writer", step_name="撰稿人正在创作", description="根据提供的大纲和设定开始撰写本章正文")
def writer_node(state: ChapterState) -> ChapterState:
    prev_summary = state.get("previous_plot", "")
    next_outline = state.get("input", "")
    style_requirement = str(state.get("styles", ""))
    character_profiles = str(state.get("characters", ""))
    worldview_settings = str(state.get("world_views", ""))
    revision_feedback = state.get("feedback", "")
    previous_draft = state.get("draft", "")

    formatted_prompt = writer_system_prompt.format(
        prev_summary=prev_summary,
        next_outline=next_outline,
        style_requirement=style_requirement,
        character_profiles=character_profiles,
        worldview_settings=worldview_settings,
        previous_draft=previous_draft,
        revision_feedback=revision_feedback
    )

    messages = [
        SystemMessage(content="你是一个经验丰富的专业网文作家..."),
        HumanMessage(content=formatted_prompt)
    ]

    print("🚀 正在调用大语言模型生成草稿...")
    try:
        response = llm.invoke(messages)
        draft_content = response.content.strip()
        
        if not draft_content:
            raise ValueError("模型返回内容为空")
    except Exception as e:
        print(f"⚠️ 模型调用失败，使用模拟内容: {str(e)}")
        draft_content = f"""【章节正文】
            
根据大纲：{next_outline[:50]}...

玄夜璃缓缓睁开了眼睛，发现自己躺在冰冷的石棺之中。她屏住呼吸，仔细聆听着周围的动静。陵墓中一片寂静，只有微弱的风声从远处传来。

她轻轻推开棺盖，小心翼翼地走了出来。月光透过石缝洒落进来，照亮了她苍白的脸庞。这是她计划中的第一步——假死脱身。"""

    return {
        **state,
        "draft": draft_content, 
        "current_stage": "writing_complete"
    }

@track_step(node_name="reviewer", step_name="审稿人正在审核", description="对当前草稿进行全方位审核")
def reviewer_node(state: ChapterState) -> ChapterState:
    prev_summary = state.get("previous_plot", "")
    next_outline = state.get("input", "")
    style_requirement = str(state.get("styles", ""))
    character_profiles = str(state.get("outlines", ""))
    worldview_settings = str(state.get("world_views", ""))
    revision_feedback = state.get("feedback", "")
    draft = state.get("draft", "")

    formatted_prompt = reviewer_system_prompt.format(
        next_outline=next_outline,
        prev_summary=prev_summary,
        character_profiles=character_profiles,
        worldview_settings=worldview_settings,
        style_requirement=style_requirement,
        current_draft=draft,
        feedback=revision_feedback
    )

    print("🚀 正在调用大语言模型审核草稿...")
    messages = [
        SystemMessage(content="你是一位专业的小说审稿编辑..."),
        HumanMessage(content=formatted_prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        review_result = response.content.strip()
        
        if "PASS" in review_result or "通过" in review_result or "无需修改" in review_result:
            status = "PASS"
            feedback = review_result
        else:
            status = "REJECT"
            feedback = review_result
    except Exception as e:
        print(f"⚠️ 模型调用失败，使用模拟审核结果: {str(e)}")
        revision_count = state.get("revision_count", 0)
        if revision_count == 0:
            status = "REJECT"
            feedback = "整体构思不错，但人物情感描写可以更细腻一些。建议增加玄夜璃从假死状态苏醒时的心理活动描写。"
        else:
            status = "PASS"
            feedback = "修改稿质量明显提升，人物塑造更加立体，可以进入人工审核阶段。"

    return {
        **state,
        "feedback": feedback,
        "revision_count": state.get("revision_count", 0) + 1,
        "need_revision": status,
        "current_stage": "review_complete"
    }

@track_step(node_name="human", step_name="等待人工审核", description="暂停执行，等待人工介入")
def human_node(state: ChapterState) -> ChapterState:
    """人工审核节点 - 这里会被 interrupt_before 暂停"""
    print("🧑‍💻 人工审核节点 - 用户可以在此编辑草稿或提交修改意见")
    
    # 获取用户之前提交的操作
    human_action = state.get("human_action", "")
    
    if human_action == "edit" and state.get("edited_draft"):
        state["draft"] = state["edited_draft"]
        state["need_revision"] = "PASS"
    
    elif human_action == "suggest" and state.get("human_suggestions"):
        suggestion_text = "\n".join(state["human_suggestions"])
        state["feedback"] = suggestion_text
        state["need_revision"] = "REJECT"
    
    return state

@track_step(node_name="printer", step_name="输出最终草稿", description="输出最终草稿，任务结束")
def printer_node(state: ChapterState) -> ChapterState:
    print(state.get("draft", "草稿为空"))
    return {**state, "current_stage": "finished"}

def router_node(state: ChapterState) -> str:
    """路由决策节点"""
    if state.get("is_terminated", False):
        print("\n--- 🚦 路由决策：会话已终止 → 结束")
        return "end"

    need_revision = state.get("need_revision", "")
    revision_count = state.get("revision_count", 0)

    print(f"\n--- 🚦 路由决策 ---")
    print(f"need_revision: {need_revision}")
    print(f"revision_count: {revision_count}")

    # 修改次数达到上限，进入人工审核（必须用户介入判断是否继续）
    if revision_count >= 3:
        print("⚠️ AI修改次数已达上限 → 转交人类处理")
        return "human"

    # 第一次审稿后（revision_count=1），始终进入人工审核（让用户看到 AI 初稿后决定）
    if revision_count == 1:
        print("👀 首轮审稿完成 → 转交人工审核")
        return "human"

    # 审核通过且已是多轮中的最后一次（PASS 且轮数 > 1），结束
    if need_revision == "PASS" and revision_count > 1:
        print("✅ 审核通过，多轮修改结束 → 任务结束")
        return "end"

    # 有明确需要修改的意见，进入写作节点继续创作
    if need_revision == "REJECT":
        print(f"➡️ 审稿人提出修改意见（第 {revision_count} 轮）→ 重新创作")
        return "write"

    print(f"➡️ 默认路由：继续写作（轮次 {revision_count}）")
    return "write"

def human_router(state: ChapterState) -> str:
    """从 human 节点出来后，根据用户选择决定下一步"""
    if state.get("is_terminated", False):
        print("🧑‍💻 → 用户选择终止 → 结束")
        return "end"

    human_action = state.get("human_action", "")
    need_revision = state.get("need_revision", "")
    revision_count = state.get("revision_count", 0)

    print(f"\n--- 🧑‍💻 人工审核后决策 ---")
    print(f"human_action: {human_action}")
    print(f"need_revision: {need_revision}")
    print(f"revision_count: {revision_count}")

    # 用户终止
    if human_action == "terminate":
        print("❌ 用户终止 → 结束")
        return "end"

    # 用户编辑了草稿 → 用新草稿作为最终稿，结束
    if human_action == "edit":
        print("✏️ 用户已编辑草稿 → 采用新稿并结束")
        return "end"

    # 用户只是点"继续"且审核状态是 PASS → 结束
    if human_action == "continue" and need_revision == "PASS":
        print("✅ 用户确认通过 → 结束")
        return "end"

    # 用户提了建议 或 继续但需要修改 → 回到 writer 重新创作
    print("🔄 回到写作节点继续创作")
    return "write"

# ======================
# 构建图（使用 interrupt_before 机制）
# ======================
graph = StateGraph(ChapterState)
graph.add_node("reviewer", reviewer_node)
graph.add_node("writer", writer_node)
graph.add_node("human", human_node)
graph.add_node("printer", printer_node)
graph.add_edge(START, "writer")
graph.add_edge("writer", "reviewer")
graph.add_conditional_edges("reviewer", router_node, {
    "human": "human",
    "write": "writer",
    "end": "printer"
})
# 从 human 出来后按 human_router 决定去向（支持多次循环）
graph.add_conditional_edges("human", human_router, {
    "write": "writer",
    "end": "printer"
})
graph.add_edge("printer", END)

# 关键：在 human 节点前暂停！
app = graph.compile(
    checkpointer=checkpoint_storage,
    interrupt_before=["human"]
)

# ======================
# API 相关函数
# ======================
def start_writing_session(session_id: str, before_text: str, current_text: str, 
                          character_ids: list, worldview_ids: list, style_ids: list) -> dict:
    initial_state: ChapterState = {
        "input": current_text,
        "previous_plot": before_text,
        "revision_count": 0,
        "characters": readfrom("characters.json", character_ids),
        "world_views": readfrom("wordviews.json", worldview_ids),
        "styles": readfrom("styles.json", style_ids),
        "current_stage": "start",
        "step_logs": [],
        "session_id": session_id,
        "is_paused": False,
        "is_terminated": False,
        "draft": None,
        "feedback": None,
        "need_revision": None,
        "human_feedback": None,
        "outlines": [],
        "edited_draft": None,
        "human_suggestions": [],
        "human_action": None,
        "waiting_for_human": False,
        "interrupt_data": None
    }
    
    agent_states[session_id] = initial_state
    
    return {
        "session_id": session_id,
        "status": "started"
    }

def execute_step(session_id: str) -> dict:
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    print(session_id)
    import threading
    thread = threading.Thread(target=_execute_step_async, args=(session_id,))
    thread.daemon = True
    thread.start()
    
    return {
        "status": "running",
        "message": "任务已启动，正在执行中..."
    }

def _execute_step_async(session_id: str):
    """异步执行步骤的实际逻辑"""
    try:
        state = agent_states[session_id]
        config = {"configurable": {"thread_id": session_id}}
        
        print("🔄 开始执行LangGraph...")
        
        # 执行到第一个暂停点
        app.invoke(state, config=config)
        
        # 获取执行后的状态
        state_result = app.get_state(config)
        
        # 更新本地状态
        agent_states[session_id] = state_result.values
        
        # 检查是否暂停在 human 节点前
        if len(state_result.next) > 0 and "human" in state_result.next:
            print("⏸️ 已暂停在 human 节点前")
            agent_states[session_id]["waiting_for_human"] = True
            agent_states[session_id]["current_stage"] = "human_review"
        
        push_state_update(session_id, agent_states[session_id])
        
    except Exception as e:
        import traceback
        print(f"❌ 异步执行失败: {str(e)}")
        traceback.print_exc()

def get_session_state(session_id: str) -> dict:
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    
    # agent_states 是唯一真相源（_execute_step_async 已把执行后的状态写进去）
    state = agent_states[session_id]
    config = {"configurable": {"thread_id": session_id}}
    
    # 只从 graph 判断 next 节点来确认是否在 human 节点前暂停，不覆盖 state 中的字段
    try:
        graph_state = app.get_state(config)
        if len(graph_state.next) > 0 and "human" in graph_state.next:
            state["waiting_for_human"] = True
            if not state.get("current_stage"):
                state["current_stage"] = "human_review"
    except Exception:
        pass
    
    current_stage = state.get("current_stage", "")
    is_terminated = state.get("is_terminated", False)
    waiting_for_human = state.get("waiting_for_human", False)
    
    if is_terminated:
        status = "terminated"
    elif current_stage == "finished":
        status = "finished"
    elif waiting_for_human:
        status = "waiting_for_human"
    elif current_stage:
        status = "running"
    else:
        status = "idle"
    
    return {
        "session_id": session_id,
        "status": status,
        "current_stage": current_stage,
        "step_logs": state.get("step_logs", []),
        "draft": state.get("draft", ""),
        "feedback": state.get("feedback", ""),
        "revision_count": state.get("revision_count", 0),
        "is_paused": state.get("is_paused", False),
        "is_terminated": is_terminated,
        "waiting_for_human": waiting_for_human,
        "human_action": state.get("human_action"),
        "human_suggestions": state.get("human_suggestions", []),
        "edited_draft": state.get("edited_draft")
    }

def update_draft(session_id: str, new_draft: str) -> dict:
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    
    state = agent_states[session_id]
    state["draft"] = new_draft
    agent_states[session_id] = state
    
    # 更新 graph 状态
    config = {"configurable": {"thread_id": session_id}}
    app.update_state(config, {"draft": new_draft})
    
    return {"success": True, "message": "草稿已更新"}

def submit_human_action(session_id: str, action: str, edited_draft: str = None, 
                         suggestions: list = None) -> dict:
    """提交人工操作"""
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    
    state = agent_states[session_id]
    config = {"configurable": {"thread_id": session_id}}
    
    # 更新状态
    updates = {"waiting_for_human": False, "human_action": action}
    
    if action == "edit" and edited_draft:
        updates["draft"] = edited_draft
        updates["edited_draft"] = edited_draft
        updates["need_revision"] = "PASS"
        
    elif action == "suggest" and suggestions:
        updates["feedback"] = "\n".join(suggestions)
        updates["need_revision"] = "REJECT"
        updates["human_suggestions"] = suggestions
        
    elif action == "terminate":
        updates["is_terminated"] = True
        updates["current_stage"] = "terminated"
    
    else:  # continue
        updates["need_revision"] = "PASS"
    
    # ✅ 正确：调用 graph.update_state() 不是字典.update()
    app.update_state(config, updates)
    
    # 更新本地状态
    agent_states[session_id] = {**state, **updates}

    # 立刻推一次状态给前端（让 UI 立即感知到"继续执行中"）
    push_state_update(session_id, agent_states[session_id])

    # 如果不是终止，继续执行
    if action != "terminate":
        import threading
        thread = threading.Thread(target=_continue_execution, args=(session_id,))
        thread.daemon = True
        thread.start()

    # 返回完整的当前状态给前端
    return get_session_state(session_id)

def _continue_execution(session_id: str):
    """从暂停处继续执行"""
    try:
        config = {"configurable": {"thread_id": session_id}}
        
        print("🔄 从暂停处继续执行LangGraph...")
        
        # ✅ 关键：从断点继续，传入 None
        app.invoke(None, config=config)
        
        # 获取最新状态
        state_result = app.get_state(config)
        agent_states[session_id] = state_result.values
        
        # 检查是否再次暂停
        if len(state_result.next) > 0 and "human" in state_result.next:
            print("⏸️ 再次暂停在 human 节点前")
            agent_states[session_id]["waiting_for_human"] = True
            agent_states[session_id]["current_stage"] = "human_review"
        
        push_state_update(session_id, agent_states[session_id])
        
    except Exception as e:
        import traceback
        print(f"❌ 继续执行失败: {str(e)}")
        traceback.print_exc()

def submit_human_feedback(session_id: str, feedback: str) -> dict:
    """兼容旧接口"""
    if feedback and feedback.strip():
        return submit_human_action(session_id, "suggest", suggestions=[feedback])
    else:
        return submit_human_action(session_id, "continue")

def terminate_session(session_id: str) -> dict:
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    
    state = agent_states[session_id]
    state["is_terminated"] = True
    state["current_stage"] = "terminated"
    agent_states[session_id] = state
    
    return {"success": True, "message": "会话已终止"}

def resume_session(session_id: str) -> dict:
    if session_id not in agent_states:
        return {"error": "会话不存在"}
    
    state = agent_states[session_id]
    state["is_paused"] = False
    agent_states[session_id] = state
    
    return {"success": True, "message": "会话已恢复"}

def delete_session(session_id: str) -> dict:
    if session_id in agent_states:
        del agent_states[session_id]
        return {"success": True, "message": "会话已删除"}
    return {"error": "会话不存在"}

def push_state_update(session_id: str, state: dict):
    """把最新状态写入 agent_states，供前端轮询 /state 接口读取"""
    agent_states[session_id] = state
    status = "running"
    if state.get("is_terminated", False):
        status = "terminated"
    elif state.get("current_stage", "") == "finished":
        status = "finished"
    elif state.get("waiting_for_human", False):
        status = "waiting_for_human"
    print(f"ℹ️ 状态更新 - session: {session_id[:8]}... stage: {status} logs: {len(state.get('step_logs', []))}")

# 测试用
if __name__ == "__main__":
    session_id = "test_session_1"
    start_writing_session(session_id, "上一章内容...", "本章大纲...", [], [], [])
    execute_step(session_id)