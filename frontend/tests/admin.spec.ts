import { expect, test } from './fixtures'

const api = 'https://124.220.147.193/api/v1'
const admin = { id: 'admin', email: 'manager@example.com', nickname: '管理员M', role: 'admin' }
const ordinary = { id: 'a', email: 'a@example.com', nickname: '用户A', role: 'user' }
const full = (user: typeof admin) => ({ ...user, email_verified: true, enabled: true, created_at: '2026-10-04T00:00:00Z' })

test.beforeEach(async ({ page }) => {
  await page.route(`${api}/health`, route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.route(`${api}/me`, route => route.fulfill({ json: admin }))
  await page.route(`${api}/auth/logout`, route => route.fulfill({ json: { code: 'LOGGED_OUT' } }))
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'token-M')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.goto('about:blank')
})

test('admin pagination, protected roles, failure recovery and status changes work on mobile', async ({ page }) => {
  let target = full(ordinary)
  let fail = true
  await page.route(`${api}/admin/users?*`, route => {
    const pageNumber = Number(new URL(route.request().url()).searchParams.get('page'))
    expect(route.request().headers()['authorization']).toBe('Bearer token-M')
    return route.fulfill({ json: { page: pageNumber, page_size: 20, total: 21, items: pageNumber === 1 ? [full(admin), target] : [] } })
  })
  await page.route(`${api}/admin/users/a/status`, route => {
    if (fail) return route.fulfill({ status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'private details' } })
    target = { ...target, enabled: route.request().postDataJSON().enabled }
    return route.fulfill({ json: target })
  })
  await page.goto('./#/admin/users')
  await expect(page.getByRole('navigation').getByRole('link', { name: '用户管理' })).toBeVisible()
  await expect(page.getByText('共 21 个用户 · 第 1 页')).toBeVisible()
  const adminCard = page.getByRole('listitem').filter({ has: page.getByText(admin.email, { exact: true }) })
  const userCard = page.getByRole('listitem').filter({ has: page.getByText(ordinary.email, { exact: true }) })
  await expect(adminCard.getByRole('button')).toHaveCount(0)
  await userCard.getByRole('button', { name: '禁用用户' }).click()
  await expect(page.getByRole('alert')).toContainText('请求暂未完成')
  await expect(userCard.getByText('已启用', { exact: true })).toBeVisible()
  await expect(page.getByText('private details')).toHaveCount(0)
  fail = false
  await userCard.getByRole('button', { name: '禁用用户' }).click()
  await expect(userCard.getByText('已禁用', { exact: true })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '已有会话已失效' })).toBeVisible()
  await userCard.getByRole('button', { name: '恢复用户' }).click()
  await expect(page.getByRole('status').filter({ hasText: '恢复，可重新登录' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.getByText('本页没有用户。')).toBeVisible()
  await expect(page.getByRole('button', { name: '下一页' })).toBeDisabled()
  await page.getByRole('button', { name: '上一页' }).click()
  await expect(page.getByText('共 21 个用户 · 第 1 页')).toBeVisible()
  await page.reload()
  await expect(page.getByText('共 21 个用户 · 第 1 页')).toBeVisible()
})

test('ordinary users have no admin entry and cannot read a direct admin route', async ({ page }) => {
  let calls = 0
  await page.route(`${api}/me`, route => route.fulfill({ json: ordinary }))
  await page.route(`${api}/admin/users?*`, route => { calls++; return route.fulfill({ status: 403, json: { code: 'ADMIN_REQUIRED' } }) })
  await page.goto('./#/admin/users')
  await expect(page.getByRole('alert')).toContainText('仅管理员')
  await expect(page.getByRole('navigation').getByRole('link', { name: '用户管理' })).toHaveCount(0)
  await expect(page.getByRole('listitem')).toHaveCount(0)
  expect(calls).toBe(0)
})

test('a server-side permission change clears the list without a false success', async ({ page }) => {
  await page.route(`${api}/admin/users?*`, route => route.fulfill({ json: { page: 1, page_size: 20, total: 1, items: [full(ordinary)] } }))
  await page.route(`${api}/admin/users/a/status`, route => route.fulfill({ status: 403, json: { code: 'ADMIN_REQUIRED' } }))
  await page.goto('./#/admin/users')
  await page.getByRole('button', { name: '禁用用户' }).click()
  await expect(page.getByRole('alert')).toContainText('仅管理员')
  await expect(page.getByRole('listitem')).toHaveCount(0)
  await expect(page.getByRole('status').filter({ hasText: '已有会话已失效' })).toHaveCount(0)
})

test('a late admin list cannot leak after logout and ordinary-user login', async ({ page }) => {
  let release: (() => void) | undefined
  let started = false
  let completed = false
  const waiting = new Promise<void>(resolve => { release = resolve })
  await page.route(`${api}/admin/users?*`, async route => {
    started = true
    await waiting
    await route.fulfill({ json: { page: 1, page_size: 20, total: 1, items: [full(admin)] } })
    completed = true
  })
  await page.route(`${api}/me`, route => route.fulfill({ json: route.request().headers()['authorization'] === 'Bearer token-M' ? admin : ordinary }))
  await page.route(`${api}/auth/login`, route => route.fulfill({ json: { token: 'token-A', expires_at: new Date(Date.now() + 60_000).toISOString(), user: ordinary } }))
  await page.goto('./#/admin/users')
  await expect.poll(() => started).toBe(true)
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill(ordinary.email)
  await page.getByLabel('密码', { exact: true }).fill('password A')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('邮箱：a@example.com')).toBeVisible()
  release?.()
  await expect.poll(() => completed).toBe(true)
  await expect(page.getByText(admin.email, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('navigation').getByRole('link', { name: '用户管理' })).toHaveCount(0)
})

test('admin deep links return after login and after session expiry', async ({ page }) => {
  let expired = false
  let logins = 0
  await page.route(`${api}/admin/users?*`, route => route.fulfill(expired
    ? { status: 401, json: { code: 'UNAUTHORIZED' } }
    : { json: { page: 1, page_size: 20, total: 1, items: [full(admin)] } }))
  await page.route(`${api}/auth/login`, route => {
    expired = false
    logins++
    return route.fulfill({ json: { token: 'fresh-M-' + logins, expires_at: new Date(Date.now() + 60_000).toISOString(), user: admin } })
  })
  await page.goto('./')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('about:blank')
  await page.goto('./#/admin/users')
  for (let iteration = 0; iteration < 2; iteration++) {
    await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
    await expect(page).toHaveURL(/redirect=\/admin\/users/)
    await page.getByLabel('邮箱', { exact: true }).fill(admin.email)
    await page.getByLabel('密码', { exact: true }).fill('admin password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('heading', { name: '用户管理', exact: true })).toBeVisible()
    await expect(page.getByText(admin.email, { exact: true })).toBeVisible()
    if (iteration === 0) {
      expired = true
      await page.getByRole('button', { name: '刷新列表' }).click()
      await expect(page.getByRole('alert')).toContainText('登录状态已失效')
    }
  }
  expect(logins).toBe(2)
})
