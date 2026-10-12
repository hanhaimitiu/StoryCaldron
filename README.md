# StoryCaldron - 小说炼丹炉

一个基于 AI 的小说创作工具，支持小说解析和智能写作，采用 TUI（终端用户界面）模式。

## 技术栈

- **核心**: Python + LangGraph + LangChain
- **界面**: TUI (终端交互)
- **AI模型**: 支持 OpenAI 兼容格式的 API（如 glm-5、GPT 等）

## 快速开始

### 1. 安装依赖

推荐使用项目自带的虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

或直接安装：

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

默认配置已内置，如需自定义可设置以下环境变量：

```bash
# LLM 模型配置（默认值仅供测试使用）
set LLM_MODEL=glm-5
set LLM_API_KEY=your-api-key
set LLM_BASE_URL=http://localhost:8080
```

### 3. 启动程序

```bash
.venv\Scripts\python.exe backend\run_chapter.py
```

> 说明：早先规划的 TUI 入口 `tui_main.py` **尚未实现**，下面「使用说明」里描述的是它规划中的菜单。
> 目前在用的一是可用的命令行入口 `backend/run_chapter.py`，二是多 Agent 协作工作流（见下文）。

## 功能特性

### 小说解析
- **人物卡解析**: 提取角色姓名、性别、性格、身份、关系、说话习惯等信息
- **世界观解析**: 提取题材基调、修炼体系、势力分布、地域场景等设定
- **文风节奏解析**: 分析整体文风、句式特征、高频用词、叙事节奏等
- **剧情脉络解析**: 梳理主线剧情、支线任务、当前冲突、埋伏笔等

### 小说创作
- 根据上一章概括和本章大纲生成草稿
- 自动审稿和多轮修改
- 支持人工审核和编辑功能
- 可提交修改建议让 AI 重写

### 数据管理
- 解析结果自动保存到 JSON 文件
- 支持查看、添加、编辑、删除已保存的素材
- 管理人物、文风、剧情、世界观等设定

### 多 Agent 协作创作
新增 `backend/collab_novel_agent.py`，按以下工作流驱动多个 Agent 协作完成一章：

```
加载素材上下文 -> 规划本章 -> 审批大纲卡 -> 撰写草稿
    -> 连续性检查 ->（发现问题）修复问题 -> 再次检查
    -> 文风润色 -> 人工审核 -> 更新素材记忆
    -> 提出正典提案 -> 审批正典 -> 提交定稿
```

支持的素材卡：
- **人物卡** (`characters.json`)
- **剧情卡** (`plots.json` / `stories.json`)
- **文风卡** (`styles.json`)
- **伏笔卡** (`foreshadowing.json`)
- **世界观卡** (`wordviews.json`)

#### 用法一：命令行入口（推荐）

`backend/run_chapter.py` 是日常使用的入口。它**只读取** `backend/data/` 下的素材卡，不会覆盖或重置它们。

```bash
# 看有哪些素材卡可用
.venv\Scripts\python.exe backend\run_chapter.py --list-cards

# 交互式写一章：跑到「人工审核」时会在终端里问你
.venv\Scripts\python.exe backend\run_chapter.py ^
    --title "第二章 剑鸣" ^
    --outline "陆青崖引动古剑击退妖兽，封印裂痕扩大被长老察觉。" ^
    --prev "第一章：参加外门考核，进入断魂林。"

# 不带参数也行，会提示你输入标题、大纲、上一章概括
.venv\Scripts\python.exe backend\run_chapter.py

# 跳过人工审核，直接跑完
.venv\Scripts\python.exe backend\run_chapter.py --title "..." --outline "..." --auto
```

参数说明：

| 参数 | 说明 |
|---|---|
| `--title` | 章节标题 |
| `--outline` | 本章大纲 |
| `--prev` | 上一章概括；省略会交互询问，传 `""` 表示确实没有 |
| `--characters` / `--plots` / `--styles` / `--fore` / `--worlds` | 按 id 选卡，逗号分隔；留空=全部加载 |
| `--auto` | 跳过人工审核，自动通过后跑完 |
| `--list-cards` | 列出可用素材卡的 id 和摘要 |

跑到「人工审核」时停住，终端里给出四个选项：

```
[1] 通过              → 继续到出稿
[2] 提修改意见        → 回到文风润色重排，之后再停一次
[3] 直接给出全文      → 用你贴的全文替换（输入单独一行 END 结束）
[4] 终止本次创作      → 停止，不出稿
```

定稿写到 `backend/output/chapter_<会话id前8位>.txt`。

#### 用法二：自带演示脚本

```bash
.venv\Scripts\python.exe backend\collab_novel_agent.py
```

> ⚠️ 这个演示入口每次运行都会把 `backend/data/` 里的素材卡**重置成演示用的那套**，请勿用于真实创作。

#### 更换模型

代码默认指向本地 llama.cpp 服务（`http://localhost:8080/v1`）。换模型或换服务地址用环境变量覆盖：

```bash
set LLM_MODEL=你的模型名
set LLM_API_KEY=your-api-key
set LLM_BASE_URL=http://your-host:port/v1
```

## 使用说明

### 主菜单

启动后将显示主菜单：

```
【主菜单】
  1. 解析小说 (Parse Novel)
  2. 创作小说 (Write Novel)
  3. 管理素材 (Data Management)
  4. 退出 (Exit)
```

### 解析小说
1. 选择「1. 解析小说」
2. 粘贴小说原文（空行结束输入）
3. 等待 AI 自动解析四个维度
4. 解析结果自动保存

### 创作小说
1. 选择「2. 创作小说」
2. 输入上一章概括和本章大纲
3. 选择要使用的素材（人物、文风、剧情、世界观）
4. AI 自动生成草稿并进行审稿
5. 在人工审核环节可以：
   - **采纳**: 直接使用当前草稿
   - **编辑**: 修改草稿内容后继续
   - **建议**: 提交修改建议让 AI 重写
   - **终止**: 放弃本次创作

### 数据管理
1. 选择「3. 管理素材」
2. 选择要管理的素材类型（人物/文风/剧情/世界观）
3. 执行查看、添加、编辑、删除操作

## 项目结构

```
StoryCaldron/
├── backend/
│   ├── run_chapter.py          # 命令行入口（日常使用）
│   ├── collab_novel_agent.py   # 多 Agent 协作小说创作工作流
│   ├── ReadNovelAgent.py       # 小说解析 Agent
│   ├── WriteNovelAgent.py      # 小说写作 Agent (LangGraph)
│   ├── output/                 # 定稿输出目录
│   └── data/                   # 素材卡存储目录
├── .gitignore
├── README.md
├── requirements.txt
└── LICENSE
```

## 注意事项

- LLM 服务需在配置的 `LLM_BASE_URL` 地址可用
- 建议使用性能较好的模型以获得更准确的解析和创作结果
- 解析和创作时间取决于文本长度和 API 响应速度
- 创作过程中支持多轮人工审核，可反复打磨内容

## License

MIT License
