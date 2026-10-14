<script setup>
import { computed, ref, reactive } from 'vue'
import { store, saveCard, deleteCard, importMd, startParseBook, stopParseBook, commitParseBook, closeDrawer, toast } from '../store'
import { api } from '../api'

const tab = ref('cards') // cards | md | book

// ---- 卡片编辑 ----
const editing = ref(null) // { type, card }
const fieldsOf = (type) => store.cardFields[type] || ['id']
// 表单不展示 id：新建时由后端自动分配（api_save_card 兜底 <类型前缀>_<随机>），
// 编辑时 id 是卡片主键不可改，只在标题旁只读展示，避免用户手动填写无意义的 id。
const editFields = (type) => fieldsOf(type).filter((f) => f !== 'id')
// 卡片类型的中文标签（找不到时回退为类型名）
const typeLabel = (type) => (store.cardTypes.find((t) => t.type === type) || {}).label || type
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
  it.personality || it.description || it.style_overall || it.status || it.power_system || it.content || ''

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
    : '未识别到卡片。请检查二级标题是否包含：人物 / 剧情 / 文风 / 伏笔 / 世界观 / 去AI风。'
}

const types = computed(() => store.cardTypes || [])

// ---- 拆书解析 ----
const bookName = ref('')
const bookMerge = ref(true)
const bookClear = ref(false) // 导入前清空已有章节
const bookText = ref('')
const bookRunning = computed(() => ['pending', 'running'].includes(store.parse.status))
const CARD_LABELS = {
  character: '人物卡', plot: '剧情卡', style: '文风卡',
  foreshadowing: '伏笔卡', worldview: '世界观卡', anti_ai: '去AI风卡',
}

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

async function commitParse() {
  if (!store.parse.task) {
    toast('没有可写入的解析结果', true)
    return
  }
  await commitParseBook(bookMerge.value, bookClear.value)
}

// 勾选辅助
function isChSel(i) {
  return store.parse.selChapters.includes(i)
}
function toggleCh(i) {
  const arr = store.parse.selChapters
  const k = arr.indexOf(i)
  if (k >= 0) arr.splice(k, 1)
  else arr.push(i)
}
function chAll(on) {
  store.parse.selChapters = on && store.parse.result
    ? store.parse.result.chapters.map((_, i) => i)
    : []
}
function isCardSel(ctype, id) {
  return (store.parse.selCards[ctype] || []).includes(String(id))
}
function toggleCard(ctype, id) {
  const arr = store.parse.selCards[ctype] || (store.parse.selCards[ctype] = [])
  const k = arr.indexOf(String(id))
  if (k >= 0) arr.splice(k, 1)
  else arr.push(String(id))
}
function cardAll(ctype, on) {
  const items = (store.parse.result && store.parse.result.cards[ctype]) || []
  store.parse.selCards[ctype] = on ? items.map((c) => String(c.id)) : []
}
const cardLabel = (ctype) => CARD_LABELS[ctype] || ctype

const parsePct = computed(() => {
  const p = store.parse.progress
  return p.total ? Math.round((p.done / p.total) * 100) : 0
})

