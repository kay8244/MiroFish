<template>
  <div class="process-page">
    <!-- Top navbar -->
    <nav class="navbar">
      <div class="nav-brand" @click="goHome">MIROFISH</div>
      
      <!-- Center step indicator -->
      <div class="nav-center">
        <div class="step-badge">STEP 01</div>
        <div class="step-name">지식 그래프 구축</div>
      </div>

      <div class="nav-status">
        <span class="status-dot" :class="statusClass"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
    </nav>

    <!-- Main content area -->
    <div class="main-content">
      <!-- Left: Real-time graph display -->
      <div class="left-panel" :class="{ 'full-screen': isFullScreen }">
        <div class="panel-header">
          <div class="header-left">
            <span class="header-deco">◆</span>
            <span class="header-title">Real-time Knowledge Graph</span>
          </div>
          <div class="header-right">
            <template v-if="graphData">
              <span class="stat-item">{{ graphData.node_count || graphData.nodes?.length || 0 }} Nodes</span>
              <span class="stat-divider">|</span>
              <span class="stat-item">{{ graphData.edge_count || graphData.edges?.length || 0 }} Edges</span>
              <span class="stat-divider">|</span>
            </template>
            <div class="action-buttons">
                <button class="action-btn" @click="refreshGraph" :disabled="graphLoading" title="Refresh Graph">
                  <span class="icon-refresh" :class="{ 'spinning': graphLoading }">↻</span>
                </button>
                <button class="action-btn" @click="toggleFullScreen" :title="isFullScreen ? 'Exit Fullscreen' : 'Fullscreen'">
                  <span class="icon-fullscreen">{{ isFullScreen ? '↙' : '↗' }}</span>
                </button>
            </div>
          </div>
        </div>
        
        <div class="graph-container" ref="graphContainer">
          <!-- Graph visualization (shown whenever data is available) -->
          <div v-if="graphData" class="graph-view">
            <svg ref="graphSvg" class="graph-svg"></svg>
            <!-- Building hint -->
            <div v-if="currentPhase === 1" class="graph-building-hint">
              <span class="building-dot"></span>
              Updating in real-time...
            </div>
            
            <!-- Node/edge detail panel -->
            <DetailPanel v-if="selectedItem" :item="selectedItem" @close="closeDetailPanel" />
          </div>
          
          <!-- Loading state -->
          <div v-else-if="graphLoading" class="graph-loading">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="loading-text">Loading graph data...</p>
          </div>
          
          <!-- Waiting for build -->
          <div v-else-if="currentPhase < 1" class="graph-waiting">
            <div class="waiting-icon">
              <svg viewBox="0 0 100 100" class="network-icon">
                <circle cx="50" cy="20" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="20" cy="60" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="80" cy="60" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="50" cy="80" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <line x1="50" y1="28" x2="25" y2="54" stroke="#000" stroke-width="1"/>
                <line x1="50" y1="28" x2="75" y2="54" stroke="#000" stroke-width="1"/>
                <line x1="28" y1="60" x2="72" y2="60" stroke="#000" stroke-width="1" stroke-dasharray="4"/>
                <line x1="50" y1="72" x2="26" y2="66" stroke="#000" stroke-width="1"/>
                <line x1="50" y1="72" x2="74" y2="66" stroke="#000" stroke-width="1"/>
              </svg>
            </div>
            <p class="waiting-text">온톨로지 생성 대기 중</p>
            <p class="waiting-hint">생성이 완료되면 그래프 구축이 자동으로 시작됩니다</p>
          </div>
          
          <!-- Building but no data yet -->
          <div v-else-if="currentPhase === 1 && !graphData" class="graph-waiting">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="waiting-text">지식 그래프 구축 중</p>
            <p class="waiting-hint">Data will appear shortly...</p>
          </div>
          
          <!-- Error state -->
          <div v-else-if="error" class="graph-error">
            <span class="error-icon">⚠</span>
            <p>{{ error }}</p>
          </div>
        </div>
        
        <!-- Graph legend -->
        <div v-if="graphData" class="graph-legend">
          <div class="legend-item" v-for="type in entityTypes" :key="type.name">
            <span class="legend-dot" :style="{ background: type.color }"></span>
            <span class="legend-label">{{ type.name }}</span>
            <span class="legend-count">{{ type.count }}</span>
          </div>
        </div>
      </div>

      <!-- Right: Build pipeline details -->
      <div class="right-panel" :class="{ 'hidden': isFullScreen }">
        <div class="panel-header dark-header">
          <span class="header-icon">▣</span>
          <span class="header-title">구축 파이프라인</span>
        </div>

        <BuildPipeline
          :current-phase="currentPhase"
          :ontology-progress="ontologyProgress"
          :project-data="projectData"
          :build-progress="buildProgress"
          :graph-data="graphData"
          :entity-types="entityTypes"
          @next-step="goToNextStep"
        />

        <ProjectInfoPanel :project-data="projectData" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { generateOntology, getProject, buildGraph } from '../api/graph'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { useGraphPolling } from '../composables/useGraphPolling'
