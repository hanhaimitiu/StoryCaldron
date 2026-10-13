<script setup>
import { computed, ref, reactive } from 'vue'
import { store, saveCard, deleteCard, importMd, startParseBook, stopParseBook, closeDrawer, toast } from '../store'
import { api } from '../api'

const tab = ref('cards') // cards | md | book

// ---- 卡片编辑 ----
const editing = ref(null) // { type, card }
const fieldsOf = (type) => store.cardFields[type] || ['id']
const LONG = ['appearance', 'personality', 'ability', 'identity', 'description',
  'style_overall', 'sentence_feature', 'word_preference', 'content',
  'world_theme', 'power_system', 'world_rule']

const newType = ref('')
const blank = reactive({})

function startNew() {
  const type = newType.value || (store.cardTypes[0] && store.cardTypes[0].type)
  if (!type) return
  editing.value = { type, card: {} }
}

function startEdit(type, card) {
  editing.value = { type, card: { ...card } }
}

async function submitCard() {
  if (!editing.value) return
  await saveCard(editing.value.type, editing.value.card)
  editing.value = null
}

async function remove(type, id) {
  if (!window.confirm(`确定删除卡片 ${id} ？`)) return
  await deleteCard(type, id)
}

const cardName = (it) => it.name || it.title || it.content || it.world_theme || ''
const cardDesc = (it) =>
  it.personality || it.description || it.style_overall || it.status || it.power_system || ''

// ---- MD 导入 ----
const md = ref('')
const useLlm = ref(true)
const merge = ref(true)
const mdResult = ref('')

async function loadTemplate() {
  const r = await api.template()
  md.value = r.template || ''
  toast('已载入书写模板')
}

async function runImport() {
  if (!md.value.trim()) {
    toast('请先粘贴 Markdown 设定', true)
    return
  }
  const r = await importMd(md.value, useLlm.value, merge.value)
  const stats = (r && r.stats) || {}
  const keys = Object.keys(stats)
  mdResult.value = keys.length
    ? '转换完成：' + keys.map((k) => `${k} ${stats[k]} 张`).join('，')
    : '未识别到卡片。请检查二级标题是否包含：人物 / 剧情 / 文风 / 伏笔 / 世界观。'
}

const types = computed(() => store.cardTypes || [])

// ---- 拆书解析 ----
const bookFile = ref(null)
const bookName = ref('')
const bookMerge = ref(true)
const bookText = ref('')
const bookRunning = computed(() => ['pending', 'running'].includes(store.parse.status))

function onBookFile(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  bookName.value = f.name
  const reader = new FileReader()
  reader.onload = () => {
    bookText.value = String(reader.result || '')
  }
  reader.readAsText(f, 'utf-8')
}

async function runParse() {
  if (!bookText.value.trim()) {
    toast('请先选择一本小说 txt', true)
    return
  }
  await startParseBook(bookText.value, bookName.value, bookMerge.value)
}

const parsePct = computed(() => {
  const p = store.parse.progress
  return p.total ? Math.round((p.done / p.total) * 100) : 0
})

const parseStatText = computed(() => {
  const s = store.parse.stats
  const map = {
    chapters: '章节', character: '人物卡', plot: '剧情卡',
    style: '文风卡', foreshadowing: '伏笔卡', worldview: '世界观卡',
  }
  return Object.keys(map)
    .filter((k) => k in s)
    .map((k) => `${map[k]} ${s[k]}`)
    .join('，')
})
</script>

