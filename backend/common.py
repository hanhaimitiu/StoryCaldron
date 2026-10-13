# -*- coding: utf-8 -*-
"""
StoryCaldron 后端共享常量与基础工具。

把原本散在 web_server.py 顶部的路径常量、项目参数解析、LangGraph 线程配置抽到此处，
供 sessions.py / api_*.py / web_server.py 复用，避免大文件互相复制、也避免循环依赖。
"""
import os
import sys

# 允许直接 `python backend/web_server.py` 或任意子模块被导入时，都能找到同目录的
# project / collab_novel_agent / md_to_cards / book_to_cards 等模块。
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)              # 仓库根
WEB_DIR = os.path.join(ROOT, "web")            # Vue 工程目录
DIST_DIR = os.path.join(WEB_DIR, "dist")       # vite build 的产物
PROJECTS_ROOT = os.path.join(ROOT, "projects")
DEFAULT_PORT = 8765                            # 网页服务默认端口（可用环境变量 PORT 改）


def resolve_project_arg(raw):
    """把前端给的项目路径解析成绝对路径；空则用 projects/default。"""
    raw = (raw or "").strip()
    if not raw:
        return os.path.join(PROJECTS_ROOT, "default")
    if not os.path.isabs(raw):
        raw = os.path.join(PROJECTS_ROOT, raw)
    return os.path.abspath(os.path.expanduser(raw))


def config_of(sid):
    """LangGraph 用 thread_id 区分会话，包成 checkpoint 配置。"""
    return {"configurable": {"thread_id": sid}}
