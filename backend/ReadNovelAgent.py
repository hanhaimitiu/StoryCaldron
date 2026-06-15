import json
import asyncio
import os
import uuid
import re
from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


# ---------- 工具函数 ----------
def safe_append_to_json(file_path, new_data):
    """安全追加数据到JSON文件（保留历史数据）"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {}
    key = f"character_{uuid.uuid4()}" if "characters" in file_path else \
        f"wordviews_{uuid.uuid4()}" if "wordviews" in file_path else \
            f"styles_{uuid.uuid4()}" if "styles" in file_path else \
                f"stories_{uuid.uuid4()}"
    db[key] = new_data
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)


def parse_llm_response(raw_content: str):
    """
    清洗 AI 返回的 Markdown 标记并解析 JSON。
    支持：
      - 单个 JSON 对象 -> 返回 dict
      - JSON 数组 -> 返回 list[dict]
      - 逗号分隔的多个 JSON 对象 -> 返回 list[dict]
    """
    match = re.search(r'```json\s*(.*?)\s*```', raw_content, re.DOTALL)
    clean_content = match.group(1) if match else raw_content
    clean_content = clean_content.strip()
    # 尝试直接解析
    try:
        parsed = json.loads(clean_content)
        return parsed
    except json.JSONDecodeError:
        # 处理逗号/换行分隔的多对象
        decoder = json.JSONDecoder()
        objects = []
        idx = 0
        length = len(clean_content)
        while idx < length:
            while idx < length and clean_content[idx] in ' \t\n\r,':
                idx += 1
            if idx >= length:
                break
            obj, end = decoder.raw_decode(clean_content, idx)
            objects.append(obj)
            idx = end
        if len(objects) == 1:
            return objects[0]
        return objects if objects else None


# ---------- 提示词模板（同原文，无修改）----------
TASK_PROMPTS = {
    "人物卡解析": """【多模型任务：人物专项解析】
你只负责抽取小说人物数据，不分析世界观、不分析文风、不梳理剧情。
严格依据用户提供的小说原文，提取角色信息。

字段要求：
{
    'name': '角色姓名',
    'gender': '性别',
    'appearance': '外貌特征',
    'personality': '核心性格（细分优缺点）',
    'identity': '身份/职位/宗门/势力',
    'experience': '关键经历/过往身世',
    'relationship': '关键人物关系',
    'language_habit': '说话习惯、口头禅、语气特征',
    'emotion_trait': '常态情绪、易怒点、软肋、执念',
    'behavior_habit': '行为习惯、处事风格',
    'taboo': '人物禁忌、绝对不能写的行为',
    'ability': '能力、功法、天赋、特长'
}

规则：
1. 只归纳原文真实出现内容，禁止脑补虚构
2. 信息不足填空字符串
3. 只专注人物维度，不要输出任何其他维度信息
注意
**必须输出纯JSON对象**，禁止任何额外文本、Markdown标记或解释。
**严格使用双引号**，禁止单引号。
**如果有多个人物时,多个对象间使用英文逗号分割
**确保逗号分隔符完整**：对象内键值对之间必须用逗号分隔，末尾不可有多余逗号。
**字符串内特殊符号需转义**。

小说原文：
{user_text}""",

    "世界观解析": """【多模型任务：世界观专项解析】
你只负责抽取小说世界观与规则体系，不分析人物、不分析文风、不梳理剧情。

输出字段：
{
    'world_theme': '小说题材与世界观基调',
    'world_rule': '世界核心规则、底层逻辑、禁忌规则',
    'power_system': '修炼体系/能力体系/战力等级划分',
    'force_faction': '各大势力、宗门、家族、正邪阵营关系',
    'region_map': '关键地域、城池、秘境、场景设定',
    'item_system': '关键道具、宝物、丹药、法器体系',
    'race_system': '种族、族群设定',
    'time_background': '时代背景、时间线格局'
}

规则：
1. 仅总结原文真实存在的设定
2. 缺省字段填空
3. 只专注世界观维度，严禁跨领域输出
注意
**必须输出纯JSON对象**，禁止任何额外文本、Markdown标记或解释。
**严格使用双引号**，禁止单引号。
**确保逗号分隔符完整**：对象内键值对之间必须用逗号分隔，末尾不可有多余逗号。
**字符串内特殊特殊符号需转义**。

