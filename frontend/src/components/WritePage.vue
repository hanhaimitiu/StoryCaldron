<template>
  <div class="write-page">
    <main class="write-content">
      <!-- 左侧：四个内容栏 -->
      <aside class="left-panel">
        <!-- 人物栏 -->
        <div class="content-column">
          <div class="column-header">
            <h4>👤 人物栏</h4>
            <div class="search-box">
              <input 
                type="text" 
                v-model="characterSearch" 
                placeholder="搜索人物..." 
                class="search-input"
              />
            </div>
          </div>
          <div class="column-content">
            <div 
              v-for="(item, key) in filteredCharacters" 
              :key="key"
              class="content-item"
              :class="{ 'selected': selectedCharacters.includes(key) }"
              @click="toggleCharacter(key)"
            >
              <div class="item-header">
                <span class="item-checkbox">{{ selectedCharacters.includes(key) ? '✓' : '' }}</span>
                <span class="item-title">{{ item.name || '未知人物' }}</span>
                <div class="item-actions">
                  <button class="action-btn-sm" @click.stop="viewItem('characters', key, item)">👁</button>
                  <button class="action-btn-sm" @click.stop="editItem('characters', key, item)">✏️</button>
                </div>
              </div>
              <p class="item-summary">{{ truncate(item.personality || item.experience || '', 50) }}</p>
            </div>
            <div v-if="Object.keys(filteredCharacters).length === 0" class="empty-state">
              <p>暂无数据</p>
            </div>
          </div>
        </div>

        <!-- 写法栏 -->
        <div class="content-column">
          <div class="column-header">
            <h4>✍️ 写法栏</h4>
            <div class="search-box">
              <input 
                type="text" 
                v-model="styleSearch" 
                placeholder="搜索写法..." 
                class="search-input"
              />
            </div>
          </div>
          <div class="column-content">
            <div 
              v-for="(item, key) in filteredStyles" 
              :key="key"
              class="content-item"
              :class="{ 'selected': selectedStyles.includes(key) }"
              @click="toggleStyle(key)"
            >
              <div class="item-header">
                <span class="item-checkbox">{{ selectedStyles.includes(key) ? '✓' : '' }}</span>
                <span class="item-title">{{ item.rhythm || '风格' }}</span>
                <div class="item-actions">
                  <button class="action-btn-sm" @click.stop="viewItem('styles', key, item)">👁</button>
                  <button class="action-btn-sm" @click.stop="editItem('styles', key, item)">✏️</button>
                </div>
              </div>
              <p class="item-summary">{{ truncate(item.language_style || '', 50) }}</p>
            </div>
            <div v-if="Object.keys(filteredStyles).length === 0" class="empty-state">
              <p>暂无数据</p>
            </div>
          </div>
        </div>

        <!-- 剧情栏 -->
        <div class="content-column">
          <div class="column-header">
            <h4>📖 剧情栏</h4>
            <div class="search-box">
              <input 
                type="text" 
                v-model="storySearch" 
                placeholder="搜索剧情..." 
                class="search-input"
              />
            </div>
          </div>
          <div class="column-content">
            <div 
              v-for="(item, key) in filteredStories" 
              :key="key"
              class="content-item"
              :class="{ 'selected': selectedStories.includes(key) }"
              @click="toggleStory(key)"
            >
              <div class="item-header">
                <span class="item-checkbox">{{ selectedStories.includes(key) ? '✓' : '' }}</span>
                <span class="item-title">{{ item.outline || '剧情' }}</span>
                <div class="item-actions">
                  <button class="action-btn-sm" @click.stop="viewItem('stories', key, item)">👁</button>
                  <button class="action-btn-sm" @click.stop="editItem('stories', key, item)">✏️</button>
                </div>
              </div>
              <p class="item-summary">{{ truncate(item.analysis || '', 50) }}</p>
            </div>
            <div v-if="Object.keys(filteredStories).length === 0" class="empty-state">
              <p>暂无数据</p>
            </div>
          </div>
        </div>

        <!-- 世界观栏 -->
        <div class="content-column">
          <div class="column-header">
            <h4>🌍 世界观栏</h4>
            <div class="search-box">
              <input 
                type="text" 
                v-model="worldviewSearch" 
                placeholder="搜索世界观..." 
                class="search-input"
              />
            </div>
          </div>
          <div class="column-content">
            <div 
              v-for="(item, key) in filteredWorldviews" 
              :key="key"
              class="content-item"
              :class="{ 'selected': selectedWorldviews.includes(key) }"
              @click="toggleWorldview(key)"
            >
              <div class="item-header">
                <span class="item-checkbox">{{ selectedWorldviews.includes(key) ? '✓' : '' }}</span>
                <span class="item-title">{{ item.world_name || '世界观' }}</span>
                <div class="item-actions">
                  <button class="action-btn-sm" @click.stop="viewItem('worldviews', key, item)">👁</button>
                  <button class="action-btn-sm" @click.stop="editItem('worldviews', key, item)">✏️</button>
                </div>
              </div>
              <p class="item-summary">{{ truncate(item.background || '', 50) }}</p>
            </div>
            <div v-if="Object.keys(filteredWorldviews).length === 0" class="empty-state">
              <p>暂无数据</p>
            </div>
          </div>
        </div>
      </aside>

      <!-- 中间：炼丹炉区域 + 步骤日志 -->
      <section class="center-panel">
        <div class="cauldron-container">
          <div class="cauldron">
            <div class="cauldron-body">
              <div class="flame" :class="{ 'active': isProcessing }"></div>
              <div class="steam" :class="{ 'active': isProcessing }"></div>
              <div class="cauldron-content">
                <div v-if="!isProcessing && !sessionId" class="idle-state">
                  <span class="cauldron-icon">⚗️</span>
                  <p>准备就绪</p>
                </div>
                <div v-else-if="isProcessing" class="processing-state">
                  <div class="progress-ring">
                    <svg width="100" height="100">
                      <circle
                        class="progress-bg"
                        cx="50"
                        cy="50"
                        r="45"
                        fill="none"
                        stroke="#443828"
                        stroke-width="8"
                      />
                      <circle
                        class="progress-bar"
                        cx="50"
                        cy="50"
                        r="45"
                        fill="none"
                        stroke="#d4a574"
                        stroke-width="8"
                        :stroke-dasharray="circumference"
                        :stroke-dashoffset="progressOffset"
                        stroke-linecap="round"
                        transform="rotate(-90 50 50)"
                      />
                    </svg>
                    <div class="progress-text">{{ Math.round(progress) }}%</div>
                  </div>
                  <p class="progress-message">{{ progressText }}</p>
                </div>
                <div v-else class="session-state">
                  <span class="cauldron-icon">🔮</span>
                  <p>会话进行中</p>
                  <p class="session-id">{{ sessionId?.substring(0, 8) }}...</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 控制按钮 -->
          <div class="control-buttons">
            <button
              v-if="!sessionId"
              class="control-btn primary"
              @click="startWriting"
              :disabled="!canStart"
            >
              🚀 开始创作
            </button>
            <button
              v-else-if="status === 'waiting_for_human'"
              class="control-btn primary"
              @click="submitHumanAction('continue')"
            >
              ▶ 继续执行
            </button>
            <button
              v-else-if="status === 'waiting_for_human'"
              class="control-btn success"
              @click="submitHumanAction('edit')"
            >
              ✏️ 用当前草稿继续
            </button>
            <button
              v-else-if="status === 'waiting_for_human'"
              class="control-btn warning"
              @click="submitHumanAction('suggest')"
            >
              💬 提交修改建议
            </button>
            <button
              v-else-if="status === 'waiting_for_human'"
              class="control-btn danger"
              @click="submitHumanAction('terminate')"
            >
              ⛔ 终止
            </button>
            <button
              v-else-if="isProcessing"
              class="control-btn danger"
              @click="terminateSession"
            >
              ⛔ 终止
            </button>
            <button
              v-else-if="status === 'finished'"
              class="control-btn secondary"
              @click="resetSession"
            >
              🔄 重新开始
            </button>
            <button
              v-else-if="status === 'terminated'"
              class="control-btn secondary"
              @click="resetSession"
            >
              🔄 重新开始
            </button>
          </div>
        </div>

        <!-- 步骤日志面板 -->
        <div class="step-log-panel">
          <div class="panel-header">
            <h4>📋 执行步骤</h4>
            <span class="step-count">{{ stepLogs.length }} 步</span>
          </div>
          <div class="step-list">
            <div 
              v-for="(log, index) in stepLogs" 
              :key="log.step_id"
              class="step-item"
              :class="log.status"
            >
              <div class="step-number">{{ index + 1 }}</div>
              <div class="step-content">
                <div class="step-header">
                  <span class="step-name">{{ log.step_name }}</span>
                  <span class="step-status" :class="log.status">
                    {{ getStatusText(log.status) }}
                  </span>
                </div>
                <p class="step-desc">{{ log.description }}</p>
                <div v-if="log.output" class="step-output">
                  <p>{{ truncate(log.output, 100) }}</p>
                </div>
                <span class="step-time">{{ formatTime(log.timestamp) }} · {{ log.duration_ms }}ms</span>
              </div>
            </div>
            <div v-if="stepLogs.length === 0" class="empty-step">
              <p>暂无执行记录</p>
            </div>
          </div>
        </div>
      </section>

      <!-- 右侧：输入输出区域 -->
      <aside class="right-panel">
        <!-- 输入区域 -->
        <div class="input-section">
          <h4>📝 前文回顾</h4>
          <textarea 
            v-model="previousText" 
            placeholder="请输入上一章内容或前文回顾..." 
            class="input-textarea"
            rows="6"
          ></textarea>
        </div>

        <div class="input-section">
          <h4>🎯 本章大纲</h4>
          <textarea 
            v-model="newOutline" 
            placeholder="请输入本章大纲..." 
            class="input-textarea"
            rows="6"
          ></textarea>
        </div>

        <!-- 修改意见输入（仅在等待人工审核时显示） -->
        <div v-if="status === 'waiting_for_human'" class="input-section feedback-section">
          <h4>💬 人工修改意见</h4>
          <textarea
            v-model="humanFeedback"
            placeholder="可在此处输入修改建议，按 Ctrl+Enter 直接提交，或点击下方按钮..."
            class="input-textarea"
            rows="4"
            @keydown.ctrl.enter.prevent="submitHumanAction('suggest')"
            @keydown.meta.enter.prevent="submitHumanAction('suggest')"
          ></textarea>

          <!-- 操作按钮（直接在输入框下方，不用滚动回顶部） -->
          <div class="control-buttons human-actions">
            <button class="control-btn primary" @click="submitHumanAction('continue')">
              ▶ 继续执行（采纳当前草稿）
            </button>
            <button class="control-btn success" @click="submitHumanAction('edit')">
              ✏ 用当前草稿作为终稿
            </button>
            <button class="control-btn warning" @click="submitHumanAction('suggest')" :disabled="!humanFeedback.trim()">
              💬 提交修改建议让AI重写
            </button>
            <button class="control-btn danger" @click="submitHumanAction('terminate')">
              ⛔ 终止会话
            </button>
          </div>

          <p class="hint">💡 提示：也可以直接修改上方「生成内容」中的文字，然后点「用当前草稿作为终稿」</p>
        </div>

        <!-- 输出区域 -->
        <div class="output-section">
          <div class="section-header">
            <h4>📄 生成内容</h4>
            <button 
              v-if="generatedContent && !isProcessing" 
              class="save-btn"
              @click="saveDraft"
            >
              💾 保存草稿
            </button>
          </div>
          <textarea 
            v-model="generatedContent" 
            placeholder="生成的内容将显示在这里..." 
            class="output-textarea"
            rows="15"
            :readonly="isProcessing"
          ></textarea>
          <div v-if="aiFeedback" class="feedback-box">
            <h5>🔍 AI 审稿意见</h5>
            <p>{{ aiFeedback }}</p>
          </div>
        </div>
      </aside>
    </main>

    <!-- 查看/编辑弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ modalTitle }}</h3>
          <button class="close-btn" @click="closeModal">✕</button>
        </div>
        <div class="modal-body">
          <pre>{{ modalContent }}</pre>
        </div>
        <div class="modal-footer">
          <button v-if="modalTitle === '编辑'" class="modal-btn confirm" @click="saveEdit">保存</button>
          <button class="modal-btn cancel" @click="closeModal">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'

