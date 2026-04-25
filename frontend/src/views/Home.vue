<template>
  <div class="home-container">
    <!-- Top navigation bar -->
    <nav class="navbar">
      <div class="nav-brand">MIROFISH</div>
      <div class="nav-links">
        <a href="https://github.com/666ghj/MiroFish" target="_blank" class="github-link">
          Visit our GitHub page <span class="arrow">↗</span>
        </a>
      </div>
    </nav>

    <div class="main-content">
      <!-- Upper section: Hero area -->
      <section class="hero-section">
        <div class="hero-left">
          <div class="tag-row">
            <span class="orange-tag">심플하고 범용적인 집단지성 엔진</span>
            <span class="version-text">/ v0.1-preview</span>
          </div>

          <h1 class="main-title">
            어떤 보고서든 업로드<br>
            <span class="gradient-text">즉시 미래를 시뮬레이션</span>
          </h1>

          <div class="hero-desc">
            <p>
              단 한 단락의 정보만으로도 <span class="highlight-bold">MiroFish</span>는 그 안의 씨드 정보에 기반해 최대 <span class="highlight-orange">100만 개의 에이전트</span>가 활동하는 병렬 세계를 자동으로 생성합니다. 전지적 시점으로 변수를 주입하고 복잡한 군집 역학 속에서 <span class="highlight-code">"국소 최적해"</span>를 탐색하세요.
            </p>
            <p class="slogan-text">
              Let the future play out among Agents. Let decisions win after a hundred battles.<span class="blinking-cursor">_</span>
            </p>
          </div>

          <div class="decoration-square"></div>
        </div>

        <div class="hero-right">
          <!-- Logo area -->
          <div class="logo-container">
            <img src="../assets/logo/MiroFish_logo_left.jpeg" alt="MiroFish Logo" class="hero-logo" />
          </div>

          <button class="scroll-down-btn" @click="scrollToBottom">
            ↓
          </button>
        </div>
      </section>

      <!-- Lower section: Two-column layout -->
      <section class="dashboard-section">
        <!-- Left column: Status and steps -->
        <div class="left-panel">
          <div class="panel-header">
            <span class="status-dot">■</span> 시스템 상태
          </div>

          <h2 class="section-title">준비 완료</h2>
          <p class="section-desc">
            예측 엔진 대기 중. 하나 이상의 비정형 데이터 파일을 업로드하여 시뮬레이션을 시작하세요.
          </p>

          <!-- Data metric cards -->
          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-value">저비용</div>
              <div class="metric-label">평균 회당 ~$5</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">대규모</div>
              <div class="metric-label">최대 100만 에이전트 시뮬레이션</div>
            </div>
          </div>

          <!-- Workflow steps (new section) -->
          <div class="steps-container">
            <div class="steps-header">
               <span class="diamond-icon">◇</span> 워크플로우 시퀀스
            </div>
            <div class="workflow-list">
              <div class="workflow-item">
                <span class="step-num">01</span>
                <div class="step-info">
                  <div class="step-title">그래프 구축</div>
                  <div class="step-desc">Reality seed extraction &amp; individual/group memory injection &amp; GraphRAG construction</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">02</span>
                <div class="step-info">
                  <div class="step-title">환경 설정</div>
                  <div class="step-desc">Entity-relation extraction &amp; persona generation &amp; environment-config agent injects simulation parameters</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">03</span>
                <div class="step-info">
                  <div class="step-title">시뮬레이션 실행</div>
                  <div class="step-desc">Dual-platform parallel simulation &amp; automatic prediction-requirement parsing &amp; dynamic temporal memory updates</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">04</span>
                <div class="step-info">
                  <div class="step-title">리포트 생성</div>
                  <div class="step-desc">ReportAgent uses a rich toolset to deeply interact with the post-simulation environment</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">05</span>
                <div class="step-info">
                  <div class="step-title">심층 상호작용</div>
                  <div class="step-desc">Chat with any individual in the simulated world &amp; chat with ReportAgent</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right column: Interactive console -->
        <div class="right-panel">
          <div class="console-box">
            <!-- Upload area -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">01 / 씨드 문서</span>
                <span class="console-meta">지원 형식: PDF, MD, TXT</span>
              </div>

              <div
                class="upload-zone"
                :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".pdf,.md,.txt"
                  @change="handleFileSelect"
                  style="display: none"
                  :disabled="loading"
                />

                <div v-if="files.length === 0" class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">파일을 드래그 앤 드롭하여 업로드</div>
                  <div class="upload-hint">또는 클릭하여 파일 선택</div>
                </div>

                <div v-else class="file-list">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Divider -->
            <div class="console-divider">
              <span>입력 파라미터</span>
            </div>

            <!-- Input area -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">>_ 02 / 시뮬레이션 요청</span>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="// Describe your simulation or prediction requirement in natural language (e.g. If Wuhan University announces the revocation of Xiao's disciplinary action, what public opinion trend would emerge?)"
                  rows="6"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">엔진: MiroFish-V1.0</div>
              </div>
            </div>

            <!-- Launch button -->
            <div class="console-section btn-section">
              <button
                class="start-engine-btn"
                @click="startSimulation"
                :disabled="!canSubmit || loading"
              >
                <span v-if="!loading">엔진 시작</span>
                <span v-else>초기화 중...</span>
                <span class="btn-arrow">→</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- History project database -->
      <HistoryDatabase />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'

