<template>
  <div class="panel-header" :class="`panel-header--${activeStep.status}`" v-if="!isComplete">
    <span class="header-dot" v-if="activeStep.status === 'active'"></span>
    <span class="header-index mono">{{ activeStep.noLabel }}</span>
    <span class="header-title">{{ activeStep.title }}</span>
    <span class="header-meta mono" v-if="activeStep.meta">{{ activeStep.meta }}</span>
  </div>

  <!-- Workflow Overview -->
  <div class="workflow-overview" v-if="agentLogs.length > 0 || reportOutline">
    <div class="workflow-metrics">
      <div class="metric">
        <span class="metric-label">섹션</span>
        <span class="metric-value mono">{{ completedSections }}/{{ totalSections }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">경과 시간</span>
        <span class="metric-value mono">{{ formatElapsedTime }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">도구</span>
        <span class="metric-value mono">{{ totalToolCalls }}</span>
      </div>
      <div class="metric metric-right">
        <span class="metric-pill" :class="`pill--${statusClass}`">{{ statusText }}</span>
      </div>
    </div>

    <div class="workflow-steps" v-if="workflowSteps.length > 0">
      <div
        v-for="(step, sidx) in workflowSteps"
        :key="step.key"
        class="wf-step"
        :class="`wf-step--${step.status}`"
      >
        <div class="wf-step-connector">
          <div class="wf-step-dot"></div>
          <div class="wf-step-line" v-if="sidx < workflowSteps.length - 1"></div>
        </div>

        <div class="wf-step-content">
          <div class="wf-step-title-row">
            <span class="wf-step-index mono">{{ step.noLabel }}</span>
            <span class="wf-step-title">{{ step.title }}</span>
            <span class="wf-step-meta mono" v-if="step.meta">{{ step.meta }}</span>
          </div>
        </div>
      </div>
    </div>

    <button v-if="isComplete" class="next-step-btn" @click="$emit('goToInteraction')">
      <span>심층 상호작용으로 이동</span>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="5" y1="12" x2="19" y2="12"></line>
        <polyline points="12 5 19 12 12 19"></polyline>
      </svg>
    </button>

    <div class="workflow-divider"></div>
  </div>

  <div class="workflow-timeline">
    <TransitionGroup name="timeline-item">
      <div
        v-for="(log, idx) in displayLogs"
        :key="log.timestamp + '-' + idx"
        class="timeline-item"
        :class="getTimelineItemClass(log, idx, displayLogs.length)"
      >
        <div class="timeline-connector">
          <div class="connector-dot" :class="getConnectorClass(log, idx, displayLogs.length)"></div>
          <div class="connector-line" v-if="idx < displayLogs.length - 1"></div>
        </div>

        <div class="timeline-content">
          <div class="timeline-header">
            <span class="action-label">{{ getActionLabel(log.action) }}</span>
            <span class="action-time">{{ formatTime(log.timestamp) }}</span>
          </div>

          <div class="timeline-body" :class="{ 'collapsed': isLogCollapsed(log) }" @click="toggleLogExpand(log)">

            <template v-if="log.action === 'report_start'">
              <div class="info-row">
                <span class="info-key">시뮬레이션</span>
                <span class="info-val mono">{{ log.details?.simulation_id }}</span>
              </div>
              <div class="info-row" v-if="log.details?.simulation_requirement">
                <span class="info-key">요청</span>
                <span class="info-val">{{ log.details.simulation_requirement }}</span>
              </div>
            </template>

            <template v-if="log.action === 'planning_start'">
              <div class="status-message planning">{{ log.details?.message }}</div>
            </template>
            <template v-if="log.action === 'planning_complete'">
              <div class="status-message success">{{ log.details?.message }}</div>
              <div class="outline-badge" v-if="log.details?.outline">
                {{ log.details.outline.sections?.length || 0 }} sections planned
              </div>
            </template>

            <template v-if="log.action === 'section_start'">
              <div class="section-tag">
                <span class="tag-num">#{{ log.section_index }}</span>
                <span class="tag-title">{{ log.section_title }}</span>
              </div>
            </template>

            <template v-if="log.action === 'section_content'">
              <div class="section-tag content-ready">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 20h9"></path>
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                </svg>
                <span class="tag-title">{{ log.section_title }}</span>
              </div>
            </template>

            <template v-if="log.action === 'section_complete'">
              <div class="section-tag completed">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span class="tag-title">{{ log.section_title }}</span>
              </div>
            </template>

            <template v-if="log.action === 'tool_call'">
              <div class="tool-badge" :class="'tool-' + getToolColor(log.details?.tool_name)">
                <svg v-if="getToolIcon(log.details?.tool_name) === 'lightbulb'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.5V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.5A7 7 0 0 0 12 2z"></path>
                </svg>
                <svg v-else-if="getToolIcon(log.details?.tool_name) === 'globe'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                </svg>
                <svg v-else-if="getToolIcon(log.details?.tool_name) === 'users'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="9" cy="7" r="4"></circle>
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                <svg v-else-if="getToolIcon(log.details?.tool_name) === 'zap'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                </svg>
                <svg v-else-if="getToolIcon(log.details?.tool_name) === 'chart'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="20" x2="18" y2="10"></line>
                  <line x1="12" y1="20" x2="12" y2="4"></line>
                  <line x1="6" y1="20" x2="6" y2="14"></line>
                </svg>
                <svg v-else-if="getToolIcon(log.details?.tool_name) === 'database'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
                </svg>
                <svg v-else class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                </svg>
                {{ getToolDisplayName(log.details?.tool_name) }}
              </div>
              <div v-if="log.details?.parameters && expandedLogs.has(log.timestamp)" class="tool-params">
                <pre>{{ formatParams(log.details.parameters) }}</pre>
              </div>
            </template>

            <template v-if="log.action === 'tool_result'">
              <div class="result-wrapper" :class="'result-' + log.details?.tool_name">
                <div v-if="!['interview_agents', 'insight_forge', 'panorama_search', 'quick_search'].includes(log.details?.tool_name)" class="result-meta">
                  <span class="result-tool">{{ getToolDisplayName(log.details?.tool_name) }}</span>
                  <span class="result-size">{{ formatResultSize(log.details?.result_length) }}</span>
                </div>

                <div v-if="!showRawResult[log.timestamp]" class="result-structured">
                  <template v-if="log.details?.tool_name === 'interview_agents'">
                    <InterviewDisplay :result="parseInterview(log.details.result)" :result-length="log.details?.result_length" />
                  </template>
                  <template v-else-if="log.details?.tool_name === 'insight_forge'">
                    <InsightDisplay :result="parseInsightForge(log.details.result)" :result-length="log.details?.result_length" />
                  </template>
                  <template v-else-if="log.details?.tool_name === 'panorama_search'">
                    <PanoramaDisplay :result="parsePanorama(log.details.result)" :result-length="log.details?.result_length" />
                  </template>
                  <template v-else-if="log.details?.tool_name === 'quick_search'">
                    <QuickSearchDisplay :result="parseQuickSearch(log.details.result)" :result-length="log.details?.result_length" />
                  </template>
                  <template v-else>
                    <pre class="raw-preview">{{ truncateText(log.details?.result, 300) }}</pre>
                  </template>
                </div>

                <div v-else class="result-raw">
                  <pre>{{ log.details?.result }}</pre>
                </div>
              </div>
            </template>

            <template v-if="log.action === 'llm_response'">
              <div class="llm-meta">
                <span class="meta-tag">Iteration {{ log.details?.iteration }}</span>
                <span class="meta-tag" :class="{ active: log.details?.has_tool_calls }">
                  Tools: {{ log.details?.has_tool_calls ? 'Yes' : 'No' }}
                </span>
                <span class="meta-tag" :class="{ active: log.details?.has_final_answer, 'final-answer': log.details?.has_final_answer }">
                  Final: {{ log.details?.has_final_answer ? 'Yes' : 'No' }}
                </span>
              </div>
              <div v-if="log.details?.has_final_answer" class="final-answer-hint">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span>Section "{{ log.section_title }}" content generated</span>
              </div>
              <div v-if="expandedLogs.has(log.timestamp) && log.details?.response" class="llm-content">
                <pre>{{ log.details.response }}</pre>
              </div>
            </template>

            <template v-if="log.action === 'report_complete'">
              <div class="complete-banner">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                  <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <span>리포트 생성 완료</span>
              </div>
            </template>
          </div>

          <div class="timeline-footer" v-if="log.elapsed_seconds || (log.action === 'tool_call' && log.details?.parameters) || log.action === 'tool_result' || (log.action === 'llm_response' && log.details?.response)">
            <span v-if="log.elapsed_seconds" class="elapsed-badge">+{{ log.elapsed_seconds.toFixed(1) }}s</span>
            <span v-else class="elapsed-placeholder"></span>

            <div class="footer-actions">
              <button v-if="log.action === 'tool_call' && log.details?.parameters" class="action-btn" @click.stop="toggleLogExpand(log)">
                {{ expandedLogs.has(log.timestamp) ? 'Hide Params' : 'Show Params' }}
              </button>
              <button v-if="log.action === 'tool_result'" class="action-btn" @click.stop="toggleRawResult(log.timestamp, $event)">
                {{ showRawResult[log.timestamp] ? 'Structured View' : 'Raw Output' }}
              </button>
              <button v-if="log.action === 'llm_response' && log.details?.response" class="action-btn" @click.stop="toggleLogExpand(log)">
                {{ expandedLogs.has(log.timestamp) ? 'Hide Response' : 'Show Response' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </TransitionGroup>

    <div v-if="agentLogs.length === 0 && !isComplete" class="workflow-empty">
      <div class="empty-pulse"></div>
      <span>Waiting for agent activity...</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, nextTick } from 'vue'
import {
  getToolDisplayName, getToolColor, getToolIcon,
  parseInsightForge, parsePanorama, parseQuickSearch, parseInterview
} from '../../composables/useReportParser'
import InsightDisplay from '../report/InsightDisplay.vue'
import PanoramaDisplay from '../report/PanoramaDisplay.vue'
import InterviewDisplay from '../report/InterviewDisplay.vue'
import QuickSearchDisplay from '../report/QuickSearchDisplay.vue'

const props = defineProps({
  agentLogs: { type: Array, required: true },
  reportOutline: { type: Object, default: null },
  generatedSections: { type: Object, required: true },
  currentSectionIndex: { type: Number, default: 0 },
  isComplete: { type: Boolean, default: false },
  startTime: { type: [Number, Date], default: null },
  scrollContainer: { type: Object, default: null },
})

defineEmits(['goToInteraction'])

const expandedLogs = ref(new Set())
const showRawResult = reactive({})

watch(() => props.reportOutline, (val, prev) => {
  if (val && !prev) {
    expandedLogs.value = new Set()
    Object.keys(showRawResult).forEach(k => delete showRawResult[k])
  }
})

const toggleLogExpand = (log) => {
  const newSet = new Set(expandedLogs.value)
  if (newSet.has(log.timestamp)) { newSet.delete(log.timestamp) } else { newSet.add(log.timestamp) }
  expandedLogs.value = newSet
}

const isLogCollapsed = (log) => {
  if (['tool_call', 'tool_result', 'llm_response'].includes(log.action)) {
    return !expandedLogs.value.has(log.timestamp)
  }
  return false
}

const toggleRawResult = (timestamp, event) => {
  const button = event?.target
  const buttonRect = button?.getBoundingClientRect()
  const buttonTopBeforeToggle = buttonRect?.top

  showRawResult[timestamp] = !showRawResult[timestamp]

  const container = props.scrollContainer?.value || props.scrollContainer
  if (button && buttonTopBeforeToggle !== undefined && container) {
    nextTick(() => {
      const newButtonRect = button.getBoundingClientRect()
      const buttonTopAfterToggle = newButtonRect.top
      const scrollDelta = buttonTopAfterToggle - buttonTopBeforeToggle
      container.scrollTop += scrollDelta
    })
  }
}

const statusClass = computed(() => {
  if (props.isComplete) return 'completed'
  if (props.agentLogs.length > 0) return 'processing'
  return 'pending'
})

const statusText = computed(() => {
  if (props.isComplete) return 'Completed'
  if (props.agentLogs.length > 0) return 'Generating...'
  return 'Waiting'
})

const totalSections = computed(() => props.reportOutline?.sections?.length || 0)
const completedSections = computed(() => Object.keys(props.generatedSections).length)
const totalToolCalls = computed(() => props.agentLogs.filter(l => l.action === 'tool_call').length)

const formatElapsedTime = computed(() => {
  if (!props.startTime) return '0s'
  const lastLog = props.agentLogs[props.agentLogs.length - 1]
  const elapsed = lastLog?.elapsed_seconds || 0
  if (elapsed < 60) return `${Math.round(elapsed)}s`
  const mins = Math.floor(elapsed / 60)
  const secs = Math.round(elapsed % 60)
  return `${mins}m ${secs}s`
})

const displayLogs = computed(() => props.agentLogs)

const activeSectionIndex = computed(() => {
  if (props.isComplete) return null
  if (props.currentSectionIndex) return props.currentSectionIndex
  if (totalSections.value > 0 && completedSections.value < totalSections.value) return completedSections.value + 1
  return null
})

const isPlanningDone = computed(() =>
  !!props.reportOutline?.sections?.length || props.agentLogs.some(l => l.action === 'planning_complete')
)

const isPlanningStarted = computed(() =>
  props.agentLogs.some(l => l.action === 'planning_start' || l.action === 'report_start')
)

const isFinalizing = computed(() =>
  !props.isComplete && isPlanningDone.value && totalSections.value > 0 && completedSections.value >= totalSections.value
)

const workflowSteps = computed(() => {
  const steps = []
  const planningStatus = isPlanningDone.value ? 'done' : (isPlanningStarted.value ? 'active' : 'todo')
  steps.push({
    key: 'planning',
    noLabel: 'PL',
    title: 'Planning / Outline',
    status: planningStatus,
    meta: planningStatus === 'active' ? 'IN PROGRESS' : ''
  })

  const sections = props.reportOutline?.sections || []
  sections.forEach((section, i) => {
    const idx = i + 1
    const status = (props.isComplete || !!props.generatedSections[idx])
      ? 'done'
      : (activeSectionIndex.value === idx ? 'active' : 'todo')
    steps.push({
      key: `section-${idx}`,
      noLabel: String(idx).padStart(2, '0'),
      title: section.title,
      status,
      meta: status === 'active' ? 'IN PROGRESS' : ''
    })
  })

  const completeStatus = props.isComplete ? 'done' : (isFinalizing.value ? 'active' : 'todo')
  steps.push({
    key: 'complete',
    noLabel: 'OK',
    title: 'Complete',
    status: completeStatus,
    meta: completeStatus === 'active' ? 'FINALIZING' : ''
  })

  return steps
})

const activeStep = computed(() => {
  const steps = workflowSteps.value
  const active = steps.find(s => s.status === 'active')
  if (active) return active
  const doneSteps = steps.filter(s => s.status === 'done')
  if (doneSteps.length > 0) return doneSteps[doneSteps.length - 1]
  return steps[0] || { noLabel: '--', title: 'Waiting to Start', status: 'todo', meta: '' }
})

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return ''
  }
}

const formatParams = (params) => {
  if (!params) return ''
  try {
    return JSON.stringify(params, null, 2)
  } catch {
    return String(params)
  }
}

const formatResultSize = (length) => {
  if (!length) return ''
  if (length < 1000) return `${length} chars`
  return `${(length / 1000).toFixed(1)}k chars`
}

const truncateText = (text, maxLen) => {
  if (!text) return ''
  if (text.length <= maxLen) return text
  return text.substring(0, maxLen) + '...'
}

const getTimelineItemClass = (log, idx, total) => {
  const isLatest = idx === total - 1 && !props.isComplete
  const isMilestone = log.action === 'section_complete' || log.action === 'report_complete'
  return {
    'node--active': isLatest,
    'node--done': !isLatest && isMilestone,
    'node--muted': !isLatest && !isMilestone,
    'node--tool': log.action === 'tool_call' || log.action === 'tool_result'
  }
}

const getConnectorClass = (log, idx, total) => {
  const isLatest = idx === total - 1 && !props.isComplete
  if (isLatest) return 'dot-active'
  if (log.action === 'section_complete' || log.action === 'report_complete') return 'dot-done'
  return 'dot-muted'
}

const getActionLabel = (action) => {
  const labels = {
    'report_start': 'Report Started',
    'planning_start': 'Planning',
    'planning_complete': 'Plan Complete',
    'section_start': 'Section Start',
    'section_content': 'Content Ready',
    'section_complete': 'Section Done',
    'tool_call': 'Tool Call',
    'tool_result': 'Tool Result',
    'llm_response': 'LLM Response',
    'report_complete': 'Complete'
  }
  return labels[action] || action
}
</script>

<style scoped src="../Step4Report.styles.css"></style>
