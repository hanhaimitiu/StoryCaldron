<script setup>
import { computed, onMounted } from 'vue'
import { store, loadProjects, openDrawer } from './store'
import SideBar from './components/SideBar.vue'
import AgentStream from './components/AgentStream.vue'
import Composer from './components/Composer.vue'
import CardsDrawer from './components/CardsDrawer.vue'
import ChaptersDrawer from './components/ChaptersDrawer.vue'

onMounted(loadProjects)

const STATUS_TEXT = {
  idle: '待命', running: '创作中', waiting: '等你审核',
  done: '已完成', error: '出错', stopped: '已终止',
}

const statusText = computed(() => STATUS_TEXT[store.session.status] || store.session.status)
const current = computed(() => store.projects.find((p) => p.path === store.project))
</script>

<template>
  <div class="app">
    <SideBar />

    <section class="main">
      <header class="topbar">
        <div class="meta">
          <h1>{{ current ? current.title : '未选择项目' }}</h1>
          <span class="path">{{ store.project || '请先新建一个项目' }}</span>
        </div>
        <div class="right">
          <span class="badge" :class="store.session.status">{{ statusText }}</span>
          <button @click="openDrawer('cards')">素材卡</button>
          <button @click="openDrawer('chapters')">章节</button>
        </div>
      </header>

      <AgentStream />
      <Composer />
    </section>

    <CardsDrawer v-if="store.drawer === 'cards'" />
    <ChaptersDrawer v-if="store.drawer === 'chapters'" />

    <div v-if="store.toast.show" class="toast" :class="{ err: store.toast.err }">
      {{ store.toast.msg }}
    </div>
  </div>
</template>
