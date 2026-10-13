# StoryCaldron 项目开发规则（agents.md）

> 本文件是项目级「开发宪法」，AI 编码助手与协作者都必须遵守。
> 目标：让多人/多 Agent 在不知历史的情况下，也能写出风格一致、可维护、可回归的代码。

---

## 1. 工程化现状与红线（诚实评估）

当前状态：**能跑、但偏"单人快糙"**。已知短板：

- ❌ 无自动化测试、无 CI；验证靠 `py_compile` + 临时脚本手测。
- ❌ 核心文件过长（见第 5 节），违反单文件行数红线。
- ✅ 已建立：中文注释规范、按"小功能点"提交纪律、长期记忆能力（#1/#2/#4/#8）、删除项目安全边界。

**行数红线（强约束）：**

- 单文件 **> 500 行**：必须评估拆分。
- 单文件 **> 800 行**：必须拆分（当前已有 2 个违规文件）。
- 单函数 **> 80 行**：优先抽子函数。

---

## 2. 目录与模块边界（当前结构）

```
StoryCaldron/
├── backend/
│   ├── web_server.py          # HTTP 服务 + 路由分发 + 会话注册表/驱动（842 行，需拆）
│   ├── collab_novel_agent.py  # LangGraph 编排 + 12 节点 + prompt（1291 行，需拆）
│   ├── project.py             # 项目模型：meta/卡片/canon/outline（352 行，OK）
│   ├── md_to_cards.py         # markdown -> 素材卡 解析（488 行，偏长）
│   ├── book_to_cards.py       # 整书拆书（329 行）
│   ├── run_chapter.py         # 单章 CLI 入口（439 行）
│   └── sessions.json          # 会话注册表持久化（gitignore，不入库）
├── web/
│   ├── src/
│   │   ├── store.js           # 全局状态（515 行，需拆）
│   │   ├── api.js             # 后端接口封装
│   │   ├── App.vue            # 根组件
│   │   └── components/        # SideBar/Composer/AgentStream/CardsDrawer/ChaptersDrawer
│   └── dist/                  # 构建产物（gitignore，不入库）
├── projects/                  # 用户书稿与素材卡（gitignore，不入库）
├── docs/设计文档.md           # 架构/接口权威文档
├── README.md
└── 启动.bat                   # 本地一键启动（生产模式，单端口 8765）
```

---

## 3. 编码规范

- **注释语言：中文**。文件头/函数头说明「意图」；关键逻辑、非常规写法、数值含义、为何这样实现必须补注释。这是长期规范，除非用户另有说明。
- **命名**：后端 `snake_case`；前端 `camelCase`；HTTP 路径全小写下划线（`/api/write/start`）。
- **改动方式**：优先用局部 `replace_in_file`，**禁止**为"顺手"整体重写大文件。改前先 `read_file` 确认最新内容。
- **提交纪律（强约束）**：见第 4 节。
- **不要擅自引入新依赖**：加 `requirements.txt` / `package.json` 依赖需说明用途并经用户确认。

---

## 4. 提交纪律（强约束）

- **按"小功能点"提交**：一次 commit 只做一件事（一个接口 / 一个 bugfix / 一处文档）。不同功能点的改动**分开 commit，不混**。
- **commit message 中文**，格式：`类型: 简述（关联编号）`
  - 类型：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`
  - 例：`fix: 同页切换项目不再丢失在跑的创作会话（#8 体感回归）`
- **提交前必须验证通过**（否则不许 commit）：
  - 后端改了：`python -m py_compile web_server.py collab_novel_agent.py project.py`
  - 前端改了：`cd web && npm run build`
  - 关键逻辑：跑针对性自测（见第 9 节），确认无回归。
- **不提交的产物**（已被 `.gitignore` 覆盖，提交前 `git status` 自检）：
  `web/dist/`、`projects/`、`backend/sessions.json`、`*.pkl`、`node_modules/`、`.venv/`、`*.log`。
- **分支/force**：未经用户明确要求，不 `git push --force`、不 `git reset --hard`、不擅自切/合分支。

---

## 5. 文件过长与拆分方案（重点）

当前违规文件及拆分指引（拆分时务必保持 import 关系与对外函数签名不变，并跑回归自测）：

### 5.1 `backend/collab_novel_agent.py`（1291 行，最优先）
LangGraph 图 + 12 个节点函数 + 各节点 prompt 全堆在一处。
- 抽出**状态/类型定义**到 `state.py`（当前用 `TypedDict`/注解集中处）。
- 抽出**各节点 prompt 模板**到 `prompts.py`（或 `nodes/prompts/`），节点函数只留"取状态→调 LLM→写回"的逻辑。
- 主文件保留：图编译（`StateGraph`）、`start_session` / `commit` 入口、节点间流转。
- 目标：主文件 < 500 行，prompt 与节点逻辑各成模块。

