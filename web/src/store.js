/**
 * 全局状态与动作（一个 reactive 单例，相当于轻量 store）。
 *
 * 写作是长任务：后端起线程驱动 LangGraph，前端每 2 秒拉一次状态，
 * 图停在 human_review 前时 status 变 waiting，界面就弹出审核卡片。
 */
import { reactive } from 'vue'
import { api } from './api'

const POLL_MS = 2000
const THEME_KEY = 'sc-theme'
const SID_KEY = 'sc-sid'      // 当前创作会话 id：跨页签/刷新恢复用
const PROJECT_KEY = 'sc-project' // 当前项目路径：恢复时对齐素材卡/章节

/** 项目路径 -> 该项目的创作会话 sid。切项目时不丢弃句柄，切回来按 sid 续上。 */
const projectSessions = {}

/** 五套皮肤（前两套浅色）；swatch 是切换器里那个小色点的颜色 */
export const THEMES = [
  { key: 'paper', name: '宣纸', swatch: '#f5f2ea' },
  { key: 'moon', name: '月白', swatch: '#eef1f3' },
  { key: 'copper', name: '暖铜', swatch: '#c98f43' },
  { key: 'mono', name: '石墨', swatch: '#6e6e6e' },
  { key: 'green', name: '苔青', swatch: '#4f7d68' },
]

export const store = reactive({
  // 皮肤（默认宣纸：浅色，用户不喜欢黑底）
  theme: 'paper',

  // 项目
  projects: [],
  project: '',
  loadingProjects: false,

  // 创作会话
  session: {
    sid: '',
    status: 'idle', // idle | running | waiting | done | error | stopped
    round: 0,
    stage: '',
    plan: '',
    draft: '',
    logs: [],
    chapterFile: '',
    error: '',
  },
  writing: false,
  // 各项目创作会话的最新状态（侧栏标记用）：{ [projectPath]: status }
  projectStatus: {},

  // 素材卡 / 章节
  cardTypes: [],
  cardFields: {},
  chapters: [],

  // 拆书解析（后台任务 + 进度轮询 + 预览勾选）
  parse: {
    task: '',
    status: 'idle', // idle | pending | running | done | committed | error | stopped | not_found
    progress: { done: 0, total: 0 },
    logs: [],
    stats: {},
    error: '',
    result: null, // 预览方案 {chapter_count, chapters:[{title,chars}], cards:{ctype:[card]}}
    selChapters: [], // 勾选写入的章节下标
    selCards: {}, // 勾选写入的卡片 {ctype:[id]}
    committing: false,
  },

  // 界面
  drawer: null, // null | 'cards' | 'chapters'
  toast: { msg: '', err: false, show: false },
})

let toastTimer = null
let pollTimer = null
let parsePollTimer = null

function toast(msg, err = false) {
  store.toast = { msg, err, show: true }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (store.toast.show = false), 2800)
}

async function guard(fn) {
  try {
    return await fn()
  } catch (e) {
    toast(e.message || String(e), true)
    return null
  }
}

/** 把当前会话 id 与项目路径写入 localStorage，供新页签/刷新后静默恢复 */
function saveSessionMeta() {
  try {
    localStorage.setItem(SID_KEY, store.session.sid)
    localStorage.setItem(PROJECT_KEY, store.project)
  } catch {
    /* 隐私模式写不了，忽略 */
  }
}

/** 清除持久化的会话 id（切换项目 / 开新创作时调用，避免恢复出错误会话） */
function clearSessionMeta() {
  try {
    localStorage.removeItem(SID_KEY)
  } catch {
    /* ignore */
  }
}

/** 把某 sid 挂为当前项目活动会话：写入 store.session、登记到 projectSessions、落盘、记状态 */
function attachSession(sid, s) {
  store.session.sid = sid
  projectSessions[store.project] = sid
  applyStatus(s)
  store.projectStatus[store.project] = s.status
  saveSessionMeta()
}

/** 把后端状态写进 store.session */
function applyStatus(s) {
  const ses = store.session
  ses.sid = s.sid || ses.sid
  ses.status = s.status
  ses.round = s.round || 0
  ses.stage = s.stage || ''
  ses.plan = s.plan || ''
  ses.draft = s.draft || ''
  ses.logs = s.logs || []
  ses.chapterFile = s.chapterFile || s.chapter_file || ''
  ses.error = s.error || ''
}