// 搜索关键词
const characterSearch = ref('')
const styleSearch = ref('')
const storySearch = ref('')
const worldviewSearch = ref('')

// 选中项（数组支持多选）
const selectedCharacters = ref([])
const selectedStyles = ref([])
const selectedStories = ref([])
const selectedWorldviews = ref([])

// 输入内容
const previousText = ref('')
const newOutline = ref('')
const generatedContent = ref('')
const humanFeedback = ref('')
const aiFeedback = ref('')

// 会话状态
const sessionId = ref('')
const currentStage = ref('')
const status = ref('')
const stepLogs = ref([])
const revisionCount = ref(0)

// 轮询定时器
let pollTimer = null

// 处理状态
const isProcessing = ref(false)
const progress = ref(0)
const progressText = ref('准备就绪')

// 弹窗状态
const showModal = ref(false)
const modalTitle = ref('')
const modalContent = ref('')
const editingItem = ref(null)
const editingType = ref('')
const editingKey = ref('')

// 数据
const characters = ref({})
const styles = ref({})
const stories = ref({})
const worldviews = ref({})

// 进度环相关
const circumference = 2 * Math.PI * 45
const progressOffset = computed(() => {
  return circumference - (progress.value / 100) * circumference
})

// 是否可以开始
const canStart = computed(() => {
  return previousText.value.trim() && newOutline.value.trim()
})

