#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目工作区管理 —— 让 Agent 像使用一个真实项目一样工作。

每个小说项目是一个独立目录，结构如下：

    <project>/
        project.json            # 项目元信息（标题、设定摘要、章节索引）
        cards/                  # 素材卡（人物 / 剧情 / 文风 / 伏笔 / 世界观）
            characters.json
            stories.json  (或 plots.json)
            styles.json
            foreshadowing.json
            wordviews.json
        chapters/               # 已写章节正文（chapter_001.txt ...）

这样「读卡片 / 建卡片 / 写小说」都落在同一个项目目录里，互不干扰；
换一本书就换一个项目目录，素材与成稿天然隔离。
"""
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

# 卡片类型 -> (文件名, 中文标签)
CARD_TYPES = {
    "character": ("characters.json", "人物卡"),
    "plot": ("stories.json", "剧情卡"),
    "style": ("styles.json", "文风卡"),
    "foreshadowing": ("foreshadowing.json", "伏笔卡"),
    "worldview": ("wordviews.json", "世界观卡"),
}

# 各类卡片的常用字段（用于交互式创建时逐个提示）
CARD_FIELDS = {
    "character": ["id", "name", "gender", "appearance", "personality", "identity", "ability"],
    "plot": ["id", "title", "status", "description"],
    "style": ["id", "title", "style_overall", "sentence_feature", "word_preference"],
    "foreshadowing": ["id", "content", "status"],
    "worldview": ["id", "world_theme", "power_system", "world_rule"],
}

PROJECT_JSON = "project.json"
CARDS_DIR = "cards"
CHAPTERS_DIR = "chapters"


# ---------------------------------------------------------------------------
# 路径与初始化
# ---------------------------------------------------------------------------
def resolve_project(arg: Optional[str]) -> str:
    """把用户给的项目路径解析成绝对路径；缺省则用 ./projects/default。"""
    if not arg:
        arg = os.path.join(os.getcwd(), "projects", "default")
    return os.path.abspath(os.path.expanduser(arg))


def ensure_project(root: str, seed_demo: bool = False) -> str:
    """
    确保项目目录存在：创建 cards/、chapters/、project.json 与各空卡片文件。
    已存在的部分不会覆盖（安全幂等）。seed_demo=True 时写入一套演示卡片。
    """
    cards_dir = os.path.join(root, CARDS_DIR)
    chapters_dir = os.path.join(root, CHAPTERS_DIR)
    os.makedirs(cards_dir, exist_ok=True)
    os.makedirs(chapters_dir, exist_ok=True)

    meta_path = os.path.join(root, PROJECT_JSON)
    if not os.path.exists(meta_path):
        write_meta(root, {
            "title": os.path.basename(root),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "chapters": [],
        })

    for fname, _ in CARD_TYPES.values():
        fp = os.path.join(cards_dir, fname)
        if not os.path.exists(fp):
            with open(fp, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    if seed_demo:
        _seed_demo(cards_dir)
    return root


# ---------------------------------------------------------------------------
# 卡片读写
# ---------------------------------------------------------------------------
def _read_db(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_db(path: str, db: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _to_list(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(db.values())


def _filter(items: List[Dict[str, Any]], ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not ids:
        return items
    out = []
    for id_ in ids:
        id_str = str(id_)
        for it in items:
            if isinstance(it, dict) and str(it.get("id", "")) == id_str:
                out.append(it)
                break
    return out


def _plot_filename(cards_dir: str) -> str:
    """剧情卡优先用 stories.json，没有才用 plots.json（与老逻辑一致）。"""
    if os.path.exists(os.path.join(cards_dir, "stories.json")):
        return "stories.json"
    return "plots.json"


def load_cards(root: str, card_type: str, ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """读取某类卡片；card_type 为 character/plot/style/foreshadowing/worldview。"""
    fname, _ = CARD_TYPES[card_type]
    cards_dir = os.path.join(root, CARDS_DIR)
    if card_type == "plot":
        # 剧情卡兼容 stories.json 与 plots.json
        for cand in ("stories.json", "plots.json"):
            fp = os.path.join(cards_dir, cand)
            if os.path.exists(fp):
                return _filter(_to_list(_read_db(fp)), ids)
        return []
    return _filter(_to_list(_read_db(os.path.join(cards_dir, fname))), ids)


def save_cards(root: str, card_type: str, items: List[Dict[str, Any]]) -> None:
    """整文件保存某类卡片（按 id 覆写）。"""
    cards_dir = os.path.join(root, CARDS_DIR)
    fname, _ = CARD_TYPES[card_type]
    if card_type == "plot":
        fname = _plot_filename(cards_dir)
    _write_db(os.path.join(cards_dir, fname), {str(i.get("id", uuid.uuid4().hex)): i for i in items})


def create_card(root: str, card_type: str, card: Dict[str, Any]) -> str:
    """向某类卡片新增/覆盖一条；返回该卡 id。"""
    cards_dir = os.path.join(root, CARDS_DIR)
    fname, _ = CARD_TYPES[card_type]
    if card_type == "plot":
        fname = _plot_filename(cards_dir)
    fp = os.path.join(cards_dir, fname)
    db = _read_db(fp)
    key = str(card.get("id") or uuid.uuid4().hex)
    db[key] = card
    _write_db(fp, db)
    return key


def list_cards(root: str) -> List[Dict[str, Any]]:
    """返回该项目所有卡片的概要列表：[{type, label, file, count, items}]。"""
    cards_dir = os.path.join(root, CARDS_DIR)
    out = []
    for ctype, (fname, label) in CARD_TYPES.items():
        if ctype == "plot":
            fp = os.path.join(cards_dir, _plot_filename(cards_dir))
        else:
            fp = os.path.join(cards_dir, fname)
        items = _to_list(_read_db(fp))
        out.append({"type": ctype, "label": label, "file": os.path.basename(fp),
                    "count": len(items), "items": items})
    return out


# ---------------------------------------------------------------------------
# 章节落盘
# ---------------------------------------------------------------------------
def add_chapter(root: str, title: str, text: str) -> str:
    """把一章正文写入 chapters/，并在 project.json 记录章节索引。返回文件路径。"""
    chapters_dir = os.path.join(root, CHAPTERS_DIR)
    os.makedirs(chapters_dir, exist_ok=True)
    meta = read_meta(root)
    idx = len(meta.get("chapters", [])) + 1
    fname = f"chapter_{idx:03d}.txt"
    path = os.path.join(chapters_dir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(text)
    meta.setdefault("chapters", []).append({
        "file": fname,
        "title": title,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    write_meta(root, meta)
    return path


def read_meta(root: str) -> Dict[str, Any]:
    path = os.path.join(root, PROJECT_JSON)
    return _read_db(path)


def write_meta(root: str, meta: Dict[str, Any]) -> None:
    _write_db(os.path.join(root, PROJECT_JSON), meta)


# ---------------------------------------------------------------------------
# 演示卡片（仅 init --demo 使用）
# ---------------------------------------------------------------------------
def _seed_demo(cards_dir: str) -> None:
    demo = {
        "characters.json": [{
            "id": "hero", "name": "陆青崖", "gender": "男",
            "appearance": "青色长袍，眉间有一道旧疤",
            "personality": "沉稳、重情义，遇到不公会挺身而出",
            "identity": "青云宗外门弟子",
            "ability": "剑术初入门槛，体内封印未解",
        }],
        "stories.json": [{
            "id": "main_1", "title": "入门考核", "status": "in_progress",
            "description": "陆青崖参加青云宗外门考核，需在秘境中存活三日",
        }],
        "styles.json": [{
            "id": "style_1", "title": "古风仙侠",
            "style_overall": "古风/热血/细腻",
            "sentence_feature": "长短句交错，打斗场景短促，心理描写绵长",
            "word_preference": "常用“剑光”“灵气”“眸子”等词汇",
        }],
        "foreshadowing.json": [{
            "id": "fore_1", "content": "陆青崖眉间旧疤与秘境中的古剑有神秘联系",
            "status": "pending",
        }],
        "wordviews.json": [{
            "id": "world_1", "world_theme": "低魔仙侠宗门世界",
            "power_system": "炼气、筑基、金丹、元婴",
            "world_rule": "灵气稀薄，功法传承严苛",
        }],
    }
    for fname, items in demo.items():
        fp = os.path.join(cards_dir, fname)
        if not os.path.exists(fp) or _read_db(fp) == {}:
            _write_db(fp, {str(i.get("id", uuid.uuid4().hex)): i for i in items})
