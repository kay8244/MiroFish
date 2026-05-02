<template>
  <div class="left-panel report-style" ref="leftPanel">
    <div v-if="reportOutline" class="report-content-wrapper">
      <!-- Report Header -->
      <div class="report-header-block">
        <div class="report-meta">
          <span class="report-tag">예측 리포트</span>
          <span class="report-id">ID: {{ reportId || 'REF-2024-X92' }}</span>
        </div>
        <h1 class="main-title">{{ reportOutline.title }}</h1>
        <p class="sub-title">{{ reportOutline.summary }}</p>
        <div class="header-divider"></div>
      </div>

      <!-- Sections List -->
      <div class="sections-list">
        <div
          v-for="(section, idx) in reportOutline.sections"
          :key="idx"
          class="report-section-item"
          :class="{
            'is-active': currentSectionIndex === idx + 1,
            'is-completed': isSectionCompleted(idx + 1),
            'is-pending': !isSectionCompleted(idx + 1) && currentSectionIndex !== idx + 1
          }"
        >
          <div class="section-header-row" @click="$emit('toggle-collapse', idx)" :class="{ 'clickable': isSectionCompleted(idx + 1) }">
            <span class="section-number">{{ String(idx + 1).padStart(2, '0') }}</span>
            <h3 class="section-title">{{ section.title }}</h3>
            <svg
              v-if="isSectionCompleted(idx + 1)"
              class="collapse-icon"
              :class="{ 'is-collapsed': collapsedSections.has(idx) }"
              viewBox="0 0 24 24"
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </div>

          <div class="section-body" v-show="!collapsedSections.has(idx)">
            <!-- Completed Content -->
            <div v-if="generatedSections[idx + 1]" class="generated-content" v-html="renderMarkdown(generatedSections[idx + 1])"></div>

            <!-- Loading State -->
            <div v-else-if="currentSectionIndex === idx + 1" class="loading-state">
              <div class="loading-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <circle cx="12" cy="12" r="10" stroke-width="4" stroke="#E5E7EB"></circle>
                  <path d="M12 2a10 10 0 0 1 10 10" stroke-width="4" stroke="#4B5563" stroke-linecap="round"></path>
                </svg>
              </div>
              <span class="loading-text">Generating {{ section.title }}...</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Waiting State -->
    <div v-if="!reportOutline" class="waiting-placeholder">
      <div class="waiting-animation">
        <div class="waiting-ring"></div>
        <div class="waiting-ring"></div>
        <div class="waiting-ring"></div>
      </div>
      <span class="waiting-text">Waiting for Report Agent...</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  reportId: { type: String, default: null },
  reportOutline: { type: Object, default: null },
  generatedSections: { type: Object, default: () => ({}) },
  collapsedSections: { type: Set, default: () => new Set() },
  currentSectionIndex: { type: Number, default: null },
  isSectionCompleted: { type: Function, required: true },
  renderMarkdown: { type: Function, required: true }
})

defineEmits(['toggle-collapse'])
</script>

<style scoped>
/* Left Panel - Report Style */
.left-panel.report-style {
  width: 45%;
  min-width: 450px;
  background: #FFFFFF;
  border-right: 1px solid #E5E7EB;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding: 30px 50px 60px 50px;
}

.left-panel::-webkit-scrollbar {
  width: 6px;
}

.left-panel::-webkit-scrollbar-track {
  background: transparent;
}

.left-panel::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
  transition: background 0.3s ease;
}

.left-panel:hover::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
}

.left-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

/* Report Header */
.report-content-wrapper {
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}

.report-header-block {
  margin-bottom: 30px;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.report-tag {
  background: #000000;
  color: #FFFFFF;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.report-id {
  font-size: 11px;
  color: #9CA3AF;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.main-title {
  font-family: 'Times New Roman', Times, serif;
  font-size: 36px;
  font-weight: 700;
  color: #111827;
  line-height: 1.2;
  margin: 0 0 16px 0;
  letter-spacing: -0.02em;
}

.sub-title {
  font-family: 'Times New Roman', Times, serif;
  font-size: 16px;
  color: #6B7280;
  font-style: italic;
  line-height: 1.6;
  margin: 0 0 30px 0;
  font-weight: 400;
}

.header-divider {
  height: 1px;
  background: #E5E7EB;
  width: 100%;
}

/* Sections List */
.sections-list {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.report-section-item {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  transition: background-color 0.2s ease;
  padding: 8px 12px;
  margin: -8px -12px;
  border-radius: 8px;
}

.section-header-row.clickable {
  cursor: pointer;
}

.section-header-row.clickable:hover {
  background-color: #F9FAFB;
}

.collapse-icon {
  margin-left: auto;
  color: #9CA3AF;
  transition: transform 0.3s ease;
  flex-shrink: 0;
  align-self: center;
}

.collapse-icon.is-collapsed {
  transform: rotate(-90deg);
}

.section-number {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  color: #E5E7EB;
  font-weight: 500;
  transition: color 0.3s ease;
}

.section-title {
  font-family: 'Times New Roman', Times, serif;
  font-size: 24px;
  font-weight: 600;
  color: #111827;
  margin: 0;
  transition: color 0.3s ease;
}

/* States */
.report-section-item.is-pending .section-number {
  color: #E5E7EB;
}
.report-section-item.is-pending .section-title {
  color: #D1D5DB;
}

.report-section-item.is-active .section-number,
.report-section-item.is-completed .section-number {
  color: #9CA3AF;
}

.report-section-item.is-active .section-title,
.report-section-item.is-completed .section-title {
  color: #111827;
}

.section-body {
  padding-left: 28px;
  overflow: hidden;
}

/* Generated Content */
.generated-content {
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}

.generated-content :deep(p) {
  margin-bottom: 1em;
}

.generated-content :deep(.md-h2),
.generated-content :deep(.md-h3),
.generated-content :deep(.md-h4) {
  font-family: 'Times New Roman', Times, serif;
  color: #111827;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
  font-weight: 700;
}

.generated-content :deep(.md-h2) { font-size: 20px; border-bottom: 1px solid #F3F4F6; padding-bottom: 8px; }
.generated-content :deep(.md-h3) { font-size: 18px; }
.generated-content :deep(.md-h4) { font-size: 16px; }

.generated-content :deep(.md-ul),
.generated-content :deep(.md-ol) {
  padding-left: 20px;
  margin-bottom: 1em;
}

.generated-content :deep(.md-li) {
  margin-bottom: 0.5em;
}

.generated-content :deep(.md-quote) {
  border-left: 3px solid #E5E7EB;
  padding-left: 16px;
  color: #6B7280;
  font-style: italic;
  margin: 1em 0;
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}

.loading-icon svg {
  width: 20px;
  height: 20px;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.loading-text {
  font-size: 13px;
  color: #9CA3AF;
}

/* Waiting Placeholder */
.waiting-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.waiting-animation {
  position: relative;
  width: 60px;
  height: 60px;
}

.waiting-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: #E5E7EB;
  animation: spin 1.5s linear infinite;
}

.waiting-ring:nth-child(2) {
  inset: 8px;
  animation-duration: 2s;
  border-top-color: #D1D5DB;
}

.waiting-ring:nth-child(3) {
  inset: 16px;
  animation-duration: 2.5s;
  border-top-color: #9CA3AF;
}

.waiting-text {
  font-size: 14px;
  color: #9CA3AF;
}
</style>
