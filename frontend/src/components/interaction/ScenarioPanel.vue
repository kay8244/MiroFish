<template>
  <div class="scenario-panel">
    <div class="scenario-header">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <circle cx="12" cy="12" r="6"></circle>
        <circle cx="12" cy="12" r="2"></circle>
      </svg>
      <div class="scenario-text">
        <h3>새 시나리오 시뮬레이션</h3>
        <p class="hint">
          기존 그래프 + 에이전트 페르소나를 그대로 재사용해 다른 질문으로 시뮬을 돌립니다.
          그래프 빌드 비용 절감 (~$0.30 → $0). 시뮬+보고서만 새로 생성됩니다.
        </p>
      </div>
    </div>

    <div class="scenario-form">
      <label class="field-label" for="scenario-input">새 시나리오 질문</label>
      <textarea
        id="scenario-input"
        v-model="scenarioInput"
        :disabled="run.isRunning.value"
        placeholder="예) TSMC CoWoS 생산 50% 감축이 발생한다면 한국 반도체 공급망 참여자들은 어떻게 반응할까?"
        rows="4"
        class="scenario-textarea"
      ></textarea>
      <div class="form-actions">
        <button
          class="btn-primary"
          :disabled="run.isRunning.value || !scenarioInput.trim()"
          @click="onSubmit"
        >
          <span v-if="!run.isRunning.value">시나리오 시작</span>
          <span v-else>실행 중...</span>
        </button>
        <button
          v-if="run.phase.value !== run.PHASE.IDLE && !run.isRunning.value"
          class="btn-secondary"
          @click="run.reset"
        >
          초기화
        </button>
      </div>
    </div>

    <!-- 진행 상태 -->
    <div v-if="run.phase.value !== run.PHASE.IDLE" class="scenario-progress">
      <div class="progress-list">
        <div
          v-for="step in steps"
          :key="step.key"
          class="progress-item"
          :class="stepClass(step.key)"
        >
          <span class="progress-dot"></span>
          <span class="progress-label">{{ step.label }}</span>
          <span v-if="isCurrent(step.key)" class="progress-spinner"></span>
        </div>
      </div>

      <div class="progress-message">{{ run.phaseLabel.value }}</div>

      <div v-if="run.phase.value === run.PHASE.ERROR" class="error-banner">
        ⚠ {{ run.errorMessage.value }}
      </div>

      <div v-if="run.phase.value === run.PHASE.DONE && run.newReportId.value" class="success-banner">
        ✓ 새 보고서 준비 완료
        <button class="btn-link" @click="goToNewReport">새 보고서 보기</button>
      </div>

      <div v-if="run.newSimulationId.value" class="meta-line">
        new sim_id: <code>{{ run.newSimulationId.value }}</code>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useScenarioRun } from '../../composables/useScenarioRun'

const props = defineProps({
  simulationId: { type: String, required: true },
})

const router = useRouter()
const scenarioInput = ref('')
const run = useScenarioRun()

const steps = [
  { key: 'CREATING', label: '시뮬 생성' },
  { key: 'PREPARING', label: '에이전트 준비' },
  { key: 'SIMULATING', label: 'OASIS 시뮬레이션' },
  { key: 'REPORTING', label: '보고서 생성' },
]

const phaseOrder = computed(() => ['CREATING', 'PREPARING', 'SIMULATING', 'REPORTING', 'DONE'])

const isCurrent = (key) => run.phase.value === run.PHASE[key]

const stepClass = (key) => {
  const order = phaseOrder.value
  const currentIdx = order.indexOf(
    Object.entries(run.PHASE).find(([k, v]) => v === run.phase.value)?.[0] || ''
  )
  const stepIdx = order.indexOf(key)
  if (run.phase.value === run.PHASE.ERROR && currentIdx === -1) return 'failed'
  if (stepIdx < currentIdx) return 'done'
  if (stepIdx === currentIdx) return 'active'
  return 'pending'
}

const onSubmit = async () => {
  await run.runScenario({
    simulationId: props.simulationId,
    simulationRequirement: scenarioInput.value,
  })
}

const goToNewReport = () => {
  if (!run.newReportId.value) return
  router.push({ name: 'Interaction', params: { reportId: run.newReportId.value } })
}
</script>

<style scoped>
.scenario-panel {
  padding: 20px;
  background: #FFFFFF;
  display: flex;
  flex-direction: column;
  gap: 18px;
  height: 100%;
  overflow-y: auto;
}

.scenario-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding-bottom: 14px;
  border-bottom: 1px solid #E5E7EB;
}

.scenario-header svg {
  color: #2563EB;
  flex-shrink: 0;
  margin-top: 2px;
}

.scenario-text h3 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.scenario-text .hint {
  margin: 0;
  font-size: 12px;
  color: #6B7280;
  line-height: 1.5;
}

.scenario-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.scenario-textarea {
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  padding: 10px 12px;
  border: 1px solid #D1D5DB;
  border-radius: 6px;
  resize: vertical;
  min-height: 80px;
  outline: none;
  transition: border-color 0.15s;
}

.scenario-textarea:focus {
  border-color: #2563EB;
}

.scenario-textarea:disabled {
  background: #F9FAFB;
  color: #6B7280;
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn-primary {
  background: #2563EB;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary:hover:not(:disabled) {
  background: #1D4ED8;
}

.btn-primary:disabled {
  background: #9CA3AF;
  cursor: not-allowed;
}

.btn-secondary {
  background: white;
  color: #374151;
  border: 1px solid #D1D5DB;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #F9FAFB;
}

.scenario-progress {
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.progress-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #D1D5DB;
}

.progress-item.done .progress-dot {
  background: #10B981;
}

.progress-item.active .progress-dot {
  background: #2563EB;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.2);
}

.progress-item.failed .progress-dot {
  background: #EF4444;
}

.progress-item.pending .progress-label {
  color: #9CA3AF;
}

.progress-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #E5E7EB;
  border-top-color: #2563EB;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.progress-message {
  font-size: 12px;
  color: #4B5563;
  font-style: italic;
}

.error-banner {
  background: #FEF2F2;
  color: #B91C1C;
  border: 1px solid #FECACA;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.success-banner {
  background: #F0FDF4;
  color: #166534;
  border: 1px solid #BBF7D0;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-link {
  background: none;
  border: none;
  color: #166534;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
}

.meta-line {
  font-size: 11px;
  color: #6B7280;
}

.meta-line code {
  font-family: 'JetBrains Mono', monospace;
  background: #E5E7EB;
  padding: 1px 6px;
  border-radius: 3px;
}
</style>
