<template>
  <div class="history-database" :class="{ 'no-projects': projects.length === 0 && !loading }">
    <!-- Title area -->
    <div class="section-header">
      <div class="section-line"></div>
      <span class="section-title">시뮬레이션 히스토리</span>
      <div class="section-line"></div>
    </div>

    <!-- Table container -->
    <div v-if="projects.length > 0" class="history-table-wrapper">
      <table class="history-table">
        <thead>
          <tr>
            <th class="col-id">ID</th>
            <th class="col-status">상태</th>
            <th class="col-files">파일</th>
            <th class="col-requirement">시뮬레이션 요청</th>
            <th class="col-datetime">생성일시</th>
            <th class="col-progress">진행률</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="project in projects"
            :key="project.simulation_id"
            class="history-row"
            @click="navigateToProject(project)"
          >
            <td class="col-id">
              <span class="row-id">{{ formatSimulationId(project.simulation_id) }}</span>
            </td>
            <td class="col-status">
              <div class="status-icons">
                <span
                  class="status-icon"
                  :class="{ available: project.project_id, unavailable: !project.project_id }"
                  title="지식 그래프 구축"
                >◇</span>
                <span class="status-icon available" title="환경 설정">◈</span>
                <span
                  class="status-icon"
                  :class="{ available: project.report_id, unavailable: !project.report_id }"
                  title="분석 리포트"
                >◆</span>
              </div>
            </td>
            <td class="col-files">
              <div class="files-cell" v-if="project.files && project.files.length > 0">
                <span
                  v-for="(file, fileIndex) in project.files.slice(0, 2)"
                  :key="fileIndex"
                  class="file-chip"
                  :title="file.filename"
                >
                  <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                  <span class="file-name">{{ truncateFilename(file.filename, 18) }}</span>
                </span>
                <span v-if="project.files.length > 2" class="files-more">+{{ project.files.length - 2 }}개</span>
              </div>
              <span v-else class="files-empty-inline">파일 없음</span>
            </td>
            <td class="col-requirement">
              <span class="requirement-text" :title="project.simulation_requirement">
                {{ truncateText(project.simulation_requirement, 80) || '제목 없는 시뮬레이션' }}
              </span>
            </td>
            <td class="col-datetime">
              <span class="datetime-text">{{ formatDate(project.created_at) }} {{ formatTime(project.created_at) }}</span>
            </td>
            <td class="col-progress">
              <span class="row-progress" :class="getProgressClass(project)">
                <span class="status-dot">●</span> {{ formatRounds(project) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading" class="empty-state">
      <span class="empty-icon">◇</span>
      <span class="empty-text">시뮬레이션 히스토리가 없습니다</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">불러오는 중...</span>
    </div>

    <!-- Simulation playback detail modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div class="modal-content">
            <!-- Modal header -->
            <div class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ formatSimulationId(selectedProject.simulation_id) }}</span>
                <span class="modal-progress" :class="getProgressClass(selectedProject)">
                  <span class="status-dot">●</span> {{ formatRounds(selectedProject) }}
                </span>
                <span class="modal-create-time">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</span>
              </div>
              <button class="modal-close" @click="closeModal">×</button>
            </div>

            <!-- Modal content -->
            <div class="modal-body">
              <div class="modal-section">
                <div class="modal-label">시뮬레이션 요청</div>
                <div class="modal-requirement">{{ selectedProject.simulation_requirement || '없음' }}</div>
              </div>

              <div class="modal-section">
                <div class="modal-label">연결된 파일</div>
                <div class="modal-files" v-if="selectedProject.files && selectedProject.files.length > 0">
                  <div v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </div>
                </div>
                <div class="modal-empty" v-else>연결된 파일 없음</div>
              </div>
            </div>

            <!-- 파일 추가 (incremental graph append) -->
            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">파일 추가 (기존 그래프에 누적)</span>
              <span class="divider-line"></span>
            </div>
            <div class="modal-append">
              <input
                ref="appendFileInput"
                type="file"
                multiple
                accept=".pdf,.md,.txt"
                style="display: none"
                @change="onAppendFilesPicked"
              />
              <button
                class="append-btn"
                @click="triggerAppendFilePick"
                :disabled="!selectedProject.project_id || appendBusy"
              >
                <span class="append-icon">⊕</span>
                <span class="append-text">{{ appendBusy ? '처리 중...' : '파일 선택해서 추가' }}</span>
              </button>
              <div v-if="appendStatusMessage" class="append-status" :class="appendStatusClass">
                {{ appendStatusMessage }}
              </div>
              <div class="append-hint">
                동일 graph_id 에 누적됩니다. 같은 entity 는 자동 dedup → 풀 재빌드 대비 비용 ~10× 절감.
              </div>
            </div>

            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">시뮬레이션 재생</span>
              <span class="divider-line"></span>
            </div>

            <div class="modal-actions">
              <button
                class="modal-btn btn-project"
                @click="goToProject"
                :disabled="!selectedProject.project_id"
              >
                <span class="btn-step">Step1</span>
                <span class="btn-icon">◇</span>
                <span class="btn-text">지식 그래프 구축</span>
              </button>
              <button class="modal-btn btn-simulation" @click="goToSimulation">
                <span class="btn-step">Step2</span>
                <span class="btn-icon">◈</span>
                <span class="btn-text">환경 설정</span>
              </button>
              <button
                class="modal-btn btn-report"
                @click="goToReport"
                :disabled="!selectedProject.report_id"
              >
                <span class="btn-step">Step4</span>
                <span class="btn-icon">◆</span>
                <span class="btn-text">분석 리포트</span>
              </button>
            </div>
            <div class="modal-playback-hint">
              <span class="hint-text">Step3(시뮬레이션 시작)과 Step5(심층 상호작용)는 실행 중에만 가능합니다. 히스토리 재생은 지원되지 않습니다</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSimulationHistory } from '../api/simulation'
