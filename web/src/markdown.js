// -*- coding: utf-8 -*-
/**
 * 轻量 Markdown -> HTML 渲染器（无第三方依赖）。
 *
 * 覆盖本项目用到的常见语法：标题、加粗、斜体、行内代码、围栏代码块、
 * 有序/无序列表、引用、分隔线、段落与换行。按行做结构识别，仅对文本片段
 * 做 HTML 转义后再套用行内强调，避免把（本地 LLM 生成的）内容当 HTML 注入。
 */
function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function inline(s) {
  return s
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

export function renderMarkdown(src) {
  if (!src) return ''
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0
  let listType = null
  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }
  while (i < lines.length) {
    const raw = lines[i]

    // 围栏代码块
    if (/^\s*```/.test(raw)) {
      closeList()
      const buf = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        buf.push(lines[i])
        i++
      }
      i++ // 跳过结束 ```
      out.push(`<pre><code>${escapeHtml(buf.join('\n'))}</code></pre>`)
      continue
    }

    // 标题
    const h = raw.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      closeList()
      const lvl = h[1].length
      out.push(`<h${lvl}>${inline(escapeHtml(h[2]))}</h${lvl}>`)
      i++
      continue
    }

    // 分隔线
    if (/^\s*---+\s*$/.test(raw)) {
      closeList()
      out.push('<hr>')
      i++
      continue
    }

    // 引用
    if (/^\s*>\s?/.test(raw)) {
      closeList()
      const buf = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      out.push(`<blockquote>${inline(escapeHtml(buf.join(' ')))}</blockquote>`)
      continue
    }

    // 无序列表
    const ul = raw.match(/^\s*[-*]\s+(.*)$/)
    if (ul) {
      if (listType !== 'ul') {
        closeList()
        out.push('<ul>')
        listType = 'ul'
      }
      out.push(`<li>${inline(escapeHtml(ul[1]))}</li>`)
      i++
      continue
    }

    // 有序列表
    const ol = raw.match(/^\s*\d+\.\s+(.*)$/)
    if (ol) {
      if (listType !== 'ol') {
        closeList()
        out.push('<ol>')
        listType = 'ol'
      }
      out.push(`<li>${inline(escapeHtml(ol[1]))}</li>`)
      i++
      continue
    }

    // 空行
    if (raw.trim() === '') {
      closeList()
      i++
      continue
    }

    // 普通段落（合并连续非空、非块级起始行）
    closeList()
    const para = [raw]
    i++
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^\s*```/.test(lines[i]) &&
      !/^(#{1,6})\s/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !/^\s*[-*]\s/.test(lines[i]) &&
      !/^\s*\d+\.\s/.test(lines[i])
    ) {
      para.push(lines[i])
      i++
    }
    out.push(`<p>${inline(escapeHtml(para.join(' ')))}</p>`)
  }
  closeList()
  return out.join('\n')
}