// 过滤后的数据
const filteredCharacters = computed(() => filterData(characters.value, characterSearch.value))
const filteredStyles = computed(() => filterData(styles.value, styleSearch.value))
const filteredStories = computed(() => filterData(stories.value, storySearch.value))
const filteredWorldviews = computed(() => filterData(worldviews.value, worldviewSearch.value))

function filterData(data, search) {
  if (!search.value) return data
  const query = search.value.toLowerCase()
  return Object.fromEntries(
    Object.entries(data).filter(([key, item]) => {
      const values = Object.values(item).map(v => String(v).toLowerCase())
      return values.some(v => v.includes(query))
    })
  )
}

// 加载数据
async function loadData() {
  try {
    const [charRes, styleRes, storyRes, worldviewRes] = await Promise.all([
      axios.get('/api/characters/'),
      axios.get('/api/styles/'),
      axios.get('/api/stories/'),
      axios.get('/api/worldviews/')
    ])
    characters.value = charRes.data.data || {}
    styles.value = styleRes.data.data || {}
    stories.value = storyRes.data.data || {}
    worldviews.value = worldviewRes.data.data || {}
  } catch (error) {
    console.error('加载数据失败:', error)
  }
}

// 选择项（toggle模式）
function toggleCharacter(key) {
  const index = selectedCharacters.value.indexOf(key)
  if (index > -1) {
    selectedCharacters.value.splice(index, 1)
  } else {
    selectedCharacters.value.push(key)
  }
}

