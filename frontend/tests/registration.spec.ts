import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/health', route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
})

test('registration preserves passwords, prevents double submit and offers retry after mail failure', async ({ page }) => {
  let requests = 0
  let finish: (() => void) | undefined
  await page.route('**/api/v1/auth/register', async route => {
    requests++
    expect(route.request().postDataJSON()).toEqual({ email: 'learner@example.com', password: ' a long password ', nickname: null })
    await new Promise<void>(resolve => { finish = resolve })
    await route.fulfill({ status: 503, json: { code: 'MAIL_UNAVAILABLE', message: 'untrusted internal mail secret' } })
  })
  await page.goto('./#/register')
  await page.getByLabel('邮箱', { exact: true }).fill('learner@example.com')
  await page.getByLabel('密码', { exact: true }).fill('short')
  await page.getByRole('button', { name: '注册并发送验证邮件' }).click()
  await expect(page.getByRole('alert')).toContainText('12～128')
  expect(requests).toBe(0)
  await page.getByLabel('密码', { exact: true }).fill(' a long password ')
  await page.getByRole('button', { name: '注册并发送验证邮件' }).click()
  await expect(page.getByRole('button', { name: '正在提交…' })).toBeDisabled()
  await expect.poll(() => !!finish).toBeTruthy()
  finish?.()
  await expect(page.getByRole('alert')).toContainText('邮件发送失败')
  await expect(page.getByText('untrusted internal mail secret')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '重发验证邮件' })).toBeVisible()
  expect(requests).toBe(1)
  await page.route('**/api/v1/auth/resend-verification', route => route.fulfill({
    status: 202,
    json: { code: 'VERIFICATION_REQUEST_ACCEPTED' },
  }))
  await page.getByRole('button', { name: '发送验证邮件', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '无法确认邮件是否送达' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '无法确认邮件是否送达' })).toHaveClass(/neutral/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0)
})

test('mail hash link survives refresh, submits only on confirmation and removes consumed token', async ({ page }) => {
  let verifications = 0
  await page.route('**/api/v1/auth/verify-email', route => {
    verifications++
    expect(route.request().postDataJSON()).toEqual({ token: 'private-verification-token' })
    return route.fulfill({ json: { code: 'EMAIL_VERIFIED' } })
  })
  await page.goto('./#/verify-email?token=private-verification-token')
  await page.reload()
  expect(verifications).toBe(0)
  await expect(page.getByText('private-verification-token')).toHaveCount(0)
  await page.getByRole('button', { name: '确认验证邮箱' }).click()
  await expect(page.getByRole('status').filter({ hasText: '邮箱验证成功' })).toBeVisible()
  await expect(page).toHaveURL(/#\/verify-email$/)
  expect(verifications).toBe(1)
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0)
  await page.getByRole('link', { name: '前往登录' }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
})
