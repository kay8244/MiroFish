/**
 * Composable for report agent log polling.
 * Manages periodic fetching of agent logs and console logs.
 */
import { ref, reactive, nextTick } from 'vue'
import { getAgentLog, getConsoleLog } from '../api/report'

export function useReportPolling({ onLogProcessed, onComplete, rightPanelRef, logContentRef }) {
  const agentLogs = ref([])
  const consoleLogs = ref([])
  const agentLogLine = ref(0)
  const consoleLogLine = ref(0)
  const reportOutline = ref(null)
  const currentSectionIndex = ref(null)
  const generatedSections = ref({})
  const isComplete = ref(false)
  const startTime = ref(null)
  const expandedContent = ref(new Set())

  let agentLogTimer = null
  let consoleLogTimer = null
  let isFetchingAgentLog = false
  let isFetchingConsoleLog = false

  const fetchAgentLog = async (reportId) => {
    if (!reportId) return
    if (isFetchingAgentLog) return
    isFetchingAgentLog = true

    try {
      const res = await getAgentLog(reportId, agentLogLine.value)

      if (res.success && res.data) {
        const newLogs = res.data.logs || []

        if (newLogs.length > 0) {
          newLogs.forEach(log => {
            agentLogs.value.push(log)

            if (log.action === 'planning_complete' && log.details?.outline) {
              reportOutline.value = log.details.outline
            }

            if (log.action === 'section_start') {
              currentSectionIndex.value = log.section_index
            }

            if (log.action === 'section_complete') {
              if (log.details?.content) {
                generatedSections.value[log.section_index] = log.details.content
                expandedContent.value.add(log.section_index - 1)
                currentSectionIndex.value = null
              }
            }

            if (log.action === 'report_complete') {
              isComplete.value = true
              currentSectionIndex.value = null
              onComplete?.()
              stopPolling()
            }

            if (log.action === 'report_start') {
              startTime.value = new Date(log.timestamp)
            }
          })

          agentLogLine.value = res.data.from_line + newLogs.length

          nextTick(() => {
            const panel = rightPanelRef?.value
            if (panel) {
              if (isComplete.value) {
                panel.scrollTop = 0
              } else {
                panel.scrollTop = panel.scrollHeight
              }
            }
          })
        }
      }
    } catch (err) {
      console.warn('Failed to fetch agent log:', err)
    } finally {
      isFetchingAgentLog = false
    }
  }

  const fetchConsoleLog = async (reportId) => {
    if (!reportId) return
    if (isFetchingConsoleLog) return
    isFetchingConsoleLog = true

    try {
      const res = await getConsoleLog(reportId, consoleLogLine.value)

      if (res.success && res.data) {
        const newLogs = res.data.logs || []

        if (newLogs.length > 0) {
          consoleLogs.value.push(...newLogs)
          consoleLogLine.value = res.data.from_line + newLogs.length

          nextTick(() => {
            const content = logContentRef?.value
            if (content) {
              content.scrollTop = content.scrollHeight
            }
          })
        }
      }
    } catch (err) {
      console.warn('Failed to fetch console log:', err)
    } finally {
      isFetchingConsoleLog = false
    }
  }

  const startPolling = (reportId) => {
    if (agentLogTimer || consoleLogTimer) return

    fetchAgentLog(reportId)
    fetchConsoleLog(reportId)

    agentLogTimer = setInterval(() => fetchAgentLog(reportId), 2000)
    consoleLogTimer = setInterval(() => fetchConsoleLog(reportId), 1500)
  }

  const stopPolling = () => {
    if (agentLogTimer) {
      clearInterval(agentLogTimer)
      agentLogTimer = null
    }
    if (consoleLogTimer) {
      clearInterval(consoleLogTimer)
      consoleLogTimer = null
    }
  }

  const resetState = () => {
    agentLogs.value = []
    consoleLogs.value = []
    agentLogLine.value = 0
    consoleLogLine.value = 0
    reportOutline.value = null
    currentSectionIndex.value = null
    generatedSections.value = {}
    expandedContent.value = new Set()
    isComplete.value = false
    startTime.value = null
  }

  return {
    agentLogs,
    consoleLogs,
    reportOutline,
    currentSectionIndex,
    generatedSections,
    isComplete,
    startTime,
    expandedContent,
    startPolling,
    stopPolling,
    resetState
  }
}
