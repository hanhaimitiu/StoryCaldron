<script setup>
/**
 * 创作输入面板：章节标题 + 本章大纲 + 高级选项。
 *
 * 高级选项里的「指定卡片」改为按类型分组的复选框：直接列出当前项目的各类素材卡，
 * 点选即用，不再让用户手填卡片 id（旧实现是 5 个文本框，毫无体验可言）。
 * 约定：某类型一张都不勾 = 该类使用全部卡片（与后端 start_session 的 None 语义一致）。
 */
import { computed, reactive, ref, watch } from 'vue'
import { store, startWrite, stopWrite, toast } from '../store'

const title = ref('')
const outline = ref('')
const prev = ref('')
const more = ref(false)

// 卡片类型 -> 后端 start_session 入参名（与 backend/api_write.api_write_start 的 body key 对应）
const PARAM_OF = {
  character: 'characters',
  plot: 'plots',
  style: 'styles',
  foreshadowing: 'fore',
  worldview: 'worlds',
  anti_ai: 'anti_ai',
}

// 各类型已勾选的卡片 id：{ [cardType]: string[] }；空数组 = 该类型用全部卡片
const picked = reactive({})

const busy = computed(() => store.session.status === 'running')
const hasProject = computed(() => !!store.project)

// 只列出「后端认识且确实有卡片」的类型，避免出现空白分组
const cardGroups = computed(() =>
  (store.cardTypes || [])
    .filter((t) => PARAM_OF[t.type] && (t.items || []).length)
    .map((t) => ({ type: t.type, label: t.label, items: t.items })),
)

// 读取某类型已勾选列表；只读，不在这里创建响应式键（避免渲染期改状态）
const pickedOf = (type) => picked[type] || []

function isPicked(type, id) {
  return pickedOf(type).includes(String(id))
}

function toggleCard(type, id) {
  const arr = picked[type] || (picked[type] = [])
  const k = arr.indexOf(String(id))
  if (k >= 0) arr.splice(k, 1)
  else arr.push(String(id))
}

/** 整组全选 / 清空 */
function toggleAll(type, on) {
  const g = cardGroups.value.find((x) => x.type === type)
  picked[type] = on && g ? g.items.map((it) => String(it.id)) : []
}

/** 卡片显示名：与 CardsDrawer 的命名逻辑保持一致 */
const cardName = (it) => it.name || it.title || it.content || it.world_theme || it.id

// 切换项目后卡片集合变了，清掉旧勾选，避免把上一项目的 id 带过去
watch(() => store.project, () => {
  for (const k of Object.keys(picked)) delete picked[k]
})

async function submit() {
  if (!hasProject.value) {
    toast('请先在左侧选择或新建一个项目', true)
    return
  }
  if (!title.value.trim() || !outline.value.trim()) {
    toast('章节标题和大纲不能为空', true)
    return
  }
  // 组装 payload：勾选的 id 以逗号拼接（后端 ids_of 再拆开）；未勾选则为空串=用全部
  const payload = {
    title: title.value.trim(),
    outline: outline.value.trim(),
    prev: prev.value.trim(),
  }
  for (const [ctype, key] of Object.entries(PARAM_OF)) {
    payload[key] = pickedOf(ctype).join(',')
  }
  await startWrite(payload)
}
</script>

<template>
  <div class="composer">
    <div class="row">
      <input v-model="title" class="title-input" placeholder="章节标题，如：第二章 剑鸣" />
      <button class="primary go" :disabled="busy" @click="submit">开始创作</button>
      <button v-if="busy" class="danger" @click="stopWrite">终止</button>
    </div>

    <textarea
      v-model="outline"
      class="outline"
      rows="2"
      placeholder="本章大纲：陆青崖引动古剑击退妖兽，封印裂痕扩大被长老察觉。"
    ></textarea>

    <div class="row tools">
      <button class="link" @click="more = !more">
        {{ more ? '收起高级选项' : '高级选项（上一章概括 / 指定卡片）' }}
      </button>
    </div>

    <div v-if="more" class="more">
      <textarea v-model="prev" rows="2" placeholder="上一章概括（可留空，留空自动取上一章全文模仿文风）"></textarea>

      <div v-if="!cardGroups.length" class="dim">
        当前项目暂无素材卡，可先在右侧「素材卡」中新建或导入。
      </div>

      <div v-for="g in cardGroups" :key="g.type" class="card-pick">
        <div class="cp-head">
          <span class="cp-label">{{ g.label }}</span>
          <span class="cp-cnt">{{ pickedOf(g.type).length }}/{{ g.items.length }}</span>
          <span class="cp-link">
            <button class="link" type="button" @click="toggleAll(g.type, true)">全选</button> /
            <button class="link" type="button" @click="toggleAll(g.type, false)">清空</button>
          </span>
        </div>
        <div class="cp-items">
          <label v-for="it in g.items" :key="it.id" class="cp-item">
            <input type="checkbox" :checked="isPicked(g.type, it.id)" @change="toggleCard(g.type, it.id)" />
            <span>{{ cardName(it) }}</span>
            <em>{{ it.id }}</em>
          </label>
        </div>
      </div>

      <div class="dim">某类一张都不勾 = 使用该类全部卡片；勾选后只注入勾选的卡片。</div>
    </div>
  </div>
</template>
