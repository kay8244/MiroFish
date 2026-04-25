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
  padding: var(--space-7);
  background: var(--color-canvas-muted);
  color: var(--color-text);
}

.login-card {
  width: 100%;
  max-width: 380px;
  padding: var(--space-10) var(--space-9);
  background: var(--color-surface);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2);
}

.title {
  font-family: var(--font-display);
  margin: 0 0 var(--space-2);
  font-size: var(--fs-utility);
  font-weight: 600;
  letter-spacing: -0.022em;
  line-height: 1.1;
  color: var(--color-text);
}

.subtitle {
  margin: 0 0 var(--space-9);
  font-size: var(--fs-control);
  color: var(--color-text-muted);
  letter-spacing: -0.014em;
}

.field {
  display: block;
  margin-bottom: var(--space-6);
}

.field span {
  display: block;
  font-size: var(--fs-micro);
  font-weight: 500;
  margin-bottom: var(--space-3);
  color: var(--color-text-muted);
  letter-spacing: -0.012em;
}

.field input {
  width: 100%;
  padding: var(--space-5) var(--space-5);
  background: var(--color-canvas);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: var(--fs-body);
  letter-spacing: -0.022em;
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}

.field input:hover:not(:disabled) {
  border-color: var(--color-border-strong);
}

.field input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18);
}

.error {
  margin: var(--space-3) 0 var(--space-6);
  padding: var(--space-5) var(--space-5);
  background: var(--color-error-bg);
  border: 1px solid rgba(211, 47, 47, 0.22);
  color: var(--color-error);
  border-radius: var(--radius-sm);
  font-size: var(--fs-control);
}

.btn {
  width: 100%;
  padding: var(--space-5);
  margin-top: var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-accent-on);
  font-size: var(--fs-control);
  font-weight: 600;
  letter-spacing: -0.014em;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
              transform var(--duration-fast) var(--ease-standard);
}

.btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.btn:active:not(:disabled) {
  transform: scale(0.99);
  background: var(--color-accent-pressed);
}

.btn:disabled {
  background: var(--color-border-subtle);
  color: var(--color-text-muted);
  cursor: not-allowed;
}
</style>
