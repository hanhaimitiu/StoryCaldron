"""
StoryCaldron 多 Agent 协作小说创作 —— 命令行入口

用法示例：
    # 看有哪些素材卡可用
    .venv\\Scripts\\python.exe backend\\run_chapter.py --list-cards

    # 交互式写一章（跑到人工审核时在终端里当场输入意见）
    .venv\\Scripts\\python.exe backend\\run_chapter.py ^
        --title "第二章 剑鸣" ^
        --outline "陆青崖引动古剑击退妖兽，封印裂痕扩大被长老察觉。" ^
        --prev "第一章：参加外门考核，进入断魂林。"

    # 不带任何参数也可以，会提示你输入标题和大纲
    .venv\\Scripts\\python.exe backend\\run_chapter.py

    # 跳过人工审核，直接跑完
    .venv\\Scripts\\python.exe backend\\run_chapter.py --title "..." --outline "..." --auto

与 collab_novel_agent.py 的区别：
    这个入口【只读取】backend/data/ 下的素材卡，不会覆盖或重置它们。
"""
import argparse
import os
import sys

# 允许直接用 `python backend/run_chapter.py` 运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collab_novel_agent as agent
from collab_novel_agent import start_session, run_session


# ---------------------------------------------------------------------------
# 素材卡浏览
# ---------------------------------------------------------------------------
CARD_FILES = [
    ("人物卡", "characters.json"),
    ("剧情卡", "stories.json"),
    ("剧情卡", "plots.json"),
    ("文风卡", "styles.json"),
    ("伏笔卡", "foreshadowing.json"),
    ("世界观卡", "wordviews.json"),
]


def list_cards():
    """列出 data/ 下所有可用素材卡的 id 与摘要，方便用 --xxx 选卡。"""
    print("可用素材卡（backend/data/）：\n")
    seen = set()
    for label, filename in CARD_FILES:
        if filename in seen:
            continue
        seen.add(filename)
        items = agent.load_card_file(filename)
        print(f"■ {label}  ({filename})  共 {len(items)} 条")
        if not items:
            print("    （无）")
            continue
        for item in items:
            cid = item.get("id", "?")
            name = (
                item.get("name")
                or item.get("title")
                or item.get("content")
                or item.get("world_theme")
                or ""
            )
            name = str(name).replace("\n", " ")[:40]
            print(f"    - id={cid}  {name}")
        print()

    print("提示：选卡参数形如 --characters hero,villain（逗号分隔）；留空表示全部加载。")


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

    sid = str(final.get("session_id", ""))[:8]
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"chapter_{sid}.txt")
    if os.path.exists(out_path):
        print(f"定稿文件：{out_path}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="StoryCaldron 多 Agent 协作小说创作（命令行入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--title", default="", help="章节标题，如 “第二章 剑鸣”")
    p.add_argument("--outline", default="", help="本章大纲")
    p.add_argument("--prev", default=None, help="上一章概括（可选，省略时会交互询问）")
    p.add_argument("--characters", default="", help="人物卡 id，逗号分隔；留空=全部")
    p.add_argument("--plots", default="", help="剧情卡 id，逗号分隔；留空=全部")
    p.add_argument("--styles", default="", help="文风卡 id，逗号分隔；留空=全部")
    p.add_argument("--fore", default="", help="伏笔卡 id，逗号分隔；留空=全部")
    p.add_argument("--worlds", default="", help="世界观卡 id，逗号分隔；留空=全部")
    p.add_argument("--auto", action="store_true", help="跳过人工审核，自动通过后跑完")
    p.add_argument("--list-cards", action="store_true", help="列出可用素材卡后退出")
    return p


def parse_ids(raw: str):
    ids = [x.strip() for x in raw.split(",") if x.strip()]
    return ids or None


def main():
    args = build_parser().parse_args()

    if args.list_cards:
        list_cards()
        return

    title = args.title or ask("请输入章节标题：")
    outline = args.outline or ask("请输入本章大纲：")
    # --prev 省略（None）才询问；显式传 --prev "" 表示确实没有上一章
    prev = args.prev if args.prev is not None else ask("请输入上一章概括（可直接回车跳过）：")

    state = start_session(
        chapter_title=title,
        chapter_outline=outline,
        previous_summary=prev,
        character_ids=parse_ids(args.characters),
        plot_ids=parse_ids(args.plots),
        style_ids=parse_ids(args.styles),
        foreshadowing_ids=parse_ids(args.fore),
        worldview_ids=parse_ids(args.worlds),
    )["state"]

    if args.auto:
        print(f"\n▶️ 开始执行（会话 {state['session_id']}，自动通过人工审核）\n")
        final = run_session(state, auto_approve_human=True)
    else:
        final = run_interactive(state)

    print_summary(final)


if __name__ == "__main__":
    main()
