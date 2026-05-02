<template>
  <div class="report-panel">
    <!-- Main Split Layout -->
    <div class="main-split-layout">
      <!-- LEFT PANEL: Report Style -->
      <div class="left-panel report-style" ref="leftPanel">
        <div v-if="reportOutline" class="report-content-wrapper">
          <!-- Report Header -->
          <div class="report-header-block">
            <div class="report-meta">
              <span class="report-tag">예측 리포트</span>
              <span class="report-id">ID: {{ reportId || 'REF-2024-X92' }}</span>
            </div>
            <h1 class="main-title">{{ reportOutline.title }}</h1>
            <p class="sub-title">{{ reportOutline.summary }}</p>
            <div class="header-divider"></div>
          </div>

          <!-- Sections List -->
          <div class="sections-list">
            <div
              v-for="(section, idx) in reportOutline.sections"
              :key="idx"
              class="report-section-item"
              :class="{
                'is-active': currentSectionIndex === idx + 1,
                'is-completed': isSectionCompleted(idx + 1),
                'is-pending': !isSectionCompleted(idx + 1) && currentSectionIndex !== idx + 1
              }"
            >
              <div class="section-header-row" @click="toggleSectionCollapse(idx)" :class="{ 'clickable': isSectionCompleted(idx + 1) }">
                <span class="section-number">{{ String(idx + 1).padStart(2, '0') }}</span>
                <h3 class="section-title">{{ section.title }}</h3>
                <svg
                  v-if="isSectionCompleted(idx + 1)"
                  class="collapse-icon"
                  :class="{ 'is-collapsed': collapsedSections.has(idx) }"
                  viewBox="0 0 24 24"
                  width="20"
                  height="20"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </div>

              <div class="section-body" v-show="!collapsedSections.has(idx)">
                <!-- Completed Content -->
                <div v-if="generatedSections[idx + 1]" class="generated-content" v-html="renderMarkdown(generatedSections[idx + 1])"></div>

                <!-- Loading State -->
                <div v-else-if="currentSectionIndex === idx + 1" class="loading-state">
                  <div class="loading-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <circle cx="12" cy="12" r="10" stroke-width="4" stroke="#E5E7EB"></circle>
                      <path d="M12 2a10 10 0 0 1 10 10" stroke-width="4" stroke="#4B5563" stroke-linecap="round"></path>
                    </svg>
                  </div>
                  <span class="loading-text">{{ section.title }} 생성 중...</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Waiting State -->
        <div v-if="!reportOutline" class="waiting-placeholder">
          <div class="waiting-animation">
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
          </div>
          <span class="waiting-text">리포트 에이전트 대기 중...</span>
        </div>
      </div>

      <!-- RIGHT PANEL: Workflow Timeline -->
      <div class="right-panel" ref="rightPanel">
        <WorkflowTimeline
          :agent-logs="agentLogs"
          :report-outline="reportOutline"
          :generated-sections="generatedSections"
          :current-section-index="currentSectionIndex"
          :is-complete="isComplete"
          :start-time="startTime"
          :scroll-container="rightPanel"
          @go-to-interaction="goToInteraction"
        />
      </div>
    </div>

    <!-- Bottom Console Logs -->
    <div class="console-logs">
      <div class="log-header">
        <span class="log-title">콘솔 출력</span>
        <span class="log-id">{{ reportId || 'NO_REPORT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in consoleLogs" :key="idx">
          <span class="log-msg" :class="getLogLevelClass(log)">{{ log }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { renderReportMarkdown } from '../utils/reportMarkdown'
import { useReportPolling } from '../composables/useReportPolling'
import WorkflowTimeline from './Step4/WorkflowTimeline.vue'

const router = useRouter()

const props = defineProps({
  reportId: String,
  simulationId: String,
  systemLogs: Array
})

const emit = defineEmits(['add-log', 'update-status'])

const goToInteraction = () => {
  if (props.reportId) {
    router.push({ name: 'Interaction', params: { reportId: props.reportId } })
  }
}

const leftPanel = ref(null)
const rightPanel = ref(null)
const logContent = ref(null)

const collapsedSections = ref(new Set())

const {
  agentLogs,
  consoleLogs,
  reportOutline,
  currentSectionIndex,
  generatedSections,
  isComplete,
  startTime,
  startPolling,
  stopPolling,
  resetState
} = useReportPolling({
  onComplete: () => emit('update-status', 'completed'),
  rightPanelRef: rightPanel,
  logContentRef: logContent
})

const renderMarkdown = (content) => renderReportMarkdown(content)

const toggleSectionCollapse = (idx) => {
  if (!generatedSections.value[idx + 1]) return
  const newSet = new Set(collapsedSections.value)
  if (newSet.has(idx)) { newSet.delete(idx) } else { newSet.add(idx) }
  collapsedSections.value = newSet
}

const isSectionCompleted = (sectionIndex) => !!generatedSections.value[sectionIndex]

const getLogLevelClass = (log) => {
  if (log.includes('ERROR') || log.includes('Error')) return 'error'
  if (log.includes('WARNING') || log.includes('Warning')) return 'warning'
  return ''
}

const addLog = (msg) => emit('add-log', msg)

onMounted(() => {
  if (props.reportId) {
    addLog(`Report Agent initialized: ${props.reportId}`)
    startPolling(props.reportId)
  }
})

onBeforeUnmount(() => stopPolling())
onUnmounted(() => stopPolling())

watch(() => props.reportId, (newId) => {
  if (newId) {
    resetState()
    collapsedSections.value = new Set()
    startPolling(newId)
  }
}, { immediate: true })
</script>


<style scoped src="./Step4Report.styles.css"></style>
