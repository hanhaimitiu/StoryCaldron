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
  store.project = path
  resetSession()
  await Promise.all([loadCards(), loadChapters()])
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
    store.session.status = 'running'
    store.writing = true
    toast('已开始，流程会在人工审核处等你')
    startPoll()
  })
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