import { appendFilesToProject, getTaskStatus } from '../api/graph'

const router = useRouter()
const route = useRoute()

const projects = ref([])
const loading = ref(true)
const selectedProject = ref(null)

// 파일 추가 (incremental append) 상태
const appendFileInput = ref(null)
const appendBusy = ref(false)
const appendStatusMessage = ref('')
const appendStatusClass = ref('')  // 'success' | 'error' | 'progress'
let appendPollTimer = null

const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0 || current === 0) return 'not-started'
  if (current >= total) return 'completed'
  return 'in-progress'
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toISOString().slice(0, 10)
  } catch {
    return dateStr?.slice(0, 10) || ''
  }
}

const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
  } catch {
    return ''
  }
}

const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
}

const formatSimulationId = (simulationId) => {
  if (!simulationId) return 'SIM_UNKNOWN'
  const prefix = simulationId.replace('sim_', '').slice(0, 6)
  return `SIM_${prefix.toUpperCase()}`
}

const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0) return '시작 전'
  return `${current}/${total} 라운드`
}

const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = {
    'pdf': 'pdf',
    'doc': 'doc', 'docx': 'doc',
    'xls': 'xls', 'xlsx': 'xls', 'csv': 'xls',
    'ppt': 'ppt', 'pptx': 'ppt',
    'txt': 'txt', 'md': 'txt', 'json': 'code',
    'jpg': 'img', 'jpeg': 'img', 'png': 'img', 'gif': 'img',
    'zip': 'zip', 'rar': 'zip', '7z': 'zip'
  }
  return typeMap[ext] || 'other'
}

const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

const truncateFilename = (filename, maxLength) => {
  if (!filename) return 'Unknown File'
  if (filename.length <= maxLength) return filename
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  const truncatedName = nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...'
  return truncatedName + ext
}

const navigateToProject = (simulation) => {
  selectedProject.value = simulation
  resetAppendState()
}

const closeModal = () => {
  selectedProject.value = null
  resetAppendState()
}

