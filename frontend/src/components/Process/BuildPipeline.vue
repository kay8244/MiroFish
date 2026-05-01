<template>
  <div class="process-content">
    <!-- Phase 1: Ontology Generation -->
    <div class="process-phase" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
      <div class="phase-header">
        <span class="phase-num">01</span>
        <div class="phase-info">
          <div class="phase-title">온톨로지 생성</div>
          <div class="phase-api">/api/graph/ontology/generate</div>
        </div>
        <span class="phase-status" :class="getPhaseStatusClass(0)">
          {{ getPhaseStatusText(0) }}
        </span>
      </div>

      <div class="phase-detail">
        <div class="detail-section">
          <div class="detail-label">API 설명</div>
          <div class="detail-content">
            After uploading documents, LLM analyzes the content and auto-generates an ontology structure (entity types + relation types) suited for opinion simulation
          </div>
        </div>

        <div class="detail-section" v-if="ontologyProgress && currentPhase === 0">
          <div class="detail-label">생성 진행률</div>
          <div class="ontology-progress">
            <div class="progress-spinner"></div>
            <span class="progress-text">{{ ontologyProgress.message }}</span>
          </div>
        </div>

        <div class="detail-section" v-if="projectData?.ontology">
          <div class="detail-label">Generated Entity Types ({{ projectData.ontology.entity_types?.length || 0 }})</div>
          <div class="entity-tags">
            <span
              v-for="entity in projectData.ontology.entity_types"
              :key="entity.name"
              class="entity-tag"
            >
              {{ entity.name }}
            </span>
          </div>
        </div>

        <div class="detail-section" v-if="projectData?.ontology">
          <div class="detail-label">Generated Relation Types ({{ projectData.ontology.relation_types?.length || 0 }})</div>
          <div class="relation-list">
            <div
              v-for="(rel, idx) in projectData.ontology.relation_types?.slice(0, 5) || []"
              :key="idx"
              class="relation-item"
            >
              <span class="rel-source">{{ rel.source_type }}</span>
              <span class="rel-arrow">→</span>
              <span class="rel-name">{{ rel.name }}</span>
              <span class="rel-arrow">→</span>
              <span class="rel-target">{{ rel.target_type }}</span>
            </div>
            <div v-if="(projectData.ontology.relation_types?.length || 0) > 5" class="relation-more">
              +{{ projectData.ontology.relation_types.length - 5 }} more relations...
            </div>
          </div>
        </div>

        <div class="detail-section waiting-state" v-if="!projectData?.ontology && currentPhase === 0 && !ontologyProgress">
          <div class="waiting-hint">Waiting for ontology generation...</div>
        </div>
      </div>
    </div>

    <!-- Phase 2: Knowledge Graph Build -->
    <div class="process-phase" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
      <div class="phase-header">
        <span class="phase-num">02</span>
        <div class="phase-info">
          <div class="phase-title">지식 그래프 구축</div>
          <div class="phase-api">/api/graph/build</div>
        </div>
        <span class="phase-status" :class="getPhaseStatusClass(1)">
          {{ getPhaseStatusText(1) }}
        </span>
      </div>

      <div class="phase-detail">
        <div class="detail-section">
          <div class="detail-label">API 설명</div>
          <div class="detail-content">
            Based on the generated ontology, documents are chunked and processed via the Zep API to build the knowledge graph, extracting entities and relations
          </div>
        </div>

        <div class="detail-section waiting-state" v-if="currentPhase < 1">
          <div class="waiting-hint">Waiting for ontology generation to complete...</div>
        </div>

        <div class="detail-section" v-if="buildProgress && currentPhase >= 1">
          <div class="detail-label">구축 진행률</div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: buildProgress.progress + '%' }"></div>
          </div>
          <div class="progress-info">
            <span class="progress-message">{{ buildProgress.message }}</span>
            <span class="progress-percent">{{ buildProgress.progress }}%</span>
          </div>
        </div>

        <div class="detail-section" v-if="graphData">
          <div class="detail-label">구축 결과</div>
          <div class="build-result">
            <div class="result-item">
              <span class="result-value">{{ graphData.node_count }}</span>
              <span class="result-label">엔티티 노드</span>
            </div>
            <div class="result-item">
              <span class="result-value">{{ graphData.edge_count }}</span>
              <span class="result-label">관계 엣지</span>
            </div>
            <div class="result-item">
              <span class="result-value">{{ entityTypes.length }}</span>
              <span class="result-label">엔티티 타입</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Phase 3: Complete -->
    <div class="process-phase" :class="{ 'active': currentPhase === 2, 'completed': currentPhase > 2 }">
      <div class="phase-header">
        <span class="phase-num">03</span>
        <div class="phase-info">
          <div class="phase-title">구축 완료</div>
          <div class="phase-api">다음 단계로 진행 가능</div>
        </div>
        <span class="phase-status" :class="getPhaseStatusClass(2)">
          {{ getPhaseStatusText(2) }}
        </span>
      </div>
    </div>

    <!-- Next step button -->
    <div class="next-step-section" v-if="currentPhase >= 2">
      <button class="next-step-btn" @click="$emit('nextStep')" :disabled="currentPhase < 2">
        Proceed to Environment Setup
        <span class="btn-arrow">→</span>
      </button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  currentPhase: { type: Number, required: true },
  ontologyProgress: { type: Object, default: null },
  projectData: { type: Object, default: null },
  buildProgress: { type: Object, default: null },
  graphData: { type: Object, default: null },
  entityTypes: { type: Array, default: () => [] },
})

