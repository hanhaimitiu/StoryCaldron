<template>
  <div class="parse-page">
    <!-- 左侧：书籍扫描区域 -->
    <aside class="left-panel">
      <div class="panel-header">
        <h3>📚 扫描书籍</h3>
      </div>
      <div class="book-scan-area">
        <div class="upload-zone" @click="triggerFileInput" @dragover.prevent @drop="handleDrop">
          <input 
            ref="fileInput" 
            type="file" 
            accept=".txt,.md" 
            class="file-input" 
            @change="handleFileSelect"
          />
          <div class="upload-icon">📁</div>
          <p>点击或拖拽上传小说文件</p>
          <p class="hint">支持 .txt、.md 格式</p>
        </div>
        
        <div v-if="selectedFile" class="file-info">
          <span class="file-name">{{ selectedFile.name }}</span>
          <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
          <button class="btn-remove" @click="removeFile">✕</button>
        </div>

        <div class="text-input-section">
          <textarea 
            v-model="novelText" 
            placeholder="或直接粘贴小说原文到此处..." 
            class="text-input"
            rows="15"
          ></textarea>
        </div>
      </div>
    </aside>

    <!-- 中间：炼丹炉和功能按钮 -->
    <section class="center-panel">
      <div class="cauldron-container">
        <div class="cauldron">
          <div class="cauldron-inner">
            <div class="progress-ring">
              <svg width="200" height="200">
                <circle
                  class="progress-bg"
                  cx="100"
                  cy="100"
                  r="90"
                  fill="none"
                  stroke="#3d2d1f"
                  stroke-width="8"
                />
                <circle
                  class="progress-bar"
                  cx="100"
                  cy="100"
                  r="90"
                  fill="none"
                  stroke="#d4a574"
                  stroke-width="8"
                  :stroke-dasharray="circumference"
                  :stroke-dashoffset="progressOffset"
                  stroke-linecap="round"
                />
              </svg>
              <div class="progress-text">
                <span class="progress-value">{{ progress }}%</span>
                <span class="progress-label">{{ progressText }}</span>
              </div>
            </div>
            <div class="flame">🔥</div>
          </div>
        </div>
      </div>

      <div class="action-buttons">
        <button 
          class="action-btn" 
          @click="parseTask('人物卡解析')"
          :disabled="isProcessing || !hasContent"
        >
          <span class="btn-icon">👤</span>
          <span class="btn-text">解构人物</span>
        </button>
        <button 
          class="action-btn" 
          @click="parseTask('文风节奏解析')"
          :disabled="isProcessing || !hasContent"
        >
          <span class="btn-icon">✍️</span>
          <span class="btn-text">结构写法</span>
        </button>
        <button 
          class="action-btn" 
          @click="parseTask('剧情脉络解析')"
          :disabled="isProcessing || !hasContent"
        >
          <span class="btn-icon">📖</span>
          <span class="btn-text">结构剧情</span>
        </button>
        <button 
          class="action-btn" 
          @click="parseTask('世界观解析')"
          :disabled="isProcessing || !hasContent"
        >
          <span class="btn-icon">🌍</span>
          <span class="btn-text">解构世界观</span>
        </button>
        <button 
          class="action-btn btn-all" 
          @click="parseAll"
          :disabled="isProcessing || !hasContent"
        >
          <span class="btn-icon">🔮</span>
          <span class="btn-text">全部解析</span>
        </button>
      </div>
    </section>

    <!-- 右侧：四个内容栏 -->
    <aside class="right-panel">
      <div class="content-column">
        <div class="column-header">
          <h4>👤 人物栏</h4>
          <div class="search-box">
            <input 
              v-model="searchKeywords.character" 
              type="text" 
              placeholder="搜索人物..."
              class="search-input"
            />
          </div>
        </div>
        <div class="column-content">
          <div 
            v-for="(character, key) in filteredCharacters" 
            :key="key" 
            class="content-item"
          >
            <div class="item-header" @click="selectItem('character', key, character)">
              <div class="item-title">{{ character.name }}</div>
              <button class="btn-delete" @click.stop="deleteItem('character', key)" title="删除">🗑️</button>
            </div>
            <div class="item-info">{{ getIdentity(character) }}</div>
          </div>
          <div v-if="filteredCharacters.length === 0" class="empty-state">
            <p>暂无人物数据</p>
          </div>
        </div>
      </div>

      <div class="content-column">
        <div class="column-header">
          <h4>✍️ 写法栏</h4>
          <div class="search-box">
            <input 
              v-model="searchKeywords.style" 
              type="text" 
              placeholder="搜索文风..."
              class="search-input"
            />
          </div>
        </div>
        <div class="column-content">
          <div 
            v-for="(style, key) in filteredStyles" 
            :key="key" 
            class="content-item"
          >
            <div class="item-header" @click="selectItem('style', key, style)">
              <div class="item-title">{{ style.style_overall || '未命名' }}</div>
              <button class="btn-delete" @click.stop="deleteItem('style', key)" title="删除">🗑️</button>
            </div>
            <div class="item-info">{{ getStyleInfo(style) }}</div>
          </div>
          <div v-if="filteredStyles.length === 0" class="empty-state">
            <p>暂无文风数据</p>
          </div>
        </div>
      </div>

      <div class="content-column">
        <div class="column-header">
          <h4>📖 剧情栏</h4>
          <div class="search-box">
            <input 
              v-model="searchKeywords.plot" 
              type="text" 
              placeholder="搜索剧情..."
              class="search-input"
            />
          </div>
        </div>
        <div class="column-content">
          <div 
            v-for="(plot, key) in filteredPlots" 
            :key="key" 
            class="content-item"
          >
            <div class="item-header" @click="selectItem('plot', key, plot)">
              <div class="item-title">{{ getPlotTitle(plot) }}</div>
              <button class="btn-delete" @click.stop="deleteItem('plot', key)" title="删除">🗑️</button>
            </div>
            <div class="item-info">{{ getPlotInfo(plot) }}</div>
          </div>
          <div v-if="filteredPlots.length === 0" class="empty-state">
            <p>暂无剧情数据</p>
          </div>
        </div>
      </div>

      <div class="content-column">
        <div class="column-header">
          <h4>🌍 世界观栏</h4>
          <div class="search-box">
            <input 
              v-model="searchKeywords.worldview" 
              type="text" 
              placeholder="搜索世界观..."
              class="search-input"
            />
          </div>
        </div>
        <div class="column-content">
          <div 
            v-for="(worldview, key) in filteredWorldviews" 
            :key="key" 
            class="content-item"
          >
            <div class="item-header" @click="selectItem('worldview', key, worldview)">
              <div class="item-title">{{ worldview.world_theme || '未命名' }}</div>
              <button class="btn-delete" @click.stop="deleteItem('worldview', key)" title="删除">🗑️</button>
            </div>
            <div class="item-info">{{ getWorldviewInfo(worldview) }}</div>
          </div>
          <div v-if="filteredWorldviews.length === 0" class="empty-state">
            <p>暂无世界观数据</p>
          </div>
        </div>
      </div>
    </aside>

    <!-- 详情弹窗 -->
    <div v-if="showDetail" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ detailTitle }}</h3>
          <button class="btn-close" @click="closeDetail">✕</button>
        </div>
        <div class="modal-body">
          <div class="detail-actions">
            <button 
              v-if="!isEditing" 
              class="btn-action btn-edit" 
              @click="startEdit"
            >
              ✏️ 编辑
            </button>
            <template v-else>
              <button class="btn-action btn-save" @click="saveEdit">💾 保存</button>
              <button class="btn-action btn-cancel" @click="cancelEdit">❌ 取消</button>
            </template>
          </div>

          <div v-if="!isEditing && selectedItem" class="detail-content">
            <div v-for="(value, key) in selectedItem" :key="key" class="detail-row">
              <span class="detail-label">{{ formatKey(key) }}:</span>
              <span class="detail-value">{{ value }}</span>
            </div>
          </div>

          <div v-else-if="isEditing && editingData" class="edit-content">
            <div v-for="(value, key) in editingData" :key="key" class="edit-row">
              <label class="edit-label">{{ formatKey(key) }}:</label>
              <textarea 
                v-model="editingData[key]" 
                class="edit-input"
                rows="3"
              ></textarea>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <div v-if="isProcessing" class="loading-overlay">
      <div class="loading-content">
        <div class="loading-spinner"></div>
        <p>{{ processingText }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const fileInput = ref(null)
const selectedFile = ref(null)
const novelText = ref('')
const isProcessing = ref(false)
const progress = ref(0)
const progressText = ref('准备就绪')
const processingText = ref('处理中...')
const showDetail = ref(false)
const selectedItem = ref(null)
const selectedItemType = ref('')
const selectedKey = ref('')
const isEditing = ref(false)
const editingData = ref(null)

const searchKeywords = ref({
  character: '',
  style: '',
  plot: '',
  worldview: ''
})

const characters = ref({})
const styles = ref({})
const plots = ref({})
const worldviews = ref({})

const circumference = 2 * Math.PI * 90
const progressOffset = computed(() => {
  return circumference - (progress.value / 100) * circumference
})

const hasContent = computed(() => {
  return novelText.value.trim().length > 0 || selectedFile.value
})

const filteredCharacters = computed(() => {
  const keyword = searchKeywords.value.character.toLowerCase()
  const filtered = Object.entries(characters.value).filter(([key, char]) => {
    const name = char.name ? char.name.toLowerCase() : ''
    const identity = char.identity ? char.identity.toLowerCase() : ''
    return name.includes(keyword) || identity.includes(keyword)
  })
  return Object.fromEntries(filtered.slice(0, 5))
})

const filteredStyles = computed(() => {
  const keyword = searchKeywords.value.style.toLowerCase()
  const filtered = Object.entries(styles.value).filter(([key, style]) => {
    const styleOverall = style.style_overall ? style.style_overall.toLowerCase() : ''
    const sentenceFeature = style.sentence_feature ? style.sentence_feature.toLowerCase() : ''
    return styleOverall.includes(keyword) || sentenceFeature.includes(keyword)
  })
  return Object.fromEntries(filtered.slice(0, 5))
})

const filteredPlots = computed(() => {
  const keyword = searchKeywords.value.plot.toLowerCase()
  const filtered = Object.entries(plots.value).filter(([key, plot]) => {
    const mainStory = plot.main_story ? plot.main_story.toLowerCase() : ''
    const keyScene = plot.key_scene ? plot.key_scene.toLowerCase() : ''
    return mainStory.includes(keyword) || keyScene.includes(keyword)
  })
  return Object.fromEntries(filtered.slice(0, 5))
})

const filteredWorldviews = computed(() => {
  const keyword = searchKeywords.value.worldview.toLowerCase()
  const filtered = Object.entries(worldviews.value).filter(([key, worldview]) => {
    const worldTheme = worldview.world_theme ? worldview.world_theme.toLowerCase() : ''
    const powerSystem = worldview.power_system ? worldview.power_system.toLowerCase() : ''
    return worldTheme.includes(keyword) || powerSystem.includes(keyword)
  })
  return Object.fromEntries(filtered.slice(0, 5))
})

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function triggerFileInput() {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
    const reader = new FileReader()
    reader.onload = function(e) {
      novelText.value = e.target.result
    }
    reader.readAsText(file, 'utf-8')
  }
}

