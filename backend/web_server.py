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
    项目：列出 / 创建（可选塞演示卡）/ 删除
    卡片：五类素材卡的读、增改、删
    MD：  把 Markdown 设定转成卡片 JSON（独立工具 md_to_cards）
    写作：启动一章 -> 后台线程跑 -> 轮询进度 -> 停在人工审核时提交动作继续
    章节：列出已写章节、读取正文
    大纲：全书大纲/结构圣经的读取与整体保存（#2）
    拆书：整本 txt -> 章节 + 五类卡片，后台线程 + 轮询

写作为什么要用线程 + 轮询：
    一章要跑十几分钟（本地大模型），HTTP 请求不可能一直挂着等。
    所以后端起线程驱动 LangGraph，前端定时拉进度；
    图停在 human_review 前时状态变 waiting，前端展示草稿并让用户选
    「通过 / 提意见 / 给全文 / 终止」，提交后线程继续往下跑。

本文件只负责「HTTP 路由分发 + 静态托管 + 启动」；具体业务实现拆到：
    common.py      共享常量与工具（路径解析、线程配置）
    sessions.py    会话注册表与持久化（#8）
    api_projects.py 项目/卡片/章节/大纲/模板
    api_write.py   写作驱动与接口
    api_parse.py   拆书解析
"""
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from common import HERE, DEFAULT_PORT, DIST_DIR, PROJECTS_ROOT
from sessions import _load_sessions
from api_projects import (
    api_template, api_list_projects, api_create_project, api_delete_project,
    api_list_cards, api_save_card, api_delete_card, api_import_md,
    api_list_chapters, api_read_chapter, api_outline, api_outline_save,
)
from api_write import api_write_start, api_write_status, api_write_action, api_write_stop
from api_parse import (
    api_parse_book, api_parse_book_status, api_parse_book_commit, api_parse_book_stop,
)

# 允许直接 `python backend/web_server.py` 运行（common 已插入 HERE，这里再保一道）
if HERE not in sys.path:
    sys.path.insert(0, HERE)

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
            if path == "/api/projects/delete":
                return self._json(200, api_delete_project(body))
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
