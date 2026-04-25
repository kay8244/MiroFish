<template>
  <div class="pipeline-view">
    <header class="page-header">
      <router-link to="/" class="back-link">← Home</router-link>
      <h1>파이프라인 러너</h1>
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
  padding: var(--space-9) var(--space-7) var(--space-11);
  background: var(--color-canvas-muted);
}

.page-header {
  max-width: 720px;
  margin: 0 auto var(--space-8);
}

.back-link {
  display: inline-block;
  margin-bottom: var(--space-4);
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: var(--fs-control);
  letter-spacing: -0.014em;
  transition: color var(--duration-fast) var(--ease-standard);
}

.back-link:hover {
  color: var(--color-accent);
  text-decoration: none;
}

.page-header h1 {
  font-family: var(--font-display);
  margin: 0 0 var(--space-2);
  font-size: var(--fs-utility);
  font-weight: 600;
  letter-spacing: -0.022em;
  line-height: 1.1;
  color: var(--color-text);
}

.subtitle {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--fs-control);
  line-height: 1.55;
  letter-spacing: -0.014em;
}

.page-body {
  max-width: 720px;
  margin: 0 auto;
}
</style>
