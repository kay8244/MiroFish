<template>
  <div class="graph-panel">
    <div class="panel-header">
      <span class="panel-title">그래프 관계 시각화</span>
      <!-- Top toolbar (Internal Top Right) -->
      <div class="header-tools">
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" title="그래프 새로고침">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">새로고침</span>
        </button>
        <button class="tool-btn" @click="$emit('toggle-maximize')" title="최대화/복원">
          <span class="icon-maximize">⛶</span>
        </button>
      </div>
    </div>

    <div class="graph-container" ref="graphContainer">
      <!-- Graph visualization -->
      <div v-if="graphData" class="graph-view">
        <svg ref="graphSvg" class="graph-svg"></svg>

        <!-- Building/simulating hint -->
        <div v-if="currentPhase === 1 || isSimulating" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
              <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
            </svg>
          </div>
          {{ isSimulating ? 'GraphRAG long/short-term memory updating in real time' : 'Updating in real time...' }}
        </div>

        <!-- Hint shown after simulation ends -->
        <div v-if="showSimulationFinishedHint" class="graph-building-hint finished-hint">
          <div class="hint-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <span class="hint-text">일부 콘텐츠가 처리 중입니다. 잠시 후 수동으로 새로고침해 주세요.</span>
          <button class="hint-close-btn" @click="dismissFinishedHint" title="Dismiss">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <!-- Node/edge detail panel -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <span class="detail-title">{{ selectedItem.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge" :style="{ background: selectedItem.color, color: '#fff' }">
              {{ selectedItem.entityType }}
            </span>
            <button class="detail-close" @click="closeDetailPanel">×</button>
          </div>

          <!-- Node details -->
          <div v-if="selectedItem.type === 'node'" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">Name:</span>
              <span class="detail-value">{{ selectedItem.data.name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">UUID:</span>
              <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
            </div>
            <div class="detail-row" v-if="selectedItem.data.created_at">
              <span class="detail-label">Created:</span>
              <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
            </div>

            <!-- Properties -->
            <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
              <div class="section-title">Properties:</div>
              <div class="properties-list">
                <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                  <span class="property-key">{{ key }}:</span>
                  <span class="property-value">{{ value || 'None' }}</span>
                </div>
              </div>
            </div>

            <!-- Summary -->
            <div class="detail-section" v-if="selectedItem.data.summary">
              <div class="section-title">Summary:</div>
              <div class="summary-text">{{ selectedItem.data.summary }}</div>
            </div>

            <!-- Labels -->
            <div class="detail-section" v-if="selectedItem.data.labels && selectedItem.data.labels.length > 0">
              <div class="section-title">Labels:</div>
              <div class="labels-list">
                <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">
                  {{ label }}
                </span>
              </div>
            </div>
          </div>

          <!-- Edge details -->
          <div v-else class="detail-content">
            <!-- Self-loop group details -->
            <template v-if="selectedItem.data.isSelfLoopGroup">
              <div class="edge-relation-header self-loop-header">
                {{ selectedItem.data.source_name }} - Self Relations
                <span class="self-loop-count">{{ selectedItem.data.selfLoopCount }} items</span>
              </div>

              <div class="self-loop-list">
                <div
                  v-for="(loop, idx) in selectedItem.data.selfLoopEdges"
                  :key="loop.uuid || idx"
                  class="self-loop-item"
                  :class="{ expanded: expandedSelfLoops.has(loop.uuid || idx) }"
                >
                  <div
                    class="self-loop-item-header"
                    @click="toggleSelfLoop(loop.uuid || idx)"
                  >
                    <span class="self-loop-index">#{{ idx + 1 }}</span>
                    <span class="self-loop-name">{{ loop.name || loop.fact_type || 'RELATED' }}</span>
                    <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
                  </div>

                  <div class="self-loop-item-content" v-show="expandedSelfLoops.has(loop.uuid || idx)">
                    <div class="detail-row" v-if="loop.uuid">
                      <span class="detail-label">UUID:</span>
                      <span class="detail-value uuid-text">{{ loop.uuid }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact">
                      <span class="detail-label">Fact:</span>
                      <span class="detail-value fact-text">{{ loop.fact }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact_type">
                      <span class="detail-label">Type:</span>
                      <span class="detail-value">{{ loop.fact_type }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.created_at">
                      <span class="detail-label">Created:</span>
                      <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
                    </div>
                    <div v-if="loop.episodes && loop.episodes.length > 0" class="self-loop-episodes">
                      <span class="detail-label">Episodes:</span>
                      <div class="episodes-list compact">
                        <span v-for="ep in loop.episodes" :key="ep" class="episode-tag small">{{ ep }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- Normal edge details -->
            <template v-else>
              <div class="edge-relation-header">
                {{ selectedItem.data.source_name }} → {{ selectedItem.data.name || 'RELATED_TO' }} → {{ selectedItem.data.target_name }}
              </div>

              <div class="detail-row">
                <span class="detail-label">UUID:</span>
                <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Label:</span>
                <span class="detail-value">{{ selectedItem.data.name || 'RELATED_TO' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ selectedItem.data.fact_type || 'Unknown' }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.fact">
                <span class="detail-label">Fact:</span>
                <span class="detail-value fact-text">{{ selectedItem.data.fact }}</span>
              </div>

              <!-- Episodes -->
              <div class="detail-section" v-if="selectedItem.data.episodes && selectedItem.data.episodes.length > 0">
                <div class="section-title">Episodes:</div>
                <div class="episodes-list">
                  <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">
                    {{ ep }}
                  </span>
                </div>
              </div>

              <div class="detail-row" v-if="selectedItem.data.created_at">
                <span class="detail-label">Created:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.valid_at">
                <span class="detail-label">Valid From:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.valid_at) }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Loading state -->
      <div v-else-if="loading" class="graph-state">
        <div class="loading-spinner"></div>
        <p>그래프 데이터 로딩 중...</p>
      </div>

      <!-- Waiting/empty state -->
      <div v-else class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">온톨로지 생성 대기 중...</p>
      </div>
    </div>

    <!-- Bottom legend (Bottom Left) -->
    <div v-if="graphData && entityTypes.length" class="graph-legend">
      <span class="legend-title">엔티티 타입</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.name }}</span>
        </div>
      </div>
    </div>

    <!-- Show edge labels toggle -->
    <div v-if="graphData" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">엣지 라벨 표시</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  graphData: Object,
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean
})

const emit = defineEmits(['refresh', 'toggle-maximize'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true) // Show edge labels by default
const expandedSelfLoops = ref(new Set()) // Expanded self-loop items
const showSimulationFinishedHint = ref(false) // Hint shown after simulation ends
const wasSimulating = ref(false) // Track whether simulation was previously running

// Dismiss the simulation-finished hint
const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

// Watch isSimulating changes to detect when simulation ends
watch(() => props.isSimulating, (newValue, oldValue) => {
  if (wasSimulating.value && !newValue) {
    // Transitioned from simulating to not simulating — show finished hint
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })

// Toggle expand/collapse state of a self-loop item
const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

// Compute entity types for the legend
const entityTypes = computed(() => {
  if (!props.graphData?.nodes) return []
  const typeMap = {}
  // Attractive color palette
  const colors = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']

  props.graphData.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  return Object.values(typeMap)
})

// Format datetime
const formatDateTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  } catch {
    return dateStr
  }
}

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set() // Reset expanded state
}

let currentSimulation = null
let linkLabelsRef = null
let linkLabelBgRef = null

const renderGraph = () => {
  if (!graphSvg.value || !props.graphData) return

  // Stop any previous simulation
  if (currentSimulation) {
    currentSimulation.stop()
  }

  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)

  svg.selectAll('*').remove()

  const nodesData = props.graphData.nodes || []
  const edgesData = props.graphData.edges || []

  if (nodesData.length === 0) return

  // Prep data
  const nodeMap = {}
  nodesData.forEach(n => nodeMap[n.uuid] = n)

  const nodes = nodesData.map(n => ({
    id: n.uuid,
    name: n.name || 'Unnamed',
    type: n.labels?.find(l => l !== 'Entity') || 'Entity',
    rawData: n
  }))

  const nodeIds = new Set(nodes.map(n => n.id))

  // Process edge data — count edges between each pair of nodes and track index
  const edgePairCount = {}
  const selfLoopEdges = {} // Self-loop edges grouped by node
  const tempEdges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))

  // Count edges per node pair and collect self-loops
  tempEdges.forEach(e => {
    if (e.source_node_uuid === e.target_node_uuid) {
      // Self-loop — collect into array
      if (!selfLoopEdges[e.source_node_uuid]) {
        selfLoopEdges[e.source_node_uuid] = []
      }
      selfLoopEdges[e.source_node_uuid].push({
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      })
    } else {
      const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
      edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
    }
  })

  // Track which index we are at for each node pair
  const edgePairIndex = {}
  const processedSelfLoopNodes = new Set() // Self-loop nodes already processed

  const edges = []

  tempEdges.forEach(e => {
    const isSelfLoop = e.source_node_uuid === e.target_node_uuid

    if (isSelfLoop) {
      // Self-loop edge — add only one merged self-loop per node
      if (processedSelfLoopNodes.has(e.source_node_uuid)) {
        return // Already processed, skip
      }
      processedSelfLoopNodes.add(e.source_node_uuid)

      const allSelfLoops = selfLoopEdges[e.source_node_uuid]
      const nodeName = nodeMap[e.source_node_uuid]?.name || 'Unknown'

      edges.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: 'SELF_LOOP',
        name: `Self Relations (${allSelfLoops.length})`,
        curvature: 0,
        isSelfLoop: true,
        rawData: {
          isSelfLoopGroup: true,
          source_name: nodeName,
          target_name: nodeName,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops // Store all self-loop edge details
        }
      })
      return
    }

    const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
    const totalCount = edgePairCount[pairKey]
    const currentIndex = edgePairIndex[pairKey] || 0
    edgePairIndex[pairKey] = currentIndex + 1

    // Check whether the edge direction matches the normalized direction (source UUID < target UUID)
    const isReversed = e.source_node_uuid > e.target_node_uuid

    // Compute curvature: spread multiple edges apart; single edges are straight
    let curvature = 0
    if (totalCount > 1) {
      // Distribute curvature evenly; range grows with edge count
      const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
      curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2

      // If edge direction is reversed relative to normalized direction, flip curvature
      // This ensures all edges are distributed in the same reference frame and won't overlap
      if (isReversed) {
        curvature = -curvature
      }
    }

    edges.push({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || 'RELATED',
      name: e.name || e.fact_type || 'RELATED',
      curvature,
      isSelfLoop: false,
      pairIndex: currentIndex,
      pairTotal: totalCount,
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      }
    })
  })

  // Color scale
  const colorMap = {}
  entityTypes.value.forEach(t => colorMap[t.name] = t.color)
  const getColor = (type) => colorMap[type] || '#999'

  // Simulation — dynamically adjust node spacing based on edge count
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
      // Dynamically adjust distance based on number of edges between each node pair
      // Base distance 150; +50 per additional edge
      const baseDistance = 150
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * 50
    }))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(50))
    // Attract isolated node clusters toward the center
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))

  currentSimulation = simulation

  const g = svg.append('g')

  // Zoom
  svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }))

  // Links — use path elements to support curves
  const linkGroup = g.append('g').attr('class', 'links')

  // Compute curve path
  const getLinkPath = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y

    // Detect self-loop
    if (d.isSelfLoop) {
      // Self-loop: draw an arc leaving and returning to the node
      const loopRadius = 30
      // Start from the right side of the node and loop back
      const x1 = sx + 8  // Start offset
      const y1 = sy - 4
      const x2 = sx + 8  // End offset
      const y2 = sy + 4
      // Draw self-loop as an arc (sweep-flag=1 clockwise)
      return `M${x1},${y1} A${loopRadius},${loopRadius} 0 1,1 ${x2},${y2}`
    }

    if (d.curvature === 0) {
      // Straight line
      return `M${sx},${sy} L${tx},${ty}`
    }

    // Compute quadratic bezier control point — offset dynamically based on distance and edge count
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    // Perpendicular offset proportional to distance — ensures curves are visible
    // More edges → larger offset ratio
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05 // Base 25%, +5% per extra edge
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY

    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
  }

  // Compute midpoint on a curve (for label positioning)
  const getLinkMidpoint = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y

    // Detect self-loop
    if (d.isSelfLoop) {
      // Self-loop label position: to the right of the node
      return { x: sx + 70, y: sy }
    }

    if (d.curvature === 0) {
      return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
    }

    // Midpoint of quadratic bezier at t=0.5
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY

    // Quadratic bezier formula B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2, t=0.5
    const midX = 0.25 * sx + 0.5 * cx + 0.25 * tx
    const midY = 0.25 * sy + 0.5 * cy + 0.25 * ty

    return { x: midX, y: midY }
  }

  const link = linkGroup.selectAll('path')
    .data(edges)
    .enter().append('path')
    .attr('stroke', '#C0C0C0')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      // Reset previously selected edge style
      linkGroup.selectAll('path').attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#666')
      // Highlight the currently selected edge
      d3.select(event.target).attr('stroke', '#3498db').attr('stroke-width', 3)

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link label background (white background for legibility)
  const linkLabelBg = linkGroup.selectAll('rect')
    .data(edges)
    .enter().append('rect')
    .attr('fill', 'rgba(255,255,255,0.95)')
    .attr('rx', 3)
    .attr('ry', 3)
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#666')
      // Highlight the corresponding edge
      link.filter(l => l === d).attr('stroke', '#3498db').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', 'rgba(52, 152, 219, 0.1)')

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text(d => d.name)
    .attr('font-size', '9px')
    .attr('fill', '#666')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('font-family', 'system-ui, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#666')
      // Highlight the corresponding edge
      link.filter(l => l === d).attr('stroke', '#3498db').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', '#3498db')

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Save references for external visibility control
  linkLabelsRef = linkLabels
  linkLabelBgRef = linkLabelBg

  // Nodes group
  const nodeGroup = g.append('g').attr('class', 'nodes')

  // Node circles
  const node = nodeGroup.selectAll('circle')
    .data(nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        // Record position only; do not restart simulation (distinguish click from drag)
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = event.x
        d._dragStartY = event.y
        d._isDragging = false
      })
      .on('drag', (event, d) => {
        // Detect whether a real drag has started (moved beyond threshold)
        const dx = event.x - d._dragStartX
        const dy = event.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (!d._isDragging && distance > 3) {
          // First detection of real drag — restart simulation
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }

        if (d._isDragging) {
          d.fx = event.x
          d.fy = event.y
        }
      })
      .on('end', (event, d) => {
        // Only let simulation cool down if the node was actually dragged
        if (d._isDragging) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
        d._isDragging = false
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      // Reset all node styles
      node.attr('stroke', '#fff').attr('stroke-width', 2.5)
      linkGroup.selectAll('path').attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
      // Highlight selected node
      d3.select(event.target).attr('stroke', '#E91E63').attr('stroke-width', 4)
      // Highlight edges connected to this node
      link.filter(l => l.source.id === d.id || l.target.id === d.id)
        .attr('stroke', '#E91E63')
        .attr('stroke-width', 2.5)

      selectedItem.value = {
        type: 'node',
        data: d.rawData,
        entityType: d.type,
        color: getColor(d.type)
      }
    })
    .on('mouseenter', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#333').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#fff').attr('stroke-width', 2.5)
      }
    })

  // Node Labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text(d => d.name.length > 8 ? d.name.substring(0, 8) + '…' : d.name)
    .attr('font-size', '11px')
    .attr('fill', '#333')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  simulation.on('tick', () => {
    // Update curve paths
    link.attr('d', d => getLinkPath(d))

    // Update edge label positions (no rotation — horizontal is cleaner)
    linkLabels.each(function(d) {
      const mid = getLinkMidpoint(d)
      d3.select(this)
        .attr('x', mid.x)
        .attr('y', mid.y)
        .attr('transform', '') // Remove rotation, keep horizontal
    })

    // Update edge label backgrounds
    linkLabelBg.each(function(d, i) {
      const mid = getLinkMidpoint(d)
      const textEl = linkLabels.nodes()[i]
      const bbox = textEl.getBBox()
      d3.select(this)
        .attr('x', mid.x - bbox.width / 2 - 4)
        .attr('y', mid.y - bbox.height / 2 - 2)
        .attr('width', bbox.width + 8)
        .attr('height', bbox.height + 4)
        .attr('transform', '') // Remove rotation
    })

    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    nodeLabels
      .attr('x', d => d.x)
      .attr('y', d => d.y)
  })

  // Click on blank area to close detail panel
  svg.on('click', () => {
    selectedItem.value = null
    node.attr('stroke', '#fff').attr('stroke-width', 2.5)
    linkGroup.selectAll('path').attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
    linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
    linkLabels.attr('fill', '#666')
  })
}

