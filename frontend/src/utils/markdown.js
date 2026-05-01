/**
 * 마크다운 렌더링 유틸리티
 * marked + DOMPurify — LLM 출력에 포함될 수 있는 <script>, onclick 등 XSS 벡터 제거.
 *
 * 모든 v-html 사용처는 이 함수를 거쳐야 함 (그렇지 않으면 XSS 위험).
 */

import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

/**
 * 마크다운 텍스트를 안전한 HTML로 변환
 * @param {string} text
 * @returns {string} XSS-safe HTML
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return DOMPurify.sanitize(marked.parse(text))
  } catch (err) {
    console.error('마크다운 렌더링 실패:', err)
    return DOMPurify.sanitize(text)
  }
}

/**
 * 마크다운 텍스트를 인라인 HTML로 변환 (블록 요소 없음)
 * @param {string} text
 * @returns {string} XSS-safe HTML
 */
export function renderMarkdownInline(text) {
  if (!text) return ''
  try {
    return DOMPurify.sanitize(marked.parseInline(text))
  } catch (err) {
    return DOMPurify.sanitize(text)
  }
}
