/**
 * 마크다운 렌더링 유틸리티
 * marked 라이브러리 기반으로 안전한 HTML 변환 제공
 */

import { marked } from 'marked'

// marked 설정
marked.setOptions({
  breaks: true,     // 줄바꿈을 <br>로 변환
  gfm: true,        // GitHub Flavored Markdown
})

/**
 * 마크다운 텍스트를 HTML로 변환
 * @param {string} text - 마크다운 텍스트
 * @returns {string} HTML 문자열
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch (err) {
    console.error('마크다운 렌더링 실패:', err)
    return text
  }
}

/**
 * 마크다운 텍스트를 인라인 HTML로 변환 (블록 요소 없음)
 * @param {string} text
 * @returns {string}
 */
export function renderMarkdownInline(text) {
  if (!text) return ''
  try {
    return marked.parseInline(text)
  } catch (err) {
    return text
  }
}