watch(() => props.graphData, () => {
  nextTick(renderGraph)
}, { deep: true })

// Watch edge label visibility toggle
watch(showEdgeLabels, (newVal) => {
  if (linkLabelsRef) {
    linkLabelsRef.style('display', newVal ? 'block' : 'none')
  }
  if (linkLabelBgRef) {
    linkLabelBgRef.style('display', newVal ? 'block' : 'none')
  }
})

const handleResize = () => {
  nextTick(renderGraph)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (currentSimulation) {
    currentSimulation.stop()
  }
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #FAFAFA;
  background-image: radial-gradient(#D0D0D0 1.5px, transparent 1.5px);
  background-size: 24px 24px;
  overflow: hidden;
}

.panel-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 16px 20px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, rgba(255,255,255,0.95), rgba(255,255,255,0));
  pointer-events: none;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  pointer-events: auto;
}

.header-tools {
  pointer-events: auto;
  display: flex;
  gap: 10px;
  align-items: center;
}

.tool-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid #E0E0E0;
  background: #FFF;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  color: #666;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  font-size: 13px;
}

.tool-btn:hover {
  background: #F5F5F5;
  color: #000;
  border-color: #CCC;
}

.tool-btn .btn-text {
  font-size: 12px;
}

.icon-refresh.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.graph-container {
  width: 100%;
  height: 100%;
}

