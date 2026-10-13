# -*- coding: utf-8 -*-
"""
拆书解析域接口（txt -> 章节 + 五类卡片）：后台线程驱动，前端轮询进度。

对外函数（被 web_server.Handler 调用）：api_parse_book / api_parse_book_status /
api_parse_book_commit / api_parse_book_stop。任务运行时状态存于本模块 BOOK_TASKS。
"""
import threading
import uuid

import book_to_cards as bookmod
from common import PROJECTS_ROOT, resolve_project_arg

# 拆书解析任务：task_id -> 运行时记录（与写作流同源的线程 + 轮询模式）
BOOK_TASKS = {}
BOOK_TASKS_LOCK = threading.Lock()


def _book_progress(task_id, done, total, msg):
    """progress_cb：把进度写进任务记录，供前端轮询。"""
    with BOOK_TASKS_LOCK:
        rec = BOOK_TASKS.get(task_id)
        if not rec:
            return
        rec["progress"] = {"done": done, "total": total}
        if msg:
            rec["logs"].append(msg)
            if len(rec["logs"]) > 200:   # 防止日志无限增长
                rec["logs"] = rec["logs"][-200:]


def _run_book_task(task_id, txt):
    """后台线程：解析出预览方案（不写入），结束写 status=done/error/stopped。"""
    try:
        with BOOK_TASKS_LOCK:
            rec = BOOK_TASKS.get(task_id)
            if rec:
                rec["status"] = "running"
        plan = bookmod.plan_book(
            txt,
            progress_cb=lambda d, t, m: _book_progress(task_id, d, t, m),
            stop_check=lambda: BOOK_TASKS.get(task_id, {}).get("stop"),
        )
        with BOOK_TASKS_LOCK:
            rec = BOOK_TASKS.get(task_id)
            if rec:
                rec["status"] = "stopped" if rec.get("stop") else "done"
                rec["_plan"] = plan  # 完整方案（含章节正文），仅服务端用于提交
                rec["result"] = {
                    "chapter_count": plan["chapter_count"],
                    "chapters": [{"title": t, "chars": len(b)} for t, b in plan["chapters"]],
                    "cards": plan["cards"],  # 各类型卡片（体积较小）
                }
                rec["progress"] = {"done": rec["progress"]["total"], "total": rec["progress"]["total"]}
    except Exception as e:
        with BOOK_TASKS_LOCK:
            rec = BOOK_TASKS.get(task_id)
            if rec:
                rec["status"] = "error"
                rec["error"] = f"{type(e).__name__}: {e}"


def api_parse_book(body):
    """启动一次拆书解析（只解析不写入），返回 task_id。body: {project, name, text, merge}。"""
    txt = body.get("text") or ""
    if not txt.strip():
        raise ValueError("txt 内容为空")
    task_id = f"book_{uuid.uuid4().hex[:12]}"
    with BOOK_TASKS_LOCK:
        BOOK_TASKS[task_id] = {
            "status": "pending",
            "progress": {"done": 0, "total": 0},
            "logs": [],
            "stats": {},
            "error": "",
            "stop": False,
            "project": body.get("project") or "",
            "merge": bool(body.get("merge", True)),
            "result": None,
            "_plan": None,
        }
    t = threading.Thread(target=_run_book_task, args=(task_id, txt), daemon=True)
    t.start()
    return {"task_id": task_id}


def api_parse_book_status(query):
    """轮询任务进度与预览方案。query: {task}。"""
    task_id = str(query.get("task", ""))
    with BOOK_TASKS_LOCK:
        rec = BOOK_TASKS.get(task_id)
        if not rec:
            return {"status": "not_found"}
        return {
            "status": rec["status"],
            "progress": rec["progress"],
            "logs": rec["logs"],
            "stats": rec["stats"],
            "error": rec["error"],
            "result": rec["result"],
        }


def api_parse_book_commit(body):
    """按勾选把预览方案写入项目。body: {task, project, merge, clear_chapters, chapters, cards}。"""
    task_id = str(body.get("task", ""))
    with BOOK_TASKS_LOCK:
        rec = BOOK_TASKS.get(task_id)
        if not rec or not rec.get("_plan"):
            raise ValueError("任务不存在或尚未解析完成")
        plan = rec["_plan"]
        project = body.get("project") or rec.get("project") or ""
        merge = bool(body.get("merge", rec.get("merge", True)))
    root = resolve_project_arg(project)
    stats = bookmod.commit_book(
        root, plan,
        chapter_idxs=body.get("chapters"),
        card_ids=body.get("cards"),
        merge=merge,
        clear_chapters=bool(body.get("clear_chapters", False)),
    )
    with BOOK_TASKS_LOCK:
        if rec:
            rec["status"] = "committed"
            rec["stats"] = stats
    return {"stats": stats}


def api_parse_book_stop(body):
    """请求中止拆书任务。body: {task}。"""
    task_id = str(body.get("task", ""))
    with BOOK_TASKS_LOCK:
        rec = BOOK_TASKS.get(task_id)
        if rec:
            rec["stop"] = True
    return {"ok": True}