const resetAppendState = () => {
  appendBusy.value = false
  appendStatusMessage.value = ''
  appendStatusClass.value = ''
  if (appendPollTimer) {
    clearTimeout(appendPollTimer)
    appendPollTimer = null
  }
}

const triggerAppendFilePick = () => {
  if (!selectedProject.value?.project_id || appendBusy.value) return
  appendStatusMessage.value = ''
  appendFileInput.value?.click()
}

const onAppendFilesPicked = async (event) => {
  const files = Array.from(event.target?.files || [])
  // 파일 input 초기화 (같은 파일 다시 선택 가능하게)
  if (appendFileInput.value) appendFileInput.value.value = ''
  if (!files.length || !selectedProject.value?.project_id) return

  appendBusy.value = true
  appendStatusClass.value = 'progress'
  appendStatusMessage.value = `${files.length}개 파일 업로드 중...`

  try {
    const res = await appendFilesToProject(selectedProject.value.project_id, files)
    if (!res.success) {
      throw new Error(res.error || '업로드 실패')
    }
    const taskId = res.data.task_id
    appendStatusMessage.value = `task=${taskId.slice(0, 12)}... 그래프 빌드 중`
    pollAppendTask(taskId)
  } catch (err) {
    appendStatusClass.value = 'error'
    appendStatusMessage.value = `❌ ${err?.response?.data?.error || err.message || err}`
    appendBusy.value = false
  }
}

const pollAppendTask = (taskId) => {
  appendPollTimer = setTimeout(async () => {
    try {
      const res = await getTaskStatus(taskId)
      if (!res.success) {
        throw new Error(res.error || 'task 조회 실패')
      }
      const t = res.data
      if (t.status === 'completed') {
        appendStatusClass.value = 'success'
        const info = t.result?.graph_info || {}
        appendStatusMessage.value = `✓ 추가 완료. nodes=${info.node_count ?? '?'}, edges=${info.edge_count ?? '?'}`
        appendBusy.value = false
        appendPollTimer = null
        loadHistory()
      } else if (t.status === 'failed') {
        appendStatusClass.value = 'error'
        appendStatusMessage.value = `❌ 빌드 실패: ${t.error || t.message || 'unknown'}`
        appendBusy.value = false
        appendPollTimer = null
      } else {
        appendStatusClass.value = 'progress'
        appendStatusMessage.value = `진행 중 ${t.progress ?? 0}% — ${t.message || ''}`
        pollAppendTask(taskId)
      }
    } catch (err) {
      appendStatusClass.value = 'error'
      appendStatusMessage.value = `❌ ${err?.response?.data?.error || err.message || err}`
      appendBusy.value = false
      appendPollTimer = null
    }
  }, 2000)
}

const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id }
    })
    closeModal()
  }
}

const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

const loadHistory = async () => {
  try {
    loading.value = true
    const response = await getSimulationHistory(20)
    if (response.success) {
      projects.value = response.data || []
    }
  } catch (error) {
    console.error('Failed to load simulation history:', error)
    projects.value = []
  } finally {
    loading.value = false
  }
}

watch(() => route.path, (newPath) => {
  if (newPath === '/') {
    loadHistory()
  }
})

onMounted(loadHistory)
onActivated(loadHistory)
onUnmounted(() => {
  if (appendPollTimer) {
    clearTimeout(appendPollTimer)
    appendPollTimer = null
  }
})
</script>

<style scoped>
.history-database {
  position: relative;
  width: 100%;
  margin-top: 40px;
  padding: 35px 0 40px;
}

.history-database.no-projects {
  min-height: auto;
  padding: 40px 0 20px;
}

/* Title area */
.section-header {
  position: relative;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-bottom: 24px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  padding: 0 40px;
}

.section-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--color-border-subtle), transparent);
  max-width: 300px;
}

