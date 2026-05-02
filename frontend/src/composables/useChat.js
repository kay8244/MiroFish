import { ref, nextTick } from 'vue'
import { chatWithReport } from '../api/report'
import { interviewAgents, startSimulation, getRunStatus } from '../api/simulation'
import { debounce } from '../utils/api-helpers'

// Detect backend "env not alive" error on stopped/completed sims.
// Matches the Korean message returned by /api/simulation/interview/batch.
const isEnvNotAliveError = (err) => {
  const msg = err?.response?.data?.error || err?.message || ''
  return /시뮬레이션 환경이 실행 중이 아니거나|환경.*종료|env.*not.*alive/i.test(msg)
}

// DESTRUCTIVE: force-restart the sim — backend cleans prior run state,
// action logs, and simulation DB artifacts before restart, and clamps
// rounds to 6. Callers MUST obtain explicit user consent before invoking.
const reviveEnv = async (simId, addLog) => {
  addLog(`시뮬레이션 환경 재시작 중... (sim=${simId})`)
  await startSimulation({ simulation_id: simId, max_rounds: 6, force: true })
  const deadline = Date.now() + 90_000  // 90s cap — 6 rounds normally completes in <30s
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000))
    let st
    try {
      const res = await getRunStatus(simId)
      st = res?.data?.runner_status
    } catch (e) {
      // transient polling error — keep polling until deadline
      continue
    }
    if (st === 'completed') {
      addLog('환경 재시작 완료 — 재질문 시도')
      return
    }
    if (st === 'failed') throw new Error('환경 재시작 실패')
  }
  throw new Error('환경 재시작 타임아웃')
}

/**
 * Chat state and logic composable for Step5 interaction.
 * @param {Object} params
 * @param {import('vue').Ref<string>} params.simulationId
 * @param {Function} params.addLog
 * @param {import('vue').Ref<Object|null>} params.selectedAgent
 * @param {import('vue').Ref<number|null>} params.selectedAgentIndex
 * @param {import('vue').Ref<string>} params.chatTarget
 */
