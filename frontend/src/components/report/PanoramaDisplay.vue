<template>
  <div class="panorama-display">
    <!-- Header Section -->
    <div class="panorama-header">
      <div class="header-main">
        <div class="header-title">파노라마 검색</div>
        <div class="header-stats">
          <span class="stat-item">
            <span class="stat-value">{{ result.stats.nodes }}</span>
            <span class="stat-label">노드</span>
          </span>
          <span class="stat-divider">/</span>
          <span class="stat-item">
            <span class="stat-value">{{ result.stats.edges }}</span>
            <span class="stat-label">엣지</span>
          </span>
          <template v-if="resultLength">
            <span class="stat-divider">&middot;</span>
            <span class="stat-size">{{ formatSize(resultLength) }}</span>
          </template>
        </div>
      </div>
      <div v-if="result.query" class="header-topic">{{ result.query }}</div>
    </div>

    <!-- Tab Navigation -->
    <div class="panorama-tabs">
      <button :class="['panorama-tab', { active: activeTab === 'active' }]" @click="activeTab = 'active'">
        <span class="tab-label">Active Memories ({{ result.activeFacts.length }})</span>
      </button>
      <button :class="['panorama-tab', { active: activeTab === 'historical' }]" @click="activeTab = 'historical'">
        <span class="tab-label">Historical Memories ({{ result.historicalFacts.length }})</span>
      </button>
      <button :class="['panorama-tab', { active: activeTab === 'entities' }]" @click="activeTab = 'entities'">
        <span class="tab-label">Involved Entities ({{ result.entities.length }})</span>
      </button>
    </div>

    <!-- Tab Content -->
    <div class="panorama-content">
      <!-- Active Facts Tab -->
      <div v-if="activeTab === 'active'" class="facts-panel active-facts">
        <div class="panel-header">
          <span class="panel-title">활성 메모리</span>
          <span class="panel-count">Total: {{ result.activeFacts.length }}</span>
        </div>
        <template v-if="result.activeFacts.length > 0">
          <div class="facts-list">
            <div v-for="(fact, i) in displayedActive" :key="i" class="fact-item active">
              <span class="fact-number">{{ i + 1 }}</span>
              <div class="fact-content">{{ fact }}</div>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">활성 메모리가 없습니다</div>
        <button v-if="result.activeFacts.length > INITIAL_SHOW_COUNT" class="expand-btn" @click="expandedActive = !expandedActive">
          {{ expandedActive ? 'Collapse \u25B2' : `Show All ${result.activeFacts.length} \u25BC` }}
        </button>
      </div>

      <!-- Historical Facts Tab -->
      <div v-if="activeTab === 'historical'" class="facts-panel historical-facts">
        <div class="panel-header">
          <span class="panel-title">과거 메모리</span>
          <span class="panel-count">Total: {{ result.historicalFacts.length }}</span>
        </div>
        <template v-if="result.historicalFacts.length > 0">
          <div class="facts-list">
            <div v-for="(fact, i) in displayedHistorical" :key="i" class="fact-item historical">
              <span class="fact-number">{{ i + 1 }}</span>
              <div class="fact-content">
                <template v-if="getTimeInfo(fact)">
                  <span class="fact-time">{{ getTimeInfo(fact).time }}</span>
                  <span class="fact-text">{{ getTimeInfo(fact).text }}</span>
                </template>
                <span v-else class="fact-text">{{ fact }}</span>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">과거 메모리가 없습니다</div>
        <button v-if="result.historicalFacts.length > INITIAL_SHOW_COUNT" class="expand-btn" @click="expandedHistorical = !expandedHistorical">
          {{ expandedHistorical ? 'Collapse \u25B2' : `Show All ${result.historicalFacts.length} \u25BC` }}
        </button>
      </div>

      <!-- Entities Tab -->
      <div v-if="activeTab === 'entities'" class="entities-panel">
        <div class="panel-header">
          <span class="panel-title">관련 엔티티</span>
          <span class="panel-count">Total: {{ result.entities.length }}</span>
        </div>
        <template v-if="result.entities.length > 0">
          <div class="entities-grid">
            <div v-for="(entity, i) in displayedEntities" :key="i" class="entity-tag">
              <span class="entity-name">{{ entity.name }}</span>
              <span v-if="entity.type" class="entity-type">{{ entity.type }}</span>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">엔티티가 없습니다</div>
        <button v-if="result.entities.length > 8" class="expand-btn" @click="expandedEntities = !expandedEntities">
          {{ expandedEntities ? 'Collapse \u25B2' : `Show All ${result.entities.length} \u25BC` }}
        </button>
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
const activeTab = ref('active')
const expandedActive = ref(false)
const expandedHistorical = ref(false)
const expandedEntities = ref(false)

const displayedActive = computed(() =>
  expandedActive.value ? props.result.activeFacts : props.result.activeFacts.slice(0, INITIAL_SHOW_COUNT)
)
const displayedHistorical = computed(() =>
  expandedHistorical.value ? props.result.historicalFacts : props.result.historicalFacts.slice(0, INITIAL_SHOW_COUNT)
)
const displayedEntities = computed(() =>
  expandedEntities.value ? props.result.entities : props.result.entities.slice(0, 8)
)

const formatSize = (length) => {
  if (!length) return ''
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`
  return `${length} chars`
}

const getTimeInfo = (fact) => {
  const timeMatch = fact.match(/^\[(.+?)\]\s*(.*)$/)
  if (timeMatch) return { time: timeMatch[1], text: timeMatch[2] }
  return null
}
</script>
