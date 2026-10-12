<script setup>
import { computed, ref } from 'vue'
import { store, startWrite, stopWrite, toast } from '../store'

const title = ref('')
const outline = ref('')
const prev = ref('')
const more = ref(false)
const ids = ref({ characters: '', plots: '', styles: '', fore: '', worlds: '' })

const busy = computed(() => store.session.status === 'running')
const hasProject = computed(() => !!store.project)

async function submit() {
  if (!hasProject.value) {
    toast('请先在左侧选择或新建一个项目', true)
    return
  }
  if (!title.value.trim() || !outline.value.trim()) {
    toast('章节标题和大纲不能为空', true)
    return
  }
  await startWrite({
    title: title.value.trim(),
    outline: outline.value.trim(),
    prev: prev.value.trim(),
    characters: ids.value.characters.trim(),
    plots: ids.value.plots.trim(),
    styles: ids.value.styles.trim(),
    fore: ids.value.fore.trim(),
    worlds: ids.value.worlds.trim(),
  })
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
      <textarea v-model="prev" rows="2" placeholder="上一章概括（可留空）"></textarea>
      <div class="id-row">
        <input v-model="ids.characters" placeholder="人物卡 id" />
        <input v-model="ids.plots" placeholder="剧情卡 id" />
        <input v-model="ids.styles" placeholder="文风卡 id" />
        <input v-model="ids.fore" placeholder="伏笔卡 id" />
        <input v-model="ids.worlds" placeholder="世界观卡 id" />
      </div>
      <div class="dim">多个 id 用逗号分隔；留空表示使用该类全部卡片。</div>
    </div>
  </div>
</template>