import { useGraphRenderer } from '../composables/useGraphRenderer'
import DetailPanel from '../components/Process/DetailPanel.vue'
import BuildPipeline from '../components/Process/BuildPipeline.vue'
import ProjectInfoPanel from '../components/Process/ProjectInfoPanel.vue'

const route = useRoute()
const router = useRouter()

// Current project ID (may change from 'new' to actual ID)
const currentProjectId = ref(route.params.projectId)

// State
const loading = ref(true)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const buildProgress = ref(null)
const ontologyProgress = ref(null) // Ontology generation progress
const currentPhase = ref(-1) // -1: uploading, 0: generating ontology, 1: building graph, 2: completed
const selectedItem = ref(null) // Currently selected node or edge
const isFullScreen = ref(false)

// DOM references
const graphContainer = ref(null)
const graphSvg = ref(null)

// Polling (graph + task) — extracted to composable
const {
  startGraphPolling,
  stopGraphPolling,
  refreshGraph,
  startPollingTask,
  stopPolling,
  loadGraph,
} = useGraphPolling({
  currentProjectId,
  projectData,
  graphData,
  currentPhase,
  error,
  buildProgress,
  graphLoading,
  onGraphUpdate: () => renderGraph(),
})

// Computed properties
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return 'Build Failed'
  if (currentPhase.value >= 2) return 'Build Complete'
  if (currentPhase.value === 1) return 'Building Graph'
  if (currentPhase.value === 0) return 'Generating Ontology'
  return 'Initializing'
})

const entityTypes = computed(() => {
  if (!graphData.value?.nodes) return []
  
  const typeMap = {}
  const colors = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C']
  
  graphData.value.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  
  return Object.values(typeMap)
})

// Methods
const goHome = () => {
  router.push('/')
}

const goToNextStep = () => {
  // TODO: Navigate to environment setup step
  alert('Environment setup feature is under development...')
}

const toggleFullScreen = () => {
  isFullScreen.value = !isFullScreen.value
  // Wait for transition to finish then re-render graph
  setTimeout(() => {
    renderGraph()
  }, 350) 
}

// Close detail panel
const closeDetailPanel = () => {
  selectedItem.value = null
}

// Select node
const selectNode = (nodeData, color) => {
  selectedItem.value = {
    type: 'node',
    data: nodeData,
    color: color,
    entityType: nodeData.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity'
  }
}

// Select edge
const selectEdge = (edgeData) => {
  selectedItem.value = {
    type: 'edge',
    data: edgeData
  }
}

// Initialize - handle new project or load existing project
const initProject = async () => {
  const paramProjectId = route.params.projectId
  
  if (paramProjectId === 'new') {
    // New project: get pending upload data from store
    await handleNewProject()
  } else {
    // Load existing project
    currentProjectId.value = paramProjectId
    await loadProject()
  }
}

