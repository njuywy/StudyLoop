import { expect, test } from '@playwright/test'

const api = 'https://124.220.147.193/api/v1'
const user = { id: 'u1', email: 'verified@example.com', nickname: '阿云', role: 'user' }

test.beforeEach(async ({ page }) => {
  await page.route(`${api}/health`, route => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
})

test('protected deep link returns after login, survives refresh and logout revokes local session', async ({ page }) => {
  let profileReads = 0
  let logouts = 0
  await page.route(`${api}/auth/login`, route => {
    expect(route.request().postDataJSON()).toEqual({ email: 'verified@example.com', password: ' valid password ' })
    return route.fulfill({ json: { token: 'browser-secret', expires_at: new Date(Date.now() + 60_000).toISOString(), user } })
  })
  await page.route(`${api}/me`, route => {
    profileReads++
    expect(route.request().headers()['authorization']).toBe('Bearer browser-secret')
    return route.fulfill({ json: user })
  })
  await page.route(`${api}/auth/logout`, route => {
    logouts++
    expect(route.request().headers()['authorization']).toBe('Bearer browser-secret')
    return route.fulfill({ json: { code: 'LOGGED_OUT' } })
  })
  await page.goto('./#/review')
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await page.getByLabel('邮箱', { exact: true }).fill('verified@example.com')
  await page.getByLabel('密码', { exact: true }).fill(' valid password ')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/StudyLoop\/#\/review$/)
  await expect(page.getByText('在线复习功能正在建设中。')).toBeVisible()
  await page.reload()
  await expect(page.getByText('在线复习功能正在建设中。')).toBeVisible()
  expect(profileReads).toBeGreaterThanOrEqual(2)
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByText('邮箱：verified@example.com')).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  expect(logouts).toBe(1)
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
  await page.goto('./#/profile')
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('server 401 clears the session and a network error offers retry without exposing data', async ({ page }) => {
  await page.goto('./')
  await page.evaluate(() => sessionStorage.setItem('studyloop_session', 'expired-token'))
  await page.evaluate(() => sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString()))
  await page.reload()
  await page.route(`${api}/me`, route => route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED' } }))
  await page.goto('./#/profile')
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
  await page.unroute(`${api}/me`)
  await page.evaluate(() => sessionStorage.setItem('studyloop_session', 'browser-secret'))
  await page.evaluate(() => sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString()))
  await page.reload()
  let available = false
  await page.route(`${api}/me`, route => available ? route.fulfill({ json: user }) : route.abort())
  await page.goto('./#/review')
  await expect(page.getByRole('alert')).toContainText('网络连接暂不可用')
  await expect(page.getByText('在线复习功能正在建设中。')).toHaveCount(0)
  available = true
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('在线复习功能正在建设中。')).toBeVisible()
})