function toggleStyle(key) {
  const index = selectedStyles.value.indexOf(key)
  if (index > -1) {
    selectedStyles.value.splice(index, 1)
  } else {
    selectedStyles.value.push(key)
  }
}

function toggleStory(key) {
  const index = selectedStories.value.indexOf(key)
  if (index > -1) {
    selectedStories.value.splice(index, 1)
  } else {
    selectedStories.value.push(key)
  }
}

function toggleWorldview(key) {
  const index = selectedWorldviews.value.indexOf(key)
  if (index > -1) {
    selectedWorldviews.value.splice(index, 1)
  } else {
    selectedWorldviews.value.push(key)
  }
}

// 查看/编辑弹窗
function viewItem(collection, key, item) {
  modalTitle.value = '查看详情'
  modalContent.value = JSON.stringify(item, null, 2)
  showModal.value = true
}

function editItem(collection, key, item) {
  editingType.value = collection
  editingKey.value = key
  editingItem.value = { ...item }
  modalTitle.value = '编辑'
  modalContent.value = JSON.stringify(item, null, 2)
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  modalTitle.value = ''
  modalContent.value = ''
  editingItem.value = null
}

async function saveEdit() {
  try {
    const data = JSON.parse(modalContent.value)
    const response = await axios.put(`/api/${editingType.value}/${editingKey.value}`, data)
    if (response.data.success) {
      await loadData()
    }
    closeModal()
  } catch (error) {
    alert('保存失败，请检查JSON格式')
  }
}

