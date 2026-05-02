import { test, expect } from '@playwright/test'

/**
 * Login flow E2E (백엔드 의존 없음 — page.route 로 API 모킹).
 *
 * - GET /api/auth/me → 401 (미인증) → 라우터 가드가 /login 으로 리다이렉트
 * - POST /api/auth/login: 401 / 400 / 200 분기 검증
 */

test.describe('Login flow', () => {
  test.beforeEach(async ({ page }) => {
    // 기본: 미인증 상태
    await page.route('**/api/auth/me', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'unauthorized' }),
      })
    )
  })

  test('미인증 사용자 / 진입 시 /login 으로 리다이렉트', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: 'MiroFish' })).toBeVisible()
    await expect(page.getByText('로그인이 필요합니다')).toBeVisible()
  })

  test('로그인 폼 렌더링', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByLabel('이메일')).toBeVisible()
    await expect(page.getByLabel('비밀번호')).toBeVisible()
    await expect(page.getByRole('button', { name: '로그인' })).toBeVisible()
  })

  test('빈 폼은 제출 버튼이 비활성화', async ({ page }) => {
    await page.goto('/login')
    const submit = page.getByRole('button', { name: /로그인/ })
    await expect(submit).toBeDisabled()
    await page.getByLabel('이메일').fill('test@example.com')
    // 비밀번호 미입력 상태에서도 비활성화 유지
    await expect(submit).toBeDisabled()
    await page.getByLabel('비밀번호').fill('pw1234')
    await expect(submit).toBeEnabled()
  })

  test('잘못된 자격증명: 401 응답 → 에러 메시지 표시', async ({ page }) => {
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'unauthorized' }),
      })
    )
    await page.goto('/login')
    await page.getByLabel('이메일').fill('wrong@example.com')
    await page.getByLabel('비밀번호').fill('wrongpass')
    await page.getByRole('button', { name: '로그인' }).click()
    await expect(
      page.getByText('이메일 또는 비밀번호가 올바르지 않습니다.')
    ).toBeVisible()
  })

  test('필수 입력 누락: 400 응답 → 입력 안내 메시지', async ({ page }) => {
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'missing_credentials' }),
      })
    )
    await page.goto('/login')
    // form `required` 가 있어 normally는 못 보내지만, JS submit 으로 우회
    await page.getByLabel('이메일').fill('a@b.c')
    await page.getByLabel('비밀번호').fill('p')
    await page.getByRole('button', { name: '로그인' }).click()
    await expect(
      page.getByText('이메일/비밀번호를 모두 입력하세요.')
    ).toBeVisible()
  })

  test('로그인 성공: / 로 리다이렉트', async ({ page }) => {
    let loginCalls = 0
    await page.route('**/api/auth/login', (route) => {
      loginCalls += 1
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          user: { id: 1, email: 'admin@test.local', role: 'admin' },
        }),
      })
    })
    // 초기 me 는 401 유지 (beforeEach). 로그인 후 me 는 인증된 사용자로 응답
    // (Home.vue 가 fetchMe 를 다시 부르지 않으므로 사실상 효과 없지만 안전망)

    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'MiroFish' })).toBeVisible()
    await page.getByLabel('이메일').fill('admin@test.local')
    await page.getByLabel('비밀번호').fill('testpass')
    await page.getByRole('button', { name: '로그인' }).click()

    // /login 에서 벗어나야 함 — 정확한 URL 매칭은 Home 의 라우팅 따라 달라짐
    await expect(page).not.toHaveURL(/\/login/)
    expect(loginCalls).toBe(1)
  })

  test('next 쿼리 보존: /login?next=/pipeline → 로그인 후 /pipeline', async ({ page }) => {
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          user: { id: 1, email: 'admin@test.local', role: 'admin' },
        }),
      })
    )
    await page.goto('/login?next=%2Fpipeline')
    await expect(page.getByRole('heading', { name: 'MiroFish' })).toBeVisible()
    await page.getByLabel('이메일').fill('admin@test.local')
    await page.getByLabel('비밀번호').fill('testpass')
    await page.getByRole('button', { name: '로그인' }).click()
    await expect(page).toHaveURL(/\/pipeline/)
  })
})
