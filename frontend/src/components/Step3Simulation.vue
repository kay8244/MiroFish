<template>
  <div class="simulation-panel">
    <!-- Top Control Bar -->
    <div class="control-bar">
      <div class="status-group">
        <!-- Info Plaza platform progress -->
        <div class="platform-status twitter" :class="{ active: runStatus.twitter_running, completed: runStatus.twitter_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
            <span class="platform-name">Info Plaza</span>
            <span v-if="runStatus.twitter_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">ROUND</span>
              <span class="stat-value mono">{{ runStatus.twitter_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">Elapsed Time</span>
              <span class="stat-value mono">{{ twitterElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">ACTS</span>
              <span class="stat-value mono">{{ runStatus.twitter_actions_count || 0 }}</span>
            </span>
          </div>
          <!-- Available actions tooltip -->
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">REPOST</span>
              <span class="tooltip-action">QUOTE</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">IDLE</span>
            </div>
          </div>
        </div>

        <!-- Topic Community platform progress -->
        <div class="platform-status reddit" :class="{ active: runStatus.reddit_running, completed: runStatus.reddit_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
            </svg>
            <span class="platform-name">Topic Community</span>
            <span v-if="runStatus.reddit_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">ROUND</span>
              <span class="stat-value mono">{{ runStatus.reddit_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">Elapsed Time</span>
              <span class="stat-value mono">{{ redditElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">ACTS</span>
              <span class="stat-value mono">{{ runStatus.reddit_actions_count || 0 }}</span>
            </span>
          </div>
          <!-- Available actions tooltip -->
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">COMMENT</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">DISLIKE</span>
              <span class="tooltip-action">SEARCH</span>
              <span class="tooltip-action">TREND</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">MUTE</span>
              <span class="tooltip-action">REFRESH</span>
              <span class="tooltip-action">IDLE</span>
            </div>
          </div>
        </div>
      </div>

      <div class="action-controls">
        <button
          class="action-btn primary"
          :disabled="phase !== 2 || isGeneratingReport"
          @click="handleNextStep"
        >
          <span v-if="isGeneratingReport" class="loading-spinner-small"></span>
          {{ isGeneratingReport ? 'Launching...' : 'Generate Result Report' }}
          <span v-if="!isGeneratingReport" class="arrow-icon">→</span>
        </button>
      </div>
    </div>

    <!-- Main Content: Dual Timeline -->
    <div class="main-content-area" ref="scrollContainer">
      <!-- Timeline Header -->
      <div class="timeline-header" v-if="allActions.length > 0">
        <div class="timeline-stats">
          <span class="total-count">TOTAL EVENTS: <span class="mono">{{ allActions.length }}</span></span>
          <span class="platform-breakdown">
            <span class="breakdown-item twitter">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
              <span class="mono">{{ twitterActionsCount }}</span>
            </span>
            <span class="breakdown-divider">/</span>
            <span class="breakdown-item reddit">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
              <span class="mono">{{ redditActionsCount }}</span>
            </span>
          </span>
        </div>
      </div>

      <!-- Timeline Feed -->
      <div class="timeline-feed">
        <div class="timeline-axis"></div>

        <TransitionGroup name="timeline-item">
          <div
            v-for="action in chronologicalActions"
            :key="action._uniqueId || action.id || `${action.timestamp}-${action.agent_id}`"
            class="timeline-item"
            :class="action.platform"
          >
            <div class="timeline-marker">
              <div class="marker-dot"></div>
            </div>

            <div class="timeline-card">
              <div class="card-header">
                <div class="agent-info">
                  <div class="avatar-placeholder">{{ (action.agent_name || 'A')[0] }}</div>
                  <span class="agent-name">{{ action.agent_name }}</span>
                </div>

                <div class="header-meta">
                  <div class="platform-indicator">
                    <svg v-if="action.platform === 'twitter'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                    <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                  </div>
                  <div class="action-badge" :class="getActionTypeClass(action.action_type)">
                    {{ getActionTypeLabel(action.action_type) }}
                  </div>
                </div>
              </div>

              <div class="card-body">
                <!-- CREATE_POST: Publish post -->
                <div v-if="action.action_type === 'CREATE_POST' && action.action_args?.content" class="content-text main-text">
                  {{ action.action_args.content }}
                </div>

                <!-- QUOTE_POST: Quote post -->
                <template v-if="action.action_type === 'QUOTE_POST'">
                  <div v-if="action.action_args?.quote_content" class="content-text">
                    {{ action.action_args.quote_content }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="quoted-block">
                    <div class="quote-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                      <span class="quote-label">@{{ action.action_args.original_author_name || 'User' }}</span>
                    </div>
                    <div class="quote-text">
                      {{ truncateContent(action.action_args.original_content, 150) }}
                    </div>
                  </div>
                </template>

                <!-- REPOST: Repost -->
                <template v-if="action.action_type === 'REPOST'">
                  <div class="repost-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>
                    <span class="repost-label">Reposted from @{{ action.action_args?.original_author_name || 'User' }}</span>
                  </div>
                  <div v-if="action.action_args?.original_content" class="repost-content">
                    {{ truncateContent(action.action_args.original_content, 200) }}
                  </div>
                </template>

                <!-- LIKE_POST: Like post -->
                <template v-if="action.action_type === 'LIKE_POST'">
                  <div class="like-info">
                    <svg class="icon-small filled" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    <span class="like-label">Liked @{{ action.action_args?.post_author_name || 'User' }}'s post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="liked-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- CREATE_COMMENT: Post comment -->
                <template v-if="action.action_type === 'CREATE_COMMENT'">
                  <div v-if="action.action_args?.content" class="content-text">
                    {{ action.action_args.content }}
                  </div>
                  <div v-if="action.action_args?.post_id" class="comment-context">
                    <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                    <span>Reply to post #{{ action.action_args.post_id }}</span>
                  </div>
                </template>

                <!-- SEARCH_POSTS: Search posts -->
                <template v-if="action.action_type === 'SEARCH_POSTS'">
                  <div class="search-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <span class="search-label">Search Query:</span>
                    <span class="search-query">"{{ action.action_args?.query || '' }}"</span>
                  </div>
                </template>

                <!-- FOLLOW: Follow user -->
                <template v-if="action.action_type === 'FOLLOW'">
                  <div class="follow-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
                    <span class="follow-label">Followed @{{ action.action_args?.target_user || action.action_args?.user_id || 'User' }}</span>
                  </div>
                </template>

                <!-- UPVOTE / DOWNVOTE -->
                <template v-if="action.action_type === 'UPVOTE_POST' || action.action_type === 'DOWNVOTE_POST'">
                  <div class="vote-info">
                    <svg v-if="action.action_type === 'UPVOTE_POST'" class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    <svg v-else class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    <span class="vote-label">{{ action.action_type === 'UPVOTE_POST' ? 'Upvoted' : 'Downvoted' }} Post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="voted-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- DO_NOTHING: No action (idle) -->
                <template v-if="action.action_type === 'DO_NOTHING'">
                  <div class="idle-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <span class="idle-label">Action Skipped</span>
                  </div>
                </template>

                <!-- Generic fallback: unknown type or content not handled above -->
                <div v-if="!['CREATE_POST', 'QUOTE_POST', 'REPOST', 'LIKE_POST', 'CREATE_COMMENT', 'SEARCH_POSTS', 'FOLLOW', 'UPVOTE_POST', 'DOWNVOTE_POST', 'DO_NOTHING'].includes(action.action_type) && action.action_args?.content" class="content-text">
                  {{ action.action_args.content }}
                </div>
              </div>

              <div class="card-footer">
                <span class="time-tag">R{{ action.round_num }} • {{ formatActionTime(action.timestamp) }}</span>
                <!-- Platform tag removed as it is in header now -->
              </div>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="allActions.length === 0" class="waiting-state">
          <div class="pulse-ring"></div>
          <span>Waiting for agent actions...</span>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SIMULATION MONITOR</span>
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
import { useRouter } from 'vue-router'
import {
  startSimulation,
  stopSimulation,
  getRunStatus,
  getRunStatusDetail
} from '../api/simulation'
import { generateReport } from '../api/report'

const props = defineProps({
  simulationId: String,
  maxRounds: Number, // Maximum rounds passed in from Step2
  minutesPerRound: {
    type: Number,
    default: 30 // Default 30 minutes per round
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const router = useRouter()

// State
const isGeneratingReport = ref(false)
const phase = ref(0) // 0: not started, 1: running, 2: completed
const isStarting = ref(false)
const isStopping = ref(false)
const startError = ref(null)
const runStatus = ref({})
const allActions = ref([]) // All actions (incrementally accumulated)
const actionIds = ref(new Set()) // Action ID set for deduplication
const scrollContainer = ref(null)

// Computed
// Display actions in chronological order (newest at the bottom)
const chronologicalActions = computed(() => {
  return allActions.value
})

// Per-platform action counts
const twitterActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'twitter').length
})

const redditActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'reddit').length
})

// Format simulated elapsed time (computed from rounds * minutes per round)
const formatElapsedTime = (currentRound) => {
  if (!currentRound || currentRound <= 0) return '0h 0m'
  const totalMinutes = currentRound * props.minutesPerRound
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${minutes}m`
}

// Simulated elapsed time for Info Plaza platform
const twitterElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.twitter_current_round || 0)
})

// Simulated elapsed time for Topic Community platform
const redditElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.reddit_current_round || 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// Reset all state (used when restarting simulation)
const resetAllState = () => {
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  prevTwitterRound.value = 0
  prevRedditRound.value = 0
  startError.value = null
  isStarting.value = false
  isStopping.value = false
  stopPolling()  // Stop any existing polling
}

// Start simulation
const doStartSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    return
  }

  // Reset all state first to avoid interference from a previous run
  resetAllState()

  isStarting.value = true
  startError.value = null
  addLog('Starting dual-platform parallel simulation...')
  emit('update-status', 'processing')

  try {
    const params = {
      simulation_id: props.simulationId,
      platform: 'parallel',
      force: true,  // Force restart
      enable_graph_memory_update: true  // Enable dynamic graph updates
    }

    if (props.maxRounds) {
      params.max_rounds = props.maxRounds
      addLog(`Setting max simulation rounds: ${props.maxRounds}`)
    }

    addLog('Dynamic graph update mode enabled')

    const res = await startSimulation(params)

    if (res.success && res.data) {
      if (res.data.force_restarted) {
        addLog('✓ Old simulation logs cleared, restarting simulation')
      }
      addLog('✓ Simulation engine started successfully')
      addLog(`  ├─ PID: ${res.data.process_pid || '-'}`)

      phase.value = 1
      runStatus.value = res.data

      startStatusPolling()
      startDetailPolling()
    } else {
      startError.value = res.error || 'Start failed'
      addLog(`✗ Start failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    startError.value = err.message
    addLog(`✗ Start error: ${err.message}`)
    emit('update-status', 'error')
  } finally {
    isStarting.value = false
  }
}

// Stop simulation
const handleStopSimulation = async () => {
  if (!props.simulationId) return

  isStopping.value = true
  addLog('Stopping simulation...')

  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })

    if (res.success) {
      addLog('✓ Simulation stopped')
      phase.value = 2
      stopPolling()
      emit('update-status', 'completed')
    } else {
      addLog(`Stop failed: ${res.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Stop error: ${err.message}`)
  } finally {
    isStopping.value = false
  }
}

// Polling
let statusTimer = null
let detailTimer = null

const startStatusPolling = () => {
  statusTimer = setInterval(fetchRunStatus, 2000)
}

const startDetailPolling = () => {
  detailTimer = setInterval(fetchRunStatusDetail, 3000)
}

const stopPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (detailTimer) {
    clearInterval(detailTimer)
    detailTimer = null
  }
}

// Track previous round numbers per platform to detect changes and log them
const prevTwitterRound = ref(0)
const prevRedditRound = ref(0)

const fetchRunStatus = async () => {
  if (!props.simulationId) return

  try {
    const res = await getRunStatus(props.simulationId)

    if (res.success && res.data) {
      const data = res.data

      runStatus.value = data

      // Log round changes per platform
      if (data.twitter_current_round > prevTwitterRound.value) {
        addLog(`[Plaza] R${data.twitter_current_round}/${data.total_rounds} | T:${data.twitter_simulated_hours || 0}h | A:${data.twitter_actions_count}`)
        prevTwitterRound.value = data.twitter_current_round
      }

      if (data.reddit_current_round > prevRedditRound.value) {
        addLog(`[Community] R${data.reddit_current_round}/${data.total_rounds} | T:${data.reddit_simulated_hours || 0}h | A:${data.reddit_actions_count}`)
        prevRedditRound.value = data.reddit_current_round
      }

      // Detect simulation completion via runner_status or platform completion flags
      const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'

      // Additional check: if backend hasn't updated runner_status yet but platforms report completion
      const platformsCompleted = checkPlatformsCompleted(data)

      if (isCompleted || platformsCompleted) {
        if (platformsCompleted && !isCompleted) {
          addLog('✓ All platform simulations detected as finished')
        }
        addLog('✓ Simulation complete')
        phase.value = 2
        stopPolling()
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Failed to fetch run status:', err)
  }
}

// Check whether all enabled platforms have completed
const checkPlatformsCompleted = (data) => {
  // If no platform data, return false
  if (!data) return false

  // Check completion flags per platform
  const twitterCompleted = data.twitter_completed === true
  const redditCompleted = data.reddit_completed === true

  // Determine which platforms are enabled (by action count or running/completed state)
  const twitterEnabled = (data.twitter_actions_count > 0) || data.twitter_running || twitterCompleted
  const redditEnabled = (data.reddit_actions_count > 0) || data.reddit_running || redditCompleted

  // If no platform is enabled, return false
  if (!twitterEnabled && !redditEnabled) return false

  // All enabled platforms must be completed
  if (twitterEnabled && !twitterCompleted) return false
  if (redditEnabled && !redditCompleted) return false

  return true
}

const fetchRunStatusDetail = async () => {
  if (!props.simulationId) return

  try {
    const res = await getRunStatusDetail(props.simulationId)

    if (res.success && res.data) {
      // Use all_actions for the complete action list
      const serverActions = res.data.all_actions || []

      // Incrementally add new actions (deduplicated)
      let newActionsAdded = 0
      serverActions.forEach(action => {
        // Generate unique ID
        const actionId = action.id || `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`

        if (!actionIds.value.has(actionId)) {
          actionIds.value.add(actionId)
          allActions.value.push({
            ...action,
            _uniqueId: actionId
          })
          newActionsAdded++
        }
      })

      // No auto-scroll — let the user freely browse the timeline
      // New actions are appended at the bottom
    }
  } catch (err) {
    console.warn('Failed to fetch detailed status:', err)
  }
}

// Helpers
const getActionTypeLabel = (type) => {
  const labels = {
    'CREATE_POST': 'POST',
    'REPOST': 'REPOST',
    'LIKE_POST': 'LIKE',
    'CREATE_COMMENT': 'COMMENT',
    'LIKE_COMMENT': 'LIKE',
    'DO_NOTHING': 'IDLE',
    'FOLLOW': 'FOLLOW',
    'SEARCH_POSTS': 'SEARCH',
    'QUOTE_POST': 'QUOTE',
    'UPVOTE_POST': 'UPVOTE',
    'DOWNVOTE_POST': 'DOWNVOTE'
  }
  return labels[type] || type || 'UNKNOWN'
}

const getActionTypeClass = (type) => {
  const classes = {
    'CREATE_POST': 'badge-post',
    'REPOST': 'badge-action',
    'LIKE_POST': 'badge-action',
    'CREATE_COMMENT': 'badge-comment',
    'LIKE_COMMENT': 'badge-action',
    'QUOTE_POST': 'badge-post',
    'FOLLOW': 'badge-meta',
    'SEARCH_POSTS': 'badge-meta',
    'UPVOTE_POST': 'badge-action',
    'DOWNVOTE_POST': 'badge-action',
    'DO_NOTHING': 'badge-idle'
  }
  return classes[type] || 'badge-default'
}

const truncateContent = (content, maxLength = 100) => {
  if (!content) return ''
  if (content.length > maxLength) return content.substring(0, maxLength) + '...'
  return content
}

const formatActionTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

const handleNextStep = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    return
  }

  if (isGeneratingReport.value) {
    addLog('Report generation request already sent, please wait...')
    return
  }

  isGeneratingReport.value = true
  addLog('Launching report generation...')

  try {
    const res = await generateReport({
      simulation_id: props.simulationId,
      force_regenerate: true
    })

    if (res.success && res.data) {
      const reportId = res.data.report_id
      addLog(`✓ Report generation task started: ${reportId}`)

      // Navigate to report page
      router.push({ name: 'Report', params: { reportId } })
    } else {
      addLog(`✗ Failed to start report generation: ${res.error || 'Unknown error'}`)
      isGeneratingReport.value = false
    }
  } catch (err) {
    addLog(`✗ Report generation error: ${err.message}`)
    isGeneratingReport.value = false
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
  addLog('Step3 simulation run initialized')
  if (props.simulationId) {
    doStartSimulation()
  }
})

const clearAllTimers = () => {
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null }
  if (detailTimer) { clearInterval(detailTimer); detailTimer = null }
}

onBeforeUnmount(() => {
  clearAllTimers()
})

onUnmounted(() => {
  clearAllTimers()
})
</script>

<style scoped>
.simulation-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FFFFFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* --- Control Bar --- */
.control-bar {
  background: #FFF;
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #EAEAEA;
  z-index: 10;
  height: 64px;
}

.status-group {
  display: flex;
  gap: 12px;
}

/* Platform Status Cards */
.platform-status {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 4px;
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  opacity: 0.7;
  transition: all 0.3s;
  min-width: 140px;
  position: relative;
  cursor: pointer;
}

.platform-status.active {
  opacity: 1;
  border-color: #333;
  background: #FFF;
}

.platform-status.completed {
  opacity: 1;
  border-color: #1A936F;
  background: #F2FAF6;
}

/* Actions Tooltip */
.actions-tooltip {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 8px;
  padding: 10px 14px;
  background: #000;
  color: #FFF;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  z-index: 100;
  min-width: 180px;
  pointer-events: none;
}

.actions-tooltip::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 6px solid #000;
}