function startPoll() {
  stopPoll()
  const tick = () => guard(poll)
  pollTimer = setInterval(tick, POLL_MS)
  tick()
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function poll() {
  if (!store.session.sid) return
  const s = await api.writeStatus(store.session.sid)
  applyStatus(s)
  store.writing = s.status === 'running'
  store.projectStatus[store.project] = s.status
  if (s.status === 'done') {
    stopPoll()
    toast('本章已完成')
    await guard(loadChapters)
  } else if (s.status === 'error') {
    stopPoll()
    toast('流程出错：' + (s.error || '未知'), true)
  } else if (s.status === 'stopped') {
    stopPoll()
    toast('已终止本次创作')
  }
}

/* ------------------------------ 项目 ------------------------------ */
export async function loadProjects() {
  return guard(async () => {
    store.loadingProjects = true
    const list = await api.listProjects()
    store.projects = list || []
    if (!store.project && list.length) store.project = list[0].path
    if (store.project && !list.some((p) => p.path === store.project)) {
      store.project = list.length ? list[0].path : ''
    }
    store.loadingProjects = false
    await Promise.all([loadCards(), loadChapters()])
  })
}

export async function selectProject(path) {
  if (!path) return
  // 同项目：仅确保素材卡/章节已加载，不动会话
  if (path === store.project) {
    await Promise.all([loadCards(), loadChapters()])
    return
  }
  // 先把当前项目正在跑的会话句柄按项目存好，切回来还能续上（后端线程不会停）
  if (store.project && store.session.sid) projectSessions[store.project] = store.session.sid
  store.project = path
  try {
    localStorage.setItem(PROJECT_KEY, path)
  } catch {
    /* ignore */
  }
  stopPoll()
  await Promise.all([loadCards(), loadChapters()])
  // 目标项目若已有会话（在跑/等待/已完成），恢复其视图并续轮询
  const prevSid = projectSessions[path]
  if (prevSid) {
    const s = await api.writeStatus(prevSid).catch(() => null)
    if (s) {
      attachSession(prevSid, s)
      store.writing = s.status === 'running'
      startPoll()
      return
    }
    // 后端已无此会话（如清过 sessions.json），放弃句柄
    delete projectSessions[path]
  }
  resetSession()
}

export async function createProject(name, demo) {
  return guard(async () => {
    await api.createProject(name, demo)
    await loadProjects()
    const p = store.projects.find((x) => x.name === name || x.path.endsWith(name))
    if (p) await selectProject(p.path)
    toast('项目已创建')
  })
}

/* ------------------------------ 素材卡 ------------------------------ */
export async function loadCards() {
  return guard(async () => {
    if (!store.project) {
      store.cardTypes = []
      return
    }
    const d = await api.listCards(store.project)
    store.cardTypes = d.types || []
    store.cardFields = d.fields || {}
  })
}

export async function saveCard(type, card) {
  return guard(async () => {
    await api.saveCard(store.project, type, card)
    toast('卡片已保存')
    await loadCards()
  })
}

export async function deleteCard(type, id) {
  return guard(async () => {
    await api.deleteCard(store.project, type, id)
    toast('已删除')
    await loadCards()
  })
}

export async function importMd(md, useLlm, merge) {
  return guard(async () => {
    const r = await api.importMd(store.project, md, useLlm, merge)
    await loadCards()
    return r
  })
}

/* ------------------------------ 拆书解析 ------------------------------ */
function applyParse(s) {
  const p = store.parse
  p.status = s.status
  p.progress = s.progress || { done: 0, total: 0 }
  p.logs = s.logs || []
  p.stats = s.stats || {}
  p.error = s.error || ''
  if (s.result) p.result = s.result
}

function startParsePoll() {
  stopParsePoll()
  const tick = () => guard(pollParse)
  parsePollTimer = setInterval(tick, POLL_MS)
  tick()
}

function stopParsePoll() {
  // 拆书轮询用独立定时器，避免与写作轮询（pollTimer）互相清空
  if (parsePollTimer) {
    clearInterval(parsePollTimer)
    parsePollTimer = null
  }
}

function initParseSel(result) {
  // 默认全选：所有章节 + 所有卡片
  const p = store.parse
  p.selChapters = (result.chapters || []).map((_, i) => i)
  const sel = {}
  for (const [ctype, items] of Object.entries(result.cards || {})) {
    sel[ctype] = (items || []).map((c) => String(c.id))
  }
  p.selCards = sel
}

function parseSummary(stats) {
  const map = { chapters: '章节', character: '人物卡', plot: '剧情卡', style: '文风卡', foreshadowing: '伏笔卡', worldview: '世界观卡' }
  return Object.keys(map)
    .filter((k) => k in (stats || {}))
    .map((k) => `${map[k]} ${stats[k]}`)
    .join('，')
}

async function pollParse() {
  if (!store.parse.task) return
  const s = await api.parseBookStatus(store.parse.task)
  applyParse(s)
  if (s.status === 'done') {
    // 解析完成、尚未写入：展示预览供勾选，不自动刷新卡片
    stopParsePoll()
    initParseSel(s.result || { chapters: [], cards: {} })
    toast('解析完成，请预览勾选后写入')
  } else if (s.status === 'error') {
    stopParsePoll()
    toast('拆书出错：' + (s.error || '未知'), true)
  } else if (s.status === 'stopped') {
    stopParsePoll()
    toast('已终止拆书')
  } else if (s.status === 'not_found') {
    stopParsePoll()
    toast('任务不存在', true)
  }
}

export async function startParseBook(text, name, merge = true) {
  return guard(async () => {
    if (!store.project) {
      toast('请先选择项目', true)
      return
    }
    if (!text || !text.trim()) {
      toast('请先选择一本小说 txt', true)
      return
    }
    stopParsePoll()
    store.parse = {
      task: '', status: 'pending', progress: { done: 0, total: 0 },
      logs: [], stats: {}, error: '', result: null, selChapters: [], selCards: {}, committing: false,
    }
    const r = await api.parseBook(store.project, name, text, merge)
    store.parse.task = r.task_id
    store.parse.status = 'running'
    startParsePoll()
  })
}

export async function commitParseBook(merge, clearChapters) {
  return guard(async () => {
    if (!store.parse.task) {
      toast('没有可写入的解析结果', true)
      return
    }
    store.parse.committing = true
    const r = await api.parseBookCommit(store.parse.task, store.project, {
      merge, clearChapters,
      chapters: store.parse.selChapters,
      cards: store.parse.selCards,
    })
    store.parse.status = 'committed'
    store.parse.stats = r.stats || {}
    store.parse.committing = false
    toast('已写入：' + parseSummary(r.stats))
    await guard(loadCards)
    await guard(loadChapters)
  })
}

export async function stopParseBook() {
  return guard(async () => {
    if (!store.parse.task) return
    await api.parseBookStop(store.parse.task)
    toast('已发送终止请求')
  })
}

/* ------------------------------ 章节 ------------------------------ */
export async function loadChapters() {
  return guard(async () => {
    if (!store.project) {
      store.chapters = []
      return
    }
    const d = await api.listChapters(store.project)
    store.chapters = d.chapters || []
  })
}

export async function readChapter(file) {
  return guard(() => api.readChapter(store.project, file))
}

/* ------------------------------ 写作 ------------------------------ */
export function resetSession() {
  stopPoll()
  clearSessionMeta()
  store.session = {
    sid: '', status: 'idle', round: 0, stage: '', plan: '',
    draft: '', logs: [], chapterFile: '', error: '',
  }
  store.writing = false
}

export async function startWrite(payload) {
  return guard(async () => {
    resetSession()
    const r = await api.writeStart({ project: store.project, ...payload })
    store.session.sid = r.sid
    saveSessionMeta()
    projectSessions[store.project] = r.sid
    store.session.status = 'running'
    store.writing = true
    toast('已开始，流程会在人工审核处等你')
    startPoll()
  })
}

/**
 * 跨页签/刷新恢复：从 localStorage 读回上次会话 sid，对齐项目后直接拉状态。
 * 后端 SESSIONS 注册表 + 进程内 MemorySaver 仍持有完整状态，因此可无缝续上。
 * 若会话在后端已不存在（如手动清过 sessions.json），则清除本地记录，不报错。
 */
export async function resumeSession() {
  let sid = ''
  let proj = ''
  try {
    sid = localStorage.getItem(SID_KEY) || ''
    proj = localStorage.getItem(PROJECT_KEY) || ''
  } catch {
    return
  }
  if (!sid) return
  if (proj && store.projects.some((p) => p.path === proj)) store.project = proj
  if (!store.project) return
  // 先探一次，确认后端还有这个会话（避免恢复出已失效的会话）
  const s = await api.writeStatus(sid).catch(() => null)
  if (!s) {
    clearSessionMeta()
    return
  }
  store.session.sid = sid
  projectSessions[store.project] = sid
  applyStatus(s)
  store.writing = s.status === 'running'
  startPoll()
}

export async function sendAction(action, extra = {}) {
  return guard(async () => {
    await api.writeAction(store.session.sid, action, extra)
    store.session.status = 'running'
    store.writing = true
    startPoll()
  })
}

export async function stopWrite() {
  return guard(async () => {
    await api.writeStop(store.session.sid)
    stopPoll()
    store.writing = false
    store.session.status = 'stopped'
    toast('已终止')
  })
}

/* ------------------------------ 皮肤 ------------------------------ */
function applyTheme() {
  document.documentElement.dataset.theme = store.theme
}

export function initTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    store.theme = THEMES.some((t) => t.key === saved) ? saved : 'paper'
  } catch {
    store.theme = 'paper'
  }
  applyTheme()
}

export function setTheme(key) {
  store.theme = key
  try {
    localStorage.setItem(THEME_KEY, key)
  } catch {
    /* 隐私模式下写不了，忽略 */
  }
  applyTheme()
}

/* ------------------------------ 界面 ------------------------------ */
export function openDrawer(name) {
  store.drawer = name
}
export function closeDrawer() {
  store.drawer = null
}
export { toast }
