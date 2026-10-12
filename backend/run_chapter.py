#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoryCaldron 多 Agent 协作小说创作 —— 命令行入口（项目模式）

每个小说是一个「项目目录」，里面自己管理素材卡和章节正文。用法：

    # 0)（推荐）用 Markdown 写设定，一键转成卡片（独立工具，不进小说流程）
    .venv\\Scripts\\python.exe backend\\run_chapter.py import-md 设定.md --project projects/mybook
    #    MD 书写模板：python backend/md_to_cards.py --template

    # 1) 新建一个项目（--demo 直接塞一套演示卡，方便第一次试跑）
    .venv\\Scripts\\python.exe backend\\run_chapter.py init --project projects/mybook --demo

    # 2) 看看这个项目里有哪些卡
    .venv\\Scripts\\python.exe backend\\run_chapter.py cards --project projects/mybook

    # 3) 交互式补一张卡（按字段提示填）
    .venv\\Scripts\\python.exe backend\\run_chapter.py new-card --project projects/mybook --type character

    # 4) 向导式一次性建好几类卡
    .venv\\Scripts\\python.exe backend\\run_chapter.py setup --project projects/mybook

    # 5) 写一章（跑到人工审核会停下来让你当场给意见）
    .venv\\Scripts\\python.exe backend\\run_chapter.py write --project projects/mybook ^
        --title "第二章 剑鸣" ^
        --outline "陆青崖引动古剑击退妖兽，封印裂痕扩大被长老察觉。" ^
        --prev "第一章：参加外门考核，进入断魂林。"

    # 不带 --project 时默认用 projects/default（不存在会自动创建）
    .venv\\Scripts\\python.exe backend\\run_chapter.py write --title "..." --outline "..."

    # 跳过人工审核直接跑完：加 --auto
    .venv\\Scripts\\python.exe backend\\run_chapter.py write --project projects/mybook --auto

项目目录结构：
    <project>/
        project.json        # 项目元信息 + 章节索引
        cards/              # 人物/剧情/文风/伏笔/世界观 卡片
        chapters/           # chapter_001.txt, chapter_002.txt ...