// 轮询获取最新状态
function startPolling(session_id) {
  // 先清掉旧的
  stopPolling()

  // 轮询函数
  async function poll() {
    if (!session_id.value) {
      stopPolling()
      return
    }

    try {
      const response = await axios.get(`/api/write/session/${session_id.value}/state`)

      if (!response.data.success) return

      const data = response.data.data

      // 无条件更新 step_logs（节点内部会改已有 log 的状态）
      if (data.step_logs && data.step_logs.length > 0) {
        stepLogs.value = data.step_logs
      }

      // 基础字段
      status.value = data.status || status.value
      currentStage.value = data.current_stage || currentStage.value
      if (data.draft) {
        generatedContent.value = data.draft
      }
      if (data.feedback) {
        aiFeedback.value = data.feedback
      }
      revisionCount.value = data.revision_count || 0

      // 根据后端返回的 status 驱动 UI
      if (data.status === 'waiting_for_human') {
        progress.value = 90
        progressText.value = '等待人工审核'
        isProcessing.value = false
        // 注意：这里不停止轮询，等用户操作后后台继续跑，轮询会收到新状态
      } else if (data.status === 'finished') {
        progressText.value = '任务已完成'
        progress.value = 100
        isProcessing.value = false
        stopPolling()
      } else if (data.status === 'terminated') {
        progressText.value = '任务已终止'
        isProcessing.value = false
        stopPolling()
      } else if (data.status === 'running') {
        const nodeCount = data.step_logs ? data.step_logs.length : 0
        const estimatedProgress = Math.min(nodeCount * 20, 75)
        if (estimatedProgress > progress.value) {
          progress.value = estimatedProgress
        }
        progressText.value = (data.current_stage || '继续执行中') + '...'
      } else if (data.status === 'idle') {
        progressText.value = '等待执行...'
      }
    } catch (error) {
      console.error('轮询失败:', error)
      // 网络错误不停止，允许重试
    }
  }

  // 立即执行一次
  poll()

  // 每 2 秒轮询一次
  pollTimer = setInterval(poll, 2000)
}

// 停止轮询
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 写作会话管理
async function startWriting() {
  if (!canStart.value) return
  
  isProcessing.value = true
  progress.value = 0
  progressText.value = '正在创建会话...'
  
  try {
    const response = await axios.post('/api/write/session/start', {
      previous_text: previousText.value,
      new_outline: newOutline.value,
      selected_characters: selectedCharacters.value,
      selected_styles: selectedStyles.value,
      selected_stories: selectedStories.value,
      selected_worldviews: selectedWorldviews.value
    })
    
    if (response.data.success) {
      sessionId.value = response.data.data.session_id
      stepLogs.value = response.data.data.step_logs
      progress.value = 30
      progressText.value = '会话已创建'
      
      // 启动轮询获取状态更新
      startPolling(sessionId)
      
      // 执行下一步
      await executeNextStep()
    }
  } catch (error) {
    console.error('启动会话失败:', error)
    alert('启动会话失败: ' + error.message)
    isProcessing.value = false
  }
}

async function executeNextStep() {
  if (!sessionId.value) return
  
  isProcessing.value = true
  progressText.value = '正在执行步骤...'
  
  try {
    // 使用 HTTP POST 请求执行步骤
    const response = await axios.post(`/api/write/session/${sessionId.value}/execute`)
    
    if (response.data.success) {
      console.log('步骤执行已启动')
    }
  } catch (error) {
    console.error('执行步骤失败:', error)
    alert('执行步骤失败: ' + error.message)
    isProcessing.value = false
  }
}

