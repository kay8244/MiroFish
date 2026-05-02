import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 설정.
 *
 * - testDir: e2e/ 하위 *.spec.js
 * - webServer: vite dev (port 3000) — Playwright 가 자동 기동/종료
 * - 기본 base URL: http://localhost:3000
 * - HTML 리포트 출력
 *
 * 백엔드 의존: 라우트 모킹 사용 (page.route) — 실제 backend 기동 불필요.
 * 인증/실데이터 테스트가 필요하면 별도 fixture 로 backend 기동 추가.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
