<template>
  <div class="env-setup-panel">
    <div class="scroll-container">
      <!-- Step 01: Simulation Instance -->
      <div class="step-card" :class="{ 'active': phase === 0, 'completed': phase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">시뮬레이션 인스턴스 초기화</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 0" class="badge success">완료</span>
            <span v-else class="badge processing">초기화 중</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">
            Create a new simulation instance and pull the simulation world parameter template
          </p>

          <div v-if="simulationId" class="info-card">
            <div class="info-row">
              <span class="info-label">프로젝트 ID</span>
              <span class="info-value mono">{{ projectData?.project_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">그래프 ID</span>
              <span class="info-value mono">{{ projectData?.graph_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">시뮬레이션 ID</span>
              <span class="info-value mono">{{ simulationId }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">태스크 ID</span>
              <span class="info-value mono">{{ taskId || 'Async task completed' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Generate Agent Profiles -->
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
                @click="selectProfile(profile)"
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

      <!-- Step 03: Generate Dual-Platform Simulation Config -->
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

      <!-- Step 04: Initial Activation Orchestration -->
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

      <!-- Step 05: Ready -->
      <div class="step-card" :class="{ 'active': phase === 4 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">05</span>
            <span class="step-title">준비 완료</span>
          </div>
          <div class="step-status">
            <span v-if="phase >= 4" class="badge processing">진행 중</span>
            <span v-else class="badge pending">대기</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/start</p>
          <p class="description">Simulation environment is ready. You can now start running the simulation.</p>
          
          <!-- Simulation rounds config - only shown after config is generated and rounds are calculated -->
          <div v-if="simulationConfig && autoGeneratedRounds" class="rounds-config-section">
            <div class="rounds-header">
              <div class="header-left">
                <span class="section-title">시뮬레이션 라운드 설정</span>
                <span class="section-desc">MiroFish automatically plans simulation of <span class="desc-highlight">{{ simulationConfig?.time_config?.total_simulation_hours || '-' }}</span> real-world hours, each round represents <span class="desc-highlight">{{ simulationConfig?.time_config?.minutes_per_round || '-' }}</span> real-world minutes</span>
              </div>
              <label class="switch-control">
                <input type="checkbox" v-model="useCustomRounds">
                <span class="switch-track"></span>
                <span class="switch-label">커스텀</span>
              </label>
            </div>
            
            <Transition name="fade" mode="out-in">
              <div v-if="useCustomRounds" class="rounds-content custom" key="custom">
                <div class="slider-display">
                  <div class="slider-main-value">
                    <span class="val-num">{{ customMaxRounds }}</span>
                    <span class="val-unit">rounds</span>
                  </div>
                  <div class="slider-meta-info">
                    <span>With 100 agents: estimated ~{{ Math.round(customMaxRounds * 0.6) }} minutes</span>
                  </div>
                </div>

                <div class="range-wrapper">
                  <input 
                    type="range" 
                    v-model.number="customMaxRounds" 
                    min="10" 
                    :max="autoGeneratedRounds"
                    step="5"
                    class="minimal-slider"
                    :style="{ '--percent': ((customMaxRounds - 10) / (autoGeneratedRounds - 10)) * 100 + '%' }"
                  />
                  <div class="range-marks">
                    <span>10</span>
                    <span 
                      class="mark-recommend" 
                      :class="{ active: customMaxRounds === 40 }"
                      @click="customMaxRounds = 40"
                      :style="{ position: 'absolute', left: `calc(${(40 - 10) / (autoGeneratedRounds - 10) * 100}% - 30px)` }"
                    >40 (Recommended)</span>
                    <span>{{ autoGeneratedRounds }}</span>
                  </div>
                </div>
              </div>
              
              <div v-else class="rounds-content auto" key="auto">
                <div class="auto-info-card">
                  <div class="auto-value">
                    <span class="val-num">{{ autoGeneratedRounds }}</span>
                    <span class="val-unit">rounds</span>
                  </div>
                  <div class="auto-content">
                    <div class="auto-meta-row">
                      <span class="duration-badge">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <circle cx="12" cy="12" r="10"></circle>
                          <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        With 100 agents: estimated {{ Math.round(autoGeneratedRounds * 0.6) }} minutes
                      </span>
                    </div>
                    <div class="auto-desc">
                      <p class="highlight-tip" @click="useCustomRounds = true">For first-time runs, we strongly recommend switching to ‘Custom Mode’ to reduce simulation rounds for a quick preview and lower error risk ➝</p>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>

          <div class="action-group dual">
            <button 
              class="action-btn secondary"
              @click="$emit('go-back')"
            >
              ← Back to Graph Build
            </button>
            <button 
              class="action-btn primary"
              :disabled="phase < 4"
              @click="handleStartSimulation"
            >
              Start Dual-World Parallel Simulation ➝
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Profile Detail Modal -->
    <Transition name="modal">
      <div v-if="selectedProfile" class="profile-modal-overlay" @click.self="selectedProfile = null">
        <div class="profile-modal">
          <div class="modal-header">
          <div class="modal-header-info">
            <div class="modal-name-row">
              <span class="modal-realname">{{ selectedProfile.username }}</span>
              <span class="modal-username">@{{ selectedProfile.name }}</span>
            </div>
            <span class="modal-profession">{{ selectedProfile.profession }}</span>
          </div>
          <button class="close-btn" @click="selectedProfile = null">×</button>
        </div>
        
        <div class="modal-body">
          <!-- Basic Info -->
          <div class="modal-info-grid">
            <div class="info-item">
              <span class="info-label">외형 연령</span>
              <span class="info-value">{{ selectedProfile.age || '-' }} yrs</span>
            </div>
            <div class="info-item">
              <span class="info-label">외형 성별</span>
              <span class="info-value">{{ { male: 'Male', female: 'Female', other: 'Other' }[selectedProfile.gender] || selectedProfile.gender }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Country/Region</span>
              <span class="info-value">{{ selectedProfile.country || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">외형 MBTI</span>
              <span class="info-value mbti">{{ selectedProfile.mbti || '-' }}</span>
            </div>
          </div>

          <!-- Bio -->
          <div class="modal-section">
            <span class="section-label">프로필 소개</span>
            <p class="section-bio">{{ selectedProfile.bio || 'No bio available' }}</p>
          </div>

          <!-- Interested Topics -->
          <div class="modal-section" v-if="selectedProfile.interested_topics?.length">
            <span class="section-label">씨드 연관 토픽</span>
            <div class="topics-grid">
              <span 
                v-for="topic in selectedProfile.interested_topics" 
                :key="topic" 
                class="topic-item"
              >{{ topic }}</span>
            </div>
          </div>

          <!-- Detailed Persona -->
          <div class="modal-section" v-if="selectedProfile.persona">
            <span class="section-label">프로필 상세 배경</span>
            
            <!-- Persona Dimensions Overview -->
            <div class="persona-dimensions">
              <div class="dimension-card">
                <span class="dim-title">전체 이벤트 경험</span>
                <span class="dim-desc">이 이벤트에서의 전체 행동 궤적</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">행동 패턴 프로필</span>
                <span class="dim-desc">경험 요약과 행동 스타일 선호</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">고유 메모리 각인</span>
                <span class="dim-desc">씨드 기반으로 형성된 메모리</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">사회 관계 네트워크</span>
                <span class="dim-desc">개별 링크 및 상호작용 그래프</span>
              </div>
            </div>

            <div class="persona-content">
              <p class="section-persona">{{ selectedProfile.persona }}</p>
            </div>
          </div>
        </div>
      </div>
      </div>
    </Transition>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">시스템 대시보드</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, onUnmounted, nextTick } from 'vue'
import {
  prepareSimulation,
  getPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfig,
  getSimulationConfigRealtime
} from '../api/simulation'
import { showToast } from '../utils/toast'

const props = defineProps({
  simulationId: String,  // Passed from parent component
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

// State
const phase = ref(0) // 0: initializing, 1: generating profiles, 2: generating config, 3: complete
const taskId = ref(null)
const prepareProgress = ref(0)
const currentStage = ref('')
const progressMessage = ref('')
const profiles = ref([])
const entityTypes = ref([])
const expectedTotal = ref(null)
const simulationConfig = ref(null)
const selectedProfile = ref(null)
const showProfilesDetail = ref(true)

// Log dedup: record key info from last output
let lastLoggedMessage = ''
let lastLoggedProfileCount = 0
let lastLoggedConfigStage = ''

// Simulation rounds config
const useCustomRounds = ref(false) // default: use auto-configured rounds
const customMaxRounds = ref(40)   // default recommended: 40 rounds

// Watch stage to update phase
watch(currentStage, (newStage) => {
  if (newStage === 'Generating Agent Profiles' || newStage === 'generating_profiles') {
    phase.value = 1
  } else if (newStage === 'Generating Simulation Config' || newStage === 'generating_config') {
    phase.value = 2
    // Entered config generation phase, start polling config
    if (!configTimer) {
      addLog('Starting dual-platform simulation config generation...')
      startConfigPolling()
    }
  } else if (newStage === 'Preparing Simulation Scripts' || newStage === 'copying_scripts') {
    phase.value = 2 // Still in config phase
  }
})

// Calculate auto-generated rounds from config (no hardcoded defaults)
const autoGeneratedRounds = computed(() => {
  if (!simulationConfig.value?.time_config) {
    return null // return null when config not yet generated
  }
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) {
    return null // return null when config data is incomplete
  }
  const calculatedRounds = Math.floor((totalHours * 60) / minutesPerRound)
  // Ensure max rounds is at least 40 (recommended value), avoid slider range issues
  return Math.max(calculatedRounds, 40)
})

// Polling timer
let pollTimer = null
let profilesTimer = null
let configTimer = null

// Computed
const displayProfiles = computed(() => {
  if (showProfilesDetail.value) {
    return profiles.value
  }
  return profiles.value.slice(0, 6)
})

// Get username by agent_id
const getAgentUsername = (agentId) => {
  if (profiles.value && profiles.value.length > agentId && agentId >= 0) {
    const profile = profiles.value[agentId]
    return profile?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}

// Calculate total associated topic count for all profiles
const totalTopicsCount = computed(() => {
  return profiles.value.reduce((sum, p) => {
    return sum + (p.interested_topics?.length || 0)
  }, 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// Handle start simulation button click
const handleStartSimulation = () => {
  // Build params to pass to parent component
  const params = {}
  
  if (useCustomRounds.value) {
    // User custom rounds, pass max_rounds parameter
    params.maxRounds = customMaxRounds.value
    addLog(`Starting simulation, custom rounds: ${customMaxRounds.value}`)
  } else {
    // User keeps auto-generated rounds, do not pass max_rounds parameter
    addLog(`Starting simulation, using auto-configured rounds: ${autoGeneratedRounds.value}`)
  }
  
  emit('next-step', params)
}

const truncateBio = (bio) => {
  if (bio.length > 80) {
    return bio.substring(0, 80) + '...'
  }
  return bio
}

const selectProfile = (profile) => {
  selectedProfile.value = profile
}

// Auto-start simulation preparation
const startPrepareSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    emit('update-status', 'error')
    return
  }
  
  // Mark first step complete, start second step
  phase.value = 1
  addLog(`Simulation instance created: ${props.simulationId}`)
  addLog('Preparing simulation environment...')
  emit('update-status', 'processing')
  
  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5
    })
    
    if (res.success && res.data) {
      if (res.data.already_prepared) {
        addLog('Detected completed preparation work, using directly')
        await loadPreparedData()
        return
      }
      
      taskId.value = res.data.task_id
      addLog(`Preparation task started`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)
      
      // Immediately set expected Agent count (from prepare API response)
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
        addLog(`Read ${res.data.expected_entities_count} entities from Zep graph`)
        if (res.data.entity_types && res.data.entity_types.length > 0) {
          addLog(`  └─ Entity types: ${res.data.entity_types.join(', ')}`)
        }
      }
      
      addLog('Starting to poll preparation progress...')
      // Start polling progress
      startPolling()
      // Start real-time profile fetching
      startProfilesPolling()
    } else {
      addLog(`Preparation failed: ${res.error || 'Unknown error'}`)
      showToast(`시뮬레이션 준비에 실패했습니다: ${res.error || '알 수 없는 오류'}`, 'error')
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`Preparation exception: ${err.message}`)
    showToast(`시뮬레이션 준비 중 오류가 발생했습니다: ${err.message}`, 'error')
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  pollTimer = setInterval(pollPrepareStatus, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startProfilesPolling = () => {
  profilesTimer = setInterval(fetchProfilesRealtime, 3000)
}

const stopProfilesPolling = () => {
  if (profilesTimer) {
    clearInterval(profilesTimer)
    profilesTimer = null
  }
}

const pollPrepareStatus = async () => {
  if (!taskId.value && !props.simulationId) return
  
  try {
    const res = await getPrepareStatus({
      task_id: taskId.value,
      simulation_id: props.simulationId
    })
    
    if (res.success && res.data) {
      const data = res.data
      
      // Update progress
      prepareProgress.value = data.progress || 0
      progressMessage.value = data.message || ''
      
      // Parse stage info and output detailed log
      if (data.progress_detail) {
        currentStage.value = data.progress_detail.current_stage_name || ''
        
        // Output detailed progress log (avoid duplicates)
        const detail = data.progress_detail
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (logKey !== lastLoggedMessage && detail.item_description) {
          lastLoggedMessage = logKey
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          if (detail.total_items > 0) {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`)
          } else {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`)
          }
        }
      } else if (data.message) {
        // Extract stage from message
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) {
          currentStage.value = match[3].trim()
        }
        // Output message log (avoid duplicates)
        if (data.message !== lastLoggedMessage) {
          lastLoggedMessage = data.message
          addLog(data.message)
        }
      }
      
      // Check if complete
      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog('✓ Preparation completed')
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(`✗ Preparation failed: ${data.error || 'Unknown error'}`)
        stopPolling()
        stopProfilesPolling()
      }
    }
  } catch (err) {
    console.warn('Polling status failed:', err)
  }
}

const fetchProfilesRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    
    if (res.success && res.data) {
      const prevCount = profiles.value.length
      profiles.value = res.data.profiles || []
      // Only update when API returns valid value, avoid overwriting existing valid value
      if (res.data.total_expected) {
        expectedTotal.value = res.data.total_expected
      }
      
      // Extract entity types
      const types = new Set()
      profiles.value.forEach(p => {
        if (p.entity_type) types.add(p.entity_type)
      })
      entityTypes.value = Array.from(types)
      
      // Output profile generation progress log (only when count changes)
      const currentCount = profiles.value.length
      if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
        lastLoggedProfileCount = currentCount
        const total = expectedTotal.value || '?'
        const latestProfile = profiles.value[currentCount - 1]
        const profileName = latestProfile?.name || latestProfile?.username || `Agent_${currentCount}`
        if (currentCount === 1) {
          addLog(`Starting Agent profile generation...`)
        }
        addLog(`→ Agent profile ${currentCount}/${total}: ${profileName} (${latestProfile?.profession || 'Unknown profession'})`)
        
        // If all generated
        if (expectedTotal.value && currentCount >= expectedTotal.value) {
          addLog(`✓ All ${currentCount} Agent profiles generated`)
        }
      }
    }
  } catch (err) {
    console.warn('Failed to fetch profiles:', err)
  }
}

// Config polling
const startConfigPolling = () => {
  configTimer = setInterval(fetchConfigRealtime, 2000)
}

const stopConfigPolling = () => {
  if (configTimer) {
    clearInterval(configTimer)
    configTimer = null
  }
}

const fetchConfigRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      // Output config generation stage log (avoid duplicates)
      if (data.generation_stage && data.generation_stage !== lastLoggedConfigStage) {
        lastLoggedConfigStage = data.generation_stage
        if (data.generation_stage === 'generating_profiles') {
          addLog('Generating Agent profile config...')
        } else if (data.generation_stage === 'generating_config') {
          addLog('Calling LLM to generate simulation config parameters...')
        }
      }
      
      // If config has been generated
      if (data.config_generated && data.config) {
        simulationConfig.value = data.config
        addLog('✓ Simulation config generation complete')
        
        // Show detailed config summary
        if (data.summary) {
          addLog(`  ├─ Agent count: ${data.summary.total_agents}`)
          addLog(`  ├─ Simulation duration: ${data.summary.simulation_hours} hours`)
          addLog(`  ├─ Initial posts: ${data.summary.initial_posts_count}`)
          addLog(`  ├─ Trending topics: ${data.summary.hot_topics_count}`)
          addLog(`  └─ Platform config: Twitter ${data.summary.has_twitter_config ? '✓' : '✗'}, Reddit ${data.summary.has_reddit_config ? '✓' : '✗'}`)
        }
        
        // Show time config details
        if (data.config.time_config) {
          const tc = data.config.time_config
          addLog(`Time config: ${tc.minutes_per_round} min/round, ${Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)} total rounds`)
        }
        
        // Show event config
        if (data.config.event_config?.narrative_direction) {
          const narrative = data.config.event_config.narrative_direction
          addLog(`Narrative direction: ${narrative.length > 50 ? narrative.substring(0, 50) + '...' : narrative}`)
        }
        
        stopConfigPolling()
        phase.value = 4
        addLog('✓ Environment setup complete, ready to start simulation')
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Failed to fetch config:', err)
  }
}

const loadPreparedData = async () => {
  phase.value = 2
  addLog('Loading existing config data...')

  // Fetch profiles one final time
  await fetchProfilesRealtime()
  addLog(`Loaded ${profiles.value.length} Agent profiles`)

  // Fetch config (using realtime API)
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      if (res.data.config_generated && res.data.config) {
        simulationConfig.value = res.data.config
        addLog('✓ Simulation config loaded successfully')
        
        // Show detailed config summary
        if (res.data.summary) {
          addLog(`  ├─ Agent count: ${res.data.summary.total_agents}`)
          addLog(`  ├─ Simulation duration: ${res.data.summary.simulation_hours} hours`)
          addLog(`  └─ Initial posts: ${res.data.summary.initial_posts_count}`)
        }
        
        addLog('✓ Environment setup complete, ready to start simulation')
        phase.value = 4
        emit('update-status', 'completed')
      } else {
        // Config not yet generated, start polling
        addLog('Config generating, starting poll wait...')
        startConfigPolling()
      }
    }
  } catch (err) {
    addLog(`Failed to load config: ${err.message}`)
    emit('update-status', 'error')
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

onMounted(() => {
  // Auto-start preparation flow
  if (props.simulationId) {
    addLog('Step2 Environment Setup Initialization')
    startPrepareSimulation()
  }
})

const clearAllTimers = () => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (profilesTimer) { clearInterval(profilesTimer); profilesTimer = null }
  if (configTimer) { clearInterval(configTimer); configTimer = null }
}

onBeforeUnmount(() => {
  clearAllTimers()
})

onUnmounted(() => {
  clearAllTimers()
})
</script>

<style scoped src="./Step2EnvSetup.styles.css"></style>
