<template>
  <div class="pipeline-view">
    <header class="page-header">
      <router-link to="/" class="back-link">← Home</router-link>
      <h1>Pipeline Runner</h1>
      <p class="subtitle">
        Seed 문서를 업로드해 5단계 파이프라인(Graph → Agents → Simulation → Report)을 한 번에 실행.
      </p>
    </header>

    <main class="page-body">
      <RunPipelineButton />
    </main>
  </div>
</template>

<script setup>
import RunPipelineButton from '../components/RunPipelineButton.vue'
</script>

<style scoped>
.pipeline-view {
  min-height: 100vh;
  padding: 2rem 1.5rem 4rem;
  background: #f8fafc;
  font-family: system-ui, -apple-system, sans-serif;
}

.page-header {
  max-width: 640px;
  margin: 0 auto 1.5rem;
}

.back-link {
  display: inline-block;
  margin-bottom: 0.5rem;
  color: #6b7280;
  text-decoration: none;
  font-size: 0.85rem;
}

.back-link:hover {
  color: #2563eb;
  text-decoration: underline;
}

.page-header h1 {
  margin: 0 0 0.25rem;
  font-size: 1.6rem;
  font-weight: 700;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #4b5563;
  font-size: 0.9rem;
  line-height: 1.55;
}

.page-body {
  max-width: 640px;
  margin: 0 auto;
}
</style>
