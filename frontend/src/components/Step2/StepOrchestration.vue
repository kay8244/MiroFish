<template>
  <div class="step-card" :class="{ 'active': phase === 3, 'completed': phase > 3 }">
    <div class="card-header">
      <div class="step-info">
        <span class="step-num">04</span>
        <span class="step-title">초기 활성화 오케스트레이션</span>
      </div>
      <div class="step-status">
        <span v-if="phase > 3" class="badge success">완료</span>
        <span v-else-if="phase === 3" class="badge processing">오케스트레이션 중</span>
        <span v-else class="badge pending">대기</span>
      </div>
    </div>

    <div class="card-content">
      <p class="api-note">POST /api/simulation/prepare</p>
      <p class="description">
        Based on the narrative direction, automatically generates initial activation events and trending topics to guide the initial state of the simulation world
      </p>

      <div v-if="simulationConfig?.event_config" class="orchestration-content">
        <!-- Narrative Direction -->
        <div class="narrative-box">
          <span class="box-label narrative-label">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="special-icon">
              <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M16.24 7.76L14.12 14.12L7.76 16.24L9.88 9.88L16.24 7.76Z" fill="url(#paint0_linear)" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              <defs>
                <linearGradient id="paint0_linear" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#FF5722"/>
                  <stop offset="1" stop-color="#FF9800"/>
                </linearGradient>
              </defs>
            </svg>
            Narrative Direction
          </span>
          <p class="narrative-text">{{ simulationConfig.event_config.narrative_direction }}</p>
        </div>

        <!-- Trending Topics -->
        <div class="topics-section">
          <span class="box-label">초기 트렌딩 토픽</span>
          <div class="hot-topics-grid">
            <span v-for="topic in simulationConfig.event_config.hot_topics" :key="topic" class="hot-topic-tag">
              # {{ topic }}
            </span>
          </div>
        </div>

        <!-- Initial Post Stream -->
        <div class="initial-posts-section">
          <span class="box-label">Initial Activation Sequence ({{ simulationConfig.event_config.initial_posts.length }})</span>
          <div class="posts-timeline">
            <div v-for="(post, idx) in simulationConfig.event_config.initial_posts" :key="idx" class="timeline-item">
              <div class="timeline-marker"></div>
              <div class="timeline-content">
                <div class="post-header">
                  <span class="post-role">{{ post.poster_type }}</span>
                  <span class="post-agent-info">
                    <span class="post-id">Agent {{ post.poster_agent_id }}</span>
                    <span class="post-username">@{{ getAgentUsername(post.poster_agent_id) }}</span>
                  </span>
                </div>
                <p class="post-text">{{ post.content }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  phase: { type: Number, required: true },
  simulationConfig: { type: Object, default: null },
  profiles: { type: Array, default: () => [] },
})

const getAgentUsername = (agentId) => {
  if (props.profiles && props.profiles.length > agentId && agentId >= 0) {
    return props.profiles[agentId]?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}
</script>

<style scoped src="./_step-framework.css"></style>
<style scoped>
.orchestration-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 16px;
}

.box-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.narrative-box {
  background: #FFFFFF;
  padding: 20px 24px;
  border-radius: 12px;
  border: 1px solid #EEF2F6;
  box-shadow: 0 4px 24px rgba(0,0,0,0.03);
  transition: all 0.3s ease;
}

.narrative-box .box-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 13px;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  font-weight: 600;
}

.special-icon {
  filter: drop-shadow(0 2px 4px rgba(255, 87, 34, 0.2));
  transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.narrative-box:hover .special-icon {
  transform: rotate(180deg);
}

.narrative-text {
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  color: #334155;
  line-height: 1.8;
  margin: 0;
  text-align: justify;
  letter-spacing: 0.01em;
}

.topics-section {
  background: #FFF;
}

.hot-topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hot-topic-tag {
  font-size: 12px;
  color: rgba(255, 86, 34, 0.88);
  background: #FFF3E0;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.hot-topic-more {
  font-size: 11px;
  color: #999;
  padding: 4px 6px;
}

.initial-posts-section {
  border-top: 1px solid #EAEAEA;
  padding-top: 16px;
}

.posts-timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-left: 8px;
  border-left: 2px solid #F0F0F0;
  margin-top: 12px;
}

.timeline-item {
  position: relative;
  padding-left: 20px;
}

.timeline-marker {
  position: absolute;
  left: 0;
  top: 14px;
  width: 12px;
  height: 2px;
  background: #DDD;
}

.timeline-content {
  background: #F9F9F9;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #EEE;
}

.post-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.post-role {
  font-size: 11px;
  font-weight: 700;
  color: #333;
  text-transform: uppercase;
}

.post-agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.post-id,
.post-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  line-height: 1;
  vertical-align: baseline;
}

.post-username {
  margin-right: 6px;
}

.post-text {
  font-size: 12px;
  color: #555;
  line-height: 1.5;
  margin: 0;
}
</style>
