#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 协作创作工作流 —— LLM 调用与素材卡读写工具。

集中 get_llm / _call_llm（大模型访问）与 load_card_file / save_card_file /
format_cards（素材卡 IO），供各节点复用，避免 collab_novel_agent.py 过长。
"""

import json
import os
import uuid
from typing import Optional, List, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from state import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_API_KEY,
    LLM_FORCE_CONNECTION_CLOSE,
    LLM_MAX_RETRIES,
    _llm_cache,
    DATA_DIR,
)


def get_llm(temperature: float = 0.6) -> ChatOpenAI:
    """按温度取 LLM 实例（缓存），避免导入时因缺 Key 报错，也让各角色温度不同。"""
    if temperature not in _llm_cache:
        api_key = os.environ.get("LLM_API_KEY") or DEFAULT_LLM_API_KEY
        extra = {}
        if LLM_FORCE_CONNECTION_CLOSE:
            extra["default_headers"] = {"Connection": "close"}
        _llm_cache[temperature] = ChatOpenAI(
            model=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
            temperature=temperature,
            max_tokens=16384,
            **extra,
        )
    return _llm_cache[temperature]


def _call_llm(
    prompt: str,
    system: str = "你是一位专业的小说创作助手。",
    temperature: float = 0.7,
) -> str:
    """
    调用大模型，失败时返回空字符串供上层降级处理。
    temperature 控制角色温度；失败自动重试（服务端偶发 404/超时时有用）。
    """
    messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
    last_err = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            return get_llm(temperature).invoke(messages).content.strip()
        except Exception as e:
            last_err = e
            print(f" LLM 调用失败（第 {attempt + 1}/{LLM_MAX_RETRIES} 次）: {e}")
    print(f" LLM 调用最终失败: {last_err}")
    return ""


# ---------------------------------------------------------------------------
# 工具函数：读写素材卡
# ---------------------------------------------------------------------------
def load_card_file(filename: str, ids: Optional[List[str]] = None,
                   base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    读取卡片 JSON。base_dir 缺省时用全局 DATA_DIR；项目模式传入项目的 cards/ 目录。
    支持：
      - 直接按 id 列表过滤；
      - 未传 id 时返回全部；
      - 文件不存在时返回空列表。
    """
    base_dir = base_dir or DATA_DIR
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取 {filename} 失败: {e}")
        return []

    # 统一成列表
    if isinstance(data, dict):
        items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []

    if not ids:
        return items

    result = []
    for id_ in ids:
        id_str = str(id_)
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")) == id_str:
                result.append(item)
                break
    return result


def save_card_file(filename: str, items: List[Dict[str, Any]],
                   base_dir: Optional[str] = None):
    """以对象字典形式保存卡片（key = id），保留旧数据并覆盖同名 id。base_dir 缺省用 DATA_DIR。"""
    base_dir = base_dir or DATA_DIR
    path = os.path.join(base_dir, filename)
    db: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id", uuid.uuid4().hex))
        db[key] = item

    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def format_cards(cards: List[Dict[str, Any]], title: str = "卡片") -> str:
    """把卡片列表格式化成给 LLM 看的文本。"""
    if not cards:
        return f"【无{title}】"
    lines = [f"### {title}（共 {len(cards)} 条）"]
    for i, card in enumerate(cards, 1):
        name = card.get("name") or card.get("title") or card.get("id") or f"第{i}条"
        content = json.dumps(card, ensure_ascii=False)
        lines.append(f"\n--- 第 {i} 条：{name} ---\n{content}")
    return "\n".join(lines)
