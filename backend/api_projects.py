# -*- coding: utf-8 -*-
"""
项目域接口：项目列表/创建/删除、素材卡读写、章节读写、全书大纲、MD 导入模板。

对外函数（被 web_server.Handler 调用）：api_template / api_list_projects /
api_create_project / api_delete_project / api_list_cards / api_save_card /
api_delete_card / api_import_md / api_list_chapters / api_read_chapter /
api_outline / api_outline_save。
"""
import os
import shutil
import tempfile
import uuid

import project as proj
from md_to_cards import convert_to_project
from common import HERE, PROJECTS_ROOT, resolve_project_arg
from sessions import SESSIONS, SESSIONS_LOCK

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


def api_delete_project(body):
    """删除一个项目目录（含章节/素材卡/大纲/正典等全部文件）。

    安全边界：只允许删除 PROJECTS_ROOT 下的子目录，禁止越界删除系统文件。
    若该项目有正在跑的创作会话，先从注册表移除其句柄，避免后续轮询/写入报错。
    """
    raw = body.get("project") or body.get("path") or body.get("name")
    if not raw:
        raise KeyError("缺少 project 参数")
    root = resolve_project_arg(raw)
    # 规范化为真实路径，校验仍在 projects/ 内（防 ../ 越界）
    real_root = os.path.realpath(root)
    real_base = os.path.realpath(PROJECTS_ROOT)
    if real_root == real_base or not real_root.startswith(real_base + os.sep):
        raise KeyError(f"只能删除 projects 下的项目：{root}")
    if not os.path.isdir(real_root):
        return {"deleted": False, "name": os.path.basename(root), "reason": "不存在"}
    name = os.path.basename(real_root)
    # 清掉该项目在跑的会话句柄（守护线程会自行结束），防止轮询/写入落到已删目录
    with SESSIONS_LOCK:
        for sid in [s for s, m in SESSIONS.items() if m.get("project") == root]:
            SESSIONS.pop(sid, None)
    shutil.rmtree(real_root)
    return {"deleted": True, "name": name}


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