export function useChat({ simulationId, addLog, selectedAgent, selectedAgentIndex, chatTarget }) {
  const chatInput = ref('')
  const chatHistory = ref([])
  const chatHistoryCache = ref({})
  const isSending = ref(false)
  const chatMessagesRef = ref(null)
  const chatInputRef = ref(null)

  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    try {
      return new Date(timestamp).toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return ''
    }
  }

  const scrollToBottom = () => {
    nextTick(() => {
      if (chatMessagesRef.value) {
        chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
      }
    })
  }

  const saveChatHistory = () => {
    if (chatHistory.value.length === 0) return

    if (chatTarget.value === 'report_agent') {
      chatHistoryCache.value['report_agent'] = [...chatHistory.value]
    } else if (selectedAgentIndex.value !== null) {
      chatHistoryCache.value[`agent_${selectedAgentIndex.value}`] = [...chatHistory.value]
    }
  }

  const restoreChatHistory = (key) => {
    chatHistory.value = chatHistoryCache.value[key] || []
  }

  const sendToReportAgent = async (message) => {
    addLog(`Sending to Report Agent: ${message.substring(0, 50)}...`)

    const historyForApi = chatHistory.value
      .filter(msg => msg.role !== 'user' || msg.content !== message)
      .slice(-10)
      .map(msg => ({
        role: msg.role,
        content: msg.content
      }))

    const res = await chatWithReport({
      simulation_id: simulationId.value,
      message: message,
      chat_history: historyForApi
    })

    if (res.success && res.data) {
      chatHistory.value.push({
        role: 'assistant',
        content: res.data.response || res.data.answer || 'No response',
        timestamp: new Date().toISOString()
      })
      addLog('Report Agent has replied')
    } else {
      throw new Error(res.error || 'Request failed')
    }
  }

  const sendToAgent = async (message) => {
    if (!selectedAgent.value || selectedAgentIndex.value === null) {
      throw new Error('Please select a simulated individual first')
    }

    addLog(`Sending to ${selectedAgent.value.username}: ${message.substring(0, 50)}...`)

    let prompt = message
    if (chatHistory.value.length > 1) {
      const historyContext = chatHistory.value
        .filter(msg => msg.content !== message)
        .slice(-6)
        .map(msg => `${msg.role === 'user' ? 'Questioner' : 'You'}: ${msg.content}`)
        .join('\n')
      prompt = `Here is our previous conversation:\n${historyContext}\n\nMy new question is: ${message}`
    }

    const interviewPayload = {
      simulation_id: simulationId.value,
      interviews: [{
        agent_id: selectedAgentIndex.value,
        prompt: prompt
      }]
    }
    let res
    try {
      res = await interviewAgents(interviewPayload)
    } catch (err) {
      if (isEnvNotAliveError(err)) {
        // Explicit user consent required: force-restart is destructive —
        // prior run state, action logs, and simulation DB artifacts are
        // cleared, and rounds are clamped to 6. Silently auto-restarting
        // would mutate the world state existing reports were based on.
        const ok = typeof window !== 'undefined' && window.confirm
          ? window.confirm(
              '시뮬레이션 환경이 종료되었습니다. 재시작하시겠습니까?\n\n' +
              '⚠️ 경고: 재시작은 파괴적입니다.\n' +
              '- 기존 run 상태, 액션 로그, 시뮬레이션 DB 아티팩트가 초기화됩니다\n' +
              '- 이전 리포트의 근거 데이터가 변경될 수 있습니다\n' +
              '- 라운드 수는 6으로 축소됩니다'
            )
          : false
        if (!ok) {
          addLog('재시작 취소됨 — 환경이 종료된 상태로 유지')
          throw err
        }
        await reviveEnv(simulationId.value, addLog)
        res = await interviewAgents(interviewPayload)
      } else {
        throw err
      }
    }

    if (res.success && res.data) {
      const resultData = res.data.result || res.data
      const resultsDict = resultData.results || resultData

      let responseContent = null
      const agentId = selectedAgentIndex.value

      if (typeof resultsDict === 'object' && !Array.isArray(resultsDict)) {
        const redditKey = `reddit_${agentId}`
        const twitterKey = `twitter_${agentId}`
        const agentResult = resultsDict[redditKey] || resultsDict[twitterKey] || Object.values(resultsDict)[0]
        if (agentResult) {
          responseContent = agentResult.response || agentResult.answer
        }
      } else if (Array.isArray(resultsDict) && resultsDict.length > 0) {
        responseContent = resultsDict[0].response || resultsDict[0].answer
      }

      if (responseContent) {
        chatHistory.value.push({
          role: 'assistant',
          content: responseContent,
          timestamp: new Date().toISOString()
        })
        addLog(`${selectedAgent.value.username} has replied`)
      } else {
        throw new Error('No response data')
      }
    } else {
      throw new Error(res.error || 'Request failed')
    }
  }

  const sendMessage = async () => {
    if (!chatInput.value.trim() || isSending.value) return

    const message = chatInput.value.trim()
    chatInput.value = ''

    chatHistory.value.push({
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    })

    scrollToBottom()
    isSending.value = true

    try {
      if (chatTarget.value === 'report_agent') {
        await sendToReportAgent(message)
      } else {
        await sendToAgent(message)
      }
    } catch (err) {
      addLog(`Send failed: ${err.message}`)
      chatHistory.value.push({
        role: 'assistant',
        content: `Sorry, an error occurred: ${err.message}`,
        timestamp: new Date().toISOString()
      })
    } finally {
      isSending.value = false
      scrollToBottom()
      saveChatHistory()
    }
  }

  const debouncedSendMessage = debounce(async () => {
    await sendMessage()
  }, 300)

  return {
    chatInput,
    chatHistory,
    chatHistoryCache,
    isSending,
    chatMessagesRef,
    chatInputRef,
    formatTime,
    scrollToBottom,
    saveChatHistory,
    restoreChatHistory,
    sendMessage,
    debouncedSendMessage
  }
}
