<script setup>
import { computed } from 'vue'
import { store } from '../store'
import StreamItem from './StreamItem.vue'
import ReviewCard from './ReviewCard.vue'

const logs = computed(() => store.session.logs || [])
const started = computed(() => store.session.status !== 'idle')
const running = computed(() => store.session.status === 'running')
const waiting = computed(() => store.session.status === 'waiting')
const failed = computed(() => store.session.status === 'error')
</script>

<template>
  <div class="stream">
    <div v-if="!started" class="empty-state">
      <h2>开始创作新的一章</h2>
      <p>
        在下方填写章节标题与大纲，多个 Agent 会依次接力：
        <b>规划</b> → <b>大纲审批</b> → <b>写作</b> → <b>连续性检查</b> → <b>文风润色</b>
        → <b class="hl">停下来等你审核</b> → <b>记忆更新</b> → <b>正典入库</b> → <b>定稿</b>。
      </p>
      <p class="dim">写作全程在本地模型上跑，一章通常要十几分钟，中途会暂停等你拍板。</p>
    </div>

    <template v-else>
      <StreamItem v-for="(l, i) in logs" :key="i" :log="l" />

      <div v-if="running" class="thinking">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        <span class="txt">{{ store.session.stage || 'Agent 正在工作' }}…</span>
      </div>

      <ReviewCard v-if="waiting" />

      <div v-if="failed" class="err-box">
        流程出错：{{ store.session.error || '未知错误' }}
      </div>
    </template>
  </div>
</template>