const router = useRouter()

// Form data
const formData = ref({
  simulationRequirement: ''
})

// File list
const files = ref([])

// State
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)

// File input reference
const fileInput = ref(null)

// Computed: whether submission is allowed
const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== '' && files.value.length > 0
})

// Trigger file selection
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// Handle file selection
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

// Handle drag-and-drop events
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return

  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// Add files
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
}

// Remove file
const removeFile = (index) => {
  files.value.splice(index, 1)
}

// Scroll to bottom
const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

// Start simulation — navigate immediately; API call happens on the Process page
const startSimulation = () => {
  if (!canSubmit.value || loading.value) return

  // Store pending upload data
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(files.value, formData.value.simulationRequirement)

    // Navigate immediately to Process page (special identifier for new project)
    router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
  })
}
</script>

<style scoped>
/*
 * Apple-inspired Light theme — Home.
 * All colors/spacing reference global tokens from src/assets/styles/tokens.css.
 * Monospace is preserved as an UI-label accent (Apple uses similar utility labels).
 */

.home-container {
  min-height: 100vh;
  background: var(--color-canvas);
  font-family: var(--font-text);
  color: var(--color-text);
}

/* Top navigation — light translucent bar with subtle bottom border */
.navbar {
  height: 64px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  color: var(--color-text);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 var(--space-9);
  border-bottom: 1px solid var(--color-border-subtle);
  position: sticky;
  top: 0;
  z-index: 10;
}

.nav-brand {
  font-family: var(--font-display);
  font-weight: 600;
  letter-spacing: -0.01em;
  font-size: 1.05rem;
  color: var(--color-text);
}

.nav-links {
  display: flex;
  align-items: center;
}

.github-link {
  color: var(--color-text);
  text-decoration: none;
  font-size: var(--fs-control);
  font-weight: 500;
  letter-spacing: -0.014em;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color var(--duration-fast) var(--ease-standard);
}

.github-link:hover {
  color: var(--color-accent);
}

.arrow {
  font-family: var(--font-text);
}

/* Main content area */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-11) var(--space-9);
}

/* Hero section */
.hero-section {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-11);
  position: relative;
}

.hero-left {
  flex: 1;
  padding-right: var(--space-11);
}

.tag-row {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  margin-bottom: var(--space-7);
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
}

.orange-tag {
  background: var(--color-canvas-muted);
  color: var(--color-text);
  padding: 4px 10px;
  font-weight: 600;
  letter-spacing: -0.012em;
  font-size: var(--fs-micro);
  border-radius: var(--radius-pill);
  border: 1px solid var(--color-border-subtle);
  font-family: var(--font-text);
}

.version-text {
  color: var(--color-text-muted);
  font-weight: 500;
  letter-spacing: 0;
}

.main-title {
  font-family: var(--font-display);
  font-size: 4.5rem;
  line-height: 1.05;
  font-weight: 600;
  margin: 0 0 var(--space-9) 0;
  letter-spacing: -0.025em;
  color: var(--color-text);
}