.section-title {
  font-size: var(--fs-micro);
  font-weight: 500;
  color: var(--color-text-muted);
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

/* ===== Table ===== */
.history-table-wrapper {
  margin: 0 40px;
  background: var(--color-surface, #FFFFFF);
  border: 1px solid var(--color-border-subtle, #E5E7EB);
  border-radius: var(--radius-md, 12px);
  overflow: hidden;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04);
}

.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.history-table thead {
  background: #F9FAFB;
  border-bottom: 1px solid #E5E7EB;
}

.history-table th {
  padding: 12px 16px;
  text-align: left;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.7rem;
  font-weight: 500;
  color: #6B7280;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  white-space: nowrap;
}

.history-table tbody tr.history-row {
  border-bottom: 1px solid #F3F4F6;
  cursor: pointer;
  transition: background 0.15s ease;
}

.history-table tbody tr.history-row:last-child {
  border-bottom: none;
}

.history-table tbody tr.history-row:hover {
  background: #F9FAFB;
}

.history-table td {
  padding: 14px 16px;
  vertical-align: middle;
  color: #374151;
}

/* Column widths */
.col-id { width: 110px; }
.col-status { width: 90px; }
.col-files { width: 260px; }
.col-requirement { min-width: 240px; }
.col-datetime { width: 140px; }
.col-progress { width: 130px; }

/* ID cell */
.row-id {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: #111827;
  letter-spacing: 0.04em;
}

/* Status icons cell */
.status-icons {
  display: flex;
  gap: 6px;
  font-size: 1rem;
  line-height: 1;
}

.status-icon {
  transition: color 0.2s ease;
}

.status-icon.available {
  opacity: 1;
}

.status-icon:nth-child(1).available { color: #3B82F6; }
.status-icon:nth-child(2).available { color: #F59E0B; }
.status-icon:nth-child(3).available { color: #10B981; }

.status-icon.unavailable {
  color: #D1D5DB;
  opacity: 0.6;
}

/* Files cell */
.files-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 170px;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}

.file-tag.pdf { background: #f2e6e6; color: #a65a5a; }
.file-tag.doc { background: #e6eff5; color: #5a7ea6; }
.file-tag.xls { background: #e6f2e8; color: #5aa668; }
.file-tag.ppt { background: #f5efe6; color: #a6815a; }
.file-tag.txt { background: #f0f0f0; color: #757575; }
.file-tag.code { background: #eae6f2; color: #815aa6; }
.file-tag.img { background: #e6f2f2; color: #5aa6a6; }
.file-tag.zip { background: #f2f0e6; color: #a69b5a; }
.file-tag.other { background: #f3f4f6; color: #6b7280; }

.file-name {
  font-size: 0.75rem;
  color: #4B5563;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.files-more {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  padding: 2px 6px;
  background: #F3F4F6;
  border-radius: 4px;
}

.files-empty-inline {
  font-size: 0.75rem;
  color: #9CA3AF;
  font-style: italic;
}

/* Requirement cell */
.requirement-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #374151;
  line-height: 1.45;
}

/* Datetime cell */
.datetime-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #6B7280;
  white-space: nowrap;
}

/* Progress cell */
.row-progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.status-dot {
  font-size: 0.5rem;
  line-height: 1;
}

.row-progress.completed { color: #10B981; }
.row-progress.in-progress { color: #F59E0B; }
.row-progress.not-started { color: #9CA3AF; }

/* Empty / loading states */
.empty-state, .loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 48px;
  color: #9CA3AF;
}

.empty-icon {
  font-size: 2rem;
  opacity: 0.5;
}

.empty-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  letter-spacing: 0.05em;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E5E7EB;
  border-top-color: #6B7280;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Responsive */
@media (max-width: 1200px) {
  .history-table-wrapper { margin: 0 20px; }
  .col-files { width: auto; }
  .file-name { display: none; }
}

@media (max-width: 768px) {
  .history-table-wrapper {
    margin: 0 12px;
    overflow-x: auto;
  }
  .history-table { min-width: 720px; }
}

/* ===== Simulation Playback Detail Modal Styles ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: #FFFFFF;
  width: 560px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-content {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .modal-content {
  transition: all 0.2s ease-in;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  border-bottom: 1px solid #F3F4F6;
  background: #FFFFFF;
}

.modal-title-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.modal-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
  letter-spacing: 0.5px;
}

.modal-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  background: #F9FAFB;
}

.modal-progress.completed { color: #10B981; background: rgba(16, 185, 129, 0.1); }
.modal-progress.in-progress { color: #F59E0B; background: rgba(245, 158, 11, 0.1); }
.modal-progress.not-started { color: #9CA3AF; background: #F3F4F6; }

.modal-create-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 1.5rem;
  color: #9CA3AF;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.modal-close:hover {
  background: #F3F4F6;
  color: #111827;
}

.modal-body {
  padding: 24px 32px;
}

.modal-section {
  margin-bottom: 24px;
}

.modal-section:last-child {
  margin-bottom: 0;
}

.modal-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  font-weight: 500;
}

.modal-requirement {
  font-size: 0.95rem;
  color: #374151;
  line-height: 1.6;
  padding: 16px;
  background: #F9FAFB;
  border: 1px solid #F3F4F6;
  border-radius: 8px;
}

.modal-files {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 200px;
  overflow-y: auto;
  padding-right: 4px;
}

.modal-files::-webkit-scrollbar {
  width: 4px;
}

.modal-files::-webkit-scrollbar-track {
  background: #F3F4F6;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb {
  background: #D1D5DB;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb:hover {
  background: #9CA3AF;
}

.modal-file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.modal-file-item:hover {
  border-color: #D1D5DB;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.modal-file-name {
  font-size: 0.85rem;
  color: #4B5563;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-empty {
  font-size: 0.85rem;
  color: #9CA3AF;
  padding: 16px;
  background: #F9FAFB;
  border: 1px dashed #E5E7EB;
  border-radius: 6px;
  text-align: center;
}

/* === 파일 추가 (incremental append) === */
.modal-append {
  padding: 14px 32px 6px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #FFFFFF;
}

.append-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  background: #FFFFFF;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: #4B5563;
  cursor: pointer;
  transition: all 0.15s ease;
}

.append-btn:hover:not(:disabled) {
  border-color: #111827;
  color: #111827;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.06);
}

.append-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #F9FAFB;
}

.append-icon {
  font-size: 1rem;
  line-height: 1;
  color: #3B82F6;
}

.append-status {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  padding: 8px 12px;
  border-radius: 4px;
  letter-spacing: 0.02em;
  line-height: 1.5;
}

.append-status.progress { background: rgba(59, 130, 246, 0.08); color: #1D4ED8; }
.append-status.success  { background: rgba(16, 185, 129, 0.08); color: #047857; }
.append-status.error    { background: rgba(220, 38, 38, 0.08); color: #B91C1C; }

.append-hint {
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 0.01em;
  line-height: 1.5;
}

.modal-divider {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 32px 0;
  background: #FFFFFF;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
}

.divider-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 2px;
  text-transform: uppercase;
  white-space: nowrap;
}

.modal-actions {
  display: flex;
  gap: 16px;
  padding: 20px 32px;
  background: #FFFFFF;
}

.modal-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFFFFF;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}

.modal-btn:hover:not(:disabled) {
  border-color: #000000;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #F9FAFB;
}

.btn-step {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 500;
  color: #9CA3AF;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.btn-icon {
  font-size: 1.4rem;
  line-height: 1;
  transition: color 0.2s ease;
}

.btn-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #4B5563;
}

.modal-btn.btn-project .btn-icon { color: #3B82F6; }
.modal-btn.btn-simulation .btn-icon { color: #F59E0B; }
.modal-btn.btn-report .btn-icon { color: #10B981; }

.modal-btn:hover:not(:disabled) .btn-text {
  color: #111827;
}

.modal-playback-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 32px 20px;
  background: #FFFFFF;
}

.hint-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
  text-align: center;
  line-height: 1.5;
}
</style>
