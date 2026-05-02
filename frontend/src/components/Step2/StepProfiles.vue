<template>
  <div class="step-card" :class="{ 'active': phase === 1, 'completed': phase > 1 }">
    <div class="card-header">
      <div class="step-info">
        <span class="step-num">02</span>
        <span class="step-title">에이전트 프로필 생성</span>
      </div>
      <div class="step-status">
        <span v-if="phase > 1" class="badge success">완료</span>
        <span v-else-if="phase === 1" class="badge processing">{{ prepareProgress }}%</span>
        <span v-else class="badge pending">대기</span>
      </div>
    </div>

    <div class="card-content">
      <p class="api-note">POST /api/simulation/prepare</p>
      <p class="description">
        Using context, automatically calls tools to extract entities and relationships from the knowledge graph, initializes simulated individuals, and assigns them unique behaviors and memories based on reality seeds
      </p>

      <!-- Profiles Stats -->
      <div v-if="profiles.length > 0" class="stats-grid">
        <div class="stat-card">
          <span class="stat-value">{{ profiles.length }}</span>
          <span class="stat-label">현재 에이전트 수</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ expectedTotal || '-' }}</span>
          <span class="stat-label">예상 총 에이전트 수</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ totalTopicsCount }}</span>
          <span class="stat-label">씨드 주제 수</span>
        </div>
      </div>

      <!-- Profiles List Preview -->
      <div v-if="profiles.length > 0" class="profiles-preview">
        <div class="preview-header">
          <span class="preview-title">생성된 에이전트 프로필</span>
        </div>
        <div class="profiles-list">
          <div
            v-for="(profile, idx) in profiles"
            :key="idx"
            class="profile-card"
            @click="$emit('select-profile', profile)"
          >
            <div class="profile-header">
              <span class="profile-realname">{{ profile.username || 'Unknown' }}</span>
              <span class="profile-username">@{{ profile.name || `agent_${idx}` }}</span>
            </div>
            <div class="profile-meta">
              <span class="profile-profession">{{ profile.profession || 'Unknown Profession' }}</span>
            </div>
            <p class="profile-bio">{{ profile.bio || 'No bio available' }}</p>
            <div v-if="profile.interested_topics?.length" class="profile-topics">
              <span
                v-for="topic in profile.interested_topics.slice(0, 3)"
                :key="topic"
                class="topic-tag"
              >{{ topic }}</span>
              <span v-if="profile.interested_topics.length > 3" class="topic-more">
                +{{ profile.interested_topics.length - 3 }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  phase: { type: Number, required: true },
  prepareProgress: { type: Number, default: 0 },
  profiles: { type: Array, default: () => [] },
  expectedTotal: { type: [Number, String], default: null },
})

defineEmits(['select-profile'])

const totalTopicsCount = computed(() =>
  props.profiles.reduce((sum, p) => sum + (p.interested_topics?.length || 0), 0),
)
</script>

<style scoped src="./_step-framework.css"></style>
<style scoped>
/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Profiles Preview */
.profiles-preview {
  margin-top: 20px;
  border-top: 1px solid #E5E5E5;
  padding-top: 16px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.preview-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.profiles-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.profiles-list::-webkit-scrollbar {
  width: 4px;
}

.profiles-list::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.profiles-list::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.profile-card {
  background: #FAFAFA;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.profile-card:hover {
  border-color: #999;
  background: #FFF;
}

.profile-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.profile-realname {
  font-size: 14px;
  font-weight: 700;
  color: #000;
}

.profile-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #999;
}

.profile-meta {
  margin-bottom: 8px;
}

.profile-profession {
  font-size: 11px;
  color: #666;
  background: #F0F0F0;
  padding: 2px 8px;
  border-radius: 3px;
}

.profile-bio {
  font-size: 12px;
  color: #444;
  line-height: 1.6;
  margin: 0 0 10px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.profile-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-tag {
  font-size: 10px;
  color: #1565C0;
  background: #E3F2FD;
  padding: 2px 8px;
  border-radius: 10px;
}

.topic-more {
  font-size: 10px;
  color: #999;
  padding: 2px 6px;
}
</style>
