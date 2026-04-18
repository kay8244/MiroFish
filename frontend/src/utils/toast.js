/**
 * 간단한 토스트 알림 유틸리티
 * DOM에 직접 토스트 요소를 추가하여 사용자에게 피드백 제공
 */

let toastContainer = null

function getContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div')
    toastContainer.id = 'toast-container'
    toastContainer.style.cssText = `
      position: fixed; top: 20px; right: 20px; z-index: 10000;
      display: flex; flex-direction: column; gap: 8px;
      pointer-events: none;
    `
    document.body.appendChild(toastContainer)
  }
  return toastContainer
}

export function showToast(message, type = 'error', duration = 4000) {
  const container = getContainer()
  const toast = document.createElement('div')

  const bgColor = type === 'error' ? '#ef4444' : type === 'success' ? '#22c55e' : '#f59e0b'
  toast.style.cssText = `
    background: ${bgColor}; color: white; padding: 12px 20px;
    border-radius: 8px; font-size: 14px; max-width: 400px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: auto;
    animation: slideIn 0.3s ease-out;
    opacity: 1; transition: opacity 0.3s ease;
  `
  toast.textContent = message
  container.appendChild(toast)

  setTimeout(() => {
    toast.style.opacity = '0'
    setTimeout(() => toast.remove(), 300)
  }, duration)
}

// CSS animation 추가
const style = document.createElement('style')
style.textContent = `
  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
`
document.head.appendChild(style)
