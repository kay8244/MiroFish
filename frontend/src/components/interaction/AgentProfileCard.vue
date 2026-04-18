<template>
  <div class="agent-profile-card">
    <div class="profile-card-header">
      <div class="profile-card-avatar">{{ (agent.username || 'A')[0] }}</div>
      <div class="profile-card-info">
        <div class="profile-card-name">{{ agent.username }}</div>
        <div class="profile-card-meta">
          <span v-if="agent.name" class="profile-card-handle">@{{ agent.name }}</span>
          <span class="profile-card-profession">{{ agent.profession || 'Unknown profession' }}</span>
        </div>
      </div>
      <button class="profile-card-toggle" @click="expanded = !expanded">
        <svg :class="{ 'is-expanded': expanded }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
    </div>
    <div v-if="expanded && agent.bio" class="profile-card-body">
      <div class="profile-card-bio">
        <div class="profile-card-label">Bio</div>
        <p>{{ agent.bio }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  agent: { type: Object, required: true },
  showFullProfile: { type: Boolean, default: true }
})

const expanded = ref(props.showFullProfile)
</script>

<style scoped>
.agent-profile-card {
  background: #FFFFFF;
  border-bottom: 1px solid #E5E7EB;
  flex-shrink: 0;
}

.profile-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
}

.profile-card-avatar {
  width: 36px;
  height: 36px;
  background: #374151;
  color: #FFF;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.profile-card-info {
  flex: 1;
  min-width: 0;
}

.profile-card-name {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.profile-card-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}

.profile-card-handle {
  font-size: 11px;
  color: #9CA3AF;
}

.profile-card-profession {
  font-size: 11px;
  color: #9CA3AF;
}

.profile-card-toggle {
  background: none;
  border: none;
  cursor: pointer;
  color: #9CA3AF;
  padding: 4px;
  display: flex;
  align-items: center;
}

.profile-card-toggle svg {
  transition: transform 0.3s;
}

.profile-card-toggle svg.is-expanded {
  transform: rotate(180deg);
}

.profile-card-body {
  padding: 0 20px 14px;
}

.profile-card-label {
  font-size: 10px;
  font-weight: 600;
  color: #9CA3AF;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.profile-card-bio p {
  font-size: 12px;
  color: #4B5563;
  line-height: 1.6;
  margin: 0;
}
</style>
