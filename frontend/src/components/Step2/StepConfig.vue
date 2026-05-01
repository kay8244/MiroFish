<template>
  <div class="step-card" :class="{ 'active': phase === 2, 'completed': phase > 2 }">
    <div class="card-header">
      <div class="step-info">
        <span class="step-num">03</span>
        <span class="step-title">Generate Dual-Platform Simulation Config</span>
      </div>
      <div class="step-status">
        <span v-if="phase > 2" class="badge success">완료</span>
        <span v-else-if="phase === 2" class="badge processing">생성 중</span>
        <span v-else class="badge pending">대기</span>
      </div>
    </div>

    <div class="card-content">
      <p class="api-note">POST /api/simulation/prepare</p>
      <p class="description">
        LLM intelligently configures world time speed based on simulation requirements and reality seeds, recommendation algorithm, each individual's active time periods, posting frequency, event triggers, and other parameters
      </p>

      <!-- Config Preview -->
      <div v-if="simulationConfig" class="config-detail-panel">
        <!-- Time Config -->
        <div class="config-block">
          <div class="config-grid">
            <div class="config-item">
              <span class="config-item-label">시뮬레이션 기간</span>
              <span class="config-item-value">{{ simulationConfig.time_config?.total_simulation_hours || '-' }} hrs</span>
            </div>
            <div class="config-item">
              <span class="config-item-label">라운드 길이</span>
              <span class="config-item-value">{{ simulationConfig.time_config?.minutes_per_round || '-' }} min</span>
            </div>
            <div class="config-item">
              <span class="config-item-label">총 라운드</span>
              <span class="config-item-value">{{ Math.floor((simulationConfig.time_config?.total_simulation_hours * 60 / simulationConfig.time_config?.minutes_per_round)) || '-' }} rounds</span>
            </div>
            <div class="config-item">
              <span class="config-item-label">시간당 활성 수</span>
              <span class="config-item-value">{{ simulationConfig.time_config?.agents_per_hour_min }}-{{ simulationConfig.time_config?.agents_per_hour_max }}</span>
            </div>
          </div>
          <div class="time-periods">
            <div class="period-item">
              <span class="period-label">피크 시간대</span>
              <span class="period-hours">{{ simulationConfig.time_config?.peak_hours?.join(':00, ') }}:00</span>
              <span class="period-multiplier">×{{ simulationConfig.time_config?.peak_activity_multiplier }}</span>
            </div>
            <div class="period-item">
              <span class="period-label">업무 시간대</span>
              <span class="period-hours">{{ simulationConfig.time_config?.work_hours?.[0] }}:00-{{ simulationConfig.time_config?.work_hours?.slice(-1)[0] }}:00</span>
              <span class="period-multiplier">×{{ simulationConfig.time_config?.work_activity_multiplier }}</span>
            </div>
            <div class="period-item">
              <span class="period-label">아침 시간대</span>
              <span class="period-hours">{{ simulationConfig.time_config?.morning_hours?.[0] }}:00-{{ simulationConfig.time_config?.morning_hours?.slice(-1)[0] }}:00</span>
              <span class="period-multiplier">×{{ simulationConfig.time_config?.morning_activity_multiplier }}</span>
            </div>
            <div class="period-item">
              <span class="period-label">Off-Peak Hours</span>
              <span class="period-hours">{{ simulationConfig.time_config?.off_peak_hours?.[0] }}:00-{{ simulationConfig.time_config?.off_peak_hours?.slice(-1)[0] }}:00</span>
              <span class="period-multiplier">×{{ simulationConfig.time_config?.off_peak_activity_multiplier }}</span>
            </div>
          </div>
        </div>

        <!-- Agent Config -->
        <div class="config-block">
          <div class="config-block-header">
            <span class="config-block-title">에이전트 설정</span>
            <span class="config-block-badge">{{ simulationConfig.agent_configs?.length || 0 }}</span>
          </div>
          <div class="agents-cards">
            <div
              v-for="agent in simulationConfig.agent_configs"
              :key="agent.agent_id"
              class="agent-card"
            >
              <!-- Card Header -->
              <div class="agent-card-header">
                <div class="agent-identity">
                  <span class="agent-id">Agent {{ agent.agent_id }}</span>
                  <span class="agent-name">{{ agent.entity_name }}</span>
                </div>
                <div class="agent-tags">
                  <span class="agent-type">{{ agent.entity_type }}</span>
                  <span class="agent-stance" :class="'stance-' + agent.stance">{{ agent.stance }}</span>
                </div>
              </div>

              <!-- Active Timeline -->
              <div class="agent-timeline">
                <span class="timeline-label">활성 시간</span>
                <div class="mini-timeline">
                  <div
                    v-for="hour in 24"
                    :key="hour - 1"
                    class="timeline-hour"
                    :class="{ 'active': agent.active_hours?.includes(hour - 1) }"
                    :title="`${hour - 1}:00`"
                  ></div>
                </div>
                <div class="timeline-marks">
                  <span>0</span>
                  <span>6</span>
                  <span>12</span>
                  <span>18</span>
                  <span>24</span>
                </div>
              </div>

              <!-- Behavior Parameters -->
              <div class="agent-params">
                <div class="param-group">
                  <div class="param-item">
                    <span class="param-label">Posts/hr</span>
                    <span class="param-value">{{ agent.posts_per_hour }}</span>
                  </div>
                  <div class="param-item">
                    <span class="param-label">Comments/hr</span>
                    <span class="param-value">{{ agent.comments_per_hour }}</span>
                  </div>
                  <div class="param-item">
                    <span class="param-label">응답 지연</span>
                    <span class="param-value">{{ agent.response_delay_min }}-{{ agent.response_delay_max }}min</span>
                  </div>
                </div>
                <div class="param-group">
                  <div class="param-item">
                    <span class="param-label">활성도</span>
                    <span class="param-value with-bar">
                      <span class="mini-bar" :style="{ width: (agent.activity_level * 100) + '%' }"></span>
                      {{ (agent.activity_level * 100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="param-item">
                    <span class="param-label">감정 편향</span>
                    <span class="param-value" :class="agent.sentiment_bias > 0 ? 'positive' : agent.sentiment_bias < 0 ? 'negative' : 'neutral'">
                      {{ agent.sentiment_bias > 0 ? '+' : '' }}{{ agent.sentiment_bias?.toFixed(1) }}
                    </span>
                  </div>
                  <div class="param-item">
                    <span class="param-label">영향력</span>
                    <span class="param-value highlight">{{ agent.influence_weight?.toFixed(1) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Platform Config -->
        <div class="config-block">
          <div class="config-block-header">
            <span class="config-block-title">추천 알고리즘 설정</span>
          </div>
          <div class="platforms-grid">
            <div v-if="simulationConfig.twitter_config" class="platform-card">
              <div class="platform-card-header">
                <span class="platform-name">Platform 1: Square / Feed</span>
              </div>
              <div class="platform-params">
                <div class="param-row">
                  <span class="param-label">최신성 가중치</span>
                  <span class="param-value">{{ simulationConfig.twitter_config.recency_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">인기도 가중치</span>
                  <span class="param-value">{{ simulationConfig.twitter_config.popularity_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">관련성 가중치</span>
                  <span class="param-value">{{ simulationConfig.twitter_config.relevance_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">바이럴 임계값</span>
                  <span class="param-value">{{ simulationConfig.twitter_config.viral_threshold }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">에코챔버 강도</span>
                  <span class="param-value">{{ simulationConfig.twitter_config.echo_chamber_strength }}</span>
                </div>
              </div>
            </div>
            <div v-if="simulationConfig.reddit_config" class="platform-card">
              <div class="platform-card-header">
                <span class="platform-name">Platform 2: Topics / Community</span>
              </div>
              <div class="platform-params">
                <div class="param-row">
                  <span class="param-label">최신성 가중치</span>
                  <span class="param-value">{{ simulationConfig.reddit_config.recency_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">인기도 가중치</span>
                  <span class="param-value">{{ simulationConfig.reddit_config.popularity_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">관련성 가중치</span>
                  <span class="param-value">{{ simulationConfig.reddit_config.relevance_weight }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">바이럴 임계값</span>
                  <span class="param-value">{{ simulationConfig.reddit_config.viral_threshold }}</span>
                </div>
                <div class="param-row">
                  <span class="param-label">에코챔버 강도</span>
                  <span class="param-value">{{ simulationConfig.reddit_config.echo_chamber_strength }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- LLM Config Reasoning -->
        <div v-if="simulationConfig.generation_reasoning" class="config-block">
          <div class="config-block-header">
            <span class="config-block-title">LLM 설정 근거</span>
          </div>
          <div class="reasoning-content">
            <div
              v-for="(reason, idx) in simulationConfig.generation_reasoning.split('|').slice(0, 2)"
              :key="idx"
              class="reasoning-item"
            >
              <p class="reasoning-text">{{ reason.trim() }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  phase: { type: Number, required: true },
  simulationConfig: { type: Object, default: null },
})
</script>

<style scoped src="./_step-framework.css"></style>
<style scoped>
/* Config Detail Panel */
.config-detail-panel {
  margin-top: 16px;
}

.config-block {
  margin-top: 16px;
  border-top: 1px solid #E5E5E5;
  padding-top: 12px;
}

.config-block:first-child {
  margin-top: 0;
  border-top: none;
  padding-top: 0;
}

.config-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.config-block-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.config-block-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  background: #F1F5F9;
  color: #475569;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Config Grid */
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.config-item {
  background: #F9F9F9;
  padding: 12px 14px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-item-label {
  font-size: 11px;
  color: #94A3B8;
}

.config-item-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 600;
  color: #1E293B;
}

/* Time Periods */
.time-periods {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.period-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #F9F9F9;
  border-radius: 6px;
}

.period-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748B;
  min-width: 70px;
}

.period-hours {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #475569;
  flex: 1;
}

.period-multiplier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  color: #6366F1;
  background: #EEF2FF;
  padding: 2px 6px;
  border-radius: 4px;
}

/* Agents Cards */
.agents-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 4px;
}

.agents-cards::-webkit-scrollbar {
  width: 4px;
}

.agents-cards::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.agents-cards::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.agent-card {
  background: #F9F9F9;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  transition: all 0.2s ease;
}

.agent-card:hover {
  border-color: #999;
  background: #FFF;
}

/* Agent Card Header */
.agent-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F1F5F9;
}

.agent-identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #94A3B8;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.agent-tags {
  display: flex;
  gap: 6px;
}

.agent-type {
  font-size: 10px;
  color: #64748B;
  background: #F1F5F9;
  padding: 2px 8px;
  border-radius: 4px;
}

.agent-stance {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}

.stance-neutral {
  background: #F1F5F9;
  color: #64748B;
}

.stance-supportive {
  background: #DCFCE7;
  color: #16A34A;
}

.stance-opposing {
  background: #FEE2E2;
  color: #DC2626;
}

.stance-observer {
  background: #FEF3C7;
  color: #D97706;
}

/* Agent Timeline */
.agent-timeline {
  margin-bottom: 14px;
}

.timeline-label {
  display: block;
  font-size: 10px;
  color: #94A3B8;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mini-timeline {
  display: flex;
  gap: 2px;
  height: 16px;
  background: #F8FAFC;
  border-radius: 4px;
  padding: 3px;
}

.timeline-hour {
  flex: 1;
  background: #E2E8F0;
  border-radius: 2px;
  transition: all 0.2s;
}

.timeline-hour.active {
  background: linear-gradient(180deg, #6366F1, #818CF8);
}

.timeline-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: #94A3B8;
}

/* Agent Params */
.agent-params {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.param-item .param-label {
  font-size: 10px;
  color: #94A3B8;
}

.param-item .param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.param-value.with-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mini-bar {
  height: 4px;
  background: linear-gradient(90deg, #6366F1, #A855F7);
  border-radius: 2px;
  min-width: 4px;
  max-width: 40px;
}

.param-value.positive {
  color: #16A34A;
}

.param-value.negative {
  color: #DC2626;
}

.param-value.neutral {
  color: #64748B;
}

.param-value.highlight {
  color: #6366F1;
}

/* Platforms Grid */
.platforms-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.platform-card {
  background: #F9F9F9;
  padding: 14px;
  border-radius: 6px;
}

.platform-card-header {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #E5E5E5;
}

.platform-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.platform-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-label {
  font-size: 12px;
  color: #64748B;
}

.param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #1E293B;
}

/* Reasoning Content */
.reasoning-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reasoning-item {
  padding: 12px 14px;
  background: #F9F9F9;
  border-radius: 6px;
}

.reasoning-text {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  margin: 0;
}
</style>
