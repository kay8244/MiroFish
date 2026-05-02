<template>
  <div class="interaction-panel">
    <!-- Main Split Layout -->
    <div class="main-split-layout">
      <!-- LEFT PANEL: Report Style -->
      <ReportPanel
        :reportId="reportId"
        :reportOutline="reportOutline"
        :generatedSections="generatedSections"
        :collapsedSections="collapsedSections"
        :currentSectionIndex="currentSectionIndex"
        :isSectionCompleted="isSectionCompleted"
        :renderMarkdown="renderMarkdown"
        @toggle-collapse="toggleSectionCollapse"
      />

      <!-- RIGHT PANEL: Interaction Interface -->
      <div class="right-panel" ref="rightPanel">
        <!-- Unified Action Bar -->
        <ActionBar
          :profiles="profiles"
          :activeTab="activeTab"
          :chatTarget="chatTarget"
          :selectedAgent="selectedAgent"
          :showAgentDropdown="showAgentDropdown"
          @select-report-agent="selectReportAgentChat"
          @toggle-dropdown="toggleAgentDropdown"
          @select-agent="selectAgent"
          @select-survey="selectSurveyTab"
          @select-scenario="selectScenarioTab"
        />

        <!-- Chat Mode -->
        <div v-if="activeTab === 'chat'" class="chat-container">

          <!-- Report Agent Tools Card -->
          <ReportAgentToolsCard v-if="chatTarget === 'report_agent'" />

          <!-- Agent Profile Card -->
          <AgentProfileCard v-if="chatTarget === 'agent' && selectedAgent" :agent="selectedAgent" />

          <!-- Chat Messages + Input -->
          <ChatMessages
            :chatHistory="chat.chatHistory.value"
            :chatTarget="chatTarget"
            :selectedAgent="selectedAgent"
            :isSending="chat.isSending.value"
            :chatInput="chat.chatInput.value"
            :formatTime="chat.formatTime"
            :renderMarkdown="renderMarkdown"
            @send="chat.debouncedSendMessage"
            @update:chatInput="chat.chatInput.value = $event"
            ref="chatMessagesComp"
          />
        </div>

        <!-- Survey Mode -->
        <SurveyPanel
          v-if="activeTab === 'survey'"
          :profiles="profiles"
          :selectedAgents="survey.selectedAgents.value"
          :surveyQuestion="survey.surveyQuestion.value"
          :surveyResults="survey.surveyResults.value"
          :isSurveying="survey.isSurveying.value"
          :renderMarkdown="renderMarkdown"
          @toggle-agent="survey.toggleAgentSelection"
          @select-all="survey.selectAllAgents"
          @clear-selection="survey.clearAgentSelection"
          @update:surveyQuestion="survey.surveyQuestion.value = $event"
          @submit="survey.submitSurvey"
        />

        <!-- B 시나리오: 같은 graph + 새 질문 → 시뮬+보고서 -->
        <ScenarioPanel
          v-if="activeTab === 'scenario' && simulationId"
          :simulationId="simulationId"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import DOMPurify from 'dompurify'
import { getReport, getAgentLog } from '../api/report'
import { getSimulationProfilesRealtime } from '../api/simulation'
import { useChat } from '../composables/useChat'
import { useSurvey } from '../composables/useSurvey'
import ReportPanel from './interaction/ReportPanel.vue'
import ActionBar from './interaction/ActionBar.vue'
import ChatMessages from './interaction/ChatMessages.vue'
import SurveyPanel from './interaction/SurveyPanel.vue'
import ReportAgentToolsCard from './interaction/ReportAgentToolsCard.vue'
import AgentProfileCard from './interaction/AgentProfileCard.vue'
import ScenarioPanel from './interaction/ScenarioPanel.vue'

const props = defineProps({
  reportId: String,
  simulationId: String
})

const emit = defineEmits(['add-log', 'update-status'])

// State
const activeTab = ref('chat')
const chatTarget = ref('report_agent')
const showAgentDropdown = ref(false)
const selectedAgent = ref(null)
const selectedAgentIndex = ref(null)

// Report Data
const reportOutline = ref(null)
const generatedSections = ref({})
const collapsedSections = ref(new Set())
const currentSectionIndex = ref(null)
const profiles = ref([])

