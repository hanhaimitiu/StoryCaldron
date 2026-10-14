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
- 两段式：plan_book 只解析不写入（切章+抽卡+跨章合并，供前端预览/勾选），
  commit_book 按勾选把章节与卡片写入项目（支持「导入前清空已有章节」）；
- 大模型不可用时，章节照常拆分，但卡片提取为空（拆书的核心是 LLM，没有就只拆章）；
- plan_book 接收 progress_cb(done, total, msg) 上报进度，便于前端做进度条/日志；
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


def extract_chapter(title: str, body: str, global_context: str = "") -> Dict[str, List[Dict[str, Any]]]:
    """调用大模型，从一章正文抽取五类卡片。

    返回 {ctype: [card, ...]}；模型不可用或解析失败返回空字典（只拆章不抽卡）。
    global_context: 来自全书全局汇总的上下文（人物总表/剧情主线/本章定位），
                    让单章抽卡与全书一致，避免人物关系与剧情主线割裂。
    """
    if not body.strip():
        return {}
    system = (
        "你是一个小说拆书助手。给定一章小说正文与全书的全局背景，请从中提取出现的人物、"
        "剧情线、文风特征、伏笔、世界观设定，整理成一个 JSON 对象。"
        "只输出 JSON，不要任何解释或代码块标记。"
    )
    global_block = ""
    if global_context:
        global_block = (
            "【全书全局背景（抽卡必须与全局一致）】\n"
            f"{global_context}\n\n"
            "抽卡对齐要求：\n"
            "- 人物卡必须与「全局人物总表」对齐：同名人物合并到总表条目，身份/关系从总表继承或补充，不要另起一条；\n"
            "- 剧情卡要基于「全局剧情主线」描述本章推进，保持连贯，不要被单章切割得支离破碎；\n"
            "- 伏笔/世界观同样与全局对齐。\n"
        )
    prompt = f"""章节标题：{title or '（未命名）'}

章节正文：
{body}

{global_block}
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
5. 同名人物/事物在多处出现时只列一条，关键特征合并（并与全局总表对齐）。
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


import json


# ---------------------------------------------------------------------------
# 全局汇总（拆书关键：先一次性通读全书，建立全局人物/剧情/世界观，再按章拆卡，
# 避免逐章孤立抽取导致人物关系与剧情主线割裂）
# ---------------------------------------------------------------------------
GLOBAL_TEXT_LIMIT = 60000  # 送入「一次性全局汇总」的整本字符上限；超长则两级（分块摘要->合并）


def _summary_system() -> str:
    return "你是一位资深小说编辑，擅长通读整本书后做全局结构梳理，输出严格的结构化 JSON。"


_GLOBAL_SCHEMA_HINT = """输出 JSON 结构：
{
  "characters": [ {"name": 姓名, "identity": 身份, "aliases": 别称, "role": 戏份定位, "relationships": [{"target": 相关人物, "relation": 关系}]} ],
  "plot_arcs": [ {"title": 主线名, "summary": 主线概要, "key_chapters": ["第X章"]} ],
  "worldviews": [ {"theme": 主题, "setting": 世界设定, "power_system": 力量体系} ],
  "foreshadowings": [ {"seed": 伏笔, "planted": 埋下处, "payoff": 预期回收} ],
  "chapter_index": [ {"title": 章节标题, "position": 位置, "summary": 本章概要, "characters": [出场人物], "plot_threads": [推进的剧情线]} ]
}"""


def _summary_once(text: str, titles, local: bool = False) -> Dict[str, Any]:
    """一次性全局/局部梳理，返回 global_view 字典（解析失败返回 {}）。"""
    scope = "全书" if not local else "以下若干连续章节"
    prompt = (
        f"这是{scope}的完整正文（共 {len(titles)} 章）。请通读后做结构梳理，"
        + _GLOBAL_SCHEMA_HINT
        + """
要求：
1. 人物关系必须跨章一致，同一人物只列一条并合并其全部关系；
2. 剧情主线（plot_arcs）要连贯，不要被章节切割得支离破碎；
3. chapter_index 每章一条，给出本章概要、出场人物与推进的剧情线；
4. 只输出一个 JSON 对象，不要解释或代码块标记。

