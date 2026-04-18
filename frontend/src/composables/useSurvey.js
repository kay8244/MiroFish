import { ref } from 'vue'
import { interviewAgents } from '../api/simulation'

/**
 * Survey state and logic composable for Step5 interaction.
 * @param {Object} params
 * @param {import('vue').Ref<string>} params.simulationId
 * @param {import('vue').Ref<Array>} params.profiles
 * @param {Function} params.addLog
 */
export function useSurvey({ simulationId, profiles, addLog }) {
  const selectedAgents = ref(new Set())
  const surveyQuestion = ref('')
  const surveyResults = ref([])
  const isSurveying = ref(false)

  const toggleAgentSelection = (idx) => {
    const newSet = new Set(selectedAgents.value)
    if (newSet.has(idx)) {
      newSet.delete(idx)
    } else {
      newSet.add(idx)
    }
    selectedAgents.value = newSet
  }

  const selectAllAgents = () => {
    const newSet = new Set()
    profiles.value.forEach((_, idx) => newSet.add(idx))
    selectedAgents.value = newSet
  }

  const clearAgentSelection = () => {
    selectedAgents.value = new Set()
  }

  const submitSurvey = async () => {
    if (selectedAgents.value.size === 0 || !surveyQuestion.value.trim()) return

    isSurveying.value = true
    addLog(`Sending survey to ${selectedAgents.value.size} targets...`)

    try {
      const interviews = Array.from(selectedAgents.value).map(idx => ({
        agent_id: idx,
        prompt: surveyQuestion.value.trim()
      }))

      const res = await interviewAgents({
        simulation_id: simulationId.value,
        interviews: interviews
      })

      if (res.success && res.data) {
        const resultData = res.data.result || res.data
        const resultsDict = resultData.results || resultData

        const surveyResultsList = []

        for (const interview of interviews) {
          const agentIdx = interview.agent_id
          const agent = profiles.value[agentIdx]

          let responseContent = 'No response'

          if (typeof resultsDict === 'object' && !Array.isArray(resultsDict)) {
            const redditKey = `reddit_${agentIdx}`
            const twitterKey = `twitter_${agentIdx}`
            const agentResult = resultsDict[redditKey] || resultsDict[twitterKey]
            if (agentResult) {
              responseContent = agentResult.response || agentResult.answer || 'No response'
            }
          } else if (Array.isArray(resultsDict)) {
            const matchedResult = resultsDict.find(r => r.agent_id === agentIdx)
            if (matchedResult) {
              responseContent = matchedResult.response || matchedResult.answer || 'No response'
            }
          }

          surveyResultsList.push({
            agent_id: agentIdx,
            agent_name: agent?.username || `Agent ${agentIdx}`,
            profession: agent?.profession,
            question: surveyQuestion.value.trim(),
            answer: responseContent
          })
        }

        surveyResults.value = surveyResultsList
        addLog(`Received ${surveyResults.value.length} responses`)
      } else {
        throw new Error(res.error || 'Request failed')
      }
    } catch (err) {
      addLog(`Survey send failed: ${err.message}`)
    } finally {
      isSurveying.value = false
    }
  }

  return {
    selectedAgents,
    surveyQuestion,
    surveyResults,
    isSurveying,
    toggleAgentSelection,
    selectAllAgents,
    clearAgentSelection,
    submitSurvey
  }
}
