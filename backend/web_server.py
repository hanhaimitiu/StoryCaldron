#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 网页服务 —— 给多 Agent 小说创作套一层浏览器界面。

零依赖：只用 Python 标准库 http.server，不需要装 Flask/FastAPI。
启动：

    .venv\\Scripts\\python.exe backend\\web_server.py
    # 然后浏览器打开 http://127.0.0.1:8765

对外只暴露 127.0.0.1，端口可用环境变量 PORT 改。

提供的能力（与命令行入口 run_chapter.py 同源）：
    项目：列出 / 创建（可选塞演示卡）
    卡片：五类素材卡的读、增改、删
    MD：  把 Markdown 设定转成卡片 JSON（独立工具 md_to_cards）
    写作：启动一章 -> 后台线程跑 -> 轮询进度 -> 停在人工审核时提交动作继续
    章节：列出已写章节、读取正文

写作为什么要用线程 + 轮询：
    一章要跑十几分钟（本地大模型），HTTP 请求不可能一直挂着等。
    所以后端起线程驱动 LangGraph，前端定时拉进度；
    图停在 human_review 前时状态变 waiting，前端展示草稿并让用户选
    「通过 / 提意见 / 给全文 / 终止」，提交后线程继续往下跑。
"""
import json
import os
import sys
import tempfile
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 允许直接 `python backend/web_server.py` 运行
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)              # 仓库根
WEB_DIR = os.path.join(ROOT, "web")            # Vue 工程目录
DIST_DIR = os.path.join(WEB_DIR, "dist")       # vite build 的产物
PROJECTS_ROOT = os.path.join(ROOT, "projects")
sys.path.insert(0, HERE)

import project as proj                     # noqa: E402
import collab_novel_agent as agent         # noqa: E402
from collab_novel_agent import start_session  # noqa: E402
from md_to_cards import convert_to_project     # noqa: E402
import book_to_cards as bookmod               # noqa: E402  # 拆书解析（txt -> 章节 + 卡片）


DEFAULT_PORT = 8765
DEV_HINT = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>StoryCaldron</title></head><body style="font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:40px">
<h2>前端还没有构建</h2>
<p>两种方式任选其一：</p>
<ul>
<li><b>开发模式</b>（推荐改代码时用）：在 <code>web/</code> 下执行 <code>npm run dev</code>，
    然后打开 <a style="color:#58a6ff" href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>，
    已配好 /api 代理到本服务。</li>
<li><b>生产模式</b>：在 <code>web/</code> 下执行 <code>npm run build</code>，
    再刷新本页，由 Python 服务直接托管 dist。</li>
</ul></body></html>"""
# 一次 invoke 到下一个 interrupt 之间最多循环几次（安全阀，正常 1 次就够）
MAX_DRIVE_LOOPS = 8

# 会话运行时状态：sid -> 运行时记录
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()

# 会话注册表落盘路径：重启后据此恢复历史会话
# （与 collab_novel_agent 的落盘 Checkpointer 配合，实现崩溃恢复 / 按 sid 恢复）
SESSIONS_FILE = os.path.join(HERE, "sessions.json")

# 拆书解析任务：task_id -> 运行时记录（与写作流同源的线程 + 轮询模式）
BOOK_TASKS = {}
BOOK_TASKS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def _config(sid):
    """LangGraph 用 thread_id 区分会话。"""
    return {"configurable": {"thread_id": sid}}


def _snapshot(sid):
    """读图的当前状态：返回 (下一个节点列表, 状态字典)。"""
    gs = agent.app.get_state(_config(sid))
    return list(gs.next or []), dict(gs.values or {})


def resolve_project_arg(raw):
    """把前端给的项目路径解析成绝对路径；空则用 projects/default。"""
    raw = (raw or "").strip()
    if not raw:
        return os.path.join(PROJECTS_ROOT, "default")
    if not os.path.isabs(raw):
        raw = os.path.join(PROJECTS_ROOT, raw)
    return os.path.abspath(os.path.expanduser(raw))


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
                agent.app.invoke(s["state"], _config(sid))
                s["started"] = True
            else:
                agent.app.invoke(None, _config(sid))

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