// Refs
const rightPanel = ref(null)
const chatMessagesComp = ref(null)

// Helper Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

const isSectionCompleted = (sectionIndex) => {
  return !!generatedSections.value[sectionIndex]
}

const simulationIdRef = computed(() => props.simulationId)

// Composables
const chat = useChat({
  simulationId: simulationIdRef,
  addLog,
  selectedAgent,
  selectedAgentIndex,
  chatTarget
})

const survey = useSurvey({
  simulationId: simulationIdRef,
  profiles,
  addLog
})

// Markdown renderer (custom, produces CSS-class-based HTML)
const renderMarkdown = (content) => {
  if (!content) return ''

  let processedContent = content.replace(/^##\s+.+\n+/, '')
  let html = processedContent.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/^#### (.+)$/gm, '<h5 class="md-h5">$1</h5>')
  html = html.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2 class="md-h2">$1</h2>')
  html = html.replace(/^> (.+)$/gm, '<blockquote class="md-quote">$1</blockquote>')

  html = html.replace(/^(\s*)- (.+)$/gm, (match, indent, text) => {
    const level = Math.floor(indent.length / 2)
    return `<li class="md-li" data-level="${level}">${text}</li>`
  })
  html = html.replace(/^(\s*)(\d+)\. (.+)$/gm, (match, indent, num, text) => {
    const level = Math.floor(indent.length / 2)
    return `<li class="md-oli" data-level="${level}">${text}</li>`
  })

  html = html.replace(/(<li class="md-li"[^>]*>.*?<\/li>\s*)+/g, '<ul class="md-ul">$&</ul>')
  html = html.replace(/(<li class="md-oli"[^>]*>.*?<\/li>\s*)+/g, '<ol class="md-ol">$&</ol>')

  html = html.replace(/<\/li>\s+<li/g, '</li><li')
  html = html.replace(/<ul class="md-ul">\s+/g, '<ul class="md-ul">')
  html = html.replace(/<ol class="md-ol">\s+/g, '<ol class="md-ol">')
  html = html.replace(/\s+<\/ul>/g, '</ul>')
  html = html.replace(/\s+<\/ol>/g, '</ol>')

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/_(.+?)_/g, '<em>$1</em>')
  html = html.replace(/^---$/gm, '<hr class="md-hr">')
  html = html.replace(/\n\n/g, '</p><p class="md-p">')
  html = html.replace(/\n/g, '<br>')
  html = '<p class="md-p">' + html + '</p>'
  html = html.replace(/<p class="md-p"><\/p>/g, '')
  html = html.replace(/<p class="md-p">(<h[2-5])/g, '$1')
  html = html.replace(/(<\/h[2-5]>)<\/p>/g, '$1')
  html = html.replace(/<p class="md-p">(<ul|<ol|<blockquote|<pre|<hr)/g, '$1')
  html = html.replace(/(<\/ul>|<\/ol>|<\/blockquote>|<\/pre>)<\/p>/g, '$1')
  html = html.replace(/<br>\s*(<ul|<ol|<blockquote)/g, '$1')
  html = html.replace(/(<\/ul>|<\/ol>|<\/blockquote>)\s*<br>/g, '$1')
  html = html.replace(/<p class="md-p">(<br>\s*)+(<ul|<ol|<blockquote|<pre|<hr)/g, '$2')
  html = html.replace(/(<br>\s*){2,}/g, '<br>')
  html = html.replace(/(<\/ol>|<\/ul>|<\/blockquote>)<br>(<p|<div)/g, '$1$2')

  const tokens = html.split(/(<ol class="md-ol">(?:<li class="md-oli"[^>]*>[\s\S]*?<\/li>)+<\/ol>)/g)
  let olCounter = 0
  let inSequence = false
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].startsWith('<ol class="md-ol">')) {
      const liCount = (tokens[i].match(/<li class="md-oli"/g) || []).length
      if (liCount === 1) {
        olCounter++
        if (olCounter > 1) {
          tokens[i] = tokens[i].replace('<ol class="md-ol">', `<ol class="md-ol" start="${olCounter}">`)
        }
        inSequence = true
      } else {
        olCounter = 0
        inSequence = false
      }
    } else if (inSequence) {
      if (/<h[2-5]/.test(tokens[i])) {
        olCounter = 0
        inSequence = false
      }
    }
  }
  html = tokens.join('')

  // XSS 방지: LLM/사용자 콘텐츠가 v-html 로 삽입되므로 위험 태그 제거 (utils/reportMarkdown.js 와 동일)
  return DOMPurify.sanitize(html, { ADD_ATTR: ['data-level', 'start'] })
}

