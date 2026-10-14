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
- **跨章节前情自动注入（#1）**：未填「上一章概括」时自动从近期章节尾部拼出前情，规划/写作/连续性检查节点都能看到前文真实片段
- **全书大纲/结构圣经（#2）**：规划节点对齐 `outline.md` 整体走向，定稿后自动把本章进展回写大纲
- **正典落盘（#4）**：审批通过的正典提案累积写入 `canon.md`，作为后续章节的权威事实源
- **会话持久化（#8）**：写作会话检查点落盘，服务重启后按会话恢复、崩溃自动续跑（见 `checkpoints.pkl` / `sessions.json`）
- 自动审稿和多轮修改
- 支持人工审核和编辑功能
- 可提交修改建议让 AI 重写
- 去AI风卡：写作与润色节点注入，约束生成文本规避 AI 套路文风（空洞金句、套路词、强行升华等）

### 数据管理
- 解析结果自动保存到 JSON 文件
- 支持查看、添加、编辑、删除已保存的素材
- 管理人物、文风、剧情、世界观、去AI风等设定
- 新建素材卡时 id 由系统自动分配，无需手动填写

### 多 Agent 协作创作
新增 `backend/collab_novel_agent.py`，按以下工作流驱动多个 Agent 协作完成一章：

```
加载素材上下文 -> 规划本章 -> 审批大纲卡 -> 撰写草稿
    -> 连续性检查 ->（发现问题）修复问题 -> 再次检查
    -> 文风润色 -> 人工审核 -> 更新素材记忆
    -> 提出正典提案 -> 审批正典 -> 提交定稿
```

> 长期记忆：定稿时会把正典提案追加写入 `canon.md`、把本章进展追加到 `outline.md`；开篇未填「上一章概括」会自动从近期章节拼出前情（详见设计文档 #1/#2/#4）。

支持的素材卡：
- **人物卡** (`characters.json`)
- **剧情卡** (`plots.json` / `stories.json`)
- **文风卡** (`styles.json`)
- **伏笔卡** (`foreshadowing.json`)
- **世界观卡** (`wordviews.json`)
- **去AI风卡** (`anti_ai.json`)：作者手写/从 MD 导入的「去 AI 味」禁忌要点，写作与润色节点据此规避套路文风

#### 用法一：网页工作台（推荐）

`backend/web_server.py` 是 HTTP 接口服务，`web/` 是 Vue 3 + Vite 前端。界面按常见 Agent 工作台组织：左侧项目列表、中间多个 Agent 的执行流、底部发起创作；跑到「人工审核」会弹出确认卡，让你选 **通过 / 提修改意见 / 直接给全文 / 终止**。

```bash
# 1) 装前端依赖（仅第一次）
cd web && npm install

# 2) 开发模式：起两个进程
.venv\Scripts\python.exe backend\web_server.py   # 8765，提供 /api
cd web && npm run dev                            # 5173，已配好 /api 代理到 8765
# 浏览器打开 http://127.0.0.1:5173

# 3) 生产模式：构建后由 Python 服务单端口托管
cd web && npm run build
.venv\Scripts\python.exe backend\web_server.py   # 打开 http://127.0.0.1:8765
```

网页上可以做的事：新建/切换项目、六类素材卡（含去AI风）增删改、把 Markdown 设定转成卡片、写一章并实时看到每个 Agent 节点的耗时与输出、浏览已写章节正文。

卡片编辑体验：**新建卡片时 id 由后端自动分配、无需手填**（编辑已有卡片时 id 只读展示）；发起创作时展开「高级选项」，可直接**按类型勾选**要注入本章的卡片（人物/剧情/文风/伏笔/世界观/去AI风），不再手输卡片 id；某类一张都不勾即该类使用全部卡片。

#### 用法二：命令行入口（项目模式）

`backend/run_chapter.py` 是命令行入口。**每个小说是一个项目目录**，素材卡和章节正文都放在该项目里，互不干扰、天然隔离。换一本书就换一个 `--project` 目录。

```bash
# 1) 新建项目（--demo 直接塞一套演示卡，方便第一次试跑）
.venv\Scripts\python.exe backend\run_chapter.py init --project projects/mybook --demo

# 2) 看看这个项目里有哪些卡
.venv\Scripts\python.exe backend\run_chapter.py cards --project projects/mybook

# 3) 交互式补一张卡（按字段提示填；也可 --data '{"id":..}' 直传 JSON）
.venv\Scripts\python.exe backend\run_chapter.py new-card --project projects/mybook --type character

# 4) 向导式一次性建立人物/剧情/文风/伏笔/世界观几类卡
.venv\Scripts\python.exe backend\run_chapter.py setup --project projects/mybook

# 5) 写一章：跑到「人工审核」时会在终端里问你
.venv\Scripts\python.exe backend\run_chapter.py write --project projects/mybook ^
    --title "第二章 剑鸣" ^
    --outline "陆青崖引动古剑击退妖兽，封印裂痕扩大被长老察觉。" ^
    --prev "第一章：参加外门考核，进入断魂林。"

# 不带 --project 时默认用 projects/default（不存在会自动创建）
.venv\Scripts\python.exe backend\run_chapter.py write --title "..." --outline "..."

# 跳过人工审核，直接跑完
.venv\Scripts\python.exe backend\run_chapter.py write --project projects/mybook --auto
```

