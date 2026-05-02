/**
 * 인증 API — Flask-Login 기반 세션 쿠키.
 * withCredentials=true 는 api/index.js 에서 전역 설정됨.
 */
import service from './index'

export function login(email, password) {
  return service.post('/api/auth/login', { email, password })
}

export function logout() {
  return service.post('/api/auth/logout')
}

export function fetchMe() {
  return service.get('/api/auth/me')
}