小说原文：
{user_text}""",

    "文风节奏解析": """【多模型任务：文风节奏专项解析】
你只负责分析文本写作风格、句式、节奏、情绪特征，不抽人物、不抽世界观、不梳理剧情。

输出字段：
{
    'style_overall': '整体文风总结（古风/写实/轻快/压抑/热血等）',
    'sentence_feature': '句式特征：长短句偏好、断句习惯、是否简洁、是否铺陈',
    'word_preference': '高频用词、专属词汇、惯用修辞',
    'rhythm_feature': '叙事节奏：快节奏/慢铺垫/张弛有度/对话密集/描写密集',
    'emotion_tone': '全文情绪基调、氛围感',
    'narrate_habit': '叙事视角、旁白习惯、心理描写占比',
    'dialogue_style': '对话风格：简洁/幽默/隐忍/直白/古风对白',
    'taboo_style': '作者不喜欢的写法、避开的套路'
}

规则：
1. 全部基于文本统计归纳，不瞎编
2. 只专注文风节奏维度
注意
**必须输出纯JSON对象**，禁止任何额外文本、Markdown标记或解释。
**严格使用双引号**，禁止单引号。
**确保逗号分隔符完整**：对象内键值对之间必须用逗号分隔，末尾不可有多余逗号。
**字符串内特殊符号需转义**

小说原文：
{user_text}""",

    "剧情脉络解析": """【多模型任务：剧情专项解析】
你只负责梳理剧情、伏笔、故事进度，不分析人物、不分析世界观、不分析文风。
只输出纯净JSON，不要markdown、不输出任何多余内容。

输出字段：
{
    'main_story': '当前主线剧情进度与核心目标',
    'side_story': '正在进行的支线剧情',
    'current_conflict': '当前章节冲突、矛盾、危机',
    'pending_plot': '待解决剧情、未完成事件',
    'key_scene': '本章关键场景、关键事件记录'
}

规则：
1. 只总结原文已有剧情，禁止脑洞续写
2. 伏笔必须精准摘录，不得编造
3. 只专注剧情维度
4. 输出纯JSON，用于后续章节炼丹约束

小说原文：
{user_text}"""
}

import json
import asyncio
import os
import uuid
import re
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


# ---------- 工具函数 ----------
def safe_append_to_json(file_path, new_data):
    """安全追加数据到JSON文件（保留历史数据）"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {}
    key = f"character_{uuid.uuid4()}" if "characters" in file_path else \
        f"wordviews_{uuid.uuid4()}" if "wordviews" in file_path else \
            f"styles_{uuid.uuid4()}" if "styles" in file_path else \
                f"stories_{uuid.uuid4()}"
    db[key] = new_data
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)


def parse_llm_response(raw_content: str):
    """清洗并解析JSON，支持单对象、数组、逗号分隔多对象"""
    match = re.search(r'```json\s*(.*?)\s*```', raw_content, re.DOTALL)
    clean_content = match.group(1) if match else raw_content
    clean_content = clean_content.strip()
    try:
        parsed = json.loads(clean_content)
        return parsed
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        objects = []
        idx = 0
        length = len(clean_content)
        while idx < length:
            while idx < length and clean_content[idx] in ' \t\n\r,':
                idx += 1
            if idx >= length:
                break
            obj, end = decoder.raw_decode(clean_content, idx)
            objects.append(obj)
            idx = end
        if len(objects) == 1:
            return objects[0]
        return objects if objects else None


def save_task_result(task_name: str, data):
    """根据任务类型立即保存结果到对应文件"""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    if task_name == "人物卡解析":
        path = os.path.join(data_dir, "characters.json")
        # 如果返回的是列表（多个角色），逐个保存
        if isinstance(data, list):
            for idx, character in enumerate(data):
                safe_append_to_json(path, character)
                print(f"  → 已保存第 {idx + 1} 个角色")
        else:
            safe_append_to_json(path, data)
    elif task_name == "世界观解析":
        path = os.path.join(data_dir, "wordviews.json")
        safe_append_to_json(path, data)
    elif task_name == "文风节奏解析":
        path = os.path.join(data_dir, "styles.json")
        safe_append_to_json(path, data)
    elif task_name == "剧情脉络解析":
        path = os.path.join(data_dir, "stories.json")
        safe_append_to_json(path, data)
    print(f"✅ {task_name} 已保存至 {path}")