async function submitHumanAction(action) {
  if (!sessionId.value) return

  isProcessing.value = true
  progressText.value = '正在提交...'

  try {
    const body = { action: action }
    if (action === 'edit') {
      body.edited_draft = generatedContent.value
    } else if (action === 'suggest') {
      if (!humanFeedback.value || !humanFeedback.value.trim()) {
        alert('请先在「人工修改意见」框中输入建议')
        isProcessing.value = false
        progressText.value = '等待人工审核'
        return
      }
      body.suggestions = [humanFeedback.value]
    }

    const response = await axios.post(`/api/write/session/${sessionId.value}/action`, body)

    if (response.data.success) {
      const data = response.data.data
      if (data.step_logs && data.step_logs.length > 0) {
        stepLogs.value = data.step_logs
      }
      status.value = data.status || status.value
      currentStage.value = data.current_stage || currentStage.value
      if (data.draft) generatedContent.value = data.draft
      if (data.feedback) aiFeedback.value = data.feedback
      revisionCount.value = data.revision_count || 0
      humanFeedback.value = ''

      if (action === 'terminate') {
        progressText.value = '任务已终止'
        status.value = 'terminated'
        stopPolling()
      } else {
        progressText.value = '继续执行中...'
        // 不停止轮询，继续收后台执行结果
      }
    }
  } catch (error) {
    console.error('提交操作失败:', error)
    alert('提交操作失败: ' + (error.message || '未知错误'))
    isProcessing.value = false
  }
}

async function terminateSession() {
  if (!sessionId.value) return
  
  try {
    await axios.post(`/api/write/session/${sessionId.value}/terminate`)
    resetSession()
  } catch (error) {
    console.error('终止会话失败:', error)
  }
}

function resetSession() {
  stopPolling()
  sessionId.value = ''
  currentStage.value = ''
  status.value = ''
  stepLogs.value = []
  generatedContent.value = ''
  aiFeedback.value = ''
  humanFeedback.value = ''
  progress.value = 0
  progressText.value = '准备就绪'
  isProcessing.value = false
}

async function saveDraft() {
  if (!sessionId.value || !generatedContent.value) return
  
  try {
    const response = await axios.put(`/api/write/session/${sessionId.value}/draft`, {
      new_draft: generatedContent.value
    })
    
    if (response.data.success) {
      stepLogs.value = response.data.data.step_logs
      alert('草稿已保存')
    }
  } catch (error) {
    console.error('保存草稿失败:', error)
    alert('保存草稿失败: ' + error.message)
  }
}

// 辅助函数
function truncate(str, length) {
  if (!str) return ''
  return str.length > length ? str.substring(0, length) + '...' : str
}

