# -*- coding: utf-8 -*-
"""
写作域接口与驱动：启动一章 -> 后台线程跑 LangGraph -> 轮询进度 -> 人工审核续跑。

对外函数（被 web_server.Handler 调用）：api_write_start / api_write_status /
api_write_action / api_write_stop。内部 _drive / _start_thread 由 sessions 注册为续跑钩子。
"""
import os
import threading
import time
import traceback

import collab_novel_agent as agent
from collab_novel_agent import start_session
import project as proj
from common import PROJECTS_ROOT, resolve_project_arg, config_of
from sessions import (
    SESSIONS, SESSIONS_LOCK, _save_sessions, _ensure_session, register_thread_starter,
)

# 一次 invoke 到下一个 interrupt 之间最多循环几次（安全阀，正常 1 次就够）
MAX_DRIVE_LOOPS = 8


def _snapshot(sid):
    """读图的当前状态：返回 (下一个节点列表, 状态字典)。"""
    gs = agent.app.get_state(config_of(sid))
    return list(gs.next or []), dict(gs.values or {})


def last_chapter_path(project_dir, values):
    """找出本次（或该项目）最后一章的文件路径，前端用来跳转到成稿。"""
    try:
        if project_dir:
            meta = proj.read_meta(project_dir)
            chapters = meta.get("chapters", [])
            if chapters:
                return os.path.join(project_dir, proj.CHAPTERS_DIR, chapters[-1]["file"])
        else:
            sid = str(values.get("session_id", ""))[:8]
            p = os.path.join(agent.OUTPUT_DIR, f"chapter_{sid}.txt")
            if os.path.exists(p):
                return p
    except Exception:
        pass
    return ""


def ids_of(raw):
    """'a,b' -> ['a','b']；空则返回 None（表示加载该类全部卡片）。"""
    xs = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return xs or None


# ---------------------------------------------------------------------------
# 写作驱动（跑在工作线程里）
# ---------------------------------------------------------------------------
def _drive(sid):
    """
    驱动一章工作流，直到「停在人工审核」或「跑完」。

    首次调用带初始 state 进去；之后前端提交人工动作，再 invoke(None) 续跑。
    revise 会回到文风润色再停一次，所以 waiting 可能出现多次。
    """
    with SESSIONS_LOCK:
        s = SESSIONS.get(sid)
    if not s:
        return

    try:
        for _ in range(MAX_DRIVE_LOOPS):
            if s.get("stop"):
                s["status"] = "stopped"
                _save_sessions()
                return

            if not s.get("started"):
                agent.app.invoke(s["state"], config_of(sid))
                s["started"] = True
            else:
                agent.app.invoke(None, config_of(sid))

            nxt, values = _snapshot(sid)
            s["state"] = values

            if "human_review" in nxt:
                s["status"] = "waiting"
                s["round"] = s.get("round", 0) + 1
                _save_sessions()
                return

            if not nxt:
                s["status"] = "done"
                s["chapter_file"] = last_chapter_path(s.get("project"), values)
                _save_sessions()
                return

        # 兜底：循环次数用尽仍未结束，按完成处理，避免前端永远转圈
        s["status"] = "done"
        s["chapter_file"] = last_chapter_path(s.get("project"), s["state"])
        _save_sessions()
    except Exception:
        s["status"] = "error"
        s["error"] = traceback.format_exc()
        _save_sessions()


def _start_thread(sid):
    t = threading.Thread(target=_drive, args=(sid,), daemon=True)
    with SESSIONS_LOCK:
        SESSIONS[sid]["thread"] = t
    t.start()


# 注册为会话续跑钩子：sessions._load_sessions / _ensure_session 在崩溃恢复时回调
register_thread_starter(_start_thread)


def api_write_start(body):
    root = resolve_project_arg(body.get("project"))
    proj.ensure_project(root)

    state = start_session(
        chapter_title=body.get("title", ""),
        chapter_outline=body.get("outline", ""),
        previous_summary=body.get("prev", ""),
        character_ids=ids_of(body.get("characters")),
        plot_ids=ids_of(body.get("plots")),
        style_ids=ids_of(body.get("styles")),
        foreshadowing_ids=ids_of(body.get("fore")),
        worldview_ids=ids_of(body.get("worlds")),
        project_dir=root,
    )["state"]

    sid = state["session_id"]
    with SESSIONS_LOCK:
        SESSIONS[sid] = {
            "sid": sid,
            "project": root,
            "title": body.get("title", ""),
            "state": state,
            "status": "running",
            "started": False,
            "stop": False,
            "round": 0,
            "error": "",
            "chapter_file": "",
            "thread": None,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    _save_sessions()
    _start_thread(sid)
    return {"sid": sid, "project": root}


def api_write_status(query):
    sid = str(query.get("sid", ""))
    s = _ensure_session(sid)
    if not s:
        raise KeyError(f"会话不存在: {sid}")

    # 线程跑的过程中也读一次图状态，这样 step_logs 能增量刷新出进度
    values = s.get("state") or {}
    try:
        _, values = _snapshot(sid)
        s["state"] = values
    except Exception:
        pass

    return {
        "sid": sid,
        "status": s.get("status", "running"),
        "round": s.get("round", 0),
        "error": s.get("error", ""),
        "stage": values.get("current_stage", ""),
        "plan": values.get("chapter_plan", ""),
        "draft": values.get("style_edited_draft") or values.get("draft", ""),
        "feedback": values.get("human_feedback", ""),
        "logs": values.get("step_logs", []),
        "chapter_file": s.get("chapter_file", ""),
        "project": s.get("project", ""),
    }


def api_write_action(body):
    """提交人工审核动作：approved / revise / edit / quit。"""
    sid = str(body.get("sid", ""))
    s = _ensure_session(sid)
    if not s:
        raise KeyError(f"会话不存在: {sid}")

    action = str(body.get("action", ""))
    if action == "quit":
        s["stop"] = True
        s["status"] = "stopped"
        _save_sessions()
        return {"ok": True, "status": "stopped"}

    if action not in ("approved", "revise", "edit"):
        raise ValueError(f"未知人工操作: {action}")

    updates = {
        "waiting_for_human": False,
        "human_action": action,
        "human_feedback": body.get("feedback", ""),
    }
    if action == "edit":
        updates["style_edited_draft"] = body.get("edited_draft", "") or body.get("feedback", "")

    agent.app.update_state(config_of(sid), updates)
    s["status"] = "running"
    _save_sessions()
    _start_thread(sid)
    return {"ok": True, "status": "running"}


def api_write_stop(body):
    sid = str(body.get("sid", ""))
    with SESSIONS_LOCK:
        s = SESSIONS.get(sid)
    if s:
        s["stop"] = True
        s["status"] = "stopped"
        _save_sessions()
    return {"ok": True}
