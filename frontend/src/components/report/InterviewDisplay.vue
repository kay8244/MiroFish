<template>
  <div class="interview-display">
    <!-- Header Section -->
    <div class="interview-header">
      <div class="header-main">
        <div class="header-title">Agent Interview</div>
        <div class="header-stats">
          <span class="stat-item">
            <span class="stat-value">{{ result.successCount || result.interviews.length }}</span>
            <span class="stat-label">Interviewed</span>
          </span>
          <template v-if="result.totalCount > 0">
            <span class="stat-divider">/</span>
            <span class="stat-item">
              <span class="stat-value">{{ result.totalCount }}</span>
              <span class="stat-label">Total</span>
            </span>
          </template>
          <template v-if="resultLength">
            <span class="stat-divider">&middot;</span>
            <span class="stat-size">{{ formatSize(resultLength) }}</span>
          </template>
        </div>
      </div>
      <div v-if="result.topic" class="header-topic">{{ result.topic }}</div>
    </div>

    <!-- Agent Selector Tabs -->
    <div v-if="result.interviews.length > 0" class="agent-tabs">
      <button
        v-for="(interview, i) in result.interviews"
        :key="i"
        :class="['agent-tab', { active: activeIndex === i }]"
        @click="activeIndex = i"
      >
        <span class="tab-avatar">{{ interview.name ? interview.name.charAt(0) : (i + 1) }}</span>
        <span class="tab-name">{{ interview.title || interview.name || `Agent ${i + 1}` }}</span>
      </button>
    </div>

    <!-- Active Interview Detail -->
    <div v-if="result.interviews.length > 0" class="interview-detail">
      <!-- Agent Profile Card -->
      <div class="agent-profile">
        <div class="profile-avatar">{{ currentInterview?.name?.charAt(0) || 'A' }}</div>
        <div class="profile-info">
          <div class="profile-name">{{ currentInterview?.name || 'Agent' }}</div>
          <div class="profile-role">{{ currentInterview?.role || '' }}</div>
          <div v-if="currentInterview?.bio" class="profile-bio">{{ currentInterview.bio }}</div>
        </div>
      </div>

      <!-- Selection Reason -->
      <div v-if="currentInterview?.selectionReason" class="selection-reason">
        <div class="reason-label">Selection Reason</div>
        <div class="reason-content">{{ currentInterview.selectionReason }}</div>
      </div>

      <!-- Q&A Conversation Thread -->
      <div class="qa-thread">
        <div v-for="(question, qIdx) in questionList" :key="qIdx" class="qa-pair">
          <!-- Question Block -->
          <div class="qa-question">
            <div class="qa-badge q-badge">Q{{ qIdx + 1 }}</div>
            <div class="qa-content">
              <div class="qa-sender">Interviewer</div>
              <div class="qa-text">{{ question }}</div>
            </div>
          </div>

          <!-- Answer Block -->
          <div
            v-if="getAnswer(qIdx)"
            :class="['qa-answer', { 'answer-placeholder': isAnswerPlaceholder(qIdx) }]"
          >
            <div class="qa-badge a-badge">A{{ qIdx + 1 }}</div>
            <div class="qa-content">
              <div class="qa-answer-header">
                <div class="qa-sender">{{ currentInterview?.name || 'Agent' }}</div>
                <!-- Dual-platform toggle -->
                <div v-if="hasDualPlatform(qIdx)" class="platform-switch">
                  <button
                    :class="['platform-btn', { active: getPlatformTab(qIdx) === 'twitter' }]"
                    @click.stop="setPlatformTab(qIdx, 'twitter')"
                  >
                    <svg class="platform-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="2" y1="12" x2="22" y2="12" />
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    </svg>
                    <span>World 1</span>
                  </button>
                  <button
                    :class="['platform-btn', { active: getPlatformTab(qIdx) === 'reddit' }]"
                    @click.stop="setPlatformTab(qIdx, 'reddit')"
                  >
                    <svg class="platform-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                    </svg>
                    <span>World 2</span>
                  </button>
                </div>
              </div>
              <div
                :class="['qa-text', 'answer-text', { 'placeholder-text': isAnswerPlaceholder(qIdx) }]"
                v-html="formatAnswerHtml(qIdx)"
              ></div>
              <button
                v-if="!isAnswerPlaceholder(qIdx) && getAnswer(qIdx).length > 400"
                class="expand-answer-btn"
                @click="toggleAnswer(qIdx)"
              >
                {{ isAnswerExpanded(qIdx) ? 'Show Less' : 'Show More' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Key Quotes Section -->
      <div v-if="currentInterview?.quotes?.length > 0" class="quotes-section">
        <div class="quotes-header">Key Quotes</div>
        <div class="quotes-list">
          <blockquote
            v-for="(quote, qi) in currentInterview.quotes.slice(0, 3)"
            :key="qi"
            class="quote-item"
            v-html="renderMarkdown(cleanQuoteText(quote).length > 200 ? cleanQuoteText(quote).substring(0, 200) + '...' : cleanQuoteText(quote))"
          ></blockquote>
        </div>
      </div>
    </div>

    <!-- Summary Section -->
    <div v-if="result.summary" class="summary-section">
      <div class="summary-header">Interview Summary</div>
      <div
        class="summary-content"
        v-html="renderMarkdown(result.summary.length > 500 ? result.summary.substring(0, 500) + '...' : result.summary)"
      ></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { renderReportMarkdown } from '../../utils/reportMarkdown'

const props = defineProps({
  result: { type: Object, required: true },
  resultLength: { type: Number, default: 0 }
})

const activeIndex = ref(0)
const expandedAnswers = ref(new Set())
const platformTabs = reactive({})

const currentInterview = computed(() => props.result.interviews[activeIndex.value])

const questionList = computed(() => {
  const interview = currentInterview.value
  if (!interview) return []
  if (interview.questions?.length > 0) return interview.questions
  return [interview.question || 'No question available']
})

const renderMarkdown = (text) => renderReportMarkdown(text)

const formatSize = (length) => {
  if (!length) return ''
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`
  return `${length} chars`
}

const cleanQuoteText = (text) => {
  if (!text) return ''
  return text.replace(/^\s*\d+[\.\u3001\)\uFF09]\s*/, '').trim()
}

const isPlaceholderText = (text) => {
  if (!text) return true
  const t = text.trim()
  return t === '(No reply from this platform)' || t === '(No reply from this platform)' || t === '[No reply]'
}

const splitAnswerByQuestions = (answerText, questionCount) => {
  if (!answerText || questionCount <= 0) return [answerText]
  if (isPlaceholderText(answerText)) return ['']

  let matches = []
  let match

  const cnPattern = /(?:^|[\r\n]+)Question(\d+)[\uFF1A:]\s*/g
  while ((match = cnPattern.exec(answerText)) !== null) {
    matches.push({ num: parseInt(match[1]), index: match.index, fullMatch: match[0] })
  }

  if (matches.length === 0) {
    const numPattern = /(?:^|[\r\n]+)(\d+)\.\s+/g
    while ((match = numPattern.exec(answerText)) !== null) {
      matches.push({ num: parseInt(match[1]), index: match.index, fullMatch: match[0] })
    }
  }

  if (matches.length <= 1) {
    const cleaned = answerText.replace(/^Question\d+[\uFF1A:]\s*/, '').replace(/^\d+\.\s+/, '').trim()
    return [cleaned || answerText]
  }

  const parts = []
  for (let i = 0; i < matches.length; i++) {
    const current = matches[i]
    const next = matches[i + 1]
    const startIdx = current.index + current.fullMatch.length
    const endIdx = next ? next.index : answerText.length
    let part = answerText.substring(startIdx, endIdx).trim()
    part = part.replace(/[\r\n]+$/, '').trim()
    parts.push(part)
  }

  if (parts.length > 0 && parts.some(p => p)) return parts
  return [answerText]
}

const getAnswerForQuestion = (interview, qIdx, platform) => {
  const answer = platform === 'twitter' ? interview.twitterAnswer : (interview.redditAnswer || interview.twitterAnswer)
  if (!answer || isPlaceholderText(answer)) return answer || ''
  const questionCount = interview.questions?.length || 1
  const answers = splitAnswerByQuestions(answer, questionCount)
  if (answers.length > 1 && qIdx < answers.length) return answers[qIdx] || ''
  return qIdx === 0 ? answer : ''
}

const getPlatformTab = (qIdx) => {
  const key = `${activeIndex.value}-${qIdx}`
  return platformTabs[key] || 'twitter'
}

const setPlatformTab = (qIdx, platform) => {
  const key = `${activeIndex.value}-${qIdx}`
  platformTabs[key] = platform
}

const getAnswer = (qIdx) => {
  const interview = currentInterview.value
  if (!interview) return ''
  return getAnswerForQuestion(interview, qIdx, getPlatformTab(qIdx))
}

const isAnswerPlaceholder = (qIdx) => isPlaceholderText(getAnswer(qIdx))

const hasDualPlatform = (qIdx) => {
  const interview = currentInterview.value
  if (!interview?.twitterAnswer || !interview?.redditAnswer) return false
  const twitterAnswer = getAnswerForQuestion(interview, qIdx, 'twitter')
  const redditAnswer = getAnswerForQuestion(interview, qIdx, 'reddit')
  return !isPlaceholderText(twitterAnswer) && !isPlaceholderText(redditAnswer) && twitterAnswer !== redditAnswer
}

const toggleAnswer = (qIdx) => {
  const key = `${activeIndex.value}-${qIdx}`
  const newSet = new Set(expandedAnswers.value)
  if (newSet.has(key)) { newSet.delete(key) } else { newSet.add(key) }
  expandedAnswers.value = newSet
}

const isAnswerExpanded = (qIdx) => {
  return expandedAnswers.value.has(`${activeIndex.value}-${qIdx}`)
}

const formatAnswerHtml = (qIdx) => {
  const answerText = getAnswer(qIdx)
  if (isPlaceholderText(answerText)) return answerText
  const expanded = isAnswerExpanded(qIdx)
  const text = (!expanded && answerText.length > 400) ? answerText.substring(0, 400) + '...' : answerText
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')
}
</script>
