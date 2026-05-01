<template>
  <div class="step-card" :class="{ 'active': phase === 0, 'completed': phase > 0 }">
    <div class="card-header">
      <div class="step-info">
        <span class="step-num">01</span>
        <span class="step-title">시뮬레이션 인스턴스 초기화</span>
      </div>
      <div class="step-status">
        <span v-if="phase > 0" class="badge success">완료</span>
        <span v-else class="badge processing">초기화 중</span>
      </div>
    </div>

    <div class="card-content">
      <p class="api-note">POST /api/simulation/create</p>
      <p class="description">
        Create a new simulation instance and pull the simulation world parameter template
      </p>

      <div v-if="simulationId" class="info-card">
        <div class="info-row">
          <span class="info-label">프로젝트 ID</span>
          <span class="info-value mono">{{ projectData?.project_id }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">그래프 ID</span>
          <span class="info-value mono">{{ projectData?.graph_id }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">시뮬레이션 ID</span>
          <span class="info-value mono">{{ simulationId }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">태스크 ID</span>
          <span class="info-value mono">{{ taskId || 'Async task completed' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  phase: { type: Number, required: true },
  simulationId: { type: String, default: null },
  projectData: { type: Object, default: null },
  taskId: { type: String, default: null },
})
</script>

<style scoped src="./_step-framework.css"></style>
<style scoped>
.info-card {
  background: #F5F5F5;
  border-radius: 6px;
  padding: 16px;
  margin-top: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed #E0E0E0;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 12px;
  color: #666;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
}

.info-value.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
</style>
