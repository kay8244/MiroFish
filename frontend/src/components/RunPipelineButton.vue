<template>
  <div class="run-pipeline-button">
    <!-- Trigger panel (before run) -->
    <section v-if="!runId" class="trigger-panel">
      <h3 class="panel-title">Pipeline 실행</h3>
      <p class="panel-desc">
        Seed 문서 업로드 → Ontology + Zep 그래프 구축 → Agents → OASIS 시뮬레이션 → Report 생성.
        5단계가 비동기로 순차 실행됩니다.
      </p>

      <label class="field">
        <span class="field-label">Seed 파일 (PDF/MD/TXT, 최대 50MB/개)</span>
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".pdf,.md,.txt,.markdown"
          @change="onFileChange"
        />
      </label>

      <div v-if="selectedFiles.length > 0" class="file-list">
        <div v-for="f in selectedFiles" :key="f.name" class="file-row">
          <span class="file-name">{{ f.name }}</span>
          <span class="file-size">{{ formatSize(f.size) }}</span>
        </div>
      </div>

      <label class="field">
        <span class="field-label">Assumptions 버전</span>
        <input
          v-model="assumptionsVersion"
          type="text"
          placeholder="ai_server_si_wafer_v1"
        />
      </label>

      <details class="advanced">
        <summary>고급 옵션 (extra_config)</summary>

        <label class="field inline">
          <span class="field-label">max_rounds (비워두면 무제한)</span>
          <input
            v-model.number="maxRounds"
            type="number"
            min="1"
            max="500"
            placeholder="20"
          />
        </label>

        <label class="field inline checkbox">
          <input v-model="enableTwitter" type="checkbox" />
          <span>Twitter 플랫폼 활성화</span>
        </label>

        <label class="field inline checkbox">
          <input v-model="enableReddit" type="checkbox" />
          <span>Reddit 플랫폼 활성화</span>
        </label>

        <label class="field inline">
          <span class="field-label">parallel_profile_count</span>
          <input
            v-model.number="parallelProfileCount"
            type="number"
            min="1"
            max="10"
          />
        </label>

        <label class="field">
          <span class="field-label">simulation_requirement (override)</span>
          <textarea
            v-model="simulationRequirement"
            rows="3"
            placeholder="기본값 사용하려면 비워두세요"
          />
        </label>
      </details>

      <button
        class="run-btn primary"
        :disabled="startDisabled"
        @click="startRun"
      >
        {{ starting ? '시작 중...' : '실행 시작' }}
      </button>

      <p v-if="startError" class="error-text">
        시작 실패: {{ startError }}
      </p>
    </section>

    <!-- Progress panel (after run started) -->
    <section v-else class="progress-panel">
      <header class="progress-header">
        <div>
          <h3 class="panel-title">Pipeline 진행 중</h3>
          <p class="run-id">
            run_id: <code>{{ runId }}</code>
            <span class="status-pill" :class="`status-${status || 'pending'}`">
              {{ status || '초기화' }}
            </span>
          </p>
        </div>
        <div class="header-actions">
          <button class="secondary-btn" @click="fetchManifest">Manifest</button>
          <button
            class="secondary-btn"
            :disabled="!isTerminal"
            @click="resetForNewRun"
          >
            새 실행
          </button>
        </div>
      </header>

      <!-- Error block (A3 error surface) -->
      <div v-if="error" class="error-block">
        <div class="error-head">
          <strong>❌ {{ stepLabel(error.step) }} 실패</strong>
          <span class="error-retries">
            재시도 {{ error.retry_count }}/3
            <span v-if="error.retry_exhausted">(소진)</span>
            <span v-if="error.wall_clock_exceeded"> · wall-clock 초과</span>
          </span>
        </div>
        <pre class="error-summary">{{ error.summary || '요약 없음' }}</pre>
        <div class="error-actions">
          <button
            class="resume-btn"
            :disabled="!resumableFrom || resuming"
            @click="resume"
          >
            {{ resuming ? '재개 중...' : resumableFrom ? `${stepLabel(resumableFrom)}부터 재개` : '재개 불가' }}
          </button>
          <a
            v-if="error.manifest_url"
            :href="error.manifest_url"
            target="_blank"
            rel="noopener"
            class="manifest-link"
          >manifest 원본 열기 ↗</a>
        </div>
        <p v-if="resumeError" class="error-text">
          재개 실패: {{ resumeError }}
        </p>
      </div>

      <!-- 5-step progress rows -->
      <ol class="steps">
        <li
          v-for="s in steps"
          :key="s.name"
          class="step-row"
          :class="[`status-${s.status}`, { current: currentStep === s.name }]"
        >
          <span class="step-idx">{{ stepIndex(s.name) + 1 }}</span>
          <span class="step-name">{{ stepLabel(s.name) }}</span>
          <span class="step-status">{{ statusBadge(s.status) }}</span>
          <span class="step-metrics">
            <span v-if="s.duration_s">{{ s.duration_s }}s</span>
            <span v-if="s.llm_calls">· LLM {{ s.llm_calls }}회</span>
            <span v-if="s.retry_count">· 재시도 {{ s.retry_count }}</span>
          </span>
        </li>
      </ol>

      <div class="polling-hint">
        <span v-if="polling">2초 간격 폴링 중...</span>
        <span v-else>폴링 중지</span>
        <span v-if="lastPolledAt"> · 마지막 갱신 {{ relativeTime(lastPolledAt) }}</span>
      </div>

      <div v-if="manifestJson" class="manifest-block">
        <header>
          <strong>Manifest</strong>
          <button class="tiny-btn" @click="manifestJson = null">닫기</button>
        </header>
        <pre>{{ manifestPretty }}</pre>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import {
  startPipelineRun,
  getPipelineStatus,
  getPipelineManifest,
  resumePipelineRun,
  PIPELINE_STEP_LABELS,
  PIPELINE_STEP_NAMES
} from '../api/pipeline'