test('failed logout retains local session so it can be retried', async ({ page }) => {
  await page.goto('./')
  await page.evaluate(() => sessionStorage.setItem('studyloop_session', 'browser-secret'))
  await page.evaluate(() => sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString()))
  await page.reload()
  await page.route(`${api}/me`, route => route.fulfill({ json: user }))
  await page.route(`${api}/auth/logout`, route => route.abort())
  await page.goto('./#/profile')
  await expect(page.getByText('邮箱：verified@example.com')).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('alert')).toContainText('网络连接暂不可用')
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBe('browser-secret')
  await page.unroute(`${api}/auth/logout`)
  await page.route(`${api}/auth/logout`, route => route.fulfill({ json: { code: 'LOGGED_OUT' } }))
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('expired tab session is removed before a protected view opens', async ({ page }) => {
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'expired-token')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() - 1000).toISOString())
  })
  await page.reload()
  await page.goto('./#/profile')
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('an open protected page redirects when its session expires', async ({ page }) => {
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'short-lived-token')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 2500).toISOString())
  })
  await page.reload()
  await page.route(`${api}/me`, route => route.fulfill({ json: user }))
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByText('邮箱：verified@example.com')).toBeVisible()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('登录状态已失效')
  await expect(page).toHaveURL(/redirect=\/profile.*expired=1/)
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('a 401 from the previous protected route redirects the current route', async ({ page }) => {
  let releaseFirst: (() => void) | undefined
  let releaseSecond: (() => void) | undefined
  const first = new Promise<void>(resolve => { releaseFirst = resolve })
  const second = new Promise<void>(resolve => { releaseSecond = resolve })
  let reads = 0
  await page.route(`${api}/me`, async route => {
    reads++
    if (reads === 1) {
      await first
      await route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED' } })
    } else {
      await second
      await route.fulfill({ json: user })
    }
  })
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'browser-secret')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.reload()
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect.poll(() => reads).toBe(1)
  await page.getByRole('navigation').getByRole('link', { name: '在线复习' }).click()
  await expect.poll(() => reads).toBe(2)
  releaseFirst?.()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('登录状态已失效')
  await expect(page).toHaveURL(/redirect=\/review.*expired=1/)
  releaseSecond?.()
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

for (const oldStatus of [200, 401]) {
  test(`a delayed account A response (${oldStatus}) cannot affect account B`, async ({ page }) => {
    let releaseA: (() => void) | undefined
    let aRequested = false
    let aCompleted = false
    const waitingForA = new Promise<void>(resolve => { releaseA = resolve })
    const userB = { id: 'u2', email: 'second@example.com', nickname: '阿布', role: 'user' }
    await page.route(`${api}/me`, async route => {
      const authorization = route.request().headers()['authorization']
      if (authorization === 'Bearer token-A') {
        aRequested = true
        await waitingForA
        await route.fulfill(oldStatus === 401 ? { status: 401, json: { code: 'UNAUTHORIZED' } } : { json: user })
        aCompleted = true
      } else {
        expect(authorization).toBe('Bearer token-B')
        await route.fulfill({ json: userB })
      }
    })
    await page.route(`${api}/auth/logout`, route => route.fulfill({ json: { code: 'LOGGED_OUT' } }))
    await page.route(`${api}/auth/login`, route => route.fulfill({ json: {
      token: 'token-B', expires_at: new Date(Date.now() + 60_000).toISOString(), user: userB,
    } }))
    await page.goto('./')
    await page.evaluate(() => {
      sessionStorage.setItem('studyloop_session', 'token-A')
      sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
    })
    await page.reload()
    await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
    await expect.poll(() => aRequested).toBe(true)
    await page.getByRole('button', { name: '退出' }).click()
    await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
    await page.getByLabel('邮箱', { exact: true }).fill(userB.email)
    await page.getByLabel('密码', { exact: true }).fill('password-B')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByText('邮箱：second@example.com')).toBeVisible()
    releaseA?.()
    await expect.poll(() => aCompleted).toBe(true)
    await expect(page.getByText('邮箱：second@example.com')).toBeVisible()
    await expect(page.getByText('邮箱：verified@example.com')).toHaveCount(0)
    expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBe('token-B')
  })
}

test('a delayed logout from account A cannot sign out account B', async ({ page }) => {
  let releaseLogout: (() => void) | undefined
  let logoutRequested = false
  let logoutCompleted = false
  const waitingForLogout = new Promise<void>(resolve => { releaseLogout = resolve })
  const userB = { id: 'u2', email: 'second@example.com', nickname: '阿布', role: 'user' }
  await page.route(`${api}/me`, route => route.fulfill({ json: route.request().headers()['authorization'] === 'Bearer token-B' ? userB : user }))
  await page.route(`${api}/auth/logout`, async route => {
    logoutRequested = true
    await waitingForLogout
    await route.fulfill({ json: { code: 'LOGGED_OUT' } })
    logoutCompleted = true
  })
  await page.route(`${api}/auth/login`, route => route.fulfill({ json: {
    token: 'token-B', expires_at: new Date(Date.now() + 60_000).toISOString(), user: userB,
  } }))
  await page.goto('./')
  await page.evaluate(() => {
    sessionStorage.setItem('studyloop_session', 'token-A')
    sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 60_000).toISOString())
  })
  await page.reload()
  await page.getByRole('navigation').getByRole('link', { name: '个人中心' }).click()
  await expect(page.getByText('邮箱：verified@example.com')).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await expect.poll(() => logoutRequested).toBe(true)
  await page.evaluate(() => { window.location.hash = '#/login' })
  await page.getByLabel('邮箱', { exact: true }).fill(userB.email)
  await page.getByLabel('密码', { exact: true }).fill('password-B')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('邮箱：second@example.com')).toBeVisible()
  releaseLogout?.()
  await expect.poll(() => logoutCompleted).toBe(true)
  await expect(page.getByText('邮箱：second@example.com')).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBe('token-B')
})
