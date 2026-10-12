#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MD -> 卡片 JSON 转换工具（独立 Agent 模块）

这是一个「建卡」工具，不是小说生成流程的一部分：
    你用 Markdown 自由书写小说设定（人物 / 剧情 / 文风 / 伏笔 / 世界观）
        -> 本模块作为一个独立的 Agent，把 MD 解析成项目目录里 cards/ 下的五类 JSON 卡片
        -> 之后 run_chapter.py write 再去读取这些卡片写小说

设计要点：
- 独立的模块、独立的 CLI，与 collab_novel_agent 的小说生成流程解耦；
- 优先用大模型做结构化提取（更鲁棒，能读懂自由书写的散文式设定）；
- 大模型不可用时自动退回到纯规则解析（按「- 字段：值」 bullet 提取），保证离线可用；
- 写入时按 id 合并已有卡片，重复运行可增量更新，不会整体覆盖。

用法：
    python md_to_cards.py 设定.md --project 项目目录
    python md_to_cards.py 设定.md --out ./cards_out        # 直接出 JSON，不建项目
    python md_to_cards.py --template                        # 打印一份 MD 书写模板
    python md_to_cards.py --list-types                      # 列出支持的卡片类型与字段
"""
import glob
import json
import os
import re
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

# 复用项目卡片管理 + 现有 LLM 调用（含 keep-alive 修复与重试），避免重复造轮子
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project as proj
from collab_novel_agent import _call_llm

# ---------------------------------------------------------------------------
# 卡片 schema：与 project.CARD_FIELDS 保持一致
# ---------------------------------------------------------------------------
CARD_SCHEMA: Dict[str, Dict[str, Any]] = {
    "character": {
        "label": "人物卡",
        "fields": ["id", "name", "gender", "appearance", "personality", "identity", "ability"],
        "field_aliases": {
            "name": ["姓名", "名字", "角色名", "称谓"],
            "gender": ["性别"],
            "appearance": ["外貌", "长相", "样貌", "形象", "外表"],
            "personality": ["性格", "性情", "秉性", "脾气"],
            "identity": ["身份", "职业", "门派", "地位", "阵营"],
            "ability": ["能力", "修为", "实力", "功法", "技能", "境界"],
        },
    },
    "plot": {
        "label": "剧情卡",
        "fields": ["id", "title", "status", "description"],
        "field_aliases": {
            "title": ["标题", "名称", "章节", "事件"],
            "status": ["状态"],
            "description": ["概述", "简介", "描述", "内容", "剧情", "梗概"],
        },
    },
    "style": {
        "label": "文风卡",
        "fields": ["id", "title", "style_overall", "sentence_feature", "word_preference"],
        "field_aliases": {
            "title": ["标题", "名称", "名称风格"],
            "style_overall": ["整体风格", "风格", "总览", "基调", "调性"],
            "sentence_feature": ["句式", "句法", "句式特点", "节奏", "句子"],
            "word_preference": ["用词", "词汇", "用词偏好", "词语", "遣词"],
        },
    },
    "foreshadowing": {
        "label": "伏笔卡",
        "fields": ["id", "content", "status"],
        "field_aliases": {
            "content": ["内容", "描述", "伏笔", "详情", "线索"],
            "status": ["状态"],
        },
    },
    "worldview": {
        "label": "世界观卡",
        "fields": ["id", "world_theme", "power_system", "world_rule"],
        "field_aliases": {
            "world_theme": ["主题", "世界观", "题材", "背景", "世界"],
            "power_system": ["力量体系", "修炼体系", "力量", "修为体系", "等级", "境界体系"],
            "world_rule": ["规则", "世界规则", "法则", "设定", "规矩"],
        },
    },
}

# 章节标题 -> 卡片类型（宽容匹配，命中任一关键词即可）
SECTION_KEYWORDS: Dict[str, List[str]] = {
    "character": ["人物", "角色", "人设"],
    "plot": ["剧情", "故事", "情节"],
    "style": ["文风", "风格", "笔风", "文笔"],
    "foreshadowing": ["伏笔", "悬念", "暗线"],
    "worldview": ["世界观", "世界", "设定", "背景"],
}

# 显式指定 id 的别名（优先级最高）
ID_ALIASES = ["id", "编号", "标识", "卡id", "卡号"]


# ---------------------------------------------------------------------------
# MD 解析（与是否联网无关，纯文本处理）
# ---------------------------------------------------------------------------
def split_sections(md: str) -> List[Tuple[str, str]]:
    """按二级标题 '##' 把 MD 切成 (标题, 正文) 列表。一级标题前言被忽略。"""
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", md)
    out: List[Tuple[str, str]] = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        out.append((title, body))
    return out


def match_card_type(header: str) -> Optional[str]:
    """把 '## 人物卡' 之类的标题映射到卡片类型。"""
    h = header.lower()
    for ctype, kws in SECTION_KEYWORDS.items():
        for kw in kws:
            if kw in h:
                return ctype
    return None


def split_cards(body: str) -> List[Tuple[str, str]]:
    """
    把一个 section 的正文按三级标题 '###' 切成 (卡片标题, 卡片正文) 列表。
    若没有 '###'，则整段作为一张卡（标题为空）。
    """
    blocks = re.split(r"(?m)^###\s+(.+?)\s*$", body)
    cards: List[Tuple[str, str]] = []
    for i in range(1, len(blocks), 2):
        title = blocks[i].strip()
        cbody = blocks[i + 1] if i + 1 < len(blocks) else ""
        cards.append((title, cbody.strip()))
    if not cards and body.strip():
        cards.append(("", body.strip()))
    return cards


def parse_bullets(body: str) -> Tuple[Dict[str, str], List[str]]:
    """
    解析 '- 字段：值' / '字段：值' 行。
    返回 (键值对字典, 无法识别为 key:value 的自由文本行)。
    """
    kv: Dict[str, str] = {}
    free: List[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*+]\s*(.*)$", s)
        if m:
            s = m.group(1).strip()
        m2 = re.match(r"^([^：:]{1,20})[：:]\s*(.*)$", s)
        if m2:
            kv[m2.group(1).strip()] = m2.group(2).strip()
        else:
            free.append(s)
    return kv, free


def _slug_id(title: str, ctype: str) -> str:
    """根据标题生成稳定 id（中文保留，空格/标点替换为下划线）。"""
    t = re.sub(r"\s+", "_", (title or "").strip())
    t = re.sub(r"[^\w一-鿿]+", "", t)
    if not t:
        t = f"{ctype[:3]}_{uuid.uuid4().hex[:6]}"
    return t[:40]


def _has_content(card: Dict[str, Any]) -> bool:
    return any(v for k, v in card.items() if k != "id" and isinstance(v, str) and v.strip())


# ---------------------------------------------------------------------------
# 大模型提取（Agent 的核心：读懂自由书写的设定）
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出里稳健地抠出一个 JSON 对象。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    try:
        obj = json.loads(text[s : e + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def llm_extract(ctype: str, title: str, body: str) -> Optional[Dict[str, Any]]:
    """调用大模型，把一张卡的原始内容整理成结构化 JSON。失败返回 None。"""
    schema = CARD_SCHEMA[ctype]
    fields = [f for f in schema["fields"] if f != "id"]
    alias_hint = "; ".join(
        f"{f}（别名：{'/'.join(schema['field_aliases'].get(f, [f])) or '—'}）" for f in fields
    )
    system = (
        "你是一个小说设定卡提取助手。用户会给你一张设定卡片的标题和原始内容，"
        "你需要把它整理成结构化的 JSON 对象，字段必须严格遵循给定的字段列表。"
        "只输出 JSON，不要输出任何解释或代码块标记。"
    )
    prompt = f"""卡片类型：{schema['label']}
