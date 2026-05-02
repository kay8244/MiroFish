<template>
  <div class="action-bar">
    <div class="action-bar-header">
      <svg class="action-bar-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
      <div class="action-bar-text">
        <span class="action-bar-title">인터랙션 도구</span>
        <span class="action-bar-subtitle mono">에이전트 {{ profiles.length }}명 가능</span>
      </div>
    </div>
    <div class="action-bar-tabs">
      <button
        class="tab-pill"
        :class="{ active: activeTab === 'chat' && chatTarget === 'report_agent' }"
        @click="$emit('select-report-agent')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
        </svg>
        <span>리포트 에이전트와 대화</span>
      </button>
      <div class="agent-dropdown" v-if="profiles.length > 0">
        <button
          class="tab-pill agent-pill"
          :class="{ active: activeTab === 'chat' && chatTarget === 'agent' }"
          @click="$emit('toggle-dropdown')"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          <span>{{ selectedAgent ? selectedAgent.username : 'Chat with any individual in the world' }}</span>
          <svg class="dropdown-arrow" :class="{ open: showAgentDropdown }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
        <div v-if="showAgentDropdown" class="dropdown-menu">
          <div class="dropdown-header">대화 대상 선택</div>
          <div
            v-for="(agent, idx) in profiles"
            :key="idx"
            class="dropdown-item"
            @click="$emit('select-agent', agent, idx)"
          >
            <div class="agent-avatar">{{ (agent.username || 'A')[0] }}</div>
            <div class="agent-info">
              <span class="agent-name">{{ agent.username }}</span>
              <span class="agent-role">{{ agent.profession || 'Unknown profession' }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="tab-divider"></div>
      <button
        class="tab-pill survey-pill"
        :class="{ active: activeTab === 'survey' }"
        @click="$emit('select-survey')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
        <span>세계에 설문 전송</span>
      </button>
      <button
        class="tab-pill scenario-pill"
        :class="{ active: activeTab === 'scenario' }"
        @click="$emit('select-scenario')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <circle cx="12" cy="12" r="6"></circle>
          <circle cx="12" cy="12" r="2"></circle>
        </svg>
        <span>새 시나리오 실행</span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  profiles: { type: Array, required: true },
  activeTab: { type: String, required: true },
  chatTarget: { type: String, required: true },
  selectedAgent: { type: Object, default: null },
  showAgentDropdown: { type: Boolean, default: false }
})

defineEmits(['select-report-agent', 'toggle-dropdown', 'select-agent', 'select-survey', 'select-scenario'])
</script>

<style scoped>
.mono {
  font-family: 'JetBrains Mono', 'SF Mono', 'Monaco', 'Consolas', monospace;
}

/* Action Bar */
.action-bar {
  background: #FFFFFF;
  border-bottom: 1px solid #E5E7EB;
  padding: 16px 20px;
  flex-shrink: 0;
}

.action-bar-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.action-bar-icon {
  color: #374151;
  flex-shrink: 0;
}

.action-bar-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-bar-title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.action-bar-subtitle {
  font-size: 11px;
  color: #9CA3AF;
}

.action-bar-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tab-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid #E5E7EB;
  background: #F9FAFB;
  font-size: 12px;
  font-weight: 500;
  color: #6B7280;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab-pill:hover {
  background: #F3F4F6;
  border-color: #D1D5DB;
  color: #374151;
}

.tab-pill.active {
  background: #111827;
  border-color: #111827;
  color: #FFFFFF;
}

.tab-divider {
  width: 1px;
  height: 20px;
  background: #E5E7EB;
  flex-shrink: 0;
}

/* Agent Dropdown */
.agent-dropdown {
  position: relative;
}

.dropdown-arrow {
  transition: transform 0.2s;
}

.dropdown-arrow.open {
  transform: rotate(180deg);
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  min-width: 220px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  z-index: 50;
  overflow: hidden;
}

.dropdown-header {
  padding: 10px 14px;
  font-size: 11px;
  font-weight: 600;
  color: #9CA3AF;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid #F3F4F6;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.dropdown-item:hover {
  background: #F9FAFB;
}

.agent-avatar {
  width: 28px;
  height: 28px;
  background: #374151;
  color: #FFF;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.agent-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.agent-role {
  font-size: 11px;
  color: #9CA3AF;
}
</style>