function handleDrop(event) {
  const file = event.dataTransfer.files[0]
  if (file && (file.name.endsWith('.txt') || file.name.endsWith('.md'))) {
    selectedFile.value = file
    const reader = new FileReader()
    reader.onload = function(e) {
      novelText.value = e.target.result
    }
    reader.readAsText(file, 'utf-8')
  }
}

function removeFile() {
  selectedFile.value = null
  novelText.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function parseTask(taskName) {
  if (!novelText.value.trim()) return
  
  isProcessing.value = true
  progress.value = 0
  progressText.value = '正在解析' + getTaskName(taskName) + '...'
  processingText.value = '正在解析' + getTaskName(taskName) + '...'

  try {
    const progressInterval = setInterval(function() {
      if (progress.value < 80) {
        progress.value += Math.random() * 15
      }
    }, 300)

    const response = await axios.post('/api/novel/parse/', {
      user_text: novelText.value.substring(0, 15000),
      model_name: 'gpt-4o',
      api_key: 'test',
      base_url: 'http://localhost:8080',
      task_name: taskName
    })

    clearInterval(progressInterval)
    progress.value = 100

    if (response.data.success) {
      const result = response.data.data[taskName]
      if (result && result.data) {
        saveResult(taskName, result.data)
      }
      progressText.value = getTaskName(taskName) + '完成'
    } else {
      progressText.value = '解析失败'
    }

    setTimeout(function() {
      progress.value = 0
      progressText.value = '准备就绪'
    }, 1500)
  } catch (error) {
    console.error('解析失败:', error)
    progressText.value = '解析失败'
    progress.value = 0
  } finally {
    isProcessing.value = false
  }
}

async function parseAll() {
  if (!novelText.value.trim()) return

  isProcessing.value = true
  progress.value = 0
  progressText.value = '正在进行全面解析...'
  processingText.value = '正在进行全面解析...'

  const tasks = ['人物卡解析', '文风节奏解析', '剧情脉络解析', '世界观解析']
  let completed = 0

  for (let i = 0; i < tasks.length; i++) {
    const taskName = tasks[i]
    progressText.value = '正在解析' + getTaskName(taskName) + '...'
    processingText.value = getTaskName(taskName) + ' (' + (completed + 1) + '/' + tasks.length + ')'

    try {
      const response = await axios.post('/api/novel/parse/', {
        user_text: novelText.value.substring(0, 15000),
        model_name: 'gpt-4o',
        api_key: 'test',
        base_url: 'http://localhost:8080',
        task_name: taskName
      })

      if (response.data.success) {
        const result = response.data.data[taskName]
        if (result && result.data) {
          saveResult(taskName, result.data)
        }
      }

      completed++
      progress.value = (completed / tasks.length) * 100
    } catch (error) {
      console.error('解析' + taskName + '失败:', error)
      completed++
      progress.value = (completed / tasks.length) * 100
    }
  }

  progressText.value = '全部解析完成'
  processingText.value = '解析完成'

  setTimeout(function() {
    progress.value = 0
    progressText.value = '准备就绪'
  }, 1500)

  isProcessing.value = false
}

function saveResult(taskName, data) {
  const key = taskName.split('解析')[0].toLowerCase() + '_' + Date.now()
  
  if (taskName === '人物卡解析') {
    if (Array.isArray(data)) {
      data.forEach(function(item, index) {
        characters.value['character_' + Date.now() + '_' + index] = item
      })
    } else {
      characters.value[key] = data
    }
  } else if (taskName === '文风节奏解析') {
    styles.value[key] = data
  } else if (taskName === '剧情脉络解析') {
    plots.value[key] = data
  } else if (taskName === '世界观解析') {
    worldviews.value[key] = data
  }
}

function getTaskName(taskName) {
  const map = {
    '人物卡解析': '人物卡',
    '文风节奏解析': '文风节奏',
    '剧情脉络解析': '剧情脉络',
    '世界观解析': '世界观'
  }
  return map[taskName] || taskName
}

function getIdentity(character) {
  return character.identity || ''
}

function getStyleInfo(style) {
  const feature = style.sentence_feature || ''
  return feature.substring(0, 30) + '...'
}

function getPlotTitle(plot) {
  const story = plot.main_story || ''
  return story.substring(0, 20) + '...'
}

function getPlotInfo(plot) {
  const scene = plot.key_scene || ''
  return scene.substring(0, 30) + '...'
}

function getWorldviewInfo(worldview) {
  const system = worldview.power_system || ''
  return system.substring(0, 30) + '...'
}

function selectItem(type, key, item) {
  selectedItem.value = JSON.parse(JSON.stringify(item))
  selectedItemType.value = type
  selectedKey.value = key
  isEditing.value = false
  editingData.value = null
  showDetail.value = true
}

function closeDetail() {
  showDetail.value = false
  isEditing.value = false
  editingData.value = null
}

async function deleteItem(type, key) {
  const typeMap = {
    'character': '人物',
    'style': '文风',
    'plot': '剧情',
    'worldview': '世界观'
  }
  const name = typeMap[type] || '数据'
  const apiMap = {
    'character': '/api/characters/',
    'style': '/api/styles/',
    'plot': '/api/stories/',
    'worldview': '/api/worldviews/'
  }
  const dataMap = {
    'character': characters.value,
    'style': styles.value,
    'plot': plots.value,
    'worldview': worldviews.value
  }
  
  if (confirm('确定要删除这条' + name + '吗？')) {
    try {
      const response = await axios.delete(apiMap[type] + key)
      if (response.data.success) {
        delete dataMap[type][key]
      } else {
        alert('删除失败: ' + response.data.message)
      }
    } catch (error) {
      console.error('删除失败:', error)
      delete dataMap[type][key]
    }
  }
}

function startEdit() {
  editingData.value = JSON.parse(JSON.stringify(selectedItem.value))
  isEditing.value = true
}

function cancelEdit() {
  editingData.value = null
  isEditing.value = false
}

async function saveEdit() {
  if (!editingData.value || !selectedKey.value) return

  const apiMap = {
    'character': '/api/characters/',
    'style': '/api/styles/',
    'plot': '/api/stories/',
    'worldview': '/api/worldviews/'
  }
  const dataMap = {
    'character': characters.value,
    'style': styles.value,
    'plot': plots.value,
    'worldview': worldviews.value
  }

  try {
    const response = await axios.put(apiMap[selectedItemType.value] + selectedKey.value, editingData.value)
    if (response.data.success) {
      dataMap[selectedItemType.value][selectedKey.value] = JSON.parse(JSON.stringify(editingData.value))
      selectedItem.value = JSON.parse(JSON.stringify(editingData.value))
      editingData.value = null
      isEditing.value = false
    } else {
      alert('保存失败: ' + response.data.message)
    }
  } catch (error) {
    console.error('保存失败:', error)
    dataMap[selectedItemType.value][selectedKey.value] = JSON.parse(JSON.stringify(editingData.value))
    selectedItem.value = JSON.parse(JSON.stringify(editingData.value))
    editingData.value = null
    isEditing.value = false
  }
}

const detailTitle = computed(function() {
  const typeMap = {
    'character': '👤 人物详情',
    'style': '✍️ 文风详情',
    'plot': '📖 剧情详情',
    'worldview': '🌍 世界观详情'
  }
  return typeMap[selectedItemType.value] || '详情'
})

function formatKey(key) {
  const keyMap = {
    name: '姓名',
    gender: '性别',
    appearance: '外貌特征',
    personality: '核心性格',
    identity: '身份/职位',
    experience: '关键经历',
    relationship: '人物关系',
    language_habit: '说话习惯',
    emotion_trait: '情绪特征',
    behavior_habit: '行为习惯',
    taboo: '人物禁忌',
    ability: '能力/特长',
    style_overall: '整体文风',
    sentence_feature: '句式特征',
    word_preference: '高频用词',
    rhythm_feature: '叙事节奏',
    emotion_tone: '情绪基调',
    narrate_habit: '叙事习惯',
    dialogue_style: '对话风格',
    taboo_style: '写作禁忌',
    main_story: '主线剧情',
    side_story: '支线剧情',
    current_conflict: '当前冲突',
    pending_plot: '待解决事件',
    foreshadowing_list: '已埋伏笔',
    key_scene: '关键场景',
    world_theme: '题材与基调',
    world_rule: '核心规则',
    power_system: '修炼/能力体系',
    force_faction: '势力分布',
    region_map: '地域场景',
    item_system: '道具/宝物体系',
    race_system: '种族设定',
    time_background: '时代背景'
  }
  return keyMap[key] || key
}

async function loadDataFromBackend() {
  try {
    const [charResponse, styleResponse, storyResponse, worldviewResponse] = await Promise.all([
      axios.get('/api/characters/'),
      axios.get('/api/styles/'),
      axios.get('/api/stories/'),
      axios.get('/api/worldviews/')
    ])

    if (charResponse.data.success) {
      characters.value = charResponse.data.data
    }
    if (styleResponse.data.success) {
      styles.value = styleResponse.data.data
    }
    if (storyResponse.data.success) {
      plots.value = storyResponse.data.data
    }
    if (worldviewResponse.data.success) {
      worldviews.value = worldviewResponse.data.data
    }
  } catch (error) {
    console.error('加载数据失败:', error)
    loadMockData()
  }
}

function loadMockData() {
  characters.value = {
    'character_1': {
      name: '杨伯符',
      gender: '男',
      appearance: '身着玄色蟒袍，目光深邃沉稳',
      personality: '沉稳、隐忍、深情、心思通透',
      identity: '皇帝、恭亲王、武林盟主',
      experience: '自幼被父皇冷落，在少林寺习武',
      relationship: '与玄夜璃为知己、爱人',
      language_habit: '语气平淡、沉稳，自称"朕"',
      emotion_trait: '冷静自持，软肋：玄夜璃',
      behavior_habit: '隐忍谋划，步步为营',
      taboo: '不能伤害玄夜璃',
      ability: '帝王权谋、武功、易容术'
    },
    'character_2': {
      name: '玄夜璃',
      gender: '女',
      appearance: '步履轻盈，指尖莹白，青丝飘逸',
      personality: '从容、淡然、深情、聪慧',
      identity: '玄乐师、魔教教主',
      experience: '曾与杨伯符并肩破局平乱',
      relationship: '与杨伯符为知己、爱人',
      language_habit: '语气轻浅柔和',
      emotion_trait: '释然、安心，软肋：杨伯符',
      behavior_habit: '行事轻盈，从容应对',
      taboo: '不能伤害杨伯符',
      ability: '高超琴艺、绝世武功、易容术'
    }
  }

  styles.value = {
    'style_1': {
      style_overall: '古风权谋与武侠结合，基调悲怆压抑',
      sentence_feature: '句式长短结合，多用四字短语',
      word_preference: '高频使用描写动作与环境的词汇',
      rhythm_feature: '叙事节奏张弛有度',
      emotion_tone: '情绪基调从冷静转为悲痛',
      narrate_habit: '采用全知视角叙事',
      dialogue_style: '对话直白且带有古风色彩',
      taboo_style: '避开现代口语化表达'
    }
  }

  plots.value = {
    'plot_1': {
      main_story: '杨伯符与玄夜璃联手平定篡位阴谋',
      side_story: '无',
      current_conflict: '杨伯符登基后玄夜璃离奇死亡',
      pending_plot: '无',
      key_scene: '雨夜对峙、登基大典、玄夜璃身亡'
    }
  }

  worldviews.value = {
    'worldview_1': {
      world_theme: '古代东方玄幻武侠，融合朝堂权谋',
      world_rule: '皇权至上、易容与身份伪装、内力体系',
      power_system: '内力/真气、武功招式、特殊能力',
      force_faction: '皇室/朝廷、武林盟主、魔教、北漠势力',
      region_map: '皇宫、魔教总坛、北漠、江湖、皇陵宗庙',
      item_system: '寒霜散、金属盒、武器、易容面具',
      race_system: '人类、魔教教主、北漠使节',
      time_background: '古代皇朝，深秋时节'
    }
  }
}

onMounted(function() {
  loadDataFromBackend()
})
</script>

<style scoped>
.parse-page {
  flex: 1;
  display: flex;
  gap: 20px;
  padding: 20px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
}

/* 左侧面板 */
.left-panel {
  width: 280px;
  background: linear-gradient(145deg, #1a1510, #110e0a);
  border: 1px solid #8c724a;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.panel-header h3 {
  color: #d4b886;
  font-size: 16px;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #443828;
}

.upload-zone {
  border: 2px dashed #6b583b;
  border-radius: 8px;
  padding: 30px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 16px;
}

.upload-zone:hover {
  border-color: #d4b886;
  background: rgba(212, 184, 134, 0.1);
}

.upload-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.upload-zone p {
  color: #e6c998;
  font-size: 14px;
  margin-bottom: 4px;
}

.upload-zone .hint {
  color: #8c724a;
  font-size: 12px;
}

.file-input {
  display: none;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #1f1a13;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 16px;
}

.file-name {
  flex: 1;
  color: #e6c998;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  color: #8c724a;
  font-size: 12px;
}

.btn-remove {
  background: #5c4a32;
  border: none;
  color: #e6c998;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn-remove:hover {
  background: #7a5d3a;
}

.text-input-section {
  flex: 1;
}

.text-input {
  width: 100%;
  height: 100%;
  min-height: 200px;
  background: #1f1a13;
  border: 1px solid #6b583b;
  border-radius: 8px;
  padding: 12px;
  color: #e6dcc8;
  font-size: 13px;
  resize: vertical;
  outline: none;
  font-family: inherit;
}

.text-input:focus {
  border-color: #d4b886;
}

.text-input::placeholder {
  color: #6b583b;
}

/* 中间面板 */
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.cauldron-container {
  margin-bottom: 40px;
}

.cauldron {
  width: 280px;
  height: 280px;
  background: linear-gradient(145deg, #2d1f14, #1a120a);
  border-radius: 50%;
  border: 4px solid #4a3520;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 60px rgba(212, 184, 134, 0.3), inset 0 -30px 60px rgba(0, 0, 0, 0.5);
  position: relative;
}

.cauldron-inner {
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, #3d2d1f 0%, #1a120a 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.progress-ring {
  position: relative;
}

.progress-bg {
  opacity: 0.3;
}

.progress-bar {
  transform: rotate(-90deg);
  transform-origin: center;
  transition: stroke-dashoffset 0.5s ease;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.progress-value {
  display: block;
  font-size: 32px;
  font-weight: bold;
  color: #d4b886;
}

.progress-label {
  display: block;
  font-size: 12px;
  color: #8c724a;
  margin-top: 4px;
}

.flame {
  position: absolute;
  bottom: -20px;
  font-size: 32px;
  animation: flicker 0.5s ease-in-out infinite alternate;
}

@keyframes flicker {
  from { opacity: 0.8; transform: scale(1); }
  to { opacity: 1; transform: scale(1.1); }
}

.action-buttons {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  width: 100%;
  max-width: 800px;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  background: linear-gradient(145deg, #2d241a, #1a1410);
  border: 2px solid #6b583b;
  border-radius: 10px;
  color: #e6c998;
  cursor: pointer;
  transition: all 0.3s;
}

.action-btn:hover:not(:disabled) {
  border-color: #d4b886;
  background: linear-gradient(145deg, #3d3224, #2a2018);
  transform: translateY(-3px);
  box-shadow: 0 5px 20px rgba(212, 184, 134, 0.3);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  font-size: 24px;
}

.btn-text {
  font-size: 13px;
}

.btn-all {
  background: linear-gradient(145deg, #a07c48, #8c6d4e);
  border-color: #a07c48;
}

.btn-all:hover:not(:disabled) {
  background: linear-gradient(145deg, #b89258, #a07c48);
  border-color: #b89258;
}

/* 右侧面板 */
.right-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.content-column {
  background: linear-gradient(145deg, #1a1510, #110e0a);
  border: 1px solid #8c724a;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  height: fit-content;
  max-height: 500px;
}

.column-header {
  padding: 12px 15px;
  border-bottom: 1px solid #443828;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.column-header h4 {
  color: #d4b886;
  font-size: 14px;
  margin: 0;
}

.search-box {
  position: relative;
}

.search-input {
  width: 100%;
  background: #1f1a13;
  border: 1px solid #6b583b;
  border-radius: 6px;
  padding: 6px 10px;
  color: #e6dcc8;
  font-size: 12px;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
}

.search-input:focus {
  border-color: #d4b886;
}

.search-input::placeholder {
  color: #6b583b;
}

.column-content {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  max-height: 400px;
}

.content-item {
  padding: 12px;
  background: #1f1a13;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.content-item:hover {
  background: #2a231a;
  transform: translateX(4px);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.item-title {
  color: #e6c998;
  font-size: 13px;
  font-weight: 500;
}

.item-info {
  color: #8c724a;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-delete {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.5;
  transition: opacity 0.3s;
  padding: 2px 6px;
}

.btn-delete:hover {
  opacity: 1;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6b583b;
}

.empty-state p {
  font-size: 13px;
}

/* 弹窗遮罩 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-content {
  background: linear-gradient(145deg, #1a1510, #110e0a);
  border: 2px solid #8c724a;
  border-radius: 12px;
  width: 90%;
  max-width: 700px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { 
    opacity: 0; 
    transform: translateY(20px); 
  }
  to { 
    opacity: 1; 
    transform: translateY(0); 
  }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #443828;
}

.modal-header h3 {
  color: #d4b886;
  font-size: 18px;
  margin: 0;
}

.btn-close {
  background: transparent;
  border: none;
  color: #8c724a;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.3s;
}

.btn-close:hover {
  background: #3d3224;
  color: #d4b886;
}

.modal-body {
  padding: 20px;
  max-height: calc(85vh - 60px);
  overflow-y: auto;
}

.detail-content {
  max-height: 400px;
  overflow-y: auto;
}

.detail-row {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid #3d3224;
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  width: 130px;
  color: #d4b886;
  font-weight: 500;
  flex-shrink: 0;
}

.detail-value {
  flex: 1;
  color: #e6dcc8;
  word-break: break-all;
  line-height: 1.6;
}

.detail-actions {
  margin-bottom: 20px;
  display: flex;
  gap: 10px;
}

.btn-action {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.btn-edit {
  background: #4a7c59;
  color: #fff;
}

.btn-edit:hover {
  background: #5a9c6a;
}

.btn-save {
  background: #d4b886;
  color: #1a1510;
}

.btn-save:hover {
  background: #e6c998;
}

.btn-cancel {
  background: #5c4a32;
  color: #e6c998;
}

.btn-cancel:hover {
  background: #7a5d3a;
}

.edit-content {
  max-height: 400px;
  overflow-y: auto;
}

.edit-row {
  margin-bottom: 16px;
}

.edit-label {
  display: block;
  color: #d4b886;
  font-weight: 500;
  margin-bottom: 8px;
  font-size: 14px;
}

.edit-input {
  width: 100%;
  background: #1f1a13;
  border: 1px solid #6b583b;
  border-radius: 6px;
  padding: 10px;
  color: #e6dcc8;
  font-size: 14px;
  resize: vertical;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
}

.edit-input:focus {
  border-color: #d4b886;
}

/* 加载遮罩 */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.loading-content {
  text-align: center;
}

.loading-spinner {
  width: 60px;
  height: 60px;
  border: 4px solid #3d2d1f;
  border-top-color: #d4b886;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-content p {
  color: #d4b886;
  font-size: 16px;
}

/* 响应式 */
@media (max-width: 1400px) {
  .action-buttons {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 1200px) {
  .parse-page {
    flex-direction: column;
    align-items: center;
  }
  
  .left-panel,
  .right-panel {
    width: 100%;
    max-width: 600px;
  }
  
  .action-buttons {
    grid-template-columns: repeat(5, 1fr);
    max-width: 600px;
  }
}

@media (max-width: 700px) {
  .action-buttons {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