卡片标题：{title or '（未命名）'}

原始内容：
{body}

请提取为如下字段的 JSON 对象（id 不要填，由系统生成）：
{', '.join(fields)}

字段含义提示：
{alias_hint}

要求：
1. 只输出一个 JSON 对象，键名必须用上面列出的英文字段名；
2. 找不到对应信息的字段填空字符串 ""；
3. 如果卡片标题本身就是人物名 / 剧情名 / 世界观主题，请填入对应字段；
4. 不要编造原文没有的关键事实，可对原文做合理归纳。
"""
    raw = _call_llm(prompt, system=system, temperature=0.3)
    if not raw:
        return None
    return _extract_json(raw)


def _apply_defaults(ctype: str, title: str, card: Dict[str, Any], explicit_id: Optional[str]) -> Dict[str, Any]:
    """补齐缺字段、兜底名字/标题、默认状态，并最终确定 id。"""
    schema = CARD_SCHEMA[ctype]
    for f in schema["fields"]:
        if f == "id":
            continue
        card.setdefault(f, "")
    # 标题/名字兜底
    if ctype == "character" and not card.get("name") and title:
        card["name"] = title
    if ctype in ("plot", "style") and not card.get("title") and title:
        card["title"] = title
    if ctype == "worldview" and not card.get("world_theme") and title:
        card["world_theme"] = title
    # 默认状态
    if ctype in ("plot", "foreshadowing") and not card.get("status"):
        card["status"] = "pending"
    card["id"] = (explicit_id or _slug_id(
        title or card.get("name") or card.get("title") or card.get("world_theme") or "", ctype
    ))
    return card


def extract_card(ctype: str, title: str, body: str, use_llm: bool = True) -> Dict[str, Any]:
    """一张卡的完整提取：优先 LLM，失败/关闭时回退规则解析。"""
    schema = CARD_SCHEMA[ctype]
    kv, free = parse_bullets(body)

    # 显式 id（规则层先抓，最高优先级）
    explicit_id: Optional[str] = None
    for a in ID_ALIASES:
        if a in kv and kv[a].strip():
            explicit_id = re.sub(r"\s+", "_", kv[a].strip())[:40]
            break

    card: Dict[str, Any] = {}
    if use_llm:
        obj = llm_extract(ctype, title, body)
        if obj:
            for f in schema["fields"]:
                if f == "id":
                    continue
                if f in obj and obj[f] not in (None, ""):
                    card[f] = obj[f] if isinstance(obj[f], str) else str(obj[f])
            if isinstance(obj.get("id"), str) and obj["id"].strip():
                explicit_id = obj["id"].strip()[:40]

    # 规则层兜底：把 bullet 按别名塞进对应字段
    if not _has_content(card):
        for field in schema["fields"]:
            if field == "id":
                continue
            for a in schema["field_aliases"].get(field, [field]):
                if a in kv:
                    card[field] = kv[a]
                    break
        # 伏笔没有结构化内容时，用自由文本兜底
        if ctype == "foreshadowing" and not card.get("content"):
            card["content"] = "\n".join(free) or body.strip()

    return _apply_defaults(ctype, title, card, explicit_id)


# ---------------------------------------------------------------------------
# 收集与写入
# ---------------------------------------------------------------------------
def _collect(md_path: str, use_llm: bool) -> Dict[str, List[Dict[str, Any]]]:
    """从 MD（文件或目录）里收集所有卡片。"""
    md_files: List[str] = []
    if os.path.isdir(md_path):
        for fn in sorted(os.listdir(md_path)):
            if fn.lower().endswith((".md", ".markdown", ".txt")):
                md_files.append(os.path.join(md_path, fn))
    else:
        md_files = [md_path]

    collected: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CARD_SCHEMA}
    for fp in md_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"⚠️ 读取 {fp} 失败: {e}")
            continue
        for sec_title, sec_body in split_sections(text):
            ctype = match_card_type(sec_title)
            if not ctype:
                continue
            for card_title, card_body in split_cards(sec_body):
                card = extract_card(ctype, card_title, card_body, use_llm)
                if _has_content(card):
                    collected[ctype].append(card)
    return collected


def _merge(items_new: List[Dict[str, Any]], items_existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {
        str(i.get("id")): i for i in items_existing if isinstance(i, dict)
    }
    for n in items_new:
        by_id[str(n.get("id"))] = n
    return list(by_id.values())


def convert_to_project(
    md_path: str, project_dir: str, use_llm: bool = True, merge: bool = True
) -> Tuple[Dict[str, int], Dict[str, List[Dict[str, Any]]]]:
    """把 MD 转换进某个项目目录的 cards/（按 id 合并已有卡片）。"""
    proj.ensure_project(project_dir)
    collected = _collect(md_path, use_llm)
    stats: Dict[str, int] = {}
    for ctype, items in collected.items():
        if not items:
            continue
        existing = proj.load_cards(project_dir, ctype) if merge else []
        merged = _merge(items, existing)
        proj.save_cards(project_dir, ctype, merged)
        stats[ctype] = len(merged)
    return stats, collected


def convert_to_dir(
    md_path: str, out_dir: str, use_llm: bool = True, merge: bool = True
) -> Tuple[Dict[str, int], Dict[str, List[Dict[str, Any]]]]:
    """直接把五类 JSON 写到某个目录（不建项目脚手架）。"""
    os.makedirs(out_dir, exist_ok=True)
    collected = _collect(md_path, use_llm)
    stats: Dict[str, int] = {}
    for ctype, items in collected.items():
        if not items:
            continue
        fname = proj.CARD_TYPES[ctype][0]
        if ctype == "plot":  # 剧情卡文件名兼容
            fname = "stories.json" if os.path.exists(os.path.join(out_dir, "stories.json")) else "plots.json"
        fp = os.path.join(out_dir, fname)
        existing: List[Dict[str, Any]] = []
        if merge and os.path.exists(fp):
            existing = list(proj._read_db(fp).values())
        merged = _merge(items, existing)
        proj._write_db(fp, {str(i.get("id", uuid.uuid4().hex)): i for i in merged})
        stats[ctype] = len(merged)
    return stats, collected


def _print_summary(stats: Dict[str, int], target: str) -> None:
    print("\n=== 转换完成 ===")
    if not stats:
        print("未从 MD 中识别到任何卡片。请检查二级标题是否包含："
              "人物 / 剧情 / 文风 / 伏笔 / 世界观 等关键词。")
        return
    for ctype, cnt in stats.items():
        print(f"  {CARD_SCHEMA[ctype]['label']}（{ctype}）：{cnt} 张")
    print(f"\n输出位置：{target}")


# ---------------------------------------------------------------------------
# 书写模板
# ---------------------------------------------------------------------------
SETTING_TEMPLATE = """# 我的小说设定