### 5.2 `backend/web_server.py`（842 行）
HTTP 路由 + `SESSIONS` 注册表/持久化/恢复 + LangGraph 驱动线程全混。
- 抽出**领域 handler**：`api_projects.py`、`api_write.py`、`api_parse.py`、`api_cards.py`、`api_outline.py`。
- 抽出**会话管理**到 `sessions.py`：`SESSIONS` 注册表、`_ensure_session`、`_save_sessions`/`_load_sessions`、崩溃恢复续跑。
- 主文件只留：`BaseHTTPRequestHandler` 路由分发 + `main()` 启动 + `resolve_project_arg`。

### 5.3 `web/src/store.js`（515 行）
单 reactive store 处理 项目/素材卡/拆书解析/章节/写作 全部领域。
- 按领域拆 composables：`src/store/projects.js`、`cards.js`、`parse.js`、`writing.js`、`theme.js`，在 `store.js` 汇总导出。
- 各 composable 内部仍走 `api.js` + `guard` + `toast`，保持现状交互契约。

### 5.4 拆分验收
拆分后需确认：前端 `npm run build` 通过、后端 `py_compile` 通过、可用手测脚本验证"开始创作→切项目→切回→删除项目"全链路无回归。

---

## 6. 接口约定（前后端契约）

- **同源**：前端一律用相对路径 `/api/*`；开发模式由 vite 代理到 `127.0.0.1:8765`，生产由 `web_server.py` 托管 `dist`。
- **响应格式**：成功返回数据对象或 `{ok:true, ...}`；失败返回 HTTP 非 2xx + body `{error: "..."}`。前端 `api.js` 的 `request` 统一把非 2xx 抛错。
- **写作会话状态契约**（前端恢复依赖，改动需同步）：`/api/write/status` 返回
  `{sid, status, round, error, stage, plan, draft, feedback, logs, chapter_file, project}`。
- **新增/修改 HTTP 接口**：必须在 `docs/设计文档.md` 第 6 节接口表登记（GET/POST 表），并同步 `README.md`（如影响用户可见能力）。
- **项目路径参数**：前端传项目**路径**（`p.path`，绝对）；后端 `resolve_project_arg` 统一解析，空则 `projects/default`。

---

## 7. 长期记忆与会话一致性（防回归）

`#1` 跨章节前情、`#2` outline.md、`#4` canon.md、`#8` 会话持久化 是一组强相关能力，改其中一处必须确认不破坏其他：

- **切换项目不得丢会话**：`store.js` 用 `projectSessions` 注册表按项目缓存 `sid`；`selectProject` 切走时保句柄、切回按 `sid` 续轮询。严禁在切换项目时无条件 `resetSession` 清空其他项目句柄。
- **删除项目安全边界**：只允许删 `projects/` 下的子目录，先 `os.path.realpath` 再校验前缀 `projects/<name>/`，拦截 `../` 越界；删除同时从 `SESSIONS` 移除该项目在跑会话句柄。
- **落盘契约**：`commit` 定稿后追加 `canon.md`（#4）与 `outline.md`（#2）；演示模式落盘到 `OUTPUT_DIR/`。
- **检查点现状**：`MemorySaver` 仍是**内存级** checkpointer，**服务重启即丢图状态**；`sessions.json` 仅存会话元数据。要做到"重启续写"需换持久化 checkpointer（如 `SqliteSaver`）——列为待办，**改此处前先与用户确认**，避免破坏现有内存态行为。

---

## 8. 安全

- 任何接收"路径"的接口（删除/读取/解析）必须 `realpath` + 前缀校验，**禁止**越出 `projects/` 或 `OUTPUT_DIR` 访问系统文件。
- 不读取、不上传 `projects/` 之外的用户文件。
- 推理服务地址默认 `http://localhost:8080/v1`（llama.cpp），走配置不硬编死到业务函数。

---

## 9. 测试（鼓励补齐）

- 建 `tests/` 目录，优先给**纯函数**加单测（不依赖 LLM、可离线跑）：
  - `project.py`：`add_chapter` 序号推断、`load_outline`/`append_outline_entry`、`canon` 解析。
  - `md_to_cards.py` / `book_to_cards.py`：markdown/整书 -> 卡片结构解析。
- **后端手测规范**：用临时项目（如 `__deltest__`）创建+删除，验证后清理，**不污染真实 `projects/`**。
- **前端**：靠 `npm run build` 把关编译/语法；交互回归靠手测脚本或后续组件测试。

---

## 10. 文档同步

- 改了**功能**必须同步两份文档：`README.md`（功能特性/流程/目录结构）、`docs/设计文档.md`（数据模型/工作流/接口表/待办）。
- 接口变更 → 设计文档第 6 节接口表。
- 落地了某个 `#编号` 能力 → 在设计文档对应章节与"待办/近期已落地"区标注，避免后续重复造轮子。

---

## 11. 一键启动

- `启动.bat`（Windows）：建 `.venv` → 装依赖 → 首次 `npm install`+`vite build` → 检测 `localhost:8080` 推理服务 → 起 `web_server.py`（端口 8765）→ 自动开浏览器。
- 它是**生产模式**（单端口直接开网页）。改了前端后，删 `web/dist` 重跑 bat 才会重新构建（`dist` 存在时跳过 build）。
- 开发热更新模式用 `cd web && npm run dev`（5173 代理到 8765）。