.graph-view, .graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-state {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: #999;
}

.empty-icon {
  font-size: 32px;
  opacity: 0.3;
}

.empty-text {
  font-size: 14px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #EEE;
  border-top-color: #999;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* Graph building hint */
.graph-building-hint {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: #6B7280;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  white-space: nowrap;
  z-index: 20;
}

.graph-building-hint.finished-hint {
  bottom: 100px;
  background: rgba(255, 251, 235, 0.98);
  border-color: #F59E0B;
  color: #92400E;
}

.memory-icon-wrapper, .hint-icon-wrapper {
  display: flex;
  align-items: center;
}

.memory-icon, .hint-icon {
  width: 16px;
  height: 16px;
  animation: pulse-opacity 2s ease-in-out infinite;
}

@keyframes pulse-opacity {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.hint-text {
  flex: 1;
}

.hint-close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #92400E;
  opacity: 0.6;
  padding: 2px;
  display: flex;
  align-items: center;
  transition: opacity 0.2s;
}

.hint-close-btn:hover {
  opacity: 1;
}

/* Detail panel */
.detail-panel {
  position: absolute;
  top: 60px;
  right: 16px;
  width: 280px;
  max-height: calc(100% - 120px);
  background: #FFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  z-index: 20;
}

.detail-panel-header {
  padding: 12px 14px;
  border-bottom: 1px solid #F3F4F6;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #FAFAFA;
}

.detail-title {
  font-size: 13px;
  font-weight: 600;
  color: #111;
  flex: 1;
}

.detail-type-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.detail-close {
  background: none;
  border: none;
  font-size: 18px;
  color: #9CA3AF;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.detail-close:hover {
  color: #374151;
}

.detail-content {
  padding: 12px 14px;
  overflow-y: auto;
  flex: 1;
  font-size: 12px;
}

.detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: flex-start;
}