子命令一览：

| 子命令 | 说明 |
|---|---|
| `init --project <dir> [--demo]` | 创建/初始化项目目录；`--demo` 写入演示卡 |
| `cards` / `list-cards` | 列出项目内所有素材卡的 id 与摘要 |
| `new-card --type <t> [--data '<json>']` | 新建一张卡；`--data` 直传 JSON 则免交互 |
| `setup` | 向导式依次建立各类素材卡 |
| `write` | 在项目内写一章 |
| `import-md <md> [--no-llm] [--no-merge]` | **独立工具**：把 Markdown 设定转成卡片 JSON（不进入小说流程） |

> **素材卡的另一种来源：用 Markdown 写设定，一键转 JSON**
>
> 如果你更习惯用 Markdown 自由书写人物小传、世界观设定，可以用独立的转换工具 `backend/md_to_cards.py` 把它转成项目里的五类卡片，再交给 `write` 去读卡写小说。**这一步是建卡工具，不是小说生成流程的一部分。**
>
> ```bash
> # 先看书写模板（二级标题分大类、三级标题分单张卡）
> .venv\Scripts\python.exe backend\md_to_cards.py --template
>
> # 把设定.md 转进某个项目（写入 <project>/cards/）
> .venv\Scripts\python.exe backend\md_to_cards.py 设定.md --project projects/mybook
>
> # 或直接出 JSON 到某个目录（不建项目脚手架）
> .venv\Scripts\python.exe backend/md_to_cards.py 设定.md --out ./mycards
>
> # 大模型不可用时也能用：纯规则解析（按「- 字段：值」提取）
> .venv\Scripts\python.exe backend\md_to_cards.py 设定.md --project projects/mybook --no-llm
> ```
>
> 工具会优先用大模型读懂自由书写的散文式设定并结构化；大模型不可用时自动退回到按 bullet 提取的规则解析。写入时按卡片 `id` 合并已有卡片，重复运行可增量更新。
>
> 也可走 `run_chapter.py` 同一入口：`run_chapter.py import-md 设定.md --project projects/mybook`。

`write` 的更多参数：

| 参数 | 说明 |
|---|---|
| `--title` | 章节标题 |
| `--outline` | 本章大纲 |
| `--prev` | 上一章概括；省略会交互询问，传 `""` 表示确实没有 |
| `--characters` / `--plots` / `--styles` / `--fore` / `--worlds` | 按 id 选卡，逗号分隔；留空=全部加载 |
| `--auto` | 跳过人工审核，自动通过后跑完 |

跑到「人工审核」时停住，终端里给出四个选项：

```
[1] 通过              → 继续到出稿
[2] 提修改意见        → 回到文风润色重排，之后再停一次
[3] 直接给出全文      → 用你贴的全文替换（输入单独一行 END 结束）
[4] 终止本次创作      → 停止，不出稿
```

**项目目录结构**：

```
projects/mybook/
├── project.json            # 项目元信息 + 章节索引
├── cards/                  # 素材卡（Agent 会在这里读/写卡片）
│   ├── characters.json
│   ├── stories.json  (或 plots.json)
│   ├── styles.json
│   ├── foreshadowing.json
│   └── wordviews.json
└── chapters/               # 已写章节正文
    ├── chapter_001.txt
    └── chapter_002.txt
├── canon.md                # 正典/事实圣经：审批通过的正典提案按章节累积（#4）
└── outline.md              # 全书大纲/结构圣经：结构走向 + 每章进展（#2）
```

写作过程中，Agent 会**自动把本章新出场的人物、新补充的世界观落成卡片**写回 `cards/`，伏笔/剧情的进度更新也会回写——也就是「读卡 + 建卡 + 写小说」都发生在同一个项目目录里。定稿按 `chapter_001.txt` 顺序写入 `chapters/`，并在 `project.json` 登记章节索引。

#### 用法三：自带演示脚本

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
│   ├── run_chapter.py          # 命令行入口（项目模式，日常使用）
│   ├── web_server.py           # 网页服务：HTTP 接口 + 托管前端构建产物
│   ├── collab_novel_agent.py   # 多 Agent 协作小说创作工作流
│   ├── project.py              # 项目工作区管理（卡片读写、章节落盘、脚手架）
│   ├── md_to_cards.py          # 独立工具：Markdown 设定 -> 卡片 JSON
│   ├── setting_template.md     # Markdown 设定书写模板
│   ├── output/                 # 演示模式定稿输出目录
│   └── data/                   # 演示模式素材卡目录
├── web/                        # 前端（Vue 3 + Vite，Agent 工作台界面）
│   ├── src/
│   │   ├── api.js              # 后端接口封装 + Agent 角色表
│   │   ├── store.js            # 全局状态与写作轮询
│   │   ├── App.vue
│   │   └── components/         # SideBar / AgentStream / ReviewCard / Composer / Drawer
│   ├── package.json
│   └── vite.config.js          # /api 代理到 8765
├── projects/                   # 各小说项目工作区（init/cards/write 都在这）
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