.gradient-text {
  background: linear-gradient(90deg, var(--color-text) 0%, var(--color-text-muted) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

.hero-desc {
  font-size: var(--fs-body);
  line-height: 1.55;
  color: var(--color-text-muted);
  max-width: 640px;
  margin-bottom: var(--space-10);
  font-weight: 400;
  letter-spacing: -0.022em;
}

.hero-desc p {
  margin-bottom: var(--space-6);
}

.highlight-bold {
  color: var(--color-text);
  font-weight: 600;
}

.highlight-orange {
  color: var(--color-accent);
  font-weight: 600;
}

.highlight-code {
  background: var(--color-canvas-muted);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--color-text);
  font-weight: 500;
  border: 1px solid var(--color-border-subtle);
}

.slogan-text {
  font-family: var(--font-display);
  font-size: var(--fs-link-action);
  font-weight: 500;
  color: var(--color-text);
  letter-spacing: -0.02em;
  border-left: 3px solid var(--color-accent);
  padding-left: var(--space-5);
  margin-top: var(--space-7);
  line-height: 1.4;
}

.blinking-cursor {
  color: var(--color-accent);
  animation: blink 1s step-end infinite;
  font-weight: 600;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.decoration-square {
  width: 16px;
  height: 16px;
  background: var(--color-accent);
  border-radius: var(--radius-xs);
}

.hero-right {
  flex: 0.8;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
}

.logo-container {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  padding-right: 40px;
}

.hero-logo {
  max-width: 460px;
  width: 100%;
  border-radius: var(--radius-2xl);
  background: var(--color-canvas-muted);
  padding: var(--space-7);
  box-shadow: var(--shadow-2);
  /* JPEG 마스코트를 Apple 결의 spotlight 카드로 감싸 — 흰 배경 위 떠보이게 */
}

.scroll-down-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--color-border-subtle);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--color-accent);
  font-size: 1.1rem;
  border-radius: var(--radius-circle);
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}

.scroll-down-btn:hover {
  border-color: var(--color-accent);
  background: var(--color-canvas-muted);
}

/* Dashboard two-column layout */
.dashboard-section {
  display: flex;
  gap: var(--space-11);
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-11);
  align-items: flex-start;
}

.dashboard-section .left-panel,
.dashboard-section .right-panel {
  display: flex;
  flex-direction: column;
}

/* Left panel */
.left-panel {
  flex: 0.8;
}

.panel-header {
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--space-7);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.status-dot {
  color: var(--color-accent);
  font-size: 0.7rem;
}

.section-title {
  font-family: var(--font-display);
  font-size: var(--fs-product);
  font-weight: 600;
  letter-spacing: -0.022em;
  line-height: 1.1;
  margin: 0 0 var(--space-5) 0;
  color: var(--color-text);
}

.section-desc {
  color: var(--color-text-muted);
  margin-bottom: var(--space-8);
  line-height: 1.55;
  font-size: var(--fs-body);
  letter-spacing: -0.022em;
}

.metrics-row {
  display: flex;
  gap: var(--space-7);
  margin-bottom: var(--space-5);
}

.metric-card {
  border: 1px solid var(--color-border-subtle);
  padding: var(--space-7) var(--space-9);
  min-width: 150px;
  border-radius: var(--radius-md);
  background: var(--color-surface);
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.metric-card:hover {
  border-color: var(--color-border-strong);
}

.metric-value {
  font-family: var(--font-display);
  font-size: var(--fs-utility);
  font-weight: 600;
  letter-spacing: -0.022em;
  margin-bottom: var(--space-2);
  color: var(--color-text);
}

.metric-label {
  font-size: var(--fs-control);
  color: var(--color-text-muted);
  letter-spacing: -0.014em;
}

/* Workflow steps section */
.steps-container {
  border: 1px solid var(--color-border-subtle);
  padding: var(--space-9);
  position: relative;
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.steps-header {
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
  color: var(--color-text-muted);
  margin-bottom: var(--space-8);
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.diamond-icon {
  font-size: 1rem;
  line-height: 1;
  color: var(--color-accent);
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-7);
}

.workflow-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-7);
}

