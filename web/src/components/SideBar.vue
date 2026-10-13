<script setup>
import { store, selectProject, createProject, deleteProject, setTheme, THEMES } from '../store'

const AGENT_COUNT = 12

const STATUS_LABEL = {
  idle: '待命', running: '创作中', waiting: '等你审核',
  done: '已完成', error: '出错', stopped: '已终止',
}
function statusText(s) {
  return STATUS_LABEL[s] || s
}

async function onCreate() {
  const name = window.prompt('新项目名称（会建在 projects/ 下）：', 'mybook')
  if (!name) return
  const demo = window.confirm('是否写入一套演示素材卡，方便马上试跑？')
  await createProject(name, demo)
}

function onDelete(p) {
  if (window.confirm(`确定删除项目「${p.name}」？\n该操作会移除其全部章节与素材卡（含 canon.md / outline.md），不可恢复。`)) {
    deleteProject(p.path)
  }
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
        <div class="row">
          <span
            v-if="store.projectStatus[p.path]"
            class="sdot"
            :class="store.projectStatus[p.path]"
            :title="statusText(store.projectStatus[p.path])"
          ></span>
          <span class="pname">{{ p.name }}</span>
          <button class="del" title="删除项目" @click.stop="onDelete(p)">×</button>
        </div>
        <span class="pmeta">{{ p.chapters }} 章 · {{ p.cards }} 卡</span>
      </li>
      <li v-if="!store.projects.length" class="empty">还没有项目</li>
    </ul>

    <button class="new" @click="onCreate">+ 新建项目</button>

    <div class="themes">
      <span class="tlabel">皮肤</span>
      <button
        v-for="t in THEMES"
        :key="t.key"
        class="swatch"
        :class="{ on: store.theme === t.key }"
        :style="{ background: t.swatch }"
        :title="t.name"
        @click="setTheme(t.key)"
      ></button>
    </div>

    <div class="foot">
      <div><b>{{ AGENT_COUNT }}</b> 个 Agent 节点接力</div>
      <div>写作 0.9 / 审批 0.2 分温协作</div>
    </div>
  </aside>
</template>

<style scoped>
.sdot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  margin-right: 8px;
  background: #aaa;
}
.row {
  display: flex;
  align-items: center;
}
.sdot.running {
  background: #3b82f6;
  box-shadow: 0 0 6px #3b82f6;
}
.sdot.waiting {
  background: #f59e0b;
  box-shadow: 0 0 6px #f59e0b;
}
.sdot.done {
  background: #22c55e;
}
.sdot.error {
  background: #ef4444;
}
.sdot.stopped {
  background: #9ca3af;
}
.del {
  margin-left: auto;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9ca3af;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.projects li:hover .del {
  opacity: 1;
}
.del:hover {
  background: #ef4444;
  color: #fff;
}
</style>
