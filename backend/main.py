from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import os
import sys
import uuid

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ReadNovelAgent import novel_parse_endpoint

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# ==================== 小说解析相关 API ====================

@app.post("/api/novel/parse/")
async def parse_novel(
    user_text: str = Body(...),
    model_name: str = Body('gpt-4o'),
    api_key: str = Body(''),
    base_url: str = Body(''),
    task_name: str = Body(None)
):
    try:
        if not user_text:
            return {"success": False, "message": "请输入需要解析的小说内容"}
        
        # 如果指定了任务名称，只执行单个任务
        if task_name and task_name in ['人物卡解析', '文风节奏解析', '剧情脉络解析', '世界观解析']:
            from ReadNovelAgent import execute_parse_task, TASK_PROMPTS
            result = await execute_parse_task(user_text, {
                "model_name": model_name,
                "api_key": api_key,
                "base_url": base_url
            }, task_name, TASK_PROMPTS[task_name])
            return {"success": True, "message": "解析完成", "data": {task_name: result}}
        else:
            # 否则执行全部任务
            result = await novel_parse_endpoint(user_text, model_name, api_key, base_url)
            return result
    except Exception as e:
        return {"success": False, "message": str(e)}

# ==================== 数据 CRUD API ====================

@app.get("/api/characters/")
def get_characters():
    try:
        file_path = os.path.join(DATA_DIR, 'characters.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"success": True, "data": data}
        return {"success": True, "data": {}}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/styles/")
def get_styles():
    try:
        file_path = os.path.join(DATA_DIR, 'styles.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"success": True, "data": data}
        return {"success": True, "data": {}}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/stories/")
def get_stories():
    try:
        file_path = os.path.join(DATA_DIR, 'stories.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"success": True, "data": data}
        return {"success": True, "data": {}}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/worldviews/")
def get_worldviews():
    try:
        file_path = os.path.join(DATA_DIR, 'wordviews.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"success": True, "data": data}
        return {"success": True, "data": {}}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.delete("/api/characters/{key}")
def delete_character(key: str):
    try:
        file_path = os.path.join(DATA_DIR, 'characters.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if key in data:
                del data[key]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return {"success": True, "message": "删除成功"}
            return {"success": False, "message": "数据不存在"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.delete("/api/styles/{key}")
def delete_style(key: str):
    try:
        file_path = os.path.join(DATA_DIR, 'styles.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if key in data:
                del data[key]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return {"success": True, "message": "删除成功"}
            return {"success": False, "message": "数据不存在"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.delete("/api/stories/{key}")
def delete_story(key: str):
    try:
        file_path = os.path.join(DATA_DIR, 'stories.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if key in data:
                del data[key]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return {"success": True, "message": "删除成功"}
            return {"success": False, "message": "数据不存在"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.delete("/api/worldviews/{key}")
def delete_worldview(key: str):
    try:
        file_path = os.path.join(DATA_DIR, 'wordviews.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if key in data:
                del data[key]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return {"success": True, "message": "删除成功"}
            return {"success": False, "message": "数据不存在"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/characters/{key}")
def update_character(key: str, data: dict = Body(...)):
    try:
        file_path = os.path.join(DATA_DIR, 'characters.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                characters = json.load(f)
            characters[key] = data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(characters, f, ensure_ascii=False, indent=2)
            return {"success": True, "message": "更新成功"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/styles/{key}")
def update_style(key: str, data: dict = Body(...)):
    try:
        file_path = os.path.join(DATA_DIR, 'styles.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                styles = json.load(f)
            styles[key] = data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(styles, f, ensure_ascii=False, indent=2)
            return {"success": True, "message": "更新成功"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/stories/{key}")
def update_story(key: str, data: dict = Body(...)):
    try:
        file_path = os.path.join(DATA_DIR, 'stories.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                stories = json.load(f)
            stories[key] = data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(stories, f, ensure_ascii=False, indent=2)
            return {"success": True, "message": "更新成功"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/worldviews/{key}")
def update_worldview(key: str, data: dict = Body(...)):
    try:
        file_path = os.path.join(DATA_DIR, 'wordviews.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                worldviews = json.load(f)
            worldviews[key] = data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(worldviews, f, ensure_ascii=False, indent=2)
            return {"success": True, "message": "更新成功"}
        return {"success": False, "message": "文件不存在"}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ==================== 写作会话管理 API ====================

@app.post("/api/write/session/start")
async def start_writing_session(
    previous_text: str = Body(...),
    new_outline: str = Body(...),
    selected_characters: list = Body([]),
    selected_styles: list = Body([]),
    selected_stories: list = Body([]),
    selected_worldviews: list = Body([])
):
    """
    启动新的写作会话
    """
    try:
        from WriteNovelAgent import start_writing_session as agent_start
        
        session_id = str(uuid.uuid4())
        
        result = agent_start(
            session_id=session_id,
            before_text=previous_text,
            current_text=new_outline,
            character_ids=selected_characters,
            worldview_ids=selected_worldviews,
            style_ids=selected_styles
        )
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/write/session/{session_id}/execute")
async def execute_step(session_id: str):
    """
    执行指定步数
    """
    try:
        from WriteNovelAgent import execute_step as agent_execute
        
        result = agent_execute(session_id)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/write/session/{session_id}/state")
async def get_session_state(session_id: str):
    """
    获取当前会话状态
    """
    try:
        from WriteNovelAgent import get_session_state as agent_get_state
        
        result = agent_get_state(session_id)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/write/session/{session_id}/draft")
async def update_draft(session_id: str, body: dict = Body(...)):
    """
    更新草稿内容（前端修改后回传）
    """
    try:
        from WriteNovelAgent import update_draft as agent_update_draft
        
        new_draft = body.get("new_draft", "")
        result = agent_update_draft(session_id, new_draft)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/write/session/{session_id}/feedback")
async def submit_human_feedback(session_id: str, body: dict = Body(...)):
    """
    提交人工反馈，继续执行（兼容旧接口）
    """
    try:
        from WriteNovelAgent import submit_human_feedback as agent_submit_feedback
        
        feedback = body.get("feedback", "")
        result = agent_submit_feedback(session_id, feedback)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/write/session/{session_id}/action")
async def submit_human_action(session_id: str, body: dict = Body(...)):
    """
    提交人工操作，继续执行
    
    支持的操作类型:
    - "continue": 继续执行，不做修改
    - "edit": 编辑草稿后继续（需要提供 edited_draft）
    - "suggest": 提出修改建议后继续（需要提供 suggestions）
    - "terminate": 终止执行
    """
    try:
        from WriteNovelAgent import submit_human_action as agent_submit_action
        
        action = body.get("action", "continue")
        edited_draft = body.get("edited_draft", None)
        suggestions = body.get("suggestions", None)
        
        result = agent_submit_action(session_id, action, edited_draft, suggestions)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/write/session/{session_id}/terminate")
async def terminate_session(session_id: str):
    """
    终止会话
    """
    try:
        from WriteNovelAgent import terminate_session as agent_terminate
        
        result = agent_terminate(session_id)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/write/session/{session_id}/resume")
async def resume_session(session_id: str):
    """
    恢复暂停的会话
    """
    try:
        from WriteNovelAgent import resume_session as agent_resume
        
        result = agent_resume(session_id)
        
        if "error" in result:
            return {"success": False, "message": result["error"]}
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ==================== 旧版写作 API（兼容） ====================

@app.post("/api/novel/write/")
async def write_novel(
    previous_text: str = Body(...),
    new_outline: str = Body(...),
    selected_characters: list = Body([]),
    selected_styles: list = Body([]),
    selected_stories: list = Body([]),
    selected_worldviews: list = Body([]),
    model_name: str = Body('gpt-4o'),
    api_key: str = Body(''),
    base_url: str = Body('')
):
    try:
        from WriteNovelAgent import write_agent
        
        result = write_agent(
            before_text=previous_text,
            current_text=new_outline,
            charcter_ids=selected_characters,
            worldview_ids=selected_worldviews,
            style_ids=selected_styles
        )
        
        return {"success": True, "message": "创作完成", "data": result}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/novel/write/stream/")
async def write_novel_stream(
    previous_text: str = Body(...),
    new_outline: str = Body(...),
    selected_characters: list = Body([]),
    selected_styles: list = Body([]),
    selected_stories: list = Body([]),
    selected_worldviews: list = Body([]),
    human_feedback: str = Body(''),
    previous_draft: str = Body('')
):
    """
    带人工介入的流式写作端点
    返回实时执行状态，支持暂停等待人工反馈
    """
    async def generate():
        try:
            from WriteNovelAgent import write_agent
            
            # 步骤1: 开始创作
            yield json.dumps({"step": 1, "status": "running", "message": "正在提取参考资料..."})
            await asyncio.sleep(0.5)
            
            # 步骤2: 调用写作代理
            yield json.dumps({"step": 2, "status": "running", "message": "AI正在创作中..."})
            
            result = write_agent(
                before_text=previous_text,
                current_text=new_outline,
                charcter_ids=selected_characters,
                worldview_ids=selected_worldviews,
                style_ids=selected_styles
            )
            
            # 步骤3: 完成
            yield json.dumps({
                "step": 3, 
                "status": "success", 
                "message": "创作完成！",
                "data": result,
                "feedback": ""
            })
                
        except Exception as e:
            yield json.dumps({"step": 0, "status": "error", "message": str(e)})
    
    return StreamingResponse(generate(), media_type="application/json")




if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)