.step-num {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: -0.012em;
}

.step-info {
  flex: 1;
}

.step-title {
  font-weight: 600;
  font-size: var(--fs-body);
  margin-bottom: 4px;
  color: var(--color-text);
  letter-spacing: -0.022em;
}

.step-desc {
  font-size: var(--fs-control);
  color: var(--color-text-muted);
  line-height: 1.5;
  letter-spacing: -0.014em;
}

/* Right panel — interactive console */
.right-panel {
  flex: 1.2;
}

.console-box {
  border: 1px solid var(--color-border-subtle);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.console-section {
  padding: var(--space-7);
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-5);
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
  color: var(--color-text-muted);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.upload-zone {
  border: 1px dashed var(--color-border-subtle);
  height: 200px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
  background: var(--color-canvas-muted);
  border-radius: var(--radius-md);
}

.upload-zone.has-files {
  align-items: flex-start;
}

.upload-zone:hover {
  background: var(--color-surface);
  border-color: var(--color-accent);
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 40px;
  height: 40px;
  border: 1px solid var(--color-border-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--space-5);
  color: var(--color-text-muted);
  border-radius: var(--radius-circle);
  font-size: 1.1rem;
}

.upload-title {
  font-weight: 500;
  font-size: var(--fs-control);
  margin-bottom: 4px;
  color: var(--color-text);
  letter-spacing: -0.014em;
}

.upload-hint {
  font-size: var(--fs-micro);
  color: var(--color-text-muted);
  letter-spacing: -0.012em;
}

.file-list {
  width: 100%;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-item {
  display: flex;
  align-items: center;
  background: var(--color-surface);
  padding: 8px 12px;
  border: 1px solid var(--color-border-subtle);
  font-size: var(--fs-control);
  border-radius: var(--radius-sm);
  color: var(--color-text);
}

.file-name {
  flex: 1;
  margin: 0 10px;
  letter-spacing: -0.014em;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--color-text-muted);
  transition: color var(--duration-fast) var(--ease-standard);
}

.remove-btn:hover {
  color: var(--color-error);
}

.console-divider {
  display: flex;
  align-items: center;
  margin: var(--space-3) 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-border-subtle);
}

.console-divider span {
  padding: 0 var(--space-5);
  font-family: var(--font-mono);
  font-size: var(--fs-legal);
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.input-wrapper {
  position: relative;
  border: 1px solid var(--color-border-subtle);
  background: var(--color-canvas-muted);
  border-radius: var(--radius-md);
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.input-wrapper:focus-within {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18);
}

.code-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: var(--space-7);
  font-family: var(--font-mono);
  font-size: var(--fs-control);
  line-height: 1.6;
  resize: vertical;
  outline: none;
  min-height: 150px;
  color: var(--color-text);
  border-radius: var(--radius-md);
}

.model-badge {
  position: absolute;
  bottom: 10px;
  right: var(--space-5);
  font-family: var(--font-mono);
  font-size: var(--fs-legal);
  color: var(--color-text-muted);
}

.start-engine-btn {
  width: 100%;
  background: var(--color-accent);
  color: var(--color-accent-on);
  border: none;
  padding: var(--space-5) var(--space-7);
  font-family: var(--font-text);
  font-weight: 600;
  font-size: var(--fs-body);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--space-3);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
              transform var(--duration-fast) var(--ease-standard);
  letter-spacing: -0.014em;
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-pill);
}

.start-engine-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.start-engine-btn:active:not(:disabled) {
  transform: scale(0.99);
  background: var(--color-accent-pressed);
}

.start-engine-btn:disabled {
  background: var(--color-canvas-muted);
  color: var(--color-text-muted);
  cursor: not-allowed;
  border: 1px solid var(--color-border-subtle);
}

/* Responsive layout */
@media (max-width: 1024px) {
  .dashboard-section {
    flex-direction: column;
  }

  .hero-section {
    flex-direction: column;
  }

  .hero-left {
    padding-right: 0;
    margin-bottom: 40px;
  }

  .hero-logo {
    max-width: 200px;
    margin-bottom: 20px;
  }
}
</style>