> 说明：用二级标题（##）区分卡片大类，三级标题（###）区分单张卡。
> 每张卡内部用「- 字段：值」列出信息，也可直接写散文，大模型会自动归纳。
> 支持的类型：人物 / 剧情 / 文风 / 伏笔 / 世界观。

## 人物卡

### 陆青崖
- 性别：男
- 外貌：青色长袍，眉间有一道旧疤
- 性格：沉稳、重情义，遇到不公会挺身而出
- 身份：青云宗外门弟子
- 能力：剑术初入门槛，体内封印未解

### 墨无尘
- 性别：男
- 外貌：一袭黑衣，看不清面容
- 性格：阴沉、城府极深
- 身份：神秘来客
- 能力：修为高深，手段狠辣

## 剧情卡

### 入门考核
- 状态：in_progress
- 概述：陆青崖参加青云宗外门考核，需在秘境中存活三日

## 文风卡

### 古风仙侠
- 整体风格：古风 / 热血 / 细腻
- 句式特点：长短句交错，打斗场景短促，心理描写绵长
- 用词偏好：常用“剑光”“灵气”“眸子”等词汇

## 伏笔卡

### 眉间旧疤
- 状态：pending
- 内容：陆青崖眉间旧疤与秘境中的古剑有神秘联系

## 世界观卡