# ---------------------------------------------------------------------------
# 会话持久化 / 崩溃恢复（#8）：把会话注册表落盘，重启后按 sid 恢复
# ---------------------------------------------------------------------------
def _save_sessions():
    """把内存中的 SESSIONS 元信息（不含大块 state）落盘到 sessions.json。"""
    with SESSIONS_LOCK:
        data = {
            sid: {
                "project": s.get("project", ""),
                "title": s.get("title", ""),
                "status": s.get("status", "running"),
                "round": s.get("round", 0),
                "chapter_file": s.get("chapter_file", ""),
                "created_at": s.get("created_at", ""),
            }
            for sid, s in SESSIONS.items()
        }
    try:
        tmp = SESSIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SESSIONS_FILE)
    except Exception as e:
        print(f"⚠️ 保存会话注册表失败: {e}")


def _load_sessions():
    """启动时读取 sessions.json，把历史会话重建进 SESSIONS；
    此前处于 running 的会话（如服务崩溃）会重新起线程续跑。"""
    if not os.path.exists(SESSIONS_FILE):
        return
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ 读取会话注册表失败: {e}")
        return
    with SESSIONS_LOCK:
        for sid, meta in data.items():
            if sid in SESSIONS:
                continue
            SESSIONS[sid] = {
                "sid": sid,
                "project": meta.get("project", ""),
                "title": meta.get("title", ""),
                "state": {},
                "status": meta.get("status", "waiting"),
                "started": meta.get("status") in ("running", "waiting", "done"),
                "stop": False,
                "round": meta.get("round", 0),
                "error": "",
                "chapter_file": meta.get("chapter_file", ""),
                "thread": None,
                "created_at": meta.get("created_at", ""),
            }
    # 崩溃恢复：把此前仍在跑（running）的会话重新起线程续跑
    for sid, s in list(SESSIONS.items()):
        if s.get("status") == "running" and (not s.get("thread") or not s["thread"].is_alive()):
            _start_thread(sid)
    print(f"[会话恢复] 已从磁盘恢复 {len(data)} 个历史会话")


def _ensure_session(sid):
    """若 sid 不在内存 SESSIONS 中，尝试从注册表或检查点恢复，避免 status/action 误报 404。"""
    with SESSIONS_LOCK:
        if sid in SESSIONS:
            return SESSIONS[sid]
    meta = {}
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f).get(sid, {})
        except Exception:
            meta = {}
    if not meta:
        # 检查点里是否真有这个 thread
        try:
            gs = agent.app.get_state(_config(sid))
            if not (gs.values or gs.next):
                return None
        except Exception:
            return None
    entry = {
        "sid": sid,
        "project": meta.get("project", ""),
        "title": meta.get("title", ""),
        "state": {},
        "status": meta.get("status", "waiting"),
        "started": meta.get("status") in ("running", "waiting", "done"),
        "stop": False,
        "round": meta.get("round", 0),
        "error": "",
        "chapter_file": meta.get("chapter_file", ""),
        "thread": None,
        "created_at": meta.get("created_at", ""),
    }
    with SESSIONS_LOCK:
        if sid not in SESSIONS:
            SESSIONS[sid] = entry
    # 若此前在跑（崩溃遗留），补起线程续跑
    if entry.get("status") == "running" and (not entry.get("thread") or not entry["thread"].is_alive()):
        _start_thread(sid)
    return entry


def ids_of(raw):
    """'a,b' -> ['a','b']；空则返回 None（表示加载该类全部卡片）。"""
    xs = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return xs or None


# ---------------------------------------------------------------------------
# 业务接口实现
# ---------------------------------------------------------------------------
TEMPLATE_PATH = os.path.join(HERE, "setting_template.md")


