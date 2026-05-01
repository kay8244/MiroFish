<template>
  <div class="project-panel">
    <div class="project-header">
      <span class="project-icon">◇</span>
      <span class="project-title">프로젝트 정보</span>
    </div>
    <div class="project-details" v-if="projectData">
      <div class="project-item">
        <span class="item-label">프로젝트 이름</span>
        <span class="item-value">{{ projectData.name }}</span>
      </div>
      <div class="project-item">
        <span class="item-label">프로젝트 ID</span>
        <span class="item-value code">{{ projectData.project_id }}</span>
      </div>
      <div class="project-item" v-if="projectData.graph_id">
        <span class="item-label">그래프 ID</span>
        <span class="item-value code">{{ projectData.graph_id }}</span>
      </div>
      <div class="project-item">
        <span class="item-label">시뮬레이션 요청</span>
        <span class="item-value">{{ projectData.simulation_requirement || '-' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  projectData: { type: Object, default: null }
})
</script>

<style scoped>
.project-panel {
  border-top: 1px solid #E0E0E0;
  background: #FAFAFA;
}

.project-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  border-bottom: 1px solid #E0E0E0;
}

.project-icon {
  color: #FF6B35;
}

.project-title {
  font-size: 0.85rem;
  font-weight: 600;
}

.project-details {
  padding: 16px 24px;
}

.project-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px dashed #E0E0E0;
  font-size: 0.8rem;
}

.project-item:last-child {
  border-bottom: none;
}

.item-label {
  color: #999;
  flex-shrink: 0;
}

.item-value {
  color: #333;
  text-align: right;
  max-width: 60%;
  word-break: break-all;
}

.item-value.code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}
</style>
