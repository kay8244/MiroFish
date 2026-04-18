import { ref, nextTick } from 'vue'
import { chatWithReport } from '../api/report'
import { interviewAgents } from '../api/simulation'
import { debounce } from '../utils/api-helpers'

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

    const res = await interviewAgents({
      simulation_id: simulationId.value,
      interviews: [{
        agent_id: selectedAgentIndex.value,
        prompt: prompt
      }]
    })

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