async def verify_content(task_name: str, data, user_text: str, model_config: dict) -> bool:
    """内容真实性校验，返回是否通过"""
    # 构建校验提示词
    verify_prompt = f"""
你是一个小说内容审查员。请验证以下解析结果是否真实来源于原文，禁止编造。

原文：
{user_text[:8000]}  # 限制长度，避免超限

解析任务：{task_name}
解析结果：
{json.dumps(data, ensure_ascii=False, indent=2)}

请逐项判断：
1. 结果中的每个关键信息是否在原文中有明确证据？（若为列表，检查每一项）
2. 输出格式：JSON {{ "passed": true/false, "reason": "具体原因", "untrusted_fields": [] }}

注意：只有全部信息都有原文支持时才通过，否则不通过。
"""
    model = ChatOpenAI(**model_config, temperature=0.0)
    try:
        response = await model.ainvoke([HumanMessage(content=verify_prompt)])
        verify_result = parse_llm_response(response.content)  # 复用解析函数
        passed = verify_result.get("passed", False)
        if not passed:
            print(f"⚠️ {task_name} 内容校验不通过: {verify_result.get('reason')}")
        return passed
    except Exception as e:
        print(f"❌ 校验过程出错: {e}")
        return False  # 校验失败则不保存（保守）


# ---------- 单个解析任务（完成后立即保存）----------
async def execute_parse_task(user_text: str, model_config: Dict[str, Any], task_name: str, prompt_template: str) -> \
Dict[str, Any]:
    print(f"⚙️ 开始执行任务：【{task_name}】")
    model = ChatOpenAI(
        model=model_config["model_name"],
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        temperature=0.1,
        max_tokens=16384
    )
    try:
        final_prompt = prompt_template.replace("{user_text}", user_text)
        response = await model.ainvoke([HumanMessage(content=final_prompt)])
        json_data = parse_llm_response(response.content)
        print(f"✅ 任务【{task_name}】解析完成")
        # 内容真实性校验（可选，可通过配置开关）
        if False:  # 全局开关
            passed = await verify_content(task_name, json_data, user_text, model_config)
            if not passed:
                # 可选：重试一次解析
                # 或直接标记失败不保存
                return {"status": "error", "data": None, "task_name": task_name,
                        "error_msg": "内容真实性校验未通过"}

        # 校验通过，保存
        save_task_result(task_name, json_data)
        return {"status": "success", "data": json_data, "task_name": task_name}
    except Exception as e:
        print(f"❌ 任务【{task_name}】解析失败: {e}")
        if 'response' in locals():
            print(f"原始返回内容:\n{response.content}")
        return {"status": "error", "data": None, "task_name": task_name, "error_msg": str(e)}


# ---------- 对外接口 ----------
async def novel_parse_endpoint(user_text: str, model_name: str, api_key: str, base_url: str) -> Dict[str, Any]:
    if not user_text or not api_key or not base_url:
        return {"success": False, "message": "输入文本及API凭证不能为空", "data": None}

    model_config = {
        "model_name": model_name,
        "api_key": api_key,
        "base_url": base_url
    }

    # 并行执行四个解析任务（每个任务完成后自动保存）
    tasks = [
        execute_parse_task(user_text, model_config, "人物卡解析", TASK_PROMPTS["人物卡解析"]),
        execute_parse_task(user_text, model_config, "世界观解析", TASK_PROMPTS["世界观解析"]),
        execute_parse_task(user_text, model_config, "文风节奏解析", TASK_PROMPTS["文风节奏解析"]),
        execute_parse_task(user_text, model_config, "剧情脉络解析", TASK_PROMPTS["剧情脉络解析"])
    ]
    results_list = await asyncio.gather(*tasks)

    results = {res["task_name"]: res for res in results_list}
    return {
        "success": True,
        "message": "小说解析完成，每项任务已自动保存",
        "data": results
    }


# ---------- 测试入口 ----------
if __name__ == '__main__':
    # 读取小说文本（请确保当前目录下有 novel.txt）
    with open("novel.txt", "r", encoding="utf-8") as f:
        text = f.read()[:15000]

    asyncio.run(novel_parse_endpoint(
        user_text=text,
        model_name="gpt-3.5-turbo",
        api_key="222",
        base_url="http://localhost:8080"
    ))
