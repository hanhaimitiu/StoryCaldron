<script setup>
import { store, selectProject, createProject } from '../store'

const AGENT_COUNT = 12

async function onCreate() {
  const name = window.prompt('新项目名称（会建在 projects/ 下）：', 'mybook')
  if (!name) return
  const demo = window.confirm('是否写入一套演示素材卡，方便马上试跑？')
  await createProject(name, demo)
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="logo">SC</div>
      <div class="brand-txt">
        <div class="name">StoryCaldron</div>
        <div class="sub">多 Agent 创作台</div>
      </div>
    </div>

    <div class="sec-title">项目</div>
    <ul class="projects">
      <li
        v-for="p in store.projects"
        :key="p.path"
        :class="{ active: p.path === store.project }"
        @click="selectProject(p.path)"
      >
        <span class="pname">{{ p.name }}</span>
        <span class="pmeta">{{ p.chapters }} 章 · {{ p.cards }} 卡</span>
      </li>
      <li v-if="!store.projects.length" class="empty">还没有项目</li>
    </ul>

    <button class="new" @click="onCreate">+ 新建项目</button>

    <div class="foot">
      <div><b>{{ AGENT_COUNT }}</b> 个 Agent 节点接力</div>
      <div>写作 0.9 / 审批 0.2 分温协作</div>
    </div>
  </aside>
</template>
