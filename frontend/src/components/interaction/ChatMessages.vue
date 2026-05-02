<template>
  <!-- Chat Messages -->
  <div class="chat-messages" ref="chatMessagesEl">
    <div v-if="chatHistory.length === 0" class="chat-empty">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <p class="empty-text">
        {{ chatTarget === 'report_agent' ? 'Chat with Report Agent to explore report content in depth' : 'Chat with a simulated individual to learn their perspective' }}
      </p>
    </div>
    <div
      v-for="(msg, idx) in chatHistory"
      :key="idx"
      class="chat-message"
      :class="msg.role"
    >
      <div class="message-avatar">
        <span v-if="msg.role === 'user'">U</span>
        <span v-else>{{ msg.role === 'assistant' && chatTarget === 'report_agent' ? 'R' : (selectedAgent?.username?.[0] || 'A') }}</span>
      </div>
      <div class="message-content">
        <div class="message-header">
          <span class="sender-name">
            {{ msg.role === 'user' ? 'You' : (chatTarget === 'report_agent' ? 'Report Agent' : (selectedAgent?.username || 'Agent')) }}
          </span>
          <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
        </div>
        <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
      </div>
    </div>
    <div v-if="isSending" class="chat-message assistant">
      <div class="message-avatar">
        <span>{{ chatTarget === 'report_agent' ? 'R' : (selectedAgent?.username?.[0] || 'A') }}</span>
      </div>
      <div class="message-content">
        <div class="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    </div>
  </div>

  <!-- Chat Input -->
  <div class="chat-input-area">
    <textarea
      v-model="localInput"
      class="chat-input"
      placeholder="질문을 입력하세요..."
      @keydown.enter.exact.prevent="$emit('send')"
      :disabled="isSending || (!selectedAgent && chatTarget === 'agent')"
      rows="1"
      ref="chatInputEl"
    ></textarea>
    <button
      class="send-btn"
      @click="$emit('send')"
      :disabled="!localInput.trim() || isSending || (!selectedAgent && chatTarget === 'agent')"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  chatHistory: { type: Array, required: true },
  chatTarget: { type: String, required: true },
  selectedAgent: { type: Object, default: null },
  isSending: { type: Boolean, default: false },
  chatInput: { type: String, default: '' },
  formatTime: { type: Function, required: true },
  renderMarkdown: { type: Function, required: true }
})

const emit = defineEmits(['send', 'update:chatInput'])

const chatMessagesEl = ref(null)
const chatInputEl = ref(null)

const localInput = ref(props.chatInput)

watch(() => props.chatInput, (val) => {
  localInput.value = val
})

watch(localInput, (val) => {
  emit('update:chatInput', val)
})

defineExpose({
  chatMessagesEl,
  chatInputEl
})
</script>

<style scoped>
/* Chat Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #9CA3AF;
  text-align: center;
}

.chat-empty .empty-icon {
  opacity: 0.3;
}

.chat-empty .empty-text {
  font-size: 13px;
  max-width: 260px;
  line-height: 1.5;
}

.chat-message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #374151;
  color: #FFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.chat-message.user .message-avatar {
  background: #6B7280;
}

.message-content {
  max-width: 75%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.chat-message.user .message-header {
  flex-direction: row-reverse;
}

.sender-name {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.message-time {
  font-size: 10px;
  color: #9CA3AF;
}

.message-text {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
}

.chat-message.user .message-text {
  background: #111827;
  color: #FFFFFF;
  border-color: #111827;
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 14px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  width: fit-content;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #9CA3AF;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* Chat Input */
.chat-input-area {
  padding: 16px 20px;
  background: #FFFFFF;
  border-top: 1px solid #E5E7EB;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  font-family: inherit;
  resize: none;
  outline: none;
  line-height: 1.5;
  max-height: 120px;
  overflow-y: auto;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: #374151;
}

.chat-input:disabled {
  background: #F9FAFB;
  color: #9CA3AF;
}

.send-btn {
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 8px;
  background: #111827;
  color: #FFF;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: #374151;
}

.send-btn:disabled {
  background: #E5E7EB;
  color: #9CA3AF;
  cursor: not-allowed;
}
</style>
