import { expect, test } from '@playwright/test'

test('Pages subpath navigation and hash refresh keep the application available', async ({ page }) => {
  await page.route('https://124.220.147.193/api/v1/health', route => route.fulfill({
    json: { status: 'ok', database: 'ok' },
  }))
  await page.goto('./')
  await expect(page.getByRole('status')).toHaveText('平台连接已就绪')
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page).toHaveURL(/\/StudyLoop\/#\/login\?redirect=/)
  await page.reload()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('a unavailable API does not stop navigation and can be retried', async ({ page }) => {
  let available = false
  await page.route('https://124.220.147.193/api/v1/health', route => route.fulfill({
    status: available ? 200 : 503,
    json: available ? { status: 'ok', database: 'ok' } : { code: 'DATABASE_UNAVAILABLE', message: 'internal details' },
  }))
  await page.goto('./')
  await expect(page.getByRole('status')).toHaveText('平台连接暂不可用')
  await expect(page.getByText('internal details')).toHaveCount(0)
  available = true
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByRole('status')).toHaveText('平台连接已就绪')
  await page.getByRole('link', { name: '注册账号' }).click()
  await expect(page.getByRole('heading', { name: '注册账号' })).toBeVisible()
})