def api_template():
    """返回 Markdown 设定书写模板，前端「查看书写模板」直接用。"""
    if not os.path.exists(TEMPLATE_PATH):
        return {"template": ""}
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return {"template": f.read()}


def api_list_projects():
    os.makedirs(PROJECTS_ROOT, exist_ok=True)
    out = []
    for name in sorted(os.listdir(PROJECTS_ROOT)):
        p = os.path.join(PROJECTS_ROOT, name)
        if not os.path.isdir(p):
            continue
        meta = proj.read_meta(p)
        cards = proj.list_cards(p)
        out.append({
            "name": name,
            "path": p,
            "title": meta.get("title") or name,
            "chapters": len(meta.get("chapters", [])),
            "cards": sum(c["count"] for c in cards),
        })
    return out


def api_create_project(body):
    root = resolve_project_arg(body.get("path") or body.get("name"))
    proj.ensure_project(root, seed_demo=bool(body.get("demo")))
    return {"path": root, "name": os.path.basename(root)}


def api_list_cards(query):
    root = resolve_project_arg(query.get("project"))
    proj.ensure_project(root)
    return {"project": root, "types": proj.list_cards(root), "fields": proj.CARD_FIELDS}


def api_save_card(body):
    """新建或覆盖一张卡（按 id 覆写，与命令行 new-card 行为一致）。"""
    root = resolve_project_arg(body.get("project"))
    proj.ensure_project(root)
    ctype = body.get("type")
    card = dict(body.get("card") or {})
    if ctype not in proj.CARD_TYPES:
        raise ValueError(f"未知卡片类型: {ctype}")
    if not card.get("id"):
        import uuid
        card["id"] = f"{ctype[:3]}_{uuid.uuid4().hex[:6]}"
    key = proj.create_card(root, ctype, card)
    return {"id": key}


def api_delete_card(body):
    root = resolve_project_arg(body.get("project"))
    ctype = body.get("type")
    cid = str(body.get("id", ""))
    if ctype not in proj.CARD_TYPES:
        raise ValueError(f"未知卡片类型: {ctype}")
    items = proj.load_cards(root, ctype)
    rest = [i for i in items if str(i.get("id", "")) != cid]
    if len(rest) == len(items):
        return {"deleted": False}
    proj.save_cards(root, ctype, rest)
    return {"deleted": True}


