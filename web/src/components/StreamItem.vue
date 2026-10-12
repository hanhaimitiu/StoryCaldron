<script setup>
import { computed, ref } from 'vue'
import { agentOf } from '../api'

const props = defineProps({ log: { type: Object, required: true } })

const a = computed(() => agentOf(props.log.node_name))
const open = ref(false)
const mark = computed(
  () => ({ success: '✓', failed: '✗', running: '…' }[props.log.status] || '•'),
)
const hasOutput = computed(() => !!(props.log.output || '').trim())
</script>

<template>
  <div class="item" :class="log.status">
    <div class="avatar">{{ a.name.slice(0, 1) }}</div>
    <div class="body">
      <div class="head">
        <span class="who">{{ a.name }}</span>
        <span v-if="a.temp !== null" class="temp">temp {{ a.temp }}</span>
        <span class="mark">{{ mark }}</span>
        <span class="ms">{{ log.duration_ms || 0 }} ms</span>
      </div>
      <div class="what">{{ log.step_name }}</div>
      <div class="duty">{{ a.duty || log.description }}</div>
      <div v-if="hasOutput" class="out">
        <button class="link" @click="open = !open">{{ open ? '收起输出' : '查看输出' }}</button>
        <pre v-if="open" class="output">{{ log.output }}</pre>
      </div>
    </div>
  </div>
</template>
