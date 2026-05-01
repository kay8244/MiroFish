import { ref, nextTick } from 'vue'
import { getProject, getTaskStatus, getGraphData } from '../api/graph'

export function useGraphPolling({
  currentProjectId,
  projectData,
  graphData,
  currentPhase,
  error,
  buildProgress,
  graphLoading,
  onGraphUpdate,
}) {
  let pollTimer = null
  let graphPollTimer = null

  const startGraphPolling = () => {
    fetchGraphData()
    graphPollTimer = setInterval(async () => {
      await fetchGraphData()
    }, 10000)
  }

  const stopGraphPolling = () => {
    if (graphPollTimer) {
      clearInterval(graphPollTimer)
      graphPollTimer = null
    }
  }

  const refreshGraph = async () => {
    graphLoading.value = true
    await fetchGraphData()
    graphLoading.value = false
  }

  const fetchGraphData = async () => {
    try {
      const projectResponse = await getProject(currentProjectId.value)

      if (projectResponse.success && projectResponse.data.graph_id) {
        const graphId = projectResponse.data.graph_id
        projectData.value = projectResponse.data

        const graphResponse = await getGraphData(graphId)

        if (graphResponse.success && graphResponse.data) {
          const newData = graphResponse.data
          const newNodeCount = newData.node_count || newData.nodes?.length || 0
          const oldNodeCount = graphData.value?.node_count || graphData.value?.nodes?.length || 0

          console.log('Fetching graph data, nodes:', newNodeCount, 'edges:', newData.edge_count || newData.edges?.length || 0)

          if (newNodeCount !== oldNodeCount || !graphData.value) {
            graphData.value = newData
            await nextTick()
            onGraphUpdate?.()
          }
        }
      }
    } catch (err) {
      console.log('Graph data fetch:', err.message || 'not ready')
    }
  }

  const startPollingTask = (taskId) => {
    pollTaskStatus(taskId)
    pollTimer = setInterval(() => {
      pollTaskStatus(taskId)
    }, 2000)
  }

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const pollTaskStatus = async (taskId) => {
    try {
      const response = await getTaskStatus(taskId)

      if (response.success) {
        const task = response.data

        buildProgress.value = {
          progress: task.progress || 0,
          message: task.message || 'Processing...'
        }

        console.log('Task status:', task.status, 'Progress:', task.progress)

        if (task.status === 'completed') {
          console.log('✅ Graph build complete, loading full data...')

          stopPolling()
          stopGraphPolling()
          currentPhase.value = 2

          buildProgress.value = {
            progress: 100,
            message: 'Build complete, loading graph...'
          }

          const projectResponse = await getProject(currentProjectId.value)
          if (projectResponse.success) {
            projectData.value = projectResponse.data

            if (projectResponse.data.graph_id) {
              console.log('📊 Loading full graph:', projectResponse.data.graph_id)
              await loadGraph(projectResponse.data.graph_id)
              console.log('✅ Graph loaded successfully')
            }
          }

          buildProgress.value = null
        } else if (task.status === 'failed') {
          stopPolling()
          stopGraphPolling()
          error.value = 'Graph build failed: ' + (task.error || 'Unknown error')
          buildProgress.value = null
        }
      }
    } catch (err) {
      console.error('Poll task error:', err)
    }
  }

  const loadGraph = async (graphId) => {
    try {
      graphLoading.value = true
      const response = await getGraphData(graphId)

      if (response.success) {
        graphData.value = response.data
        await nextTick()
        onGraphUpdate?.()
      }
    } catch (err) {
      console.error('Load graph error:', err)
    } finally {
      graphLoading.value = false
    }
  }

  return {
    startGraphPolling,
    stopGraphPolling,
    refreshGraph,
    startPollingTask,
    stopPolling,
    loadGraph,
  }
}
