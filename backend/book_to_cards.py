#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拆书解析工具（独立模块）：把一整本小说 txt 拆成「章节文件 + 五类素材卡」。

与 md_to_cards.py 的区别：
- md_to_cards 解析的是「带 ## / ### 结构的 Markdown 设定」；
- 本模块解析的是「没有层级结构的小说正文 txt」：先按章节标记（第N章 / Chapter N / 第N回）
  切成章节，逐章调用大模型提取 人物/剧情/文风/伏笔/世界观 五类卡片，跨章按 id 合并。

设计要点：
- 复用 md_to_cards 的 CARD_SCHEMA / _extract_json / _apply_defaults / _merge 与 project 存储层，
  不重复造轮子；
- 大模型不可用时，章节照常拆分落盘，但卡片提取为空（拆书的核心是 LLM，没有就只拆章）；
- parse_book 接收 progress_cb(done, total, msg) 上报进度，便于前端做进度条/日志；
- 卡片按 id 合并，重跑同一本书可增量更新，不会整体覆盖。

用法（调试用）：
    python book_to_cards.py 小说.txt --project 项目目录
    python book_to_cards.py 小说.txt --out ./cards_out
"""
import os
import re
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

# 复用项目卡片管理 + md_to_cards 的抽取工具，避免重复造轮子
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project as proj
from md_to_cards import (
    CARD_SCHEMA,
    _extract_json,
    _apply_defaults,
    _has_content,
    _merge,
    _call_llm,
)

# 章节标记：第N章 / 第N回 / Chapter N（不区分大小写）
_CHAPTER_RE = re.compile(
    r"^\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*章"
    r"|第\s*[0-9]+\s*回"
    r"|chapter\s+[0-9]+)\b",
    re.I,
)

# 大模型返回里的键 -> 卡片类型（容忍中英文/单复数）
KEY_TO_CTYPE = {
    "characters": "character", "character": "character", "人物": "character", "人物卡": "character",
    "plots": "plot", "plot": "plot", "stories": "plot", "剧情": "plot", "剧情卡": "plot",
    "styles": "style", "style": "style", "文风": "style", "文风卡": "style",
    "foreshadowings": "foreshadowing", "foreshadowing": "foreshadowing", "伏笔": "foreshadowing", "伏笔卡": "foreshadowing",
    "worldviews": "worldview", "worldview": "worldview", "世界观": "worldview", "世界观卡": "worldview",
}


# ---------------------------------------------------------------------------
# 章节切分（与是否联网无关，纯文本处理）
# ---------------------------------------------------------------------------
def split_chapters(txt: str) -> List[Tuple[str, str]]:
    """按章节标记把整本小说切成 [(章节标题, 章节正文)]。

    识别「第N章 / 第N回 / Chapter N」；没有标记则回退为单段（标题「全书」）。
    """
    lines = (txt or "").replace("\r\n", "\n").split("\n")
    marks: List[int] = []  # 章节起始行号
    titles: List[str] = []
    for i, line in enumerate(lines):
        if _CHAPTER_RE.match(line):
            marks.append(i)
            titles.append(line.strip())

    if not marks:
        body = "\n".join(lines).strip()
        return [("全书", body)] if body else []

    out: List[Tuple[str, str]] = []
    for idx, start in enumerate(marks):
        end = marks[idx + 1] if idx + 1 < len(marks) else len(lines)
        title = titles[idx] or f"第{idx + 1}段"
        body = "\n".join(lines[start + 1 : end]).strip()
        out.append((title, body))
    return out


# ---------------------------------------------------------------------------
# 大模型抽取（拆书核心：读懂一章正文，抽五类卡）
# ---------------------------------------------------------------------------
def _build_extract_prompt() -> str:
    """拼一段「五类卡字段提示」，让模型知道每类该抽哪些字段。"""
    lines = []
    for ctype, schema in CARD_SCHEMA.items():
        fields = [f for f in schema["fields"] if f != "id"]
        alias_hint = "; ".join(
            f"{f}（{('/'.join(schema['field_aliases'].get(f, [f])) or '—')}）" for f in fields
        )
        lines.append(f"- {schema['label']}（键 {ctype}s）：字段 {', '.join(fields)}；含义：{alias_hint}")
    return "\n".join(lines)


_EXTRACT_FIELD_HINT = _build_extract_prompt()


def extract_chapter(title: str, body: str) -> Dict[str, List[Dict[str, Any]]]:
    """调用大模型，从一章正文抽取五类卡片。

    返回 {ctype: [card, ...]}；模型不可用或解析失败返回空字典（只拆章不抽卡）。
    """
    if not body.strip():
        return {}
    system = (
        "你是一个小说拆书助手。给定一章小说正文，请从中提取出现的人物、剧情线、"
        "文风特征、伏笔、世界观设定，整理成一个 JSON 对象。"
        "只输出 JSON，不要任何解释或代码块标记。"
    )
    prompt = f"""章节标题：{title or '（未命名）'}

章节正文：
{body}

请提取为如下 JSON 对象（每类是一个对象数组，没有则给空数组）：
{{
  "characters": [ {{人物卡字段}} ],
  "plots": [ {{剧情卡字段}} ],
  "styles": [ {{文风卡字段}} ],
  "foreshadowings": [ {{伏笔卡字段}} ],
  "worldviews": [ {{世界观卡字段}} ]
}}

各类字段说明：
{_EXTRACT_FIELD_HINT}