defineEmits(['nextStep'])

const getPhaseStatusClass = (phase) => {
  if (props.currentPhase > phase) return 'completed'
  if (props.currentPhase === phase) return 'active'
  return 'pending'
}

const getPhaseStatusText = (phase) => {
  if (props.currentPhase > phase) return 'Completed'
  if (props.currentPhase === phase) {
    if (phase === 1 && props.buildProgress) {
      return `${props.buildProgress.progress}%`
    }
    return 'In Progress'
  }
  return 'Pending'
}
</script>

<style scoped>
.process-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.process-phase {
  margin-bottom: 24px;
  border: 1px solid #E0E0E0;
  opacity: 0.5;
  transition: all 0.3s;
}

.process-phase.active,
.process-phase.completed {
  opacity: 1;
}

.process-phase.active {
  border-color: #FF6B35;
}

.process-phase.completed {
  border-color: #1A936F;
}

.phase-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #E0E0E0;
}

.process-phase.active .phase-header {
  background: #FFF5F2;
}

.process-phase.completed .phase-header {
  background: #F2FAF6;
}

.phase-num {
  font-size: 1.5rem;
  font-weight: 700;
  color: #ddd;
  line-height: 1;
}

.process-phase.active .phase-num {
  color: #FF6B35;
}

.process-phase.completed .phase-num {
  color: #1A936F;
}

.phase-info {
  flex: 1;
}

.phase-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.phase-api {
  font-size: 0.75rem;
  color: #999;
  font-family: 'JetBrains Mono', monospace;
}

.phase-status {
  font-size: 0.75rem;
  padding: 4px 10px;
  background: #eee;
  color: #666;
}

.phase-status.active {
  background: #FF6B35;
  color: #fff;
}

.phase-status.completed {
  background: #1A936F;
  color: #fff;
}

.phase-detail {
  padding: 16px;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-label {
  font-size: 0.8rem;
  color: #999;
  min-width: 70px;
  flex-shrink: 0;
}

.detail-content {
  font-size: 0.85rem;
  color: #333;
}

.entity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  font-size: 0.75rem;
  padding: 4px 10px;
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  color: #333;
}

.relation-list {
  font-size: 0.8rem;
}

.relation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed #eee;
}

.relation-item:last-child {
  border-bottom: none;
}

.rel-source,
.rel-target {
  color: #333;
}

.rel-arrow {
  color: #ccc;
}

.rel-name {
  color: #FF6B35;
  font-weight: 500;
}

.relation-more {
  padding-top: 8px;
  color: #999;
  font-size: 0.75rem;
}

.ontology-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #FFF5F2;
  border: 1px solid #FFE0D6;
}

.progress-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #FFE0D6;
  border-top-color: #FF6B35;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.progress-text {
  font-size: 0.85rem;
  color: #333;
}

.waiting-state {
  padding: 16px;
  background: #F9F9F9;
  border: 1px dashed #E0E0E0;
  text-align: center;
}

.waiting-hint {
  font-size: 0.85rem;
  color: #999;
}

.progress-bar {
  height: 6px;
  background: #E0E0E0;
  margin-bottom: 8px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #FF6B35;
  transition: width 0.3s;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
}

.progress-message {
  color: #666;
}

.progress-percent {
  color: #FF6B35;
  font-weight: 600;
}

.build-result {
  display: flex;
  gap: 16px;
}

.result-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: #F5F5F5;
}

.result-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #000;
  margin-bottom: 4px;
}

.result-label {
  font-size: 0.7rem;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.next-step-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #E0E0E0;
}

.next-step-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  background: #000;
  color: #fff;
  border: none;
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s;
}

.next-step-btn:hover:not(:disabled) {
  background: #FF6B35;
}

.next-step-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-arrow {
  font-size: 1.2rem;
}
</style>
