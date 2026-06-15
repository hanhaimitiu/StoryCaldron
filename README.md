# 小说解析助手 - StoryCaldron

一个基于AI的小说解析工具，可以智能提取小说中的人物、世界观、文风、剧情等核心元素。

## 技术栈

- **后端**: Flask + Flask-CORS
- **前端**: 纯HTML/CSS/JavaScript
- **AI模型**: 支持OpenAI兼容格式的API（如GLM、GPT等）

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
cd backend/api
python app.py
```

后端服务将在 http://localhost:5000 启动

### 3. 打开前端

直接在浏览器中打开项目根目录下的 `index.html` 文件

或者使用Python启动静态文件服务器：

```bash
python -m http.server 8080
```

然后访问 http://localhost:8080

## 功能特性

### 小说解析
- **人物卡解析**: 提取角色姓名、性别、性格、身份、关系、说话习惯等信息
- **世界观解析**: 提取题材基调、修炼体系、势力分布、地域场景等设定
- **文风节奏解析**: 分析整体文风、句式特征、高频用词、叙事节奏等
- **剧情脉络解析**: 梳理主线剧情、支线任务、当前冲突、埋伏笔等

### 数据管理
- 解析结果自动保存到JSON文件
- 支持查看、编辑、删除已保存的数据
- 历史解析记录功能

## API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | API首页 |
| `/characters/` | GET/POST | 获取/创建人物 |
| `/characters/{id}` | GET/PUT/DELETE | 人物CRUD操作 |
| `/stories/` | GET/POST | 获取/创建剧情 |
| `/stories/{id}` | GET/PUT/DELETE | 剧情CRUD操作 |
| `/styles/` | GET/POST | 获取/创建文风 |
| `/styles/{id}` | GET/PUT/DELETE | 文风CRUD操作 |
| `/wordviews/` | GET/POST | 获取/创建世界观 |
| `/wordviews/{id}` | GET/PUT/DELETE | 世界观CRUD操作 |
| `/novel/parse/` | POST | 解析小说 |

### 解析接口示例

```bash
curl -X POST http://localhost:5000/novel/parse/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_text": "小说原文内容...",
    "model_name": "gpt-4o",
    "api_key": "your-api-key",
    "base_url": "https://api.openai.com/v1"
  }'
```

## 项目结构

```
StoryCaldron/
├── index.html              # 前端主页面
├── backend/
│   ├── api/
│   │   └── app.py         # Flask应用
│   ├── agent/
│   │   ├── ReadNovelAgent.py    # 小说解析Agent
│   │   └── WriteNovelAgent.py  # 小说写作Agent (暂未使用)
│   ├── data/              # 数据存储目录
│   └── requirements.txt   # Python依赖
```

## 使用说明

1. 打开前端页面
2. 填写API配置（API地址、API Key、模型名称）
3. 粘贴需要解析的小说原文
4. 点击"开始解析"按钮
5. 等待解析完成，查看结果

## 注意事项

- 请确保API服务可用
- 建议使用性能较好的模型以获得更准确的解析结果
- 解析时间取决于文本长度和API响应速度

## License

MIT License
