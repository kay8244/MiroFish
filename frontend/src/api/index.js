import axios from 'axios'

// Create axios instance
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5-minute timeout (ontology generation may take a while)
  headers: {
    'Content-Type': 'application/json'
  },
  // 세션 쿠키 전송 (Flask-Login 기반 인증, Phase 9)
  withCredentials: true
})

// Request interceptor
service.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor (fault-tolerant retry mechanism)
service.interceptors.response.use(
  response => {
    const res = response.data

    // Throw an error if the returned status is not success
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }

    return res
  },
  error => {
    console.error('Response error:', error)

    // 401: 세션 만료 / 미인증 → 로그인 페이지로. 단, 로그인 자체 엔드포인트에서는 스킵.
    if (error.response && error.response.status === 401) {
      const url = (error.config && error.config.url) || ''
      const isAuthEndpoint = url.includes('/api/auth/')
      if (!isAuthEndpoint && typeof window !== 'undefined') {
        const current = window.location.pathname
        if (current !== '/login') {
          const next = encodeURIComponent(current + window.location.search)
          window.location.href = `/login?next=${next}`
        }
      }
    }

    // Handle timeout
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }

    // Handle network error
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    return Promise.reject(error)
  }
)

// Request function with retry
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
