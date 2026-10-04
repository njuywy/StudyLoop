import { expect, test } from '@playwright/test'

const api = 'https://124.220.147.193/api/v1'

test.beforeEach(async ({ page }) => {
  await page.route(`${api}/health`, route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
})

test('forgot password is reachable and shows neutral acceptance, rate limit and retry', async ({ page }) => {
  let calls = 0
  await page.route(`${api}/auth/request-password-reset`, async route => {
    expect(route.request().postDataJSON()).toEqual({ email: 'verified@example.com' })
    calls++
    if (calls === 2) return route.fulfill({ status: 429, json: { code: 'RATE_LIMITED', message: 'private backend details' } })
    if (calls === 3) return route.abort()
    return route.fulfill({ status: 202, json: { code: 'PASSWORD_RESET_REQUEST_ACCEPTED' } })
  })
  await page.goto('./#/login')
  await page.getByRole('link', { name: '忘记密码？通过邮箱找回' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('verified@example.com')
  await page.getByRole('button', { name: '发送重置邮件' }).click()
  await expect(page.getByRole('status').filter({ hasText: '请求已受理' })).toContainText('无法确认邮件是否送达')
  await page.getByRole('button', { name: '发送重置邮件' }).click()
  await expect(page.getByRole('alert')).toContainText('请求过于频繁')
  await expect(page.getByText('private backend details')).toHaveCount(0)
  await page.getByRole('button', { name: '发送重置邮件' }).click()
  await expect(page.getByRole('alert')).toContainText('平台连接暂不可用')
  await page.getByRole('button', { name: '发送重置邮件' }).click()
  await expect(page.getByRole('status').filter({ hasText: '请求已受理' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('reset deep link survives refresh, requires valid explicit submission and clears old local session', async ({ page }) => {
  let calls = 0
  await page.route(`${api}/auth/reset-password`, route => {
    calls++
    expect(route.request().postDataJSON()).toEqual({ token: 'private-reset-token', new_password: ' new password ' })
    return route.fulfill({ json: { code: 'PASSWORD_RESET' } })
  })
  await page.goto('./#/reset-password?token=private-reset-token')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'old-session')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: '重置密码' })).toBeVisible()
  expect(calls).toBe(0)
  await expect(page.getByText('private-reset-token', { exact: true })).toHaveCount(0)
  for (const invalid of ['密'.repeat(11), '密'.repeat(129)]) {
    await page.getByLabel('新密码', { exact: true }).fill(invalid)
    await page.getByRole('button', { name: '确认重置密码' }).click()
    await expect(page.getByRole('alert')).toContainText('密码需要 12～128 个字符')
    expect(calls).toBe(0)
  }
  await page.getByLabel('新密码', { exact: true }).fill(' new password ')
  await page.getByRole('button', { name: '确认重置密码' }).click()
  await expect(page.getByRole('status').filter({ hasText: '密码已更新' })).toBeVisible()
  await expect(page).toHaveURL(/#\/reset-password$/)
  expect(calls).toBe(1)
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
  await page.getByRole('link', { name: '重新登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
})

test('failed reset preserves the link for retry and invalid tokens offer a new request', async ({ page }) => {
  let available = false
  await page.route(`${api}/auth/reset-password`, route => available
    ? route.fulfill({ status: 400, json: { code: 'INVALID_RESET_TOKEN', message: 'private error with secret' } })
    : route.abort())
  await page.goto('./#/reset-password?token=expired-token')
  await page.getByLabel('新密码', { exact: true }).fill('😀'.repeat(12))
  await page.getByRole('button', { name: '确认重置密码' }).click()
  await expect(page.getByRole('alert')).toContainText('平台连接暂不可用')
  await expect(page).toHaveURL(/token=expired-token/)
  available = true
  await page.getByLabel('新密码', { exact: true }).fill('😀'.repeat(12))
  await page.getByRole('button', { name: '确认重置密码' }).click()
  await expect(page.getByRole('alert')).toContainText('重置链接无效、已使用或已过期')
  await expect(page.getByText('private error with secret')).toHaveCount(0)
  await page.getByRole('link', { name: '重新申请找回密码' }).click()
  await expect(page.getByRole('heading', { name: '忘记密码' })).toBeVisible()
  await page.goto('./#/reset-password')
  await expect(page.getByRole('alert')).toContainText('缺少重置链接')
})

test('a response for an old reset link cannot complete a new link page', async ({ page }) => {
  let release: (() => void) | undefined
  const waiting = new Promise<void>(resolve => { release = resolve })
  let oldStarted = false
  let oldFinished = false
  await page.route(`${api}/auth/reset-password`, async route => {
    if (route.request().postDataJSON().token === 'old-link') {
      oldStarted = true
      await waiting
      await route.fulfill({ json: { code: 'PASSWORD_RESET' } })
      oldFinished = true
    } else {
      expect(route.request().postDataJSON().token).toBe('new-link')
      await route.fulfill({ json: { code: 'PASSWORD_RESET' } })
    }
  })
  await page.goto('./#/reset-password?token=old-link')
  await page.getByLabel('新密码', { exact: true }).fill('new password old')
  await page.getByRole('button', { name: '确认重置密码' }).click()
  await expect.poll(() => oldStarted).toBe(true)
  await expect(page.getByRole('button', { name: '正在更新…' })).toBeDisabled()
  await page.evaluate(() => { window.location.hash = '#/reset-password?token=new-link' })
  await page.getByLabel('新密码', { exact: true }).fill('new password new')
  release?.()
  await expect.poll(() => oldFinished).toBe(true)
  await expect(page).toHaveURL(/token=new-link/)
  await expect(page.getByRole('button', { name: '确认重置密码' })).toBeEnabled()
  await page.getByRole('button', { name: '确认重置密码' }).click()
  await expect(page.getByRole('status').filter({ hasText: '密码已更新' })).toBeVisible()
})
