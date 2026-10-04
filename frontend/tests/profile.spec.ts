import { expect, test } from './fixtures'

const api = 'https://124.220.147.193/api/v1'
const user = { id: 'a', email: 'a@example.com', nickname: '原昵称', role: 'user' }

test.beforeEach(async ({ page }) => {
  await page.route(`${api}/health`, route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'token-A')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.reload()
})

test('nickname saves to profile and navigation, survives refresh, failure preserves stored data', async ({ page }) => {
  let current = { ...user }
  let fail = false
  await page.route(`${api}/me`, route => {
    if (route.request().method() === 'PATCH') {
      if (fail) return route.fulfill({ status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'private database detail' } })
      expect(route.request().postDataJSON()).toEqual({ nickname: '新昵称' })
      current = { ...current, nickname: '新昵称' }
    }
    return route.fulfill({ json: current })
  })
  await page.goto('./#/profile')
  await expect(page.getByText('邮箱：a@example.com')).toBeVisible()
  await expect(page.locator('input[type="email"]')).toHaveCount(0)
  await page.getByLabel('昵称', { exact: true }).fill('   ')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByRole('alert')).toContainText('昵称需要 1～30 个字符')
  await page.getByLabel('昵称', { exact: true }).fill(' 新昵称 ')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByRole('status').filter({ hasText: '昵称已保存' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '你好，新昵称' })).toBeVisible()
  await expect(page.getByRole('link', { name: '新昵称', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('昵称', { exact: true })).toHaveValue('新昵称')
  fail = true
  await page.getByLabel('昵称', { exact: true }).fill('未保存昵称')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByRole('alert')).toContainText('请求暂未完成')
  await expect(page.getByRole('heading', { name: '你好，新昵称' })).toBeVisible()
  await expect(page.getByText('private database detail')).toHaveCount(0)
})

test('password validation and wrong password preserve session; success requires fresh login', async ({ page }) => {
  let requests = 0
  await page.route(`${api}/me`, route => route.fulfill({ json: user }))
  await page.route(`${api}/me/change-password`, route => {
    requests++
    expect(route.request().postDataJSON()).toEqual({ old_password: ' old password ', new_password: ' new password ' })
    return route.fulfill(requests === 1 ? { status: 400, json: { code: 'INVALID_CURRENT_PASSWORD' } } : { json: { code: 'PASSWORD_CHANGED' } })
  })
  await page.goto('./#/profile')
  await page.getByLabel('旧密码', { exact: true }).fill(' old password ')
  await page.getByLabel('新密码', { exact: true }).fill('short')
  await page.getByRole('button', { name: '修改密码并重新登录' }).click()
  await expect(page.getByRole('alert')).toContainText('新密码需要 12～128 个字符')
  expect(requests).toBe(0)
  await page.getByLabel('新密码', { exact: true }).fill(' new password ')
  await page.getByRole('button', { name: '修改密码并重新登录' }).click()
  await expect(page.getByRole('alert')).toContainText('旧密码不正确')
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBe('token-A')
  await page.getByLabel('旧密码', { exact: true }).fill(' old password ')
  await page.getByLabel('新密码', { exact: true }).fill(' new password ')
  await page.getByRole('button', { name: '修改密码并重新登录' }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('密码已更新，请使用新密码重新登录')
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('a delayed nickname save from A does not overwrite B after account switch', async ({ page }) => {
  let release: (() => void) | undefined
  const waiting = new Promise<void>(resolve => { release = resolve })
  let started = false
  let completed = false
  const userB = { ...user, id: 'b', email: 'b@example.com', nickname: '用户B' }
  await page.route(`${api}/me`, async route => {
    if (route.request().method() === 'PATCH') {
      started = true
      await waiting
      await route.fulfill({ json: { ...user, nickname: '用户A的新昵称' } })
      completed = true
    } else await route.fulfill({ json: route.request().headers()['authorization'] === 'Bearer token-B' ? userB : user })
  })
  await page.route(`${api}/auth/logout`, route => route.fulfill({ json: { code: 'LOGGED_OUT' } }))
  await page.route(`${api}/auth/login`, route => route.fulfill({ json: { token: 'token-B', expires_at: new Date(Date.now() + 60_000).toISOString(), user: userB } }))
  await page.goto('./#/profile')
  await page.getByLabel('昵称', { exact: true }).fill('用户A的新昵称')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect.poll(() => started).toBe(true)
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('b@example.com')
  await page.getByLabel('密码', { exact: true }).fill('B password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('邮箱：b@example.com')).toBeVisible()
  release?.()
  await expect.poll(() => completed).toBe(true)
  await expect(page.getByRole('heading', { name: '用户B', exact: true })).toBeVisible()
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByRole('heading', { name: '你好，用户B' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBe('token-B')
})

test('password change finishing after navigation still redirects the revoked session', async ({ page }) => {
  let release: (() => void) | undefined
  const waiting = new Promise<void>(resolve => { release = resolve })
  let started = false
  await page.route(`${api}/me`, route => route.fulfill({ json: user }))
  await page.route(`${api}/me/change-password`, async route => {
    started = true
    await waiting
    await route.fulfill({ json: { code: 'PASSWORD_CHANGED' } })
  })
  await page.goto('./#/profile')
  await page.getByLabel('旧密码', { exact: true }).fill('old password')
  await page.getByLabel('新密码', { exact: true }).fill('new password')
  await page.getByRole('button', { name: '修改密码并重新登录' }).click()
  await expect.poll(() => started).toBe(true)
  await page.getByRole('navigation').getByRole('link', { name: '在线复习' }).click()
  await expect(page.getByText('在线复习功能正在建设中。')).toBeVisible()
  release?.()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('密码已更新')
})

test('a nickname save remains pending across navigation before the next save is allowed', async ({ page }) => {
  let current = { ...user }
  let release: (() => void) | undefined
  const waiting = new Promise<void>(resolve => { release = resolve })
  let writes = 0
  await page.route(`${api}/me`, async route => {
    if (route.request().method() === 'PATCH') {
      writes++
      current = { ...current, nickname: route.request().postDataJSON().nickname }
      if (writes === 1) await waiting
    }
    await route.fulfill({ json: current })
  })
  await page.goto('./#/profile')
  await page.getByLabel('昵称', { exact: true }).fill('第一次保存')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect.poll(() => writes).toBe(1)
  await page.getByRole('navigation').getByRole('link', { name: '在线复习' }).click()
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByRole('button', { name: '正在保存…' })).toBeDisabled()
  await expect(page.getByLabel('昵称', { exact: true })).toBeDisabled()
  release?.()
  await expect(page.getByRole('button', { name: '保存昵称' })).toBeEnabled()
  await page.getByLabel('昵称', { exact: true }).fill('第二次保存')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByRole('heading', { name: '你好，第二次保存' })).toBeVisible()
  expect(writes).toBe(2)
})

test('profile route variants keep the account forms available', async ({ page }) => {
  for (const path of ['/profile/', '/Profile']) {
    await page.goto(`./#${path}`)
    await expect(page.getByRole('heading', { name: '个人中心', exact: true })).toBeVisible()
    await expect(page.getByLabel('昵称', { exact: true })).toBeVisible()
    await expect(page.getByLabel('选择头像')).toBeVisible()
    await expect(page.getByLabel('旧密码', { exact: true })).toBeVisible()
  }
})