要求：
1. 只输出一个 JSON 对象，键必须用上面列出的英文复数名（characters/plots/styles/foreshadowings/worldviews）；
2. 字段尽量用英文字段名；若模型用中文键，系统会按别名映射，但优先英文字段名；
3. 找不到对应信息的字段填空字符串 ""；
4. 不要编造原文没有的关键事实，可对原文做合理归纳；
5. 同名人物/事物在多处出现时只列一条，关键特征合并。
"""
    raw = _call_llm(prompt, system=system, temperature=0.3)
    if not raw:
        return {}
    obj = _extract_json(raw)
    if not isinstance(obj, dict):
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, val in obj.items():
        ctype = KEY_TO_CTYPE.get(str(key).lower().strip())
        if not ctype or not isinstance(val, list):
            continue
        out[ctype] = [c for c in val if isinstance(c, dict)]
    return out


def _normalize(ctype: str, card: Dict[str, Any]) -> Dict[str, Any]:
    """把模型的输出（可能用中文键）映射到标准英文字段，便于 _apply_defaults 兜底。"""
    schema = CARD_SCHEMA[ctype]
    out: Dict[str, Any] = {}
    for field in schema["fields"]:
        if field == "id":
            continue
        if field in card and card[field] not in (None, ""):
            out[field] = card[field] if isinstance(card[field], str) else str(card[field])
            continue
        for a in schema["field_aliases"].get(field, []):
            if a in card and card[a] not in (None, ""):
                out[field] = card[a] if isinstance(card[a], str) else str(card[a])
                break
    return out


# ---------------------------------------------------------------------------
# 收集与写入
# ---------------------------------------------------------------------------
def parse_book(
    txt: str,
    project_dir: str,
    merge: bool = True,
    progress_cb: Optional[Any] = None,
    stop_check: Optional[Any] = None,
) -> Dict[str, int]:
    """拆书主流程：切章 -> 落盘章节 -> 逐章抽卡 -> 跨章合并 -> 写卡片。

    progress_cb(done, total, msg)：实时进度；stop_check() -> bool：返回 True 时中止。
    返回统计 {chapters, character, plot, style, foreshadowing, worldview}。
    """
    proj.ensure_project(project_dir)
    chapters = split_chapters(txt)
    total = len(chapters)
    acc: Dict[str, Dict[str, Dict[str, Any]]] = {c: {} for c in CARD_SCHEMA}  # ctype -> id -> card
    stats: Dict[str, int] = {"chapters": 0}

    for i, (title, body) in enumerate(chapters, 1):
        if stop_check and stop_check():
            if progress_cb:
                progress_cb(i - 1, total, "已终止")
            break
        # 1) 章节落盘（复用项目存储层，自动续号并登记 project.json）
        proj.add_chapter(project_dir, title, body)
        stats["chapters"] += 1
        # 2) 逐章抽卡
        extracted = extract_chapter(title, body)
        for ctype, cards in extracted.items():
            for card in cards:
                norm = _normalize(ctype, card)
                if not _has_content(norm):
                    continue
                filled = _apply_defaults(ctype, "", norm, None)
                if _has_content(filled):
                    acc[ctype][str(filled["id"])] = filled
        if progress_cb:
            progress_cb(i, total, f"已处理：{title}")

    # 3) 合并写卡
    for ctype, by_id in acc.items():
        items = list(by_id.values())
        if merge and items:
            existing = proj.load_cards(project_dir, ctype)
            items = _merge(items, existing)
        elif not items:
            continue
        proj.save_cards(project_dir, ctype, items)
        stats[ctype] = len(items)
    return stats


# ---------------------------------------------------------------------------
# CLI（调试用，不参与 Web 流程）
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="小说 txt -> 章节 + 卡片（拆书解析）")
    p.add_argument("txt", help="小说 txt 文件")
    p.add_argument("--project", default=None, help="目标项目目录（缺省 projects/default）")
    p.add_argument("--out", default=None, help="仅输出卡片 JSON 到该目录（非项目模式，不存章节）")
    p.add_argument("--no-merge", action="store_true", help="不合并已有卡片，直接覆盖")
    args = p.parse_args(argv)

    with open(args.txt, "r", encoding="utf-8") as f:
        txt = f.read()

    if args.out:
        # 仅抽卡模式：章节不落盘，卡片写 out 目录
        os.makedirs(args.out, exist_ok=True)
        chapters = split_chapters(txt)
        acc = {c: {} for c in CARD_SCHEMA}
        for title, body in chapters:
            for ctype, cards in extract_chapter(title, body).items():
                for card in cards:
                    norm = _normalize(ctype, card)
                    if not _has_content(norm):
                        continue
                    filled = _apply_defaults(ctype, "", norm, None)
                    if _has_content(filled):
                        acc[ctype][str(filled["id"])] = filled
        for ctype, by_id in acc.items():
            items = list(by_id.values())
            if not items:
                continue
            fname = proj.CARD_TYPES[ctype][0]
            if ctype == "plot":
                fname = "stories.json" if os.path.exists(os.path.join(args.out, "stories.json")) else "plots.json"
            proj._write_db(os.path.join(args.out, fname), {str(i.get("id", uuid.uuid4().hex)): i for i in items})
        print("仅卡片模式，输出到", args.out)
        return 0

    project_dir = proj.resolve_project(args.project)
    stats = parse_book(txt, project_dir, merge=not args.no_merge)
    print("\n=== 拆书完成 ===")
    print(f"章节：{stats.get('chapters', 0)} 章")
    for ctype in CARD_SCHEMA:
        if ctype in stats:
            print(f"  {CARD_SCHEMA[ctype]['label']}：{stats[ctype]} 张")
    print(f"项目位置：{project_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
