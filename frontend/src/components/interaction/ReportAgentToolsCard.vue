<template>
  <div class="report-agent-tools-card">
    <div class="tools-card-header">
      <div class="tools-card-avatar">R</div>
      <div class="tools-card-info">
        <div class="tools-card-name">Report Agent - Chat</div>
        <div class="tools-card-subtitle">Quick-chat version of the report generation agent. Can invoke 4 specialized tools and has full MiroFish memory.</div>
      </div>
      <button class="tools-card-toggle" @click="expanded = !expanded">
        <svg :class="{ 'is-expanded': expanded }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
    </div>
    <div v-if="expanded" class="tools-card-body">
      <div class="tools-grid">
        <div class="tool-item tool-purple">
          <div class="tool-icon-wrapper">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.5V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.5A7 7 0 0 0 12 2z"></path>
            </svg>
          </div>
          <div class="tool-content">
            <div class="tool-name">인사이트포지 심층 분석</div>
            <div class="tool-desc">Aligns real-world seed data with simulation state. Uses Global/Local Memory mechanisms to deliver cross-temporal deep attribution analysis.</div>
          </div>
        </div>
        <div class="tool-item tool-blue">
          <div class="tool-icon-wrapper">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
          </div>
          <div class="tool-content">
            <div class="tool-name">파노라마서치 전역 추적</div>
            <div class="tool-desc">Graph-based breadth-first traversal algorithm. Reconstructs event propagation paths and captures the full topology of information flow.</div>
          </div>
        </div>
        <div class="tool-item tool-orange">
          <div class="tool-icon-wrapper">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
          </div>
          <div class="tool-content">
            <div class="tool-name">퀵서치 빠른 조회</div>
            <div class="tool-desc">GraphRAG-based instant query interface with optimized indexing. Used for rapid extraction of specific node attributes and discrete facts.</div>
          </div>
        </div>
        <div class="tool-item tool-green">
          <div class="tool-icon-wrapper">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
              <circle cx="9" cy="7" r="4"></circle>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"></path>
            </svg>
          </div>
          <div class="tool-content">
            <div class="tool-name">인터뷰서브에이전트 가상 인터뷰</div>
            <div class="tool-desc">Autonomous interviewer that conducts parallel multi-turn conversations with individuals in the simulated world, collecting unstructured opinion data and psychological states.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  showToolsDetail: { type: Boolean, default: true }
})

const expanded = ref(props.showToolsDetail)
</script>

<style scoped>
.report-agent-tools-card {
  background: #FFFFFF;
  border-bottom: 1px solid #E5E7EB;
  flex-shrink: 0;
}

.tools-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
}

.tools-card-avatar {
  width: 36px;
  height: 36px;
  background: #111827;
  color: #FFF;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}

.tools-card-info {
  flex: 1;
  min-width: 0;
}

.tools-card-name {
  font-size: 13px;
  font-weight: 700;
  color: #111827;
}

.tools-card-subtitle {
  font-size: 11px;
  color: #9CA3AF;
  line-height: 1.4;
  margin-top: 2px;
}

.tools-card-toggle {
  background: none;
  border: none;
  cursor: pointer;
  color: #9CA3AF;
  padding: 4px;
  display: flex;
  align-items: center;
  transition: color 0.2s;
}

.tools-card-toggle svg {
  transition: transform 0.3s;
}

.tools-card-toggle svg.is-expanded {
  transform: rotate(180deg);
}

.tools-card-body {
  padding: 0 20px 16px;
}

.tools-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.tool-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
}

.tool-purple { background: #F5F3FF; border-color: #EDE9FE; }
.tool-blue { background: #EFF6FF; border-color: #DBEAFE; }
.tool-orange { background: #FFF7ED; border-color: #FED7AA; }
.tool-green { background: #F0FDF4; border-color: #BBF7D0; }

.tool-icon-wrapper {
  flex-shrink: 0;
  margin-top: 2px;
}

.tool-purple .tool-icon-wrapper { color: #7C3AED; }
.tool-blue .tool-icon-wrapper { color: #2563EB; }
.tool-orange .tool-icon-wrapper { color: #EA580C; }
.tool-green .tool-icon-wrapper { color: #16A34A; }

.tool-content {
  min-width: 0;
}

.tool-name {
  font-size: 11px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 3px;
}

.tool-desc {
  font-size: 10px;
  color: #6B7280;
  line-height: 1.4;
}
</style>
