<script setup>
import { ref } from 'vue'
import { store, readChapter, closeDrawer } from '../store'

const content = ref('')
const currentFile = ref('')

async function open(file) {
  const d = await readChapter(file)
  if (!d) return
  content.value = d.content || ''
  currentFile.value = file
}
</script>

<template>
  <aside class="drawer">
    <div class="dhead">
      <div class="dtabs"><span class="dtitle">已写章节</span></div>
      <button class="close" @click="closeDrawer">关闭</button>
    </div>

    <div class="dbody">
      <div v-if="!store.chapters.length" class="cempty">这个项目还没有写完的章节。</div>

      <div
        v-for="(c, i) in store.chapters"
        :key="c.file"
        class="chitem"
        :class="{ on: currentFile === c.file }"
        @click="open(c.file)"
      >
        <span class="idx">{{ String(i + 1).padStart(3, '0') }}</span>
        <span class="tt">{{ c.title || c.file }}</span>
        <span class="tm">{{ (c.updated_at || '').slice(0, 16).replace('T', ' ') }}</span>
      </div>

      <pre v-if="content" class="chtext">{{ content }}</pre>
    </div>
  </aside>
</template>