### 青云宗世界
- 主题：低魔仙侠宗门世界
- 力量体系：炼气、筑基、金丹、元婴
- 世界规则：灵气稀薄，功法传承严苛
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="MD 设定 -> 卡片 JSON 转换工具（独立 Agent）"
    )
    p.add_argument("md", nargs="?", help="Markdown 设定文件或目录（--template/--list-types 时可选）")
    p.add_argument("--project", default=None,
                   help="目标项目目录，写入 <project>/cards/（缺省 projects/default）")
    p.add_argument("--out", default=None,
                   help="直接输出 JSON 到该目录（非项目模式）")
    p.add_argument("--no-llm", action="store_true", help="不使用大模型，纯规则解析")
    p.add_argument("--no-merge", action="store_true", help="不合并已有卡片，直接覆盖")
    p.add_argument("--template", action="store_true", help="打印一份 MD 书写模板并退出")
    p.add_argument("--list-types", action="store_true", help="列出支持的卡片类型与字段并退出")
    args = p.parse_args(argv)

    if args.template:
        print(SETTING_TEMPLATE)
        return 0
    if args.list_types:
        for c, s in CARD_SCHEMA.items():
            print(f"{c}: {s['label']} -> {', '.join(s['fields'])}")
        return 0

    use_llm = not args.no_llm
    merge = not args.no_merge

    if args.out:
        stats, _ = convert_to_dir(args.md, args.out, use_llm, merge)
        target = args.out
    else:
        project_dir = proj.resolve_project(args.project)
        stats, _ = convert_to_project(args.md, project_dir, use_llm, merge)
        target = os.path.join(project_dir, proj.CARDS_DIR)

    _print_summary(stats, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