// Handle new project - call ontology/generate API
const handleNewProject = async () => {
  const pending = getPendingUpload()
  
  if (!pending.isPending || pending.files.length === 0) {
    error.value = 'No files to upload. Please return to the home page and try again.'
    loading.value = false
    return
  }
  
  try {
    loading.value = true
    currentPhase.value = 0 // Ontology generation phase
    ontologyProgress.value = { message: 'Uploading files and analyzing documents...' }
    
    // Build FormData
    const formDataObj = new FormData()
    pending.files.forEach(file => {
      formDataObj.append('files', file)
    })
    formDataObj.append('simulation_requirement', pending.simulationRequirement)
    
    // Call ontology generation API
    const response = await generateOntology(formDataObj)
    
    if (response.success) {
      // Clear pending upload data
      clearPendingUpload()
      
      // Update project ID and data
      currentProjectId.value = response.data.project_id
      projectData.value = response.data
      
      // Update URL (without page reload)
      router.replace({
        name: 'Process',
        params: { projectId: response.data.project_id }
      })
      
      ontologyProgress.value = null
      
      // Automatically start graph build
      await startBuildGraph()
    } else {
      error.value = response.error || 'Ontology generation failed'
    }
  } catch (err) {
    console.error('Handle new project error:', err)
    error.value = 'Project initialization failed: ' + (err.message || 'Unknown error')
  } finally {
    loading.value = false
  }
}

// Load existing project data
const loadProject = async () => {
  try {
    loading.value = true
    const response = await getProject(currentProjectId.value)
    
    if (response.success) {
      projectData.value = response.data
      updatePhaseByStatus(response.data.status)
      
      // Automatically start graph build
      if (response.data.status === 'ontology_generated' && !response.data.graph_id) {
        await startBuildGraph()
      }
      
      // Continue polling in-progress build task
      if (response.data.status === 'graph_building' && response.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(response.data.graph_build_task_id)
      }
      
      // Load completed graph
      if (response.data.status === 'graph_completed' && response.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(response.data.graph_id)
      }
    } else {
      error.value = response.error || 'Failed to load project'
    }
  } catch (err) {
    console.error('Load project error:', err)
    error.value = 'Failed to load project: ' + (err.message || 'Unknown error')
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated':
      currentPhase.value = 0
      break
    case 'graph_building':
      currentPhase.value = 1
      break
    case 'graph_completed':
      currentPhase.value = 2
      break
    case 'failed':
      error.value = projectData.value?.error || 'Processing failed'
      break
  }
}

// Start building the graph
const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    // Set initial progress
    buildProgress.value = {
      progress: 0,
      message: 'Starting graph build...'
    }
    
    const response = await buildGraph({ project_id: currentProjectId.value })
    
    if (response.success) {
      buildProgress.value.message = 'Graph build task started...'
      
      // Save task_id for polling
      const taskId = response.data.task_id
      
      // Start graph data polling (independent of task status polling)
      startGraphPolling()
      
      // Start task status polling
      startPollingTask(taskId)
    } else {
      error.value = response.error || 'Failed to start graph build'
      buildProgress.value = null
    }
  } catch (err) {
    console.error('Build graph error:', err)
    error.value = 'Failed to start graph build: ' + (err.message || 'Unknown error')
    buildProgress.value = null
  }
}

// D3 graph rendering — extracted to composable
const { renderGraph } = useGraphRenderer({
  graphSvg,
  graphData,
  graphContainer,
  onSelectNode: selectNode,
  onSelectEdge: selectEdge,
  onCloseDetail: closeDetailPanel,
})

// Watch graph data changes
watch(graphData, () => {
  if (graphData.value) {
    nextTick(() => renderGraph())
  }
})

// Lifecycle hooks
onMounted(() => {
  initProject()
})

onUnmounted(() => {
  stopPolling()
  stopGraphPolling()
})
</script>

<style scoped src="./Process.styles.css"></style>