正文：
"""
        + text
    )
    raw = _call_llm(prompt, system=_summary_system(), temperature=0.2)
    if not raw:
        return {}
    obj = _extract_json(raw)
    return obj if isinstance(obj, dict) else {}


def _merge_views(locals_views: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把多批局部梳理合并成统一全局视图（人物跨批合并去重）。"""
    payload = json.dumps(locals_views, ensure_ascii=False)
    prompt = (
        "下面是同一本书不同部分的局部梳理（JSON 数组）。请合并成一份统一的全局梳理 JSON，"
        + _GLOBAL_SCHEMA_HINT
        + """
要求：
1. 同名人物合并为一条，relationships 合并去重；
2. plot_arcs 按时间/逻辑串成连贯主线；
3. chapter_index 合并所有章节；
4. 只输出一个合并后的 JSON，不要解释。

局部梳理：
"""
        + payload
    )
    raw = _call_llm(prompt, system=_summary_system(), temperature=0.2)
    if not raw:
        return {}
    obj = _extract_json(raw)
    return obj if isinstance(obj, dict) else {}


def summarize_book(chapters: List[Tuple[str, str]], stop_check: Optional[Any] = None) -> Dict[str, Any]:
    """通读全书建立全局视图。

    - 整本正文在 GLOBAL_TEXT_LIMIT 内：一次性全局汇总；
    - 超长：分块做局部摘要，再合并成统一全局视图；
    - 模型不可用：返回 {}（上层退化为逐章孤立抽取，与原行为一致）。
    """
    full_text = "\n\n".join(f"{t}\n{b}" for t, b in chapters)
    titles = [t for t, _ in chapters]
    if len(full_text) <= GLOBAL_TEXT_LIMIT:
        return _summary_once(full_text, titles, local=False)
    batches: List[List[Tuple[str, str]]] = []
    cur: List[Tuple[str, str]] = []
    cur_len = 0
    for t, b in chapters:
        if cur and cur_len + len(b) > GLOBAL_TEXT_LIMIT:
            batches.append(cur)
            cur = []
            cur_len = 0
        cur.append((t, b))
        cur_len += len(b)
    if cur:
        batches.append(cur)
    locals_views = []
    for batch in batches:
        if stop_check and stop_check():
            break
        bt = "\n\n".join(f"{t}\n{b}" for t, b in batch)
        locals_views.append(_summary_once(bt, [t for t, _ in batch], local=True))
    if not locals_views:
        return {}
    if len(locals_views) == 1:
        return locals_views[0]
    return _merge_views(locals_views)


