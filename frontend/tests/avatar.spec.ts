import { expect, test } from './fixtures'

const api = 'https://124.220.147.193/api/v1'
const user = { id: 'a', email: 'a@example.com', nickname: '头像用户', role: 'user' }
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhXkAAAAASUVORK5CYII=', 'base64')
const file = { name: 'avatar.png', mimeType: 'image/png', buffer: png }

test.beforeEach(async ({ page }) => {
  await page.route(`${api}/health`, route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.route(`${api}/me`, route => route.fulfill({ json: user }))
  await page.route(`${api}/auth/logout`, route => route.fulfill({ json: { code: 'LOGGED_OUT' } }))
  await page.addInitScript(() => {
    const original = URL.revokeObjectURL
    ;(window as unknown as { revoked: string[] }).revoked = []
    URL.revokeObjectURL = (url: string) => {
      ;(window as unknown as { revoked: string[] }).revoked.push(url)
      original(url)
    }
  })
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'token-A')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.goto('about:blank')
})

test('avatar displays in both places, survives refresh, failures retain it and logout revokes URLs', async ({ page }) => {
  let uploaded = false
  let fail = false
  await page.route(`${api}/me/avatar`, route => {
    expect(route.request().headers()['authorization']).toBe('Bearer token-A')
    if (route.request().method() === 'PUT') {
      if (fail) return route.fulfill({ status: 503, json: { code: 'AVATAR_UNAVAILABLE' } })
      uploaded = true
    }
    return route.fulfill(uploaded ? { contentType: 'image/png', body: png } : { status: 404, json: { code: 'NO_AVATAR' } })
  })
  await page.goto('./#/profile')
  await expect(page.getByRole('img', { name: '默认头像' })).toHaveCount(2)
  await page.getByLabel('选择头像').setInputFiles(file)
  await page.getByRole('button', { name: '上传头像', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '头像已更新' })).toBeVisible()
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(2)
  const original = await page.getByRole('img', { name: '我的头像' }).first().getAttribute('src')
  fail = true
  await page.getByRole('button', { name: '上传头像', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('请求暂未完成')
  await expect(page.getByRole('img', { name: '我的头像' }).first()).toHaveAttribute('src', original!)
  fail = false
  await page.getByRole('button', { name: '上传头像', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { revoked: string[] }).revoked)).toContain(original)
  await page.reload()
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(2)
  const refreshed = await page.getByRole('img', { name: '我的头像' }).first().getAttribute('src')
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => (window as unknown as { revoked: string[] }).revoked)).toContain(refreshed)
})

test('invalid files are rejected locally and a 401 clears the displayed avatar', async ({ page }) => {
  let writes = 0
  await page.route(`${api}/me/avatar`, route => {
    if (route.request().method() === 'PUT') {
      writes++
      return route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED' } })
    }
    return route.fulfill({ contentType: 'image/png', body: png })
  })
  await page.goto('./#/profile')
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(2)
  for (const invalid of [{ name: 'a.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg/>') }, { ...file, buffer: Buffer.alloc(2097153) }]) {
    await page.getByLabel('选择头像').setInputFiles(invalid)
    await page.getByRole('button', { name: '上传头像', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('请选择不超过 2 MiB')
  }
  expect(writes).toBe(0)
  await page.getByLabel('选择头像').setInputFiles(file)
  await page.getByRole('button', { name: '上传头像', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('a delayed avatar from A cannot appear after login as B', async ({ page }) => {
  let release: (() => void) | undefined
  let started = false
  let completed = false
  const waiting = new Promise<void>(resolve => { release = resolve })
  await page.route(`${api}/me/avatar`, async route => {
    if (route.request().headers()['authorization'] === 'Bearer token-A') {
      started = true
      await waiting
      await route.fulfill({ contentType: 'image/png', body: png })
      completed = true
    } else await route.fulfill({ status: 404, json: { code: 'NO_AVATAR' } })
  })
  const userB = { ...user, id: 'b', email: 'b@example.com', nickname: '用户B' }
  await page.route(`${api}/me`, route => route.fulfill({ json: route.request().headers()['authorization'] === 'Bearer token-B' ? userB : user }))
  await page.route(`${api}/auth/login`, route => route.fulfill({ json: { token: 'token-B', expires_at: new Date(Date.now() + 60_000).toISOString(), user: userB } }))
  await page.goto('./#/profile')
  await expect.poll(() => started).toBe(true)
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill(userB.email)
  await page.getByLabel('密码', { exact: true }).fill('password B')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('邮箱：b@example.com')).toBeVisible()
  release?.()
  await expect.poll(() => completed).toBe(true)
  await expect(page.getByRole('img', { name: '默认头像' })).toHaveCount(2)
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(0)
})

test('a stale avatar read cannot replace a successful upload; pending survives navigation', async ({ page }) => {
  let releaseRead: (() => void) | undefined
  let releaseWrite: (() => void) | undefined
  let writes = 0
  let readDone = false
  const reading = new Promise<void>(resolve => { releaseRead = resolve })
  const writing = new Promise<void>(resolve => { releaseWrite = resolve })
  await page.route(`${api}/me/avatar`, async route => {
    if (route.request().method() === 'GET') {
      await reading
      await route.fulfill({ status: 404, json: { code: 'NO_AVATAR' } })
      readDone = true
    } else {
      writes++
      await writing
      await route.fulfill({ contentType: 'image/png', body: png })
    }
  })
  await page.goto('./#/profile')
  await page.getByLabel('选择头像').setInputFiles(file)
  await page.getByRole('button', { name: '上传头像', exact: true }).click()
  await expect.poll(() => writes).toBe(1)
  await page.getByRole('navigation').getByRole('link', { name: '在线复习' }).click()
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByRole('button', { name: '正在上传…' })).toBeDisabled()
  releaseWrite?.()
  await expect(page.getByRole('img', { name: '我的头像' })).toHaveCount(2)
  const uploaded = await page.getByRole('img', { name: '我的头像' }).first().getAttribute('src')
  releaseRead?.()
  await expect.poll(() => readDone).toBe(true)
  await expect(page.getByRole('img', { name: '我的头像' }).first()).toHaveAttribute('src', uploaded!)
})
