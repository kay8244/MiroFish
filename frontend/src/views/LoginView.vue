<template>
  <div class="login-wrap">
    <form class="login-card" @submit.prevent="onSubmit">
      <h1 class="title">MiroFish</h1>
      <p class="subtitle">로그인이 필요합니다</p>

      <label class="field">
        <span>이메일</span>
        <input
          v-model="email"
          type="email"
          autocomplete="username"
          required
          :disabled="submitting"
        />
      </label>

      <label class="field">
        <span>비밀번호</span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :disabled="submitting"
        />
      </label>

      <div v-if="error" class="error">{{ error }}</div>

      <button type="submit" class="btn" :disabled="submitting || !email || !password">
        {{ submitting ? '로그인 중...' : '로그인' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../store/auth'

const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const route = useRoute()
const router = useRouter()

async function onSubmit() {
  error.value = ''
  submitting.value = true
  try {
    await login(email.value.trim(), password.value)
    const next = (route.query.next && decodeURIComponent(route.query.next)) || '/'
    router.replace(next)
  } catch (err) {
    const resp = err && err.response
    if (resp && resp.status === 401) {
      error.value = '이메일 또는 비밀번호가 올바르지 않습니다.'
    } else if (resp && resp.status === 400) {
      error.value = '이메일/비밀번호를 모두 입력하세요.'
    } else {
      error.value = '로그인 실패: ' + (err.message || 'unknown')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f1115;
  color: #e5e7eb;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.login-card {
  width: 360px;
  padding: 40px 32px;
  background: #1a1d24;
  border: 1px solid #2a2f3a;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}
.title {
  margin: 0 0 4px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.subtitle {
  margin: 0 0 28px;
  font-size: 14px;
  color: #9ca3af;
}
.field {
  display: block;
  margin-bottom: 16px;
}
.field span {
  display: block;
  font-size: 13px;
  margin-bottom: 6px;
  color: #d1d5db;
}
.field input {
  width: 100%;
  padding: 10px 12px;
  background: #0f1115;
  border: 1px solid #2a2f3a;
  border-radius: 6px;
  color: #e5e7eb;
  font-size: 14px;
  box-sizing: border-box;
  outline: none;
}
.field input:focus {
  border-color: #3b82f6;
}
.error {
  margin: 8px 0 14px;
  padding: 10px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
  border-radius: 6px;
  font-size: 13px;
}
.btn {
  width: 100%;
  padding: 11px;
  margin-top: 8px;
  background: #3b82f6;
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn:hover:not(:disabled) {
  background: #2563eb;
}
.btn:disabled {
  background: #374151;
  cursor: not-allowed;
}
</style>
