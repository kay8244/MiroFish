<template>
  <div class="system-log-panel" v-if="logs.length > 0">
    <div class="log-header">
      <span class="log-icon">📋</span>
      <span class="log-title">{{ title }}</span>
      <span class="log-count">{{ logs.length }}</span>
    </div>
    <div class="log-content" ref="logContent">
      <div v-for="(log, idx) in logs" :key="idx" class="log-entry">
        <span class="log-time" v-if="log.time">{{ log.time }}</span>
        <span class="log-message">{{ log.message || log }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  logs: { type: Array, default: () => [] },
  title: { type: String, default: '시스템 로그' },
  autoScroll: { type: Boolean, default: true }
})

const logContent = ref(null)

// 자동 스크롤
watch(() => props.logs.length, async () => {
  if (props.autoScroll && logContent.value) {
    await nextTick()
    logContent.value.scrollTop = logContent.value.scrollHeight
  }
})
</script>

<style scoped>
.system-log-panel {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  margin: 12px 0;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 13px;
  font-weight: 600;
}
.log-count {
  background: #e2e8f0;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 11px;
}
.log-content {
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 12px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  background: #1e293b;
  color: #e2e8f0;
}
.log-entry {
  display: flex;
  gap: 8px;
}
.log-time {
  color: #94a3b8;
  flex-shrink: 0;
}
.log-message {
  word-break: break-all;
}
</style>
