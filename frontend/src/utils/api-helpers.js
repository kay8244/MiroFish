/**
 * API 응답 안전 처리 유틸리티
 */
import { showToast } from './toast'

/**
 * API 호출을 안전하게 실행하고 에러 시 토스트 표시
 * @param {Function} apiCall - API 호출 함수
 * @param {string} errorMessage - 실패 시 표시할 메시지
 * @returns {Promise<any|null>} - 성공 시 응답 데이터, 실패 시 null
 */
export async function safeApiCall(apiCall, errorMessage = '요청에 실패했습니다') {
  try {
    const res = await apiCall()
    if (res && res.data !== undefined) {
      return res
    }
    showToast(errorMessage, 'error')
    return null
  } catch (err) {
    const msg = err?.response?.data?.error || err?.message || errorMessage
    showToast(msg, 'error')
    console.error(errorMessage, err)
    return null
  }
}

/**
 * 디바운스 함수
 * @param {Function} fn - 실행할 함수
 * @param {number} delay - 지연 시간 (ms)
 * @returns {Function}
 */
export function debounce(fn, delay = 300) {
  let timer = null
  return function (...args) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn.apply(this, args), delay)
  }
}
