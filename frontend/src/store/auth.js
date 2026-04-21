/**
 * 인증 상태 스토어 (reactive).
 * pendingUpload.js 와 동일 패턴 (Vue reactive state, Pinia/Vuex 미사용).
 */
import { reactive, computed } from 'vue'
import { login as apiLogin, logout as apiLogout, fetchMe } from '../api/auth'

const state = reactive({
  user: null,           // { id, email, role } | null
  initialized: false,   // 부팅 시 fetchMe 1회 완료 여부
  loading: false,
})

export const authState = state

export const isAuthenticated = computed(() => state.user !== null)
export const userRole = computed(() => state.user ? state.user.role : null)
export const isAdmin = computed(() => state.user && state.user.role === 'admin')
export const canWrite = computed(
  () => state.user && (state.user.role === 'admin' || state.user.role === 'builder')
)

/**
 * 앱 부팅 시 1회 호출. 세션 쿠키로 기존 로그인 복원.
 * 미인증이면 state.user 는 null.
 */
export async function initAuth() {
  if (state.initialized) return state.user
  state.loading = true
  try {
    const res = await fetchMe()
    state.user = res.user || null
  } catch (err) {
    state.user = null
  } finally {
    state.loading = false
    state.initialized = true
  }
  return state.user
}

export async function login(email, password) {
  state.loading = true
  try {
    const res = await apiLogin(email, password)
    state.user = res.user || null
    return state.user
  } finally {
    state.loading = false
  }
}

export async function logout() {
  try {
    await apiLogout()
  } catch (err) {
    // 서버 측 세션이 이미 날아간 경우에도 프론트 상태는 비운다
    console.warn('logout request failed:', err && err.message)
  }
  state.user = null
}