<template>
  <aside class="drawer">
    <div class="dhead">
      <div class="dtabs">
        <button :class="{ on: tab === 'cards' }" @click="tab = 'cards'">素材卡</button>
        <button :class="{ on: tab === 'md' }" @click="tab = 'md'">MD 导入</button>
        <button :class="{ on: tab === 'book' }" @click="tab = 'book'">拆书解析</button>
      </div>
      <button class="close" @click="closeDrawer">关闭</button>
    </div>

    <!-- 素材卡 -->
    <div v-if="tab === 'cards'" class="dbody">
      <div class="dtools">
        <select v-model="newType">
          <option v-for="t in types" :key="t.type" :value="t.type">{{ t.label }}</option>
        </select>
        <button class="primary" @click="startNew">新建一张</button>
      </div>

      <div v-if="editing" class="cform">
        <div class="ctitle">
          编辑 · {{ (types.find((t) => t.type === editing.type) || {}).label || editing.type }}
        </div>
        <label v-for="f in fieldsOf(editing.type)" :key="f" class="cf">
          <span>{{ f }}</span>
          <textarea v-if="LONG.includes(f)" v-model="editing.card[f]" rows="2"></textarea>
          <input v-else v-model="editing.card[f]" />
        </label>
        <div class="cbtns">
          <button class="primary" @click="submitCard">保存</button>
          <button @click="editing = null">取消</button>
        </div>
      </div>

      <div v-for="t in types" :key="t.type" class="cgroup">
        <div class="cghead">
          {{ t.label }}
          <span class="cnt">{{ t.count }} 条</span>
          <span class="file">{{ t.file }}</span>
        </div>
        <div v-if="!t.items.length" class="cempty">（暂无）</div>
        <div v-for="it in t.items" :key="it.id" class="citem">
          <div class="ctxt">
            <span class="cid">{{ it.id }}</span>
            <span class="cname">{{ cardName(it) }}</span>
            <span class="cdesc">{{ cardDesc(it) }}</span>
          </div>
          <div class="cacts">
            <button class="link" @click="startEdit(t.type, it)">编辑</button>
            <button class="link danger" @click="remove(t.type, it.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- MD 导入 -->
    <div v-else-if="tab === 'md'" class="dbody">
      <p class="dim">
        用二级标题分大类（人物 / 剧情 / 文风 / 伏笔 / 世界观），三级标题分单张卡。
        这是独立工具，不进入小说生成流程。
      </p>
      <textarea v-model="md" class="mdbox" placeholder="## 人物卡&#10;### 陆青崖&#10;- name：陆青崖&#10;- personality：沉稳、重情义"></textarea>
      <div class="mdopts">
        <label><input type="checkbox" v-model="useLlm" /> 用大模型理解散文式设定</label>
        <label><input type="checkbox" v-model="merge" /> 与已有卡片合并</label>
      </div>
      <div class="mdbtns">
        <button class="primary" @click="runImport">开始转换</button>
        <button @click="loadTemplate">载入模板</button>
      </div>
      <div v-if="mdResult" class="mdres">{{ mdResult }}</div>
    </div>

    <!-- 拆书解析 -->
    <div v-else class="dbody">
      <p class="dim">
        选一本小说 txt，自动按「第N章 / Chapter N / 第N回」切分章节存入 chapters/，
        并调用大模型从中提取 人物 / 剧情 / 文风 / 伏笔 / 世界观 五类素材卡。
        整本较长时后台逐章处理，可随时终止。
      </p>
      <input type="file" accept=".txt" @change="onBookFile" />
      <div v-if="bookName" class="mdres">已选择：{{ bookName }}（{{ bookText.length }} 字）</div>
      <label class="mdopt"><input type="checkbox" v-model="bookMerge" /> 与已有卡片合并</label>
      <div class="mdbtns">
        <button class="primary" :disabled="bookRunning" @click="runParse">开始拆书</button>
        <button v-if="bookRunning" @click="stopParseBook">终止</button>
      </div>

      <div v-if="store.parse.status !== 'idle'" class="parsebox">
        <div class="pbar"><div class="pfill" :style="{ width: parsePct + '%' }"></div></div>
        <div class="pstat">
          状态：{{ store.parse.status }} · 进度 {{ store.parse.progress.done }}/{{ store.parse.progress.total }}（{{ parsePct }}%）
        </div>
        <div v-if="store.parse.error" class="perr">{{ store.parse.error }}</div>
        <div v-if="parseStatText" class="mdres">{{ parseStatText }}</div>
        <div class="plogs">
          <div v-for="(l, i) in store.parse.logs" :key="i" class="plog">{{ l }}</div>
        </div>
      </div>
    </div>
  </aside>
</template>