const fileInputRef = ref(null)
const selectedFiles = ref([])
const assumptionsVersion = ref('ai_server_si_wafer_v1')
const maxRounds = ref(20)
const enableTwitter = ref(true)
const enableReddit = ref(true)
const parallelProfileCount = ref(3)
const simulationRequirement = ref('')

const starting = ref(false)
const startError = ref('')

const runId = ref(null)
const status = ref(null)
const currentStep = ref(null)
const resumableFrom = ref(null)
const error = ref(null)
const steps = ref(
  PIPELINE_STEP_NAMES.map((name) => ({
    name,
    status: 'pending',
    duration_s: 0,
    llm_calls: 0,
    retry_count: 0
  }))
)

const polling = ref(false)
const lastPolledAt = ref(null)
const resuming = ref(false)
const resumeError = ref('')
const manifestJson = ref(null)

let pollTimer = null

const startDisabled = computed(
  () => selectedFiles.value.length === 0 || starting.value
)

const isTerminal = computed(() => ['completed', 'failed'].includes(status.value))

const manifestPretty = computed(() =>
  manifestJson.value ? JSON.stringify(manifestJson.value, null, 2) : ''
)

function onFileChange(e) {
  selectedFiles.value = Array.from(e.target.files || [])
}

function buildExtraConfig() {
  const cfg = {}
  if (maxRounds.value && Number.isFinite(maxRounds.value)) {
    cfg.simulation_max_rounds = maxRounds.value
  }
  cfg.enable_twitter = enableTwitter.value
  cfg.enable_reddit = enableReddit.value
  if (parallelProfileCount.value) {
    cfg.parallel_profile_count = parallelProfileCount.value
  }
  const req = simulationRequirement.value.trim()
  if (req) cfg.simulation_requirement = req
  return cfg
}