def api_import_md(body):
    """把 Markdown 设定转成卡片（写临时文件后交给独立工具 md_to_cards）。"""
    root = resolve_project_arg(body.get("project"))
    proj.ensure_project(root)
    md_text = body.get("md") or ""
    if not md_text.strip():
        raise ValueError("Markdown 内容为空")

    fd, tmp = tempfile.mkstemp(suffix=".md", prefix="story_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(md_text)
        stats, _ = convert_to_project(
            tmp, root,
            use_llm=bool(body.get("use_llm", True)),
            merge=bool(body.get("merge", True)),
        )
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    # 转成中文标签，前端直接展示
    labeled = {proj.CARD_TYPES[k][1]: v for k, v in (stats or {}).items()}
    return {"stats": labeled, "raw": stats or {}}


def api_list_chapters(query):
    root = resolve_project_arg(query.get("project"))
    proj.ensure_project(root)
    meta = proj.read_meta(root)
    return {"project": root, "chapters": meta.get("chapters", [])}


def api_read_chapter(query):
    root = resolve_project_arg(query.get("project"))
    fname = os.path.basename(str(query.get("file", "")))   # 防路径穿越
    path = os.path.join(root, proj.CHAPTERS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"章节不存在: {fname}")
    with open(path, "r", encoding="utf-8") as f:
        return {"file": fname, "content": f.read()}


def api_outline(query):
    """读取全书大纲/结构圣经（outline.md）。query: {project}。对应 #2。"""
    root = resolve_project_arg(query.get("project"))
    proj.ensure_project(root)
    return {"project": root, "outline": proj.load_outline(root)}


def api_outline_save(body):
    """整体覆盖保存全书大纲（outline.md）。body: {project, outline}。对应 #2。"""
    root = resolve_project_arg(body.get("project"))
    proj.ensure_project(root)
    text = str(body.get("outline", ""))
    path = proj.save_outline(root, text)
    return {"ok": True, "project": root, "path": path}


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

    agent.app.update_state(_config(sid), updates)
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


# ---------------------------------------------------------------------------
# 拆书解析（txt -> 章节 + 五类卡片）：后台线程驱动，前端轮询进度
# ---------------------------------------------------------------------------
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


    # ---------------------------------------------------------------------------
    # HTTP 处理
    # ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "StoryCaldron/1.0"

    # ---- 基础收发 ----
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_static(self, rel):
        """
        服务 web/dist 里的构建产物（单端口直接打开）。

        没构建过时给一段提示：开发用 `npm run dev`（5173，已配好 /api 代理），
        或者 `npm run build` 后由本服务托管。
        """
        if not os.path.isdir(DIST_DIR):
            self._send(200, DEV_HINT.encode("utf-8"), "text/html; charset=utf-8")
            return
        if rel in ("", "/"):
            rel = "index.html"
        path = os.path.normpath(os.path.join(DIST_DIR, rel.lstrip("/")))
        if not path.startswith(os.path.abspath(DIST_DIR)):
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        if not os.path.isfile(path):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def log_message(self, fmt, *args):   # 精简日志，避免刷屏
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        one = {k: v[0] for k, v in q.items()}

        try:
            if path.startswith("/api/"):
                if path == "/api/projects":
                    return self._json(200, api_list_projects())
                if path == "/api/cards":
                    return self._json(200, api_list_cards(one))
                if path == "/api/chapters":
                    return self._json(200, api_list_chapters(one))
                if path == "/api/chapter":
                    return self._json(200, api_read_chapter(one))
                if path == "/api/outline":
                    return self._json(200, api_outline(one))
                if path == "/api/write/status":
                    return self._json(200, api_write_status(one))
                if path == "/api/parse-book/status":
                    return self._json(200, api_parse_book_status(one))
                if path == "/api/template":
                    return self._json(200, api_template())
                if path == "/api/health":
                    return self._json(200, {"ok": True})
                return self._json(404, {"error": f"未知接口 {path}"})

            return self._serve_static(path)
        except KeyError as e:
            return self._json(404, {"error": str(e)})
        except FileNotFoundError as e:
            return self._json(404, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}",
                                    "trace": traceback.format_exc()})

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()

        try:
            if path == "/api/projects":
                return self._json(200, api_create_project(body))
            if path == "/api/cards":
                return self._json(200, api_save_card(body))
            if path == "/api/cards/delete":
                return self._json(200, api_delete_card(body))
            if path == "/api/import-md":
                return self._json(200, api_import_md(body))
            if path == "/api/write/start":
                return self._json(200, api_write_start(body))
            if path == "/api/write/action":
                return self._json(200, api_write_action(body))
            if path == "/api/write/stop":
                return self._json(200, api_write_stop(body))
            if path == "/api/outline/save":
                return self._json(200, api_outline_save(body))
            if path == "/api/parse-book":
                return self._json(200, api_parse_book(body))
            if path == "/api/parse-book/commit":
                return self._json(200, api_parse_book_commit(body))
            if path == "/api/parse-book/stop":
                return self._json(200, api_parse_book_stop(body))
            return self._json(404, {"error": f"未知接口 {path}"})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except KeyError as e:
            return self._json(404, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}",
                                    "trace": traceback.format_exc()})


def main():
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    _load_sessions()  # 重启后从磁盘恢复历史会话（崩溃恢复 / 按 sid 恢复）
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"StoryCaldron 网页服务已启动： http://127.0.0.1:{port}")
    print(f"项目根目录：{PROJECTS_ROOT}")
    print("按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.shutdown()


if __name__ == "__main__":
    main()
