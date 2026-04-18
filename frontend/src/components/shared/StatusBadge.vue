<template>
  <span :class="['status-badge', `status-${status}`]">
    <span class="status-dot"></span>
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'pending' }, // pending, processing, completed, error
  label: { type: String, default: '' }
})
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-pending { background: #f1f5f9; color: #64748b; }
.status-pending .status-dot { background: #94a3b8; }
.status-processing { background: #eff6ff; color: #3b82f6; }
.status-processing .status-dot { background: #3b82f6; animation: pulse 1.5s infinite; }
.status-completed { background: #f0fdf4; color: #22c55e; }
.status-completed .status-dot { background: #22c55e; }
.status-error { background: #fef2f2; color: #ef4444; }
.status-error .status-dot { background: #ef4444; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
