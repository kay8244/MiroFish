<template>
  <div class="detail-panel">
    <div class="detail-panel-header">
      <span class="detail-title">{{ item.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
      <span v-if="item.type === 'node'" class="detail-badge" :style="{ background: item.color }">
        {{ item.entityType }}
      </span>
      <button class="detail-close" @click="$emit('close')">×</button>
    </div>

    <!-- Node details -->
    <div v-if="item.type === 'node'" class="detail-content">
      <div class="detail-row">
        <span class="detail-label">Name:</span>
        <span class="detail-value highlight">{{ item.data.name }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">UUID:</span>
        <span class="detail-value uuid">{{ item.data.uuid }}</span>
      </div>
      <div class="detail-row" v-if="item.data.created_at">
        <span class="detail-label">Created:</span>
        <span class="detail-value">{{ formatDate(item.data.created_at) }}</span>
      </div>

      <div class="detail-section" v-if="item.data.attributes && Object.keys(item.data.attributes).length > 0">
        <span class="detail-label">Properties:</span>
        <div class="properties-list">
          <div v-for="(value, key) in item.data.attributes" :key="key" class="property-item">
            <span class="property-key">{{ key }}:</span>
            <span class="property-value">{{ value }}</span>
          </div>
        </div>
      </div>

      <div class="detail-section" v-if="item.data.summary">
        <span class="detail-label">Summary:</span>
        <p class="detail-summary">{{ item.data.summary }}</p>
      </div>

      <div class="detail-row" v-if="item.data.labels?.length">
        <span class="detail-label">Labels:</span>
        <div class="detail-labels">
          <span v-for="label in item.data.labels" :key="label" class="label-tag">{{ label }}</span>
        </div>
      </div>
    </div>

    <!-- Edge details -->
    <div v-else class="detail-content">
      <div class="edge-relation">
        <span class="edge-source">{{ item.data.source_name || item.data.source_node_name }}</span>
        <span class="edge-arrow">→</span>
        <span class="edge-type">{{ item.data.name || item.data.fact_type || 'RELATED_TO' }}</span>
        <span class="edge-arrow">→</span>
        <span class="edge-target">{{ item.data.target_name || item.data.target_node_name }}</span>
      </div>

      <div class="detail-subtitle">관계</div>

      <div class="detail-row">
        <span class="detail-label">UUID:</span>
        <span class="detail-value uuid">{{ item.data.uuid }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Label:</span>
        <span class="detail-value">{{ item.data.name || item.data.fact_type || 'RELATED_TO' }}</span>
      </div>
      <div class="detail-row" v-if="item.data.fact_type">
        <span class="detail-label">Type:</span>
        <span class="detail-value">{{ item.data.fact_type }}</span>
      </div>

      <div class="detail-section" v-if="item.data.fact">
        <span class="detail-label">Fact:</span>
        <p class="detail-summary">{{ item.data.fact }}</p>
      </div>

      <div class="detail-section" v-if="item.data.episodes?.length">
        <span class="detail-label">Episodes:</span>
        <div class="episodes-list">
          <span v-for="ep in item.data.episodes" :key="ep" class="episode-tag">{{ ep }}</span>
        </div>
      </div>

      <div class="detail-row" v-if="item.data.created_at">
        <span class="detail-label">Created:</span>
        <span class="detail-value">{{ formatDate(item.data.created_at) }}</span>
      </div>
      <div class="detail-row" v-if="item.data.valid_at">
        <span class="detail-label">Valid From:</span>
        <span class="detail-value">{{ formatDate(item.data.valid_at) }}</span>
      </div>
      <div class="detail-row" v-if="item.data.invalid_at">
        <span class="detail-label">Invalid At:</span>
        <span class="detail-value">{{ formatDate(item.data.invalid_at) }}</span>
      </div>
      <div class="detail-row" v-if="item.data.expired_at">
        <span class="detail-label">Expired At:</span>
        <span class="detail-value">{{ formatDate(item.data.expired_at) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  item: { type: Object, required: true }
})

defineEmits(['close'])

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
.detail-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 320px;
  max-height: calc(100% - 32px);
  background: #fff;
  border: 1px solid #E0E0E0;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.detail-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #E0E0E0;
}

.detail-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
}

.detail-badge {
  padding: 2px 10px;
  font-size: 0.75rem;
  color: #fff;
  border-radius: 2px;
}

.detail-close {
  margin-left: auto;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  font-size: 1.2rem;
  color: #999;
  cursor: pointer;
  transition: color 0.2s;
}

.detail-close:hover {
  color: #333;
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}

.detail-label {
  font-size: 0.8rem;
  color: #999;
  min-width: 70px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 0.85rem;
  color: #333;
  word-break: break-word;
}

.detail-value.uuid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}

.detail-value.highlight {
  font-weight: 600;
  color: #000;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-summary {
  margin: 8px 0 0 0;
  font-size: 0.85rem;
  color: #333;
  line-height: 1.6;
  padding: 10px;
  background: #F9F9F9;
  border-left: 3px solid #FF6B35;
}

.detail-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.label-tag {
  padding: 2px 8px;
  font-size: 0.75rem;
  background: #F0F0F0;
  border: 1px solid #E0E0E0;
  color: #666;
}

.detail-subtitle {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #E0E0E0;
}

.edge-relation {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #F9F9F9;
  border: 1px solid #E0E0E0;
}

.edge-source,
.edge-target {
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
}

.edge-arrow {
  color: #999;
}

.edge-type {
  padding: 2px 8px;
  font-size: 0.75rem;
  background: #FF6B35;
  color: #fff;
}

.properties-list {
  margin-top: 8px;
  padding: 10px;
  background: #F9F9F9;
  border: 1px solid #E0E0E0;
}

.property-item {
  display: flex;
  margin-bottom: 6px;
  font-size: 0.85rem;
}

.property-item:last-child {
  margin-bottom: 0;
}

.property-key {
  color: #666;
  margin-right: 8px;
  font-family: 'JetBrains Mono', monospace;
}

.property-value {
  color: #333;
  word-break: break-word;
}

.episodes-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-tag {
  display: block;
  padding: 6px 10px;
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  background: #F0F0F0;
  border: 1px solid #E0E0E0;
  color: #666;
  word-break: break-all;
}
</style>
