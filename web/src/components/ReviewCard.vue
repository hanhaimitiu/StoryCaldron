<script setup>
import { computed, ref } from 'vue'
import { store, sendAction } from '../store'
import { renderMarkdown } from '../markdown'

const mode = ref(null) // null | 'revise' | 'edit'
const fb = ref('')
const txt = ref('')

const draft = computed(() => store.session.draft || '（空）')
// 本章计划按 Markdown 渲染（来自本地 LLM，内容可信；renderMarkdown 已先做 HTML 转义防注入）
const planHtml = computed(() =>
  store.session.plan ? renderMarkdown(store.session.plan) : '<p>（无）</p>'
)

async function act(action, extra = {}) {
  mode.value = null
  fb.value = ''
  await sendAction(action, extra)
}
</script>

<template>
  <div class="review">
    <div class="rhead">
      <span class="tag">人工审核 · 第 {{ store.session.round }} 次暂停</span>
      <span class="rhint">流程已暂停，等你决定</span>
    </div>

    <div class="rsec">
      <b>本章计划</b>
      <div class="plan md" v-html="planHtml"></div>
    </div>

    <div class="rsec">
      <b>当前稿</b>
      <pre class="draft">{{ draft }}</pre>
    </div>

    <div class="rbtns">
      <button class="primary" @click="act('approved')">通过，继续</button>
      <button @click="mode = 'revise'">提修改意见</button>
      <button @click="mode = 'edit'; txt = store.session.draft">直接给全文</button>
      <button class="danger" @click="act('quit')">终止</button>
    </div>

    <div v-if="mode === 'revise'" class="rinput">
      <textarea
        v-model="fb"
        rows="3"
        placeholder="例如：环境描写再压缩一些，打斗节奏加快，结尾留个钩子"
      ></textarea>
      <button class="primary" :disabled="!fb.trim()" @click="act('revise', { feedback: fb })">
        提交意见并回炉重润
      </button>
    </div>

    <div v-if="mode === 'edit'" class="rinput">
      <textarea v-model="txt" rows="12" placeholder="粘贴你的全文，将替换当前稿"></textarea>
      <button class="primary" :disabled="!txt.trim()" @click="act('edit', { edited_draft: txt })">
        提交全文并继续
      </button>
    </div>
  </div>
</template>