def _global_context_for(global_view: Dict[str, Any], title: str) -> str:
    """把全局视图压缩成给单章抽取用的上下文文本（人物总表/剧情主线/本章定位）。

    容忍全局汇总的中英文键名（characters/人物、plot_arcs/剧情主线、relationships/关系 等），
    因为不同模型返回的键可能不一致；取不到则退化为空（退化为逐章孤立抽取）。
    """
    if not isinstance(global_view, dict):
        return ""
    chars = global_view.get("characters") or global_view.get("人物") or global_view.get("人物卡") or []
    arcs = global_view.get("plot_arcs") or global_view.get("剧情主线") or global_view.get("剧情") or []
    idx = global_view.get("chapter_index") or global_view.get("章节索引") or []

    lines: List[str] = ["【全局人物总表】"]
    for c in chars or []:
        if not isinstance(c, dict):
            continue
        rels = ", ".join(
            f"{r.get('target', r.get('相关人物', ''))}:{r.get('relation', r.get('关系', ''))}"
            for r in (c.get("relationships") or c.get("关系") or [])
        )
        name = c.get("name") or c.get("姓名") or ""
        ident = c.get("identity") or c.get("身份") or ""
        if name:
            lines.append(f"- {name}（{ident}；关系：{rels}）")
    lines.append("【全局剧情主线】")
    for a in arcs or []:
        if not isinstance(a, dict):
            continue
        lines.append(f"- {a.get('title', a.get('主线名', ''))}：{a.get('summary', a.get('概要', ''))}")
    this = next((c for c in idx if isinstance(c, dict) and c.get("title") == title), None)
    if this:
        chs = this.get("characters") or this.get("出场人物") or []
        thr = this.get("plot_threads") or this.get("推进的剧情线") or []
        lines.append(
            f"【本章（{title}）在全局中的定位】{this.get('summary', this.get('概要', ''))}；"
            f"出场：{', '.join(chs)}；推进：{', '.join(thr)}"
        )
    return "\n".join(lines)


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
# 两段式：plan_book（只解析不写） + commit_book（按勾选写入）
# ---------------------------------------------------------------------------
def plan_book(
    txt: str,
    progress_cb: Optional[Any] = None,
    stop_check: Optional[Any] = None,
    global_view: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """只解析、不写入：先通读全书做全局汇总，再带全局上下文逐章抽卡并跨章合并。

    返回 {"chapters": [(title, body), ...], "cards": {ctype: [card, ...]},
          "chapter_count": N, "global_view": {...}}。
    模型不可用则 global_view 为空、cards 为空（只拆章）；stop_check() 返回 True 时中止。
    """
    chapters = split_chapters(txt)
    total = len(chapters)
    if global_view is None:
        if progress_cb:
            progress_cb(0, total, "正在通读全书，建立全局理解…")
        global_view = summarize_book(chapters, stop_check=stop_check)
    if progress_cb:
        progress_cb(0, total, "已完成全书全局理解，开始按章拆卡")

    acc: Dict[str, Dict[str, Dict[str, Any]]] = {c: {} for c in CARD_SCHEMA}  # ctype -> id -> card

    for i, (title, body) in enumerate(chapters, 1):
        if stop_check and stop_check():
            break
        ctx = _global_context_for(global_view, title)
        extracted = extract_chapter(title, body, global_context=ctx)
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

    return {
        "chapters": chapters,  # list of (title, body)
        "cards": {c: list(by_id.values()) for c, by_id in acc.items()},
        "chapter_count": total,
        "global_view": global_view,
    }


def commit_book(
    project_dir: str,
    plan: Dict[str, Any],
    chapter_idxs: Optional[List[int]] = None,
    card_ids: Optional[Dict[str, List[str]]] = None,
    merge: bool = True,
    clear_chapters: bool = False,
) -> Dict[str, int]:
    """按勾选把方案写入项目。

    chapter_idxs: 要写入的章节下标列表（None=全部）；
    card_ids: {ctype: [id, ...]} 要写入的卡片（None=全部）；
    clear_chapters: 写入前清空已有章节（对应「导入前清空已有章节」选项）；
    merge: 卡片与已有合并（True）或覆盖（False）。
    返回统计 {chapters, character, plot, style, foreshadowing, worldview}。
    """
    proj.ensure_project(project_dir)
    stats: Dict[str, int] = {"chapters": 0}

    chapters = plan.get("chapters", [])
    if clear_chapters:
        proj.clear_chapters(project_dir)
    sel = set(chapter_idxs) if chapter_idxs is not None else None
    for idx, (title, body) in enumerate(chapters):
        if sel is not None and idx not in sel:
            continue
        proj.add_chapter(project_dir, title, body)
        stats["chapters"] += 1

    for ctype, cards in plan.get("cards", {}).items():
        if not cards:
            continue
        if card_ids:  # 前端指定了勾选
            want = set(card_ids.get(ctype, []))
            items = [c for c in cards if str(c.get("id", "")) in want]
        else:
            items = list(cards)
        if not items:
            continue
        if merge:
            existing = proj.load_cards(project_dir, ctype)
            items = _merge(items, existing)
        proj.save_cards(project_dir, ctype, items)
        stats[ctype] = len(items)
    return stats


def parse_book(
    txt: str,
    project_dir: str,
    merge: bool = True,
    progress_cb: Optional[Any] = None,
    stop_check: Optional[Any] = None,
) -> Dict[str, int]:
    """CLI 用：解析并立即全部写入（等价于 plan_book + commit_book 全选）。"""
    plan = plan_book(txt, progress_cb, stop_check)
    if stop_check and stop_check():
        return {"chapters": 0}
    return commit_book(project_dir, plan, None, None, merge, clear_chapters=False)


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