async function startRun() {
  if (selectedFiles.value.length === 0) return
  starting.value = true
  startError.value = ''
  try {
    const res = await startPipelineRun({
      seedFiles: selectedFiles.value,
      assumptionsVersion: assumptionsVersion.value.trim() || undefined,
      extraConfig: buildExtraConfig()
    })
    const id = res.run_id || res.data?.run_id
    if (!id) throw new Error('run_id 누락')
    runId.value = id
    startPolling()
  } catch (e) {
    startError.value = e.response?.data?.message || e.message || String(e)
  } finally {
    starting.value = false
  }
}

function startPolling() {
  stopPolling()
  polling.value = true
  const tick = async () => {
    if (!runId.value) return
    try {
      const res = await getPipelineStatus(runId.value)
      applyStatus(res)
      lastPolledAt.value = Date.now()
      if (isTerminal.value) {
        stopPolling()
      }
    } catch (e) {
      console.error('polling error:', e)
    }
  }
  tick()
  pollTimer = setInterval(tick, 2000)
}

function stopPolling() {
  polling.value = false
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function applyStatus(payload) {
  if (!payload || !payload.run_id) return
  status.value = payload.status
  currentStep.value = payload.current_step
  resumableFrom.value = payload.resumable_from
  error.value = payload.error
  if (Array.isArray(payload.steps) && payload.steps.length > 0) {
    steps.value = payload.steps
  }
}

async function resume() {
  if (!runId.value) return
  resuming.value = true
  resumeError.value = ''
  try {
    await resumePipelineRun(runId.value)
    startPolling()
  } catch (e) {
    resumeError.value = e.response?.data?.message || e.message || String(e)
  } finally {
    resuming.value = false
  }
}

async function fetchManifest() {
  if (!runId.value) return
  try {
    const res = await getPipelineManifest(runId.value)
    manifestJson.value = res
  } catch (e) {
    console.error('manifest fetch error:', e)
    manifestJson.value = { error: e.message }
  }
}

function resetForNewRun() {
  stopPolling()
  runId.value = null
  status.value = null
  currentStep.value = null
  resumableFrom.value = null
  error.value = null
  steps.value = PIPELINE_STEP_NAMES.map((name) => ({
    name,
    status: 'pending',
    duration_s: 0,
    llm_calls: 0,
    retry_count: 0
  }))
  manifestJson.value = null
  selectedFiles.value = []
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function stepLabel(name) {
  return PIPELINE_STEP_LABELS[name] || name || '—'
}

function stepIndex(name) {
  return PIPELINE_STEP_NAMES.indexOf(name)
}

function statusBadge(s) {
  const map = {
    pending: '대기',
    running: '실행 중',
    completed: '완료 ✓',
    failed: '실패 ✕'
  }
  return map[s] || s
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function relativeTime(ts) {
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diff < 60) return `${diff}초 전`
  return `${Math.floor(diff / 60)}분 전`
}

watch(isTerminal, (terminal) => {
  if (terminal) stopPolling()
})

onBeforeUnmount(stopPolling)
</script>

<style scoped>
.run-pipeline-button {
  font-family: system-ui, -apple-system, sans-serif;
  max-width: 640px;
  padding: 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.panel-title {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}

.panel-desc {
  margin: 0 0 1rem;
  color: #4b5563;
  font-size: 0.875rem;
  line-height: 1.5;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.field.inline {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}

.field.inline.checkbox .field-label {
  order: 1;
}

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: #374151;
}

.field input[type='text'],
.field input[type='number'],
.field textarea {
  padding: 0.4rem 0.6rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 0.875rem;
}

.field input[type='file'] {
  font-size: 0.875rem;
}

.file-list {
  margin: -0.25rem 0 0.75rem;
  padding: 0.4rem 0.6rem;
  background: #f9fafb;
  border-radius: 4px;
  font-size: 0.8rem;
}

.file-row {
  display: flex;
  justify-content: space-between;
  padding: 0.1rem 0;
}

.file-size {
  color: #6b7280;
}

.advanced {
  margin: 0.75rem 0;
  padding: 0.5rem 0.75rem;
  background: #f9fafb;
  border-radius: 4px;
}

.advanced summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  color: #374151;
}

.run-btn {
  display: block;
  width: 100%;
  padding: 0.6rem 1rem;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.run-btn.primary {
  background: #2563eb;
  color: #fff;
}

.run-btn.primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-text {
  margin: 0.5rem 0 0;
  color: #dc2626;
  font-size: 0.85rem;
}

/* Progress panel */
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.run-id {
  margin: 0.1rem 0 0;
  font-size: 0.8rem;
  color: #6b7280;
}

.run-id code {
  padding: 0.05rem 0.3rem;
  background: #f3f4f6;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
}

.status-pill {
  margin-left: 0.5rem;
  padding: 0.05rem 0.4rem;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  background: #e5e7eb;
  color: #374151;
}

.status-pill.status-running {
  background: #dbeafe;
  color: #1e40af;
}

.status-pill.status-completed {
  background: #d1fae5;
  color: #065f46;
}

.status-pill.status-failed {
  background: #fee2e2;
  color: #991b1b;
}

.header-actions {
  display: flex;
  gap: 0.4rem;
}

.secondary-btn,
.tiny-btn {
  padding: 0.3rem 0.65rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  font-size: 0.8rem;
  cursor: pointer;
}

.secondary-btn:hover,
.tiny-btn:hover {
  background: #f3f4f6;
}

.secondary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error block */
.error-block {
  margin-bottom: 1rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid #fecaca;
  border-left-width: 4px;
  border-radius: 4px;
  background: #fef2f2;
}

.error-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.4rem;
  font-size: 0.9rem;
  color: #991b1b;
}

.error-retries {
  font-size: 0.8rem;
  color: #b91c1c;
}

.error-summary {
  margin: 0.3rem 0;
  padding: 0.4rem 0.6rem;
  background: #fff;
  border-radius: 3px;
  font-size: 0.78rem;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 10rem;
  overflow-y: auto;
}

.error-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.resume-btn {
  padding: 0.4rem 0.8rem;
  border: none;
  border-radius: 4px;
  background: #dc2626;
  color: #fff;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
}

.resume-btn:hover:not(:disabled) {
  background: #b91c1c;
}

.resume-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.manifest-link {
  color: #991b1b;
  text-decoration: underline;
  font-size: 0.8rem;
}

/* Steps list */
.steps {
  list-style: none;
  margin: 0 0 0.8rem;
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.step-row {
  display: grid;
  grid-template-columns: 1.5rem 1fr auto auto;
  gap: 0.6rem;
  padding: 0.55rem 0.75rem;
  align-items: center;
  border-bottom: 1px solid #f3f4f6;
  font-size: 0.88rem;
  transition: background 0.15s;
}

.step-row:last-child {
  border-bottom: none;
}

.step-row.current {
  background: #eff6ff;
}

.step-row.status-completed {
  color: #065f46;
}

.step-row.status-failed {
  background: #fef2f2;
  color: #991b1b;
}

.step-idx {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: #e5e7eb;
  color: #374151;
  text-align: center;
  line-height: 1.5rem;
  font-size: 0.75rem;
  font-weight: 600;
}

.step-row.status-running .step-idx {
  background: #2563eb;
  color: #fff;
}

.step-row.status-completed .step-idx {
  background: #10b981;
  color: #fff;
}

.step-row.status-failed .step-idx {
  background: #dc2626;
  color: #fff;
}

.step-status {
  font-size: 0.78rem;
  color: #6b7280;
}

.step-metrics {
  font-size: 0.75rem;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}

.polling-hint {
  font-size: 0.75rem;
  color: #9ca3af;
  text-align: right;
}

.manifest-block {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #1f2937;
  color: #d1d5db;
  border-radius: 4px;
}

.manifest-block header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.4rem;
  color: #f9fafb;
  font-size: 0.85rem;
}

.manifest-block pre {
  margin: 0;
  font-family: ui-monospace, monospace;
  font-size: 0.72rem;
  line-height: 1.4;
  max-height: 18rem;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
