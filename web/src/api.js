/**
 * 后端接口封装。开发时由 vite 代理到 127.0.0.1:8765（backend/web_server.py），
 * 生产构建产物由后端托管，同源，所以这里一律用相对路径 /api。
 */

async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  let data = {}
  try {
    data = await res.json()
  } catch {
    /* 空响应 */
  }
  if (!res.ok) {
    throw new Error(data.error || `${res.status} ${res.statusText}`)
  }
  return data
}

const qs = (params) => {
  const u = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') u.append(k, v)
  })
  const s = u.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => request('/api/health'),

  listProjects: () => request('/api/projects'),
  createProject: (path, demo) => request('/api/projects', { method: 'POST', body: { path, demo } }),

  listCards: (project) => request(`/api/cards${qs({ project })}`),
  saveCard: (project, type, card) =>
    request('/api/cards', { method: 'POST', body: { project, type, card } }),
  deleteCard: (project, type, id) =>
    request('/api/cards/delete', { method: 'POST', body: { project, type, id } }),

  template: () => request('/api/template'),
  importMd: (project, md, useLlm, merge) =>
    request('/api/import-md', { method: 'POST', body: { project, md, use_llm: useLlm, merge } }),

  listChapters: (project) => request(`/api/chapters${qs({ project })}`),
  readChapter: (project, file) => request(`/api/chapter${qs({ project, file })}`),

  writeStart: (payload) => request('/api/write/start', { method: 'POST', body: payload }),
  writeStatus: (sid) => request(`/api/write/status${qs({ sid })}`),
  writeAction: (sid, action, extra = {}) =>
    request('/api/write/action', { method: 'POST', body: { sid, action, ...extra } }),
  writeStop: (sid) => request('/api/write/stop', { method: 'POST', body: { sid } }),
}

/** 后端节点 -> 前端展示用的角色信息（温度与后端 ROLE_TEMPERATURES 一致） */
export const AGENTS = {
  loader: { name: '上下文加载', duty: '读取人物卡、剧情卡、文风卡等素材', temp: null },
  planner: { name: '规划 Agent', duty: '把大纲拆成本章详细计划', temp: 0.4 },
  card_approver: { name: '大纲审批', duty: '判断本章计划是否可行', temp: 0.2 },
  writer: { name: '写作 Agent', duty: '根据计划与素材撰写正文', temp: 0.9 },
  continuity_checker: { name: '连续性检查', duty: '检查与前文、人设、伏笔是否冲突', temp: 0.2 },
  continuity_fixer: { name: '修复 Agent', duty: '按检查报告修改草稿', temp: 0.7 },
  style_editor: { name: '文风润色', duty: '按文风卡润色正文', temp: 0.5 },
  human_review: { name: '人工审核', duty: '停下来等你拍板', temp: null },
  memory_updater: { name: '记忆 Agent', duty: '把新伏笔、新进展写回素材卡', temp: 0.3 },
  canon_proposer: { name: '正典提案', duty: '总结本章确立的正典信息', temp: 0.4 },
  canon_approver: { name: '正典审批', duty: '判断正典是否可以入库', temp: 0.2 },
  committer: { name: '定稿', duty: '保存最终章节', temp: null },
}

export const agentOf = (node) =>
  AGENTS[node] || { name: node || '未知节点', duty: '', temp: null }
