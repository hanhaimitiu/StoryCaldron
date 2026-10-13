# -*- coding: utf-8 -*-
"""
会话注册表与持久化（#8）：把写作会话的元信息落盘，重启后按 sid 恢复 / 崩溃恢复。

只负责「注册表 + 落盘 + 恢复」，不持有写作驱动线程逻辑（避免与 api_write.py 循环依赖）：
线程续跑通过 register_thread_starter 注入，_load_sessions / _ensure_session 在需要时回调。
"""
import json
import os
import threading

import collab_novel_agent as agent
from common import HERE, PROJECTS_ROOT, config_of

# 会话运行时状态：sid -> 运行时记录（含 project/title/status/state/thread 等）
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()

# 会话注册表落盘路径：重启后据此恢复历史会话
# （与 collab_novel_agent 的落盘 Checkpointer 配合，实现崩溃恢复 / 按 sid 恢复）
SESSIONS_FILE = os.path.join(HERE, "sessions.json")

# 线程续跑钩子：由 api_write.py 注入 _start_thread，避免本模块反向依赖写作驱动
_thread_starter = None


def register_thread_starter(fn):
    """注册「补起会话线程」的回调（api_write._start_thread），供崩溃恢复时调用。"""
    global _thread_starter
    _thread_starter = fn


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
            if _thread_starter:
                _thread_starter(sid)
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
            gs = agent.app.get_state(config_of(sid))
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
        if _thread_starter:
            _thread_starter(sid)
    return entry