.detail-label {
  color: #9CA3AF;
  font-weight: 500;
  min-width: 52px;
  flex-shrink: 0;
}

.detail-value {
  color: #374151;
  word-break: break-all;
  flex: 1;
}

.uuid-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #6B7280;
}

.fact-text {
  font-style: italic;
  color: #4B5563;
  line-height: 1.5;
}

.detail-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #F3F4F6;
}

.section-title {
  font-weight: 600;
  color: #6B7280;
  margin-bottom: 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.property-item {
  display: flex;
  gap: 6px;
  font-size: 11px;
}

.property-key {
  color: #9CA3AF;
  font-weight: 500;
}

.property-value {
  color: #374151;
  word-break: break-word;
}

.summary-text {
  color: #4B5563;
  line-height: 1.6;
  font-size: 12px;
}

.labels-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.label-tag {
  background: #F3F4F6;
  color: #374151;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.edge-relation-header {
  font-weight: 600;
  color: #111827;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #F3F4F6;
  font-size: 12px;
  line-height: 1.5;
}

.self-loop-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.self-loop-count {
  font-size: 11px;
  background: #F3F4F6;
  color: #6B7280;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 400;
}

.self-loop-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.self-loop-item {
  border: 1px solid #F3F4F6;
  border-radius: 6px;
  overflow: hidden;
}

.self-loop-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  background: #FAFAFA;
  transition: background 0.15s;
}