.platform-status:hover .actions-tooltip {
  opacity: 1;
  visibility: visible;
}

.tooltip-title {
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.tooltip-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tooltip-action {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  color: #FFF;
  letter-spacing: 0.03em;
}

.platform-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.platform-name {
  font-size: 11px;
  font-weight: 700;
  color: #000;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.platform-status.twitter .platform-icon { color: #000; }
.platform-status.reddit .platform-icon { color: #000; }

.platform-stats {
  display: flex;
  gap: 10px;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.stat-label {
  font-size: 8px;
  color: #999;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 11px;
  font-weight: 600;
  color: #333;
}

.stat-total, .stat-unit {
  font-size: 9px;
  color: #999;
  font-weight: 400;
}

.status-badge {
  margin-left: auto;
  color: #1A936F;
  display: flex;
  align-items: center;
}

/* Action Button */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.action-btn.primary {
  background: #000;
  color: #FFF;
}

.action-btn.primary:hover:not(:disabled) {
  background: #333;
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.arrow-icon {
  font-size: 16px;
}

.loading-spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #FFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* --- Main Content Area --- */
.main-content-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

/* Timeline Header */
.timeline-header {
  padding: 12px 24px;
  border-bottom: 1px solid #F5F5F5;
  background: #FAFAFA;
  position: sticky;
  top: 0;
  z-index: 5;
}

.timeline-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  letter-spacing: 0.05em;
}

.total-count {
  text-transform: uppercase;
}

.platform-breakdown {
  display: flex;
  align-items: center;
  gap: 6px;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.breakdown-item.twitter { color: #555; }
.breakdown-item.reddit { color: #777; }

.breakdown-divider {
  color: #DDD;
}

.mini-icon {
  opacity: 0.6;
}

/* Timeline Feed */
.timeline-feed {
  padding: 20px 24px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-axis {
  position: absolute;
  left: 38px;
  top: 20px;
  bottom: 20px;
  width: 1px;
  background: #F0F0F0;
}

/* Timeline Item */
.timeline-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.timeline-marker {
  width: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-top: 14px;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.marker-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #DDD;
  border: 2px solid #FFF;
  box-shadow: 0 0 0 1px #DDD;
}

.timeline-item.twitter .marker-dot { background: #555; box-shadow: 0 0 0 1px #555; }
.timeline-item.reddit .marker-dot { background: #888; box-shadow: 0 0 0 1px #888; }

/* Timeline Card */
.timeline-card {
  flex: 1;
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.timeline-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #F5F5F5;
  background: #FAFAFA;
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar-placeholder {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #333;
  color: #FFF;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.agent-name {
  font-size: 12px;
  font-weight: 600;
  color: #333;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.platform-indicator {
  color: #999;
  display: flex;
  align-items: center;
}

/* Action Badges */
.action-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-post { background: #EFF6FF; color: #2563EB; }
.badge-comment { background: #F0FDF4; color: #16A34A; }
.badge-action { background: #FFF7ED; color: #EA580C; }
.badge-meta { background: #F5F3FF; color: #7C3AED; }
.badge-idle { background: #F9FAFB; color: #9CA3AF; }
.badge-default { background: #F3F4F6; color: #6B7280; }

/* Card Body */
.card-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.content-text {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
}

.main-text {
  font-size: 14px;
}

/* Quoted block */
.quoted-block {
  border-left: 3px solid #E5E7EB;
  padding: 8px 12px;
  background: #F9FAFB;
  border-radius: 0 4px 4px 0;
}

.quote-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.quote-label {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
}

.quote-text {
  font-size: 12px;
  color: #6B7280;
  line-height: 1.5;
}

/* Repost */
.repost-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #6B7280;
}

.repost-label { font-weight: 500; }

.repost-content {
  font-size: 13px;
  color: #4B5563;
  padding: 8px;
  background: #F9FAFB;
  border-radius: 4px;
  line-height: 1.5;
}

/* Like */
.like-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #EF4444;
}

.like-label { font-weight: 500; }

.liked-content {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}

/* Comment */
.comment-context {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #9CA3AF;
}

/* Search */
.search-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6B7280;
}

.search-label { font-weight: 500; }

.search-query {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #374151;
  background: #F3F4F6;
  padding: 2px 6px;
  border-radius: 3px;
}

/* Follow */
.follow-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #7C3AED;
}

.follow-label { font-weight: 500; }

/* Vote */
.vote-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #EA580C;
}

.vote-label { font-weight: 500; }

.voted-content {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}

/* Idle */
.idle-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #9CA3AF;
}

.idle-label { font-weight: 500; }

/* Icon helpers */
.icon-small {
  flex-shrink: 0;
}

.icon-small.filled {
  color: #EF4444;
}

/* Card Footer */
.card-footer {
  padding: 6px 14px;
  border-top: 1px solid #F9FAFB;
  display: flex;
  align-items: center;
  gap: 8px;
}

.time-tag {
  font-size: 10px;
  color: #9CA3AF;
  font-family: 'JetBrains Mono', monospace;
}

/* Waiting state */
.waiting-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 16px;
  color: #9CA3AF;
  font-size: 13px;
}

.pulse-ring {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid #E5E7EB;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.6; }
}

/* Timeline transition animation */
.timeline-item-enter-active {
  transition: all 0.3s ease;
}

.timeline-item-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

.mono {
  font-family: 'JetBrains Mono', monospace;
}
</style>
