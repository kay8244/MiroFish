<template>
  <div class="survey-container">
    <!-- Survey Setup -->
    <div class="survey-setup">
      <div class="setup-section">
        <div class="section-header">
          <span class="section-title">설문 대상 선택</span>
          <span class="selection-count">Selected {{ selectedAgents.size }} / {{ profiles.length }}</span>
        </div>
        <div class="agents-grid">
          <label
            v-for="(agent, idx) in profiles"
            :key="idx"
            class="agent-checkbox"
            :class="{ checked: selectedAgents.has(idx) }"
          >
            <input
              type="checkbox"
              :checked="selectedAgents.has(idx)"
              @change="$emit('toggle-agent', idx)"
            >
            <div class="checkbox-avatar">{{ (agent.username || 'A')[0] }}</div>
            <div class="checkbox-info">
              <span class="checkbox-name">{{ agent.username }}</span>
              <span class="checkbox-role">{{ agent.profession || 'Unknown profession' }}</span>
            </div>
            <div class="checkbox-indicator">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
          </label>
        </div>
        <div class="selection-actions">
          <button class="action-link" @click="$emit('select-all')">전체 선택</button>
          <span class="action-divider">|</span>
          <button class="action-link" @click="$emit('clear-selection')">선택 해제</button>
        </div>
      </div>

      <div class="setup-section">
        <div class="section-header">
          <span class="section-title">설문 질문</span>
        </div>
        <textarea
          :value="surveyQuestion"
          @input="$emit('update:surveyQuestion', $event.target.value)"
          class="survey-input"
          placeholder="선택한 모든 대상에게 묻고 싶은 질문을 입력하세요..."
          rows="3"
        ></textarea>
      </div>

      <button
        class="survey-submit-btn"
        :disabled="selectedAgents.size === 0 || !surveyQuestion.trim() || isSurveying"
        @click="$emit('submit')"
      >
        <span v-if="isSurveying" class="loading-spinner"></span>
        <span v-else>설문 전송</span>
      </button>
    </div>

    <!-- Survey Results -->
    <div v-if="surveyResults.length > 0" class="survey-results">
      <div class="results-header">
        <span class="results-title">설문 결과</span>
        <span class="results-count">{{ surveyResults.length }} responses</span>
      </div>
      <div class="results-list">
        <div
          v-for="(result, idx) in surveyResults"
          :key="idx"
          class="result-card"
        >
          <div class="result-header">
            <div class="result-avatar">{{ (result.agent_name || 'A')[0] }}</div>
            <div class="result-info">
              <span class="result-name">{{ result.agent_name }}</span>
              <span class="result-role">{{ result.profession || 'Unknown profession' }}</span>
            </div>
          </div>
          <div class="result-question">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            <span>{{ result.question }}</span>
          </div>
          <div class="result-answer" v-html="renderMarkdown(result.answer)"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  profiles: { type: Array, required: true },
  selectedAgents: { type: Set, required: true },
  surveyQuestion: { type: String, default: '' },
  surveyResults: { type: Array, default: () => [] },
  isSurveying: { type: Boolean, default: false },
  renderMarkdown: { type: Function, required: true }
})

defineEmits(['toggle-agent', 'select-all', 'clear-selection', 'update:surveyQuestion', 'submit'])
</script>

<style scoped>
/* Survey Container */
.survey-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.survey-setup {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.setup-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.selection-count {
  font-size: 12px;
  color: #9CA3AF;
}

.agents-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.agent-checkbox {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.agent-checkbox:hover {
  background: #F9FAFB;
}

.agent-checkbox.checked {
  background: #F0FDF4;
  border-color: #BBF7D0;
}

.agent-checkbox input {
  display: none;
}

.checkbox-avatar {
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

.checkbox-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.checkbox-name {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.checkbox-role {
  font-size: 11px;
  color: #9CA3AF;
}

.checkbox-indicator {
  color: #16A34A;
  opacity: 0;
  transition: opacity 0.15s;
}

.agent-checkbox.checked .checkbox-indicator {
  opacity: 1;
}

.selection-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-link {
  background: none;
  border: none;
  font-size: 12px;
  color: #6B7280;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  transition: color 0.15s;
}

.action-link:hover {
  color: #374151;
}

.action-divider {
  color: #D1D5DB;
  font-size: 12px;
}

.survey-input {
  width: 100%;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
  line-height: 1.5;
}

.survey-input:focus {
  border-color: #374151;
}

.survey-submit-btn {
  width: 100%;
  padding: 12px;
  background: #111827;
  color: #FFF;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.survey-submit-btn:hover:not(:disabled) {
  background: #374151;
}

.survey-submit-btn:disabled {
  background: #E5E7EB;
  color: #9CA3AF;
  cursor: not-allowed;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #FFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* Survey Results */
.survey-results {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #E5E7EB;
  background: #F9FAFB;
}

.results-title {
  font-size: 13px;
  font-weight: 700;
  color: #374151;
}

.results-count {
  font-size: 12px;
  color: #9CA3AF;
}

.results-list {
  display: flex;
  flex-direction: column;
}

.result-card {
  padding: 16px 20px;
  border-bottom: 1px solid #F3F4F6;
}

.result-card:last-child {
  border-bottom: none;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.result-avatar {
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

.result-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.result-name {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.result-role {
  font-size: 11px;
  color: #9CA3AF;
}

.result-question {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: #6B7280;
  margin-bottom: 8px;
  background: #F9FAFB;
  padding: 8px 10px;
  border-radius: 4px;
}

.result-question svg {
  flex-shrink: 0;
  margin-top: 1px;
}

.result-answer {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
}
</style>