function getStatusText(status) {
  const map = {
    'running': '运行中',
    'success': '成功',
    'failed': '失败'
  }
  return map[status] || status
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onMounted(() => {
  loadData()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.write-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1510 0%, #2d2319 50%, #1a1510 100%);
  padding: 20px;
}

.write-content {
  display: flex;
  gap: 20px;
  height: calc(100vh - 40px);
}

/* 左侧面板 */
.left-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.content-column {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 12px;
  border: 1px solid rgba(212, 184, 134, 0.1);
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.column-header h4 {
  color: #d4b886;
  font-size: 14px;
  margin: 0;
}

.search-box {
  width: 120px;
}

.search-input {
  width: 100%;
  padding: 4px 8px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid #443828;
  border-radius: 4px;
  color: #d4b886;
}

.column-content {
  max-height: 180px;
  overflow-y: auto;
}

.content-item {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.content-item:hover {
  background: rgba(212, 184, 134, 0.1);
}

.content-item.selected {
  background: rgba(212, 165, 116, 0.15);
  border-color: #d4a574;
}

.item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
    gap: 8px;
}

.item-checkbox {
    width: 18px;
    height: 18px;
    border: 1px solid #443828;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    color: #d4b886;
    background: rgba(255, 255, 255, 0.05);
    flex-shrink: 0;
}

.content-item.selected .item-checkbox {
    background: #d4a574;
    border-color: #d4b886;
    color: #1a1510;
}

.item-title {
    font-size: 12px;
    font-weight: bold;
    color: #d4b886;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.item-actions {
  display: flex;
  gap: 4px;
}

.action-btn-sm {
  width: 22px;
  height: 22px;
  background: rgba(212, 184, 134, 0.1);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 10px;
  color: #d4b886;
}

.item-summary {
  font-size: 11px;
  color: #8b7355;
  margin: 0;
  line-height: 1.4;
}

.empty-state {
  text-align: center;
  color: #5a4a3a;
  font-size: 12px;
  padding: 10px;
}

/* 中间面板 */
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cauldron-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  border: 1px solid rgba(212, 184, 134, 0.1);
  padding: 20px;
}

.cauldron {
  width: 200px;
  height: 200px;
  position: relative;
}

.cauldron-body {
  width: 100%;
  height: 100%;
  background: linear-gradient(180deg, #3d3228 0%, #2a2218 100%);
  border-radius: 50%;
  border: 4px solid #4a3f30;
  box-shadow: 
    inset 0 -30px 50px rgba(0,0,0,0.5),
    0 10px 30px rgba(0,0,0,0.5);
  position: relative;
  overflow: hidden;
}

.flame {
  position: absolute;
  bottom: -20px;
  left: 50%;
  transform: translateX(-50%);
  width: 60px;
  height: 40px;
  background: linear-gradient(180deg, #ff6b35 0%, #ffcc00 50%, #ff6b35 100%);
  border-radius: 50% 50% 20% 20%;
  opacity: 0;
  transition: opacity 0.3s;
}

.flame.active {
  opacity: 1;
  animation: flicker 0.3s infinite alternate;
}

@keyframes flicker {
  0% { transform: translateX(-50%) scale(1); }
  100% { transform: translateX(-50%) scale(1.1); }
}

.steam {
  position: absolute;
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  width: 80px;
  height: 40px;
  background: rgba(255,255,255,0.2);
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.3s;
}

.steam.active {
  opacity: 1;
  animation: steamRise 2s infinite;
}

@keyframes steamRise {
  0% { transform: translateX(-50%) translateY(0); opacity: 0.3; }
  100% { transform: translateX(-50%) translateY(-30px); opacity: 0; }
}

.cauldron-content {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.idle-state, .session-state {
  color: #d4b886;
}

.cauldron-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 10px;
}

.idle-state p, .session-state p {
  margin: 5px 0;
  font-size: 14px;
}

.session-id {
  font-family: monospace;
  font-size: 12px;
  color: #8b7355 !important;
}

.processing-state {
  color: #d4b886;
}

.progress-ring {
  position: relative;
  width: 100px;
  height: 100px;
  margin: 0 auto 10px;
}

.progress-bg {
  opacity: 0.3;
}

.progress-bar {
  transition: stroke-dashoffset 0.3s ease;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 20px;
  font-weight: bold;
}

.progress-message {
  margin: 0;
  font-size: 13px;
}

.control-buttons {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.control-buttons.human-actions {
  flex-wrap: wrap;
  justify-content: flex-start;
  margin: 15px 0;
}

.control-buttons.human-actions .control-btn {
  padding: 12px 18px;
  font-size: 14px;
  white-space: normal;
  text-align: center;
}

.control-btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-btn.primary {
  background: linear-gradient(135deg, #d4a574 0%, #c9966b 100%);
  color: #1a1510;
}

.control-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(212, 165, 116, 0.3);
}

.control-btn.warning {
  background: linear-gradient(135deg, #c95a5a 0%, #b54a4a 100%);
  color: white;
}

.control-btn.success {
  background: linear-gradient(135deg, #5a9e6f 0%, #4a8a5f 100%);
  color: white;
}

.control-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #d4b886;
  border: 1px solid rgba(212, 184, 134, 0.3);
}

/* 步骤日志面板 */
.step-log-panel {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px solid rgba(212, 184, 134, 0.1);
  padding: 12px;
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.panel-header h4 {
  color: #d4b886;
  font-size: 14px;
  margin: 0;
}

.step-count {
  font-size: 12px;
  color: #8b7355;
}

.step-list {
  flex: 1;
  overflow-y: auto;
}

.step-item {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  border-left: 3px solid #443828;
}

.step-item.running {
  border-left-color: #d4a574;
}

.step-item.success {
  border-left-color: #5a9e6f;
}

.step-item.failed {
  border-left-color: #c95a5a;
}

.step-number {
  float: left;
  width: 24px;
  height: 24px;
  background: rgba(212, 184, 134, 0.2);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #d4b886;
  margin-right: 10px;
}

.step-content {
  overflow: hidden;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.step-name {
  font-size: 13px;
  font-weight: bold;
  color: #d4b886;
}

.step-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}

.step-status.running {
  background: rgba(212, 165, 116, 0.2);
  color: #d4a574;
}

.step-status.success {
  background: rgba(90, 158, 111, 0.2);
  color: #5a9e6f;
}

.step-status.failed {
  background: rgba(201, 90, 90, 0.2);
  color: #c95a5a;
}

.step-desc {
  font-size: 12px;
  color: #8b7355;
  margin: 4px 0;
}

.step-output {
  background: rgba(0,0,0,0.2);
  border-radius: 4px;
  padding: 6px;
  margin: 4px 0;
}

.step-output p {
  font-size: 11px;
  color: #a08868;
  margin: 0;
  font-family: monospace;
}

.step-time {
  font-size: 10px;
  color: #5a4a3a;
}

.empty-step {
  text-align: center;
  color: #5a4a3a;
  padding: 20px;
}

/* 右侧面板 */
.right-panel {
  width: 400px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.input-section, .output-section {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 12px;
  border: 1px solid rgba(212, 184, 134, 0.1);
}

.input-section h4, .output-section h4 {
  color: #d4b886;
  font-size: 13px;
  margin: 0 0 8px 0;
}

.input-textarea, .output-textarea {
  width: 100%;
  padding: 10px;
  background: rgba(0,0,0,0.2);
  border: 1px solid #443828;
  border-radius: 8px;
  color: #d4b886;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  box-sizing: border-box;
}

.input-textarea::placeholder, .output-textarea::placeholder {
  color: #5a4a3a;
}

.output-textarea:read-only {
  background: rgba(0,0,0,0.1);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.save-btn {
  padding: 6px 12px;
  background: rgba(212, 165, 116, 0.2);
  border: 1px solid #d4a574;
  border-radius: 4px;
  color: #d4b886;
  font-size: 12px;
  cursor: pointer;
}

.save-btn:hover {
  background: rgba(212, 165, 116, 0.3);
}

.feedback-section {
  background: rgba(212, 165, 116, 0.08);
  border-color: rgba(212, 165, 116, 0.3);
}

.feedback-box {
  margin-top: 10px;
  background: rgba(90, 158, 111, 0.1);
  border-radius: 8px;
  padding: 10px;
  border-left: 3px solid #5a9e6f;
}

.feedback-box h5 {
  color: #5a9e6f;
  font-size: 12px;
  margin: 0 0 5px 0;
}

.feedback-box p {
  color: #a8c4b0;
  font-size: 12px;
  margin: 0;
  line-height: 1.5;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #2d2319;
  border-radius: 12px;
  width: 500px;
  max-height: 80vh;
  border: 1px solid #d4b886;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  border-bottom: 1px solid #443828;
}

.modal-header h3 {
  color: #d4b886;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  color: #8b7355;
  font-size: 20px;
  cursor: pointer;
}

.modal-body {
  padding: 20px;
  max-height: 50vh;
  overflow-y: auto;
}

.modal-body pre {
  color: #d4b886;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-size: 13px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 15px 20px;
  border-top: 1px solid #443828;
}

.modal-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.modal-btn.confirm {
  background: #d4a574;
  color: #1a1510;
}

.modal-btn.cancel {
  background: rgba(255,255,255,0.1);
  color: #d4b886;
}
</style>