const parseStatText = computed(() => {
  const s = store.parse.stats
  const map = {
    chapters: '章节', character: '人物卡', plot: '剧情卡',
    style: '文风卡', foreshadowing: '伏笔卡', worldview: '世界观卡', anti_ai: '去AI风卡',
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
          {{ editing.card.id ? '编辑' : '新建' }} · {{ typeLabel(editing.type) }}
          <span v-if="editing.card.id" class="cid">id: {{ editing.card.id }}</span>
        </div>
        <label v-for="f in editFields(editing.type)" :key="f" class="cf">
          <span>{{ f }}</span>
          <textarea v-if="LONG.includes(f)" v-model="editing.card[f]" rows="2"></textarea>
          <input v-else v-model="editing.card[f]" />
        </label>
        <div v-if="!editing.card.id" class="chint">保存后自动分配 id，无需手动填写。</div>
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
        用二级标题分大类（人物 / 剧情 / 文风 / 伏笔 / 世界观 / 去AI风），三级标题分单张卡。
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
        选一本小说 txt，自动按「第N章 / Chapter N / 第N回」切分章节，
        并调用大模型从中提取 人物 / 剧情 / 文风 / 伏笔 / 世界观 五类素材卡。
        整本较长时后台逐章处理，解析完先预览勾选，再写入项目。
      </p>
      <input type="file" accept=".txt" @change="onBookFile" :disabled="bookRunning" />
      <div v-if="bookName" class="mdres">已选择：{{ bookName }}（{{ bookText.length }} 字）</div>
      <label class="mdopt"><input type="checkbox" v-model="bookMerge" :disabled="bookRunning" /> 与已有卡片合并</label>
      <div class="mdbtns">
        <button class="primary" :disabled="bookRunning" @click="runParse">开始拆书</button>
        <button v-if="bookRunning" @click="stopParseBook">终止</button>
      </div>

      <!-- 解析中：进度 + 日志 -->
      <div v-if="bookRunning" class="parsebox">
        <div class="pbar"><div class="pfill" :style="{ width: parsePct + '%' }"></div></div>
        <div class="pstat">
          状态：{{ store.parse.status }} · 进度 {{ store.parse.progress.done }}/{{ store.parse.progress.total }}（{{ parsePct }}%）
        </div>
        <div v-if="store.parse.error" class="perr">{{ store.parse.error }}</div>
        <div class="plogs">
          <div v-for="(l, i) in store.parse.logs" :key="i" class="plog">{{ l }}</div>
        </div>
      </div>

      <!-- 解析完成：预览 + 勾选 -->
      <div v-else-if="store.parse.status === 'done' && store.parse.result" class="parsebox">
        <div class="pstat">解析完成，预览并勾选要写入的内容：</div>
        <div class="ptools">
          <label class="mdopt"><input type="checkbox" v-model="bookClear" /> 导入前清空已有章节</label>
          <button class="primary" :disabled="store.parse.committing" @click="commitParse">
            {{ store.parse.committing ? '写入中…' : '写入选中' }}
          </button>
        </div>

        <div class="psec">
          <div class="psech">
            章节（{{ store.parse.selChapters.length }}/{{ store.parse.result.chapters.length }}）
            <span class="plink">
              <button class="link" @click="chAll(true)">全选</button> /
              <button class="link" @click="chAll(false)">全不选</button>
            </span>
          </div>
          <label v-for="(c, i) in store.parse.result.chapters" :key="i" class="pitem">
            <input type="checkbox" :checked="isChSel(i)" @change="toggleCh(i)" />
            <span>{{ c.title }} <em class="dim">（{{ c.chars }} 字）</em></span>
          </label>
        </div>

        <div v-for="[ctype, items] in Object.entries(store.parse.result.cards)" :key="ctype" class="psec">
          <div class="psech">
            {{ cardLabel(ctype) }}（{{ (store.parse.selCards[ctype] || []).length }}/{{ items.length }}）
            <span class="plink">
              <button class="link" @click="cardAll(ctype, true)">全选</button> /
              <button class="link" @click="cardAll(ctype, false)">全不选</button>
            </span>
          </div>
          <label v-for="it in items" :key="it.id" class="pitem">
            <input type="checkbox" :checked="isCardSel(ctype, it.id)" @change="toggleCard(ctype, it.id)" />
            <span>{{ cardName(it) }} <em class="dim">（{{ it.id }}）</em></span>
          </label>
        </div>
      </div>

      <!-- 已写入：结果统计 -->
      <div v-else-if="store.parse.status === 'committed'" class="parsebox">
        <div class="pstat">已写入项目：</div>
        <div v-if="parseStatText" class="mdres">{{ parseStatText }}</div>
        <div v-if="store.parse.error" class="perr">{{ store.parse.error }}</div>
      </div>

      <!-- 出错 / 终止 -->
      <div v-else-if="store.parse.status !== 'idle'" class="parsebox">
        <div class="pstat">状态：{{ store.parse.status }}</div>
        <div v-if="store.parse.error" class="perr">{{ store.parse.error }}</div>
      </div>
    </div>
  </aside>
</template>