// Section collapse toggle
const toggleSectionCollapse = (idx) => {
  if (!generatedSections.value[idx + 1]) return
  const newSet = new Set(collapsedSections.value)
  if (newSet.has(idx)) {
    newSet.delete(idx)
  } else {
    newSet.add(idx)
  }
  collapsedSections.value = newSet
}

// Tab/agent selection methods
const selectReportAgentChat = () => {
  chat.saveChatHistory()
  activeTab.value = 'chat'
  chatTarget.value = 'report_agent'
  selectedAgent.value = null
  selectedAgentIndex.value = null
  showAgentDropdown.value = false
  chat.restoreChatHistory('report_agent')
}

const selectSurveyTab = () => {
  activeTab.value = 'survey'
  selectedAgent.value = null
  selectedAgentIndex.value = null
  showAgentDropdown.value = false
}

const selectScenarioTab = () => {
  activeTab.value = 'scenario'
  selectedAgent.value = null
  selectedAgentIndex.value = null
  showAgentDropdown.value = false
}

const toggleAgentDropdown = () => {
  showAgentDropdown.value = !showAgentDropdown.value
  if (showAgentDropdown.value) {
    activeTab.value = 'chat'
    chatTarget.value = 'agent'
  }
}

const selectAgent = (agent, idx) => {
  chat.saveChatHistory()
  selectedAgent.value = agent
  selectedAgentIndex.value = idx
  chatTarget.value = 'agent'
  showAgentDropdown.value = false
  chat.restoreChatHistory(`agent_${idx}`)
  addLog(`Selected conversation target: ${agent.username}`)
}

// Load Report Data
const loadReportData = async () => {
  if (!props.reportId) return

  try {
    addLog(`Loading report data: ${props.reportId}`)
    const reportRes = await getReport(props.reportId)
    if (reportRes.success && reportRes.data) {
      await loadAgentLogs()
    }
  } catch (err) {
    addLog(`Failed to load report: ${err.message}`)
  }
}

const loadAgentLogs = async () => {
  if (!props.reportId) return

  try {
    const res = await getAgentLog(props.reportId, 0)
    if (res.success && res.data) {
      const logs = res.data.logs || []

      logs.forEach(log => {
        if (log.action === 'planning_complete' && log.details?.outline) {
          reportOutline.value = log.details.outline
        }

        if (log.action === 'section_complete' && log.section_index < 100 && log.details?.content) {
          generatedSections.value[log.section_index] = log.details.content
        }
      })

      addLog('Report data loaded successfully')
    }
  } catch (err) {
    addLog(`Failed to load report logs: ${err.message}`)
  }
}

const loadProfiles = async () => {
  if (!props.simulationId) return

  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    if (res.success && res.data) {
      profiles.value = res.data.profiles || []
      addLog(`Loaded ${profiles.value.length} simulated individuals`)
    }
  } catch (err) {
    addLog(`Failed to load simulated individuals: ${err.message}`)
  }
}

// Click outside to close dropdown
const handleClickOutside = (e) => {
  const dropdown = document.querySelector('.agent-dropdown')
  if (dropdown && !dropdown.contains(e.target)) {
    showAgentDropdown.value = false
  }
}

// Lifecycle
onMounted(() => {
  addLog('Step5 deep interaction initialized')
  loadReportData()
  loadProfiles()
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

watch(() => props.reportId, (newId) => {
  if (newId) {
    loadReportData()
  }
}, { immediate: true })

watch(() => props.simulationId, (newId) => {
  if (newId) {
    loadProfiles()
  }
}, { immediate: true })
</script>

<style scoped>
.interaction-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #F8F9FA;
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* Main Split Layout */
.main-split-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Right Panel */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #F8F9FA;
}

/* Chat Container */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

</style>