"""
import argparse
import json
import os
import sys

# 允许直接用 `python backend/run_chapter.py` 运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collab_novel_agent as agent
import project as proj
from collab_novel_agent import start_session


# ---------------------------------------------------------------------------
# 输入辅助
# ---------------------------------------------------------------------------
def ask(prompt: str) -> str:
    """读一行输入；非交互环境（管道/自动化）直接报错退出。"""
    try:
        return input(prompt).strip()
    except EOFError:
        print("\n错误：当前不是交互式终端，请用 --title / --outline 传参。", file=sys.stderr)
        sys.exit(2)


def read_multiline(prompt: str) -> str:
    """读取多行文本，输入单独一行 END 结束。"""
    print(prompt)
    print("（粘贴全文，输入单独一行 END 结束输入）")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def preview(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n……（全文 {len(text)} 字，此处省略后 {len(text) - limit} 字）"


# ---------------------------------------------------------------------------
# 人工审核
# ---------------------------------------------------------------------------
def ask_action(round_no: int, state: dict) -> dict:
    """在人工审核暂停点询问用户，返回一条人工动作。"""
    draft = state.get("style_edited_draft") or state.get("draft") or ""

    print("\n" + "=" * 64)
    print(f"👤 人工审核 · 第 {round_no} 次暂停")
    print("-" * 64)
    print(f"本章计划：{(state.get('chapter_plan') or '（无）')[:200]}")
    print("-" * 64)
    print("当前稿（节选）：")
    print(preview(draft))
    print("=" * 64)

    while True:
        try:
            choice = input(
                "请选择： [1] 通过    [2] 提修改意见（回炉重润）"
                "    [3] 直接给出全文    [4] 终止本次创作\n> "
            ).strip()
        except EOFError:
            print("\n（输入已耗尽，按“终止”处理）")
            return {"action": "quit"}

        if choice in ("1", "通过", "approved"):
            return {"action": "approved"}

        if choice in ("2", "修改", "意见", "revise"):
            try:
                fb = input("请输入修改意见（回车结束）：").strip()
            except EOFError:
                fb = ""
            if not fb:
                print("⚠️ 意见为空，请重新选择。")
                continue
            return {"action": "revise", "feedback": fb}

        if choice in ("3", "全文", "edit"):
            text = read_multiline("请粘贴你的全文：")
            if not text.strip():
                print("⚠️ 内容为空，请重新选择。")
                continue
            return {"action": "edit", "edited_draft": text}

        if choice in ("4", "终止", "quit", "exit", "q"):
            return {"action": "quit"}

        print("⚠️ 输入无效，请输入 1 / 2 / 3 / 4。")


def run_interactive(state: dict) -> dict:
    """
    交互式驱动工作流：每次停在 human_review 前，就询问用户该怎么处理，
    应用后再继续。选「终止」则停止驱动，不继续出稿。
    """
    sid = state["session_id"]
    config = {"configurable": {"thread_id": sid}}

    print(f"\n▶️ 开始执行（会话 {sid}，将在人工审核处暂停）\n")
    agent.app.invoke(state, config)

    round_no = 0
    while True:
        gs = agent.app.get_state(config)

        if not gs.next:
            print("\n🏁 工作流结束")
            break
        if "human_review" not in gs.next:
            print(f"\n⚠️ 停在非预期节点 {gs.next}，结束。")
            break

        round_no += 1
        action = ask_action(round_no, gs.values)

        if action["action"] == "quit":
            print("\n⛔ 已终止本次创作，未出稿。")
            return gs.values

        updates = {
            "waiting_for_human": False,
            "human_action": action["action"],
            "human_feedback": action.get("feedback", ""),
        }
        if action["action"] == "edit":
            updates["style_edited_draft"] = action.get("edited_draft", "")

        agent.app.update_state(config, updates)
        agent.app.invoke(None, config)

    return agent.app.get_state(config).values


# ---------------------------------------------------------------------------
# 收尾汇总
# ---------------------------------------------------------------------------
def print_summary(final: dict):
    print("\n" + "=" * 64)
    print("📋 执行轨迹")
    print("-" * 64)
    for log in final.get("step_logs", []):
        status = log.get("status", "?")
        mark = {"success": "✅", "failed": "❌", "running": "⏳"}.get(status, "•")
        print(f"  {mark} {log.get('step_name', ''):<12} {log.get('duration_ms', 0):>6} ms")

    print("-" * 64)
    print(f"阶段：{final.get('current_stage')}")
    print(f"大纲通过：{final.get('plan_approved')}    正典通过：{final.get('canon_approved')}")

    project_dir = final.get("project_dir")
    if project_dir:
        meta = proj.read_meta(project_dir)
        chapters = meta.get("chapters", [])
        if chapters:
            last = chapters[-1]
            print(f"项目目录：{project_dir}")
            print(f"定稿文件：{os.path.join(project_dir, 'chapters', last['file'])}")
            print(f"已写章节数：{len(chapters)}")
    else:
        sid = str(final.get("session_id", ""))[:8]
        out_path = os.path.join(agent.OUTPUT_DIR, f"chapter_{sid}.txt")
        if os.path.exists(out_path):
            print(f"定稿文件：{out_path}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------
def cmd_init(args):
    root = proj.resolve_project(args.project)
    proj.ensure_project(root, seed_demo=args.demo)
    print(f"✅ 项目已就绪：{root}")
    if args.demo:
        print("   已写入演示卡片（人物/剧情/文风/伏笔/世界观各 1 条）。")


def cmd_cards(args):
    root = proj.resolve_project(args.project)
    proj.ensure_project(root)  # 保证目录存在，便于查看空项目
    cards = proj.list_cards(root)
    print(f"项目：{root}\n")
    for c in cards:
        print(f"■ {c['label']}  ({c['file']})  共 {c['count']} 条")
        for item in c["items"]:
            cid = item.get("id", "?")
            name = (item.get("name") or item.get("title") or item.get("content")
                    or item.get("world_theme") or "")
            name = str(name).replace("\n", " ")[:40]
            print(f"    - id={cid}  {name}")
        print()


def _prompt_card(card_type: str, data_json: str = "") -> dict:
    """构造一张卡。data_json 非空且能解析时直接采用（不再逐项提问）；否则交互式提示。"""
    fields = proj.CARD_FIELDS.get(card_type, ["id"])

    # --data 直传：解析成功就直接用，跳过逐项提问
    if data_json:
        try:
            card = json.loads(data_json)
            if isinstance(card, dict) and card:
                if not card.get("id"):
                    import uuid
                    card["id"] = f"{card_type[:3]}_{uuid.uuid4().hex[:6]}"
                return card
        except Exception as e:
            print(f"⚠️ --data 解析失败：{e}，改为逐项输入。")

    # 交互式：按字段逐个提示（回车留空）
    card: dict = {}
    print(f"—— 新建{proj.CARD_TYPES[card_type][1]}（回车可留空） ——")
    for f in fields:
        val = ask(f"{f} = ")
        if val:
            card[f] = val
    if not card.get("id"):
        import uuid
        card["id"] = f"{card_type[:3]}_{uuid.uuid4().hex[:6]}"
    return card


def cmd_new_card(args):
    root = proj.resolve_project(args.project)
    proj.ensure_project(root)
    card = _prompt_card(args.type, args.data)
    key = proj.create_card(root, args.type, card)
    print(f"✅ 已写入 {proj.CARD_TYPES[args.type][0]}  id={key}")


def cmd_setup(args):
    """向导：依次建立各类卡片。每张卡问要不要加，回车结束。"""
    root = proj.resolve_project(args.project)
    proj.ensure_project(root)
    for ctype, (fname, label) in proj.CARD_TYPES.items():
        print(f"\n=== {label}（文件 {fname}）===")
        print("  逐个添加；某张卡的名称直接回车，则结束该类、进入下一类。")
        while True:
            name = ask(f"  新建一条{label}的 id/名称（回车结束此类）：")
            if not name:
                break
            card = _prompt_card(ctype, "")
            card["id"] = card.get("id") or name
            if "name" in proj.CARD_FIELDS[ctype] and not card.get("name"):
                card["name"] = name
            key = proj.create_card(root, ctype, card)
            print(f"    ✅ 已写入 id={key}")
    print(f"\n✅ 项目素材卡建立完成：{root}")


def cmd_import_md(args):
    """把 MD 设定转成卡片（独立工具，不进入小说生成流程）。"""
    from md_to_cards import convert_to_project

    root = proj.resolve_project(args.project)
    stats, _ = convert_to_project(
        args.md, root, use_llm=not args.no_llm, merge=not args.no_merge
    )
    target = os.path.join(root, proj.CARDS_DIR)
    print("\n=== 转换完成 ===")
    if not stats:
        print("未从 MD 中识别到任何卡片。二级标题需包含："
              "人物 / 剧情 / 文风 / 伏笔 / 世界观 等关键词。")
        return
    for ctype, cnt in stats.items():
        print(f"  {proj.CARD_TYPES[ctype][1]}：{cnt} 张")
    print(f"\n输出位置：{target}")


def cmd_write(args):
    root = proj.resolve_project(args.project)
    # 写章节前确保项目存在（不存在则自动创建空项目）
    proj.ensure_project(root)
    print(f"📁 项目目录：{root}")

    title = args.title or ask("请输入章节标题：")
    outline = args.outline or ask("请输入本章大纲：")
    # --prev 省略（None）才询问；显式传 --prev "" 表示确实没有上一章
    prev = args.prev if args.prev is not None else ask("请输入上一章概括（可直接回车跳过）：")

    def ids(raw):
        xs = [x.strip() for x in raw.split(",") if x.strip()]
        return xs or None

    # 若指定了某些卡 id，则从项目里只取这些；否则全部加载
    state = start_session(
        chapter_title=title,
        chapter_outline=outline,
        previous_summary=prev,
        character_ids=ids(args.characters),
        plot_ids=ids(args.plots),
        style_ids=ids(args.styles),
        foreshadowing_ids=ids(args.fore),
        worldview_ids=ids(args.worlds),
        project_dir=root,
    )["state"]

    if not state.get("character_cards") and not state.get("plot_cards") \
            and not state.get("style_cards"):
        print("⚠️ 该项目还没有任何素材卡，Agent 只能凭大纲自由发挥。"
              "可先跑 `setup`/`new-card` 建卡，或 `init --demo` 塞演示卡。")

    if args.auto:
        print(f"\n▶️ 开始执行（会话 {state['session_id']}，自动通过人工审核）\n")
        final = agent.run_session(state, auto_approve_human=True)
    else:
        final = run_interactive(state)

    print_summary(final)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="StoryCaldron 多 Agent 协作小说创作（项目模式命令行入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=None,
                        help="项目目录路径；缺省用 ./projects/default（自动创建）")

    # init
    sp = sub.add_parser("init", parents=[common], help="创建/初始化项目目录（--demo 写入演示卡）")
    sp.add_argument("--demo", action="store_true", help="初始化时写入一套演示素材卡")

    # cards / list-cards
    sub.add_parser("cards", parents=[common], help="列出项目内所有素材卡")
    sub.add_parser("list-cards", parents=[common], help="列出项目内所有素材卡（cards 的别名）")

    # new-card
    sp = sub.add_parser("new-card", parents=[common], help="交互式新建一张素材卡")
    sp.add_argument("--type", required=True,
                    choices=list(proj.CARD_TYPES.keys()),
                    help="卡片类型：character/plot/style/foreshadowing/worldview")
    sp.add_argument("--data", default="",
                    help="可选：直接用 JSON 字符串提供字段，如 '{\"id\":\"v\",\"name\":\"张三\"}'")

    # setup
    sub.add_parser("setup", parents=[common], help="向导式一次性建立各类素材卡")

    # write
    sp = sub.add_parser("write", parents=[common], help="在项目内写一章")
    sp.add_argument("--title", default="", help="章节标题")
    sp.add_argument("--outline", default="", help="本章大纲")
    sp.add_argument("--prev", default=None, help="上一章概括（可选，省略时会交互询问）")
    sp.add_argument("--characters", default="", help="人物卡 id，逗号分隔；留空=全部")
    sp.add_argument("--plots", default="", help="剧情卡 id，逗号分隔；留空=全部")
    sp.add_argument("--styles", default="", help="文风卡 id，逗号分隔；留空=全部")
    sp.add_argument("--fore", default="", help="伏笔卡 id，逗号分隔；留空=全部")
    sp.add_argument("--worlds", default="", help="世界观卡 id，逗号分隔；留空=全部")
    sp.add_argument("--auto", action="store_true", help="跳过人工审核，自动通过后跑完")

    # import-md（独立工具：MD -> 卡片 JSON，不进入小说生成流程）
    sp = sub.add_parser("import-md", parents=[common],
                        help="把 Markdown 设定转成卡片 JSON（独立工具）")
    sp.add_argument("md", help="Markdown 设定文件或目录")
    sp.add_argument("--no-llm", action="store_true", help="不使用大模型，纯规则解析")
    sp.add_argument("--no-merge", action="store_true", help="不合并已有卡片，直接覆盖")

    return p


def main():
    args = build_parser().parse_args()
    cmd = args.cmd or "write"  # 不带子命令时默认写一章

    if cmd in ("cards", "list-cards"):
        cmd_cards(args)
    elif cmd == "init":
        cmd_init(args)
    elif cmd == "new-card":
        cmd_new_card(args)
    elif cmd == "setup":
        cmd_setup(args)
    elif cmd == "write":
        cmd_write(args)
    elif cmd == "import-md":
        cmd_import_md(args)
    else:
        build_parser().print_help()


if __name__ == "__main__":
    main()
