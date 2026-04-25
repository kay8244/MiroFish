<template>
  <div class="quick-search-display">
    <!-- Header Section -->
    <div class="quicksearch-header">
      <div class="header-main">
        <div class="header-title">빠른 검색</div>
        <div class="header-stats">
          <span class="stat-item">
            <span class="stat-value">{{ result.count || result.facts.length }}</span>
            <span class="stat-label">결과</span>
          </span>
          <template v-if="resultLength">
            <span class="stat-divider">&middot;</span>
            <span class="stat-size">{{ formatSize(resultLength) }}</span>
          </template>
        </div>
      </div>
      <div v-if="result.query" class="header-query">
        <span class="query-label">Search: </span>
        <span class="query-text">{{ result.query }}</span>
      </div>
    </div>

    <!-- Tab Navigation (only show if there are edges or nodes) -->
    <div v-if="showTabs" class="quicksearch-tabs">
      <button :class="['quicksearch-tab', { active: activeTab === 'facts' }]" @click="activeTab = 'facts'">
        <span class="tab-label">Facts ({{ result.facts.length }})</span>
      </button>
      <button v-if="hasEdges" :class="['quicksearch-tab', { active: activeTab === 'edges' }]" @click="activeTab = 'edges'">
        <span class="tab-label">Relations ({{ result.edges.length }})</span>
      </button>
      <button v-if="hasNodes" :class="['quicksearch-tab', { active: activeTab === 'nodes' }]" @click="activeTab = 'nodes'">
        <span class="tab-label">Nodes ({{ result.nodes.length }})</span>
      </button>
    </div>

    <!-- Content Area -->
    <div :class="['quicksearch-content', { 'no-tabs': !showTabs }]">
      <!-- Facts -->
      <div v-if="!showTabs || activeTab === 'facts'" class="facts-panel">
        <div v-if="!showTabs" class="panel-header">
          <span class="panel-title">검색 결과</span>
          <span class="panel-count">Total: {{ result.facts.length }}</span>
        </div>
        <template v-if="result.facts.length > 0">
          <div class="facts-list">
            <div v-for="(fact, i) in displayedFacts" :key="i" class="fact-item">
              <span class="fact-number">{{ i + 1 }}</span>
              <div class="fact-content">{{ fact }}</div>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">검색 결과가 없습니다</div>
        <button v-if="result.facts.length > INITIAL_SHOW_COUNT" class="expand-btn" @click="expandedFacts = !expandedFacts">
          {{ expandedFacts ? 'Collapse \u25B2' : `Show All ${result.facts.length} \u25BC` }}
        </button>
      </div>

      <!-- Edges Tab -->
      <div v-if="activeTab === 'edges' && hasEdges" class="edges-panel">
        <div class="panel-header">
          <span class="panel-title">관련 관계</span>
          <span class="panel-count">Total: {{ result.edges.length }}</span>
        </div>
        <div class="edges-list">
          <div v-for="(edge, i) in result.edges" :key="i" class="edge-item">
            <span class="edge-source">{{ edge.source }}</span>
            <span class="edge-arrow">
              <span class="edge-line"></span>
              <span class="edge-label">{{ edge.relation }}</span>
              <span class="edge-line"></span>
            </span>
            <span class="edge-target">{{ edge.target }}</span>
          </div>
        </div>
      </div>

      <!-- Nodes Tab -->
      <div v-if="activeTab === 'nodes' && hasNodes" class="nodes-panel">
        <div class="panel-header">
          <span class="panel-title">관련 노드</span>
          <span class="panel-count">Total: {{ result.nodes.length }}</span>
        </div>
        <div class="nodes-grid">
          <div v-for="(node, i) in result.nodes" :key="i" class="node-tag">
            <span class="node-name">{{ node.name }}</span>
            <span v-if="node.type" class="node-type">{{ node.type }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
  resultLength: { type: Number, default: 0 }
})

const INITIAL_SHOW_COUNT = 5
const activeTab = ref('facts')
const expandedFacts = ref(false)

const hasEdges = computed(() => props.result.edges && props.result.edges.length > 0)
const hasNodes = computed(() => props.result.nodes && props.result.nodes.length > 0)
const showTabs = computed(() => hasEdges.value || hasNodes.value)

const displayedFacts = computed(() =>
  expandedFacts.value ? props.result.facts : props.result.facts.slice(0, INITIAL_SHOW_COUNT)
)

const formatSize = (length) => {
  if (!length) return ''
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`
  return `${length} chars`
}
</script>