.self-loop-item-header:hover {
  background: #F3F4F6;
}

.self-loop-index {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #9CA3AF;
  min-width: 20px;
}

.self-loop-name {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  color: #374151;
}

.self-loop-toggle {
  color: #9CA3AF;
  font-size: 14px;
}

.self-loop-item-content {
  padding: 8px 10px;
  border-top: 1px solid #F3F4F6;
  background: #FFF;
}

.self-loop-episodes {
  margin-top: 6px;
}

.episodes-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.episodes-list.compact {
  margin-top: 4px;
}

.episode-tag {
  background: #EFF6FF;
  color: #3B82F6;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}

.episode-tag.small {
  font-size: 10px;
  padding: 1px 6px;
}

/* Legend */
.graph-legend {
  position: absolute;
  bottom: 16px;
  left: 16px;
  background: rgba(255,255,255,0.95);
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  z-index: 10;
}

.legend-title {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  font-size: 11px;
  color: #374151;
}

/* Edge labels toggle */
.edge-labels-toggle {
  position: absolute;
  bottom: 16px;
  right: 16px;
  background: rgba(255,255,255,0.95);
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  z-index: 10;
}

.toggle-label {
  font-size: 12px;
  color: #374151;
  font-weight: 500;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 32px;
  height: 18px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #D1D5DB;
  border-radius: 18px;
  transition: 0.3s;
}

.slider:before {
  position: absolute;
  content: '';
  height: 12px;
  width: 12px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: 0.3s;
}

input:checked + .slider {
  background-color: #374151;
}

input:checked + .slider:before {
  transform: translateX(14px);
}
</style>
