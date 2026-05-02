<template>
  <div class="insight-display">
    <!-- Header Section -->
    <div class="insight-header">
      <div class="header-main">
        <div class="header-title">심층 인사이트</div>
        <div class="header-stats">
          <span class="stat-item">
            <span class="stat-value">{{ result.stats.facts || result.facts.length }}</span>
            <span class="stat-label">사실</span>
          </span>
          <span class="stat-divider">/</span>
          <span class="stat-item">
            <span class="stat-value">{{ result.stats.entities || result.entities.length }}</span>
            <span class="stat-label">엔티티</span>
          </span>
          <span class="stat-divider">/</span>
          <span class="stat-item">
            <span class="stat-value">{{ result.stats.relationships || result.relations.length }}</span>
            <span class="stat-label">관계</span>
          </span>
          <template v-if="resultLength">
            <span class="stat-divider">&middot;</span>
            <span class="stat-size">{{ formatSize(resultLength) }}</span>
          </template>
        </div>
      </div>
      <div v-if="result.query" class="header-topic">{{ result.query }}</div>
      <div v-if="result.simulationRequirement" class="header-scenario">
        <span class="scenario-label">Prediction Scenario: </span>
        <span class="scenario-text">{{ result.simulationRequirement }}</span>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="insight-tabs">
      <button :class="['insight-tab', { active: activeTab === 'facts' }]" @click="activeTab = 'facts'">
        <span class="tab-label">Key Memories ({{ result.facts.length }})</span>
      </button>
      <button :class="['insight-tab', { active: activeTab === 'entities' }]" @click="activeTab = 'entities'">
        <span class="tab-label">Core Entities ({{ result.entities.length }})</span>
      </button>
      <button :class="['insight-tab', { active: activeTab === 'relations' }]" @click="activeTab = 'relations'">
        <span class="tab-label">Relationship Chains ({{ result.relations.length }})</span>
      </button>
      <button v-if="result.subQueries.length > 0" :class="['insight-tab', { active: activeTab === 'subqueries' }]" @click="activeTab = 'subqueries'">
        <span class="tab-label">Sub-Questions ({{ result.subQueries.length }})</span>
      </button>
    </div>

    <!-- Tab Content -->
    <div class="insight-content">
      <!-- Facts Tab -->
      <div v-if="activeTab === 'facts' && result.facts.length > 0" class="facts-panel">
        <div class="panel-header">
          <span class="panel-title">시간 메모리의 최신 핵심 사실</span>
          <span class="panel-count">Total: {{ result.facts.length }}</span>
        </div>
        <div class="facts-list">
          <div v-for="(fact, i) in displayedFacts" :key="i" class="fact-item">
            <span class="fact-number">{{ i + 1 }}</span>
            <div class="fact-content">{{ fact }}</div>
          </div>
        </div>
        <button v-if="result.facts.length > INITIAL_SHOW_COUNT" class="expand-btn" @click="expandedFacts = !expandedFacts">
          {{ expandedFacts ? 'Collapse \u25B2' : `Show All ${result.facts.length} \u25BC` }}
        </button>
      </div>

      <!-- Entities Tab -->
      <div v-if="activeTab === 'entities' && result.entities.length > 0" class="entities-panel">
        <div class="panel-header">
          <span class="panel-title">핵심 엔티티</span>
          <span class="panel-count">Total: {{ result.entities.length }}</span>
        </div>
        <div class="entities-grid">
          <div v-for="(entity, i) in displayedEntities" :key="i" class="entity-tag" :title="entity.summary || ''">
            <span class="entity-name">{{ entity.name }}</span>
            <span class="entity-type">{{ entity.type }}</span>
            <span v-if="entity.relatedFactsCount > 0" class="entity-fact-count">{{ entity.relatedFactsCount }}</span>
          </div>
        </div>
        <button v-if="result.entities.length > 12" class="expand-btn" @click="expandedEntities = !expandedEntities">
          {{ expandedEntities ? 'Collapse \u25B2' : `Show All ${result.entities.length} \u25BC` }}
        </button>
      </div>

      <!-- Relations Tab -->
      <div v-if="activeTab === 'relations' && result.relations.length > 0" class="relations-panel">
        <div class="panel-header">
          <span class="panel-title">관계 체인</span>
          <span class="panel-count">Total: {{ result.relations.length }}</span>
        </div>
        <div class="relations-list">
          <div v-for="(rel, i) in displayedRelations" :key="i" class="relation-item">
            <span class="rel-source">{{ rel.source }}</span>
            <span class="rel-arrow">
              <span class="rel-line"></span>
              <span class="rel-label">{{ rel.relation }}</span>
              <span class="rel-line"></span>
            </span>
            <span class="rel-target">{{ rel.target }}</span>
          </div>
        </div>
        <button v-if="result.relations.length > INITIAL_SHOW_COUNT" class="expand-btn" @click="expandedRelations = !expandedRelations">
          {{ expandedRelations ? 'Collapse \u25B2' : `Show All ${result.relations.length} \u25BC` }}
        </button>
      </div>

      <!-- Sub-queries Tab -->
      <div v-if="activeTab === 'subqueries' && result.subQueries.length > 0" class="subqueries-panel">
        <div class="panel-header">
          <span class="panel-title">Drift Query Generated Sub-Questions</span>
          <span class="panel-count">Total: {{ result.subQueries.length }}</span>
        </div>
        <div class="subqueries-list">
          <div v-for="(sq, i) in result.subQueries" :key="i" class="subquery-item">
            <span class="subquery-number">Q{{ i + 1 }}</span>
            <div class="subquery-text">{{ sq }}</div>
          </div>
        </div>
      </div>

      <!-- Empty states -->
      <div v-if="activeTab === 'facts' && result.facts.length === 0" class="empty-state">핵심 메모리가 없습니다</div>
      <div v-if="activeTab === 'entities' && result.entities.length === 0" class="empty-state">핵심 엔티티가 없습니다</div>
      <div v-if="activeTab === 'relations' && result.relations.length === 0" class="empty-state">관계 체인이 없습니다</div>
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
const expandedEntities = ref(false)
const expandedRelations = ref(false)

const displayedFacts = computed(() =>
  expandedFacts.value ? props.result.facts : props.result.facts.slice(0, INITIAL_SHOW_COUNT)
)
const displayedEntities = computed(() =>
  expandedEntities.value ? props.result.entities : props.result.entities.slice(0, 12)
)
const displayedRelations = computed(() =>
  expandedRelations.value ? props.result.relations : props.result.relations.slice(0, INITIAL_SHOW_COUNT)
)

const formatSize = (length) => {
  if (!length) return ''
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`
  return `${length} chars`
}
</script>
