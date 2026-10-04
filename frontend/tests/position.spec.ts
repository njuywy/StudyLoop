import type { Page, Route } from '@playwright/test'
import { test, expect } from './fixtures'
const api = 'https://124.220.147.193/api/v1'
const book = { id: 'book', title: '长篇资料', version: 'v1', point_count: 2, page_count: 3, coverage_label: '测试资料' }
const location = (point = 'p1', block = 'b12', revision = 3) => ({ point_id: point, block_id: `${point}-${block}`, offset: 0.4, content_version: 'v1', revision, updated_at: '2026-10-04T00:00:00Z' })
type Position = ReturnType<typeof location>
async function setup(page: Page, options: { initial?: Position | null; getFail?: boolean; failWrites?: boolean; slowImage?: boolean } = {}) {
  const server = { value: options.initial || null as Position | null, writes: [] as any[], getFail: options.getFail || false, failWrites: options.failWrites || false, user: 'A', handler: null as null | ((r: Route) => Promise<void>) }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('seeded')) {
      sessionStorage.setItem('studyloop_session', 'session-A'); sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 3600000).toISOString()); sessionStorage.setItem('seeded', 'yes')
    }
  })
  await page.route(`${api}/**`, async r => {
    const path = new URL(r.request().url()).pathname
    if (path.endsWith('/health')) return r.fulfill({ json: { status: 'ok', database: 'ok' } })
    if (path.endsWith('/me')) return r.fulfill({ json: { id: server.user, nickname: `读者${server.user}`, email: `${server.user}@example.com`, role: 'user' } })
    if (path.endsWith('/auth/logout')) return r.fulfill({ json: {} })
    if (path.endsWith('/auth/login')) { server.user = r.request().postDataJSON().email.startsWith('A') ? 'A' : 'B'; return r.fulfill({ json: { token: `session-${server.user}`, expires_at: new Date(Date.now() + 3600000).toISOString(), user: { id: server.user, nickname: `读者${server.user}`, email: `${server.user}@example.com`, role: 'user' } } }) }
    if (path.endsWith('/avatar')) return r.fulfill({ status: 404, json: {} })
    if (path.includes('/assets/')) { await new Promise(resolve => setTimeout(resolve, 1200)); return r.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="680" height="320"><rect width="680" height="320" fill="#e4eddf"/></svg>' }) }
    if (path.endsWith('/review/books')) return r.fulfill({ json: { items: [book] } })
    if (path.endsWith('/toc')) return r.fulfill({ json: { book, items: ['p1', 'p2'].map((id, i) => ({ id, title: `知识点${i + 1}`, point_id: id, parent_id: null, level: 1, path: [`知识点${i + 1}`], page: 1 })) } })
    if (path.includes('/review/points/')) {
      const id = path.split('/').at(-1)!
      return r.fulfill({ json: { id, book_id: 'book', title: id === 'p1' ? '知识点1' : '知识点2', version: 'v1', path: ['章节', id], source_start: 1, source_end: 1, previous_id: id === 'p2' ? 'p1' : null, next_id: id === 'p1' ? 'p2' : null,
        blocks: [...(options.slowImage ? [{ id: 'figure', type: 'figure', asset_id: 'test.svg', alt: '延迟图表', width: 680, height: 320, page: 1, bbox: [0, 0, 680, 320] }] : []), ...Array.from({ length: 30 }, (_, i) => ({ id: `${id}-b${i}`, type: 'paragraph', text: `段落${i}：${'阅读位置应按知识点与正文块保存，窗口宽度改变也能找到相同段落。'.repeat(8)}`, page: 1, bbox: [0, i * 20, 500, i * 20 + 20] }))] } })
    }
    if (path.endsWith('/position')) {
      if (r.request().method() === 'GET') return r.fulfill({ status: server.getFail ? 503 : 200, json: server.getFail ? { message: '暂时无法读取' } : { position: server.user === 'B' ? null : server.value } })
      const body = r.request().postDataJSON(); server.writes.push(body)
      if (server.handler) return server.handler(r)
      if (server.failWrites) return r.abort()
      if ((server.value?.revision || 0) !== body.expected_revision) return r.fulfill({ status: 409, json: { message: '位置冲突', position: server.value } })
      server.value = { ...body, revision: body.expected_revision + 1, updated_at: '2026-10-04T00:00:00Z' }
      return r.fulfill({ json: { position: server.value } })
    }
    return r.abort()
  })
  return server
}
async function scrollTo(page: Page, id: string) {
  await expect(page.locator(`#block-${id}`)).toBeAttached()
  await page.evaluate(id => { const e = document.getElementById(`block-${id}`)!; window.scrollTo(0, scrollY + e.getBoundingClientRect().top + e.clientHeight * 0.4 - 80) }, id)
}
async function assertRestored(page: Page, target: Position) {
  await expect.poll(() => page.evaluate(t => { const r = document.getElementById(`block-${t.block_id}`)?.getBoundingClientRect(); return r ? Math.abs(r.top + r.height * t.offset - 80) : 9999 }, target)).toBeLessThan(4)
}

test('saves reading position, restores after reopening and respects explicit point links', async ({ page, browser }, info) => {
  const server = await setup(page, { slowImage: true })
  await page.goto('./#/review?point=p1')
  await expect.poll(() => server.writes.length).toBe(1)
  await scrollTo(page, 'p1-b12')
  await expect.poll(() => server.value?.block_id).toBe('p1-b12')
  const saved = { ...server.value! }
  await page.goto('./#/review')
  await page.getByRole('button', { name: '继续上次阅读' }).click()
  await assertRestored(page, saved)
  const context = await browser.newContext({ viewport: { width: info.project.name === 'mobile' ? 1280 : 390, height: 900 } })
  const second = await context.newPage(); await setup(second, { initial: saved, slowImage: true })
  await second.goto(page.url().split('#')[0] + '#/review')
  await second.getByRole('button', { name: '继续上次阅读' }).click()
  await assertRestored(second, saved)
  await expect(second.getByRole('img', { name: '延迟图表' })).toBeAttached()
  await assertRestored(second, saved)
  await second.setViewportSize({ width: 768, height: 900 }); await assertRestored(second, saved)
  await context.close()
  await page.goto('./#/review?point=p2')
  await expect(page.getByRole('heading', { name: '知识点2', exact: true })).toBeVisible()
  await expect.poll(() => server.value?.point_id).toBe('p2')
})

test('failed first read never writes a default position and offers a safe conflict decision', async ({ page }) => {
  const server = await setup(page, { initial: location(), getFail: true })
  await page.goto('./#/review?point=p2')
  await expect(page.getByText('上次位置读取失败，自动同步已暂停')).toBeVisible()
  await scrollTo(page, 'p2-b8')
  await page.waitForTimeout(1200); expect(server.writes).toHaveLength(0)
  server.getFail = false
  await page.getByRole('button', { name: '重试读取位置' }).click()
  await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
  expect(server.writes).toHaveLength(0)
  await page.getByRole('button', { name: '使用服务器位置' }).click()
  await assertRestored(page, location())
})

test('unknown save result retries the same operation; new conflicts require a fresh decision', async ({ page }) => {
  const server = await setup(page, { failWrites: true })
  await page.goto('./#/review?point=p1')
  await expect(page.getByRole('button', { name: '重试保存位置' })).toBeVisible()
  const operation = server.writes[0].operation_id
  await page.getByRole('button', { name: '重试保存位置' }).click()
  await expect.poll(() => server.writes.length).toBeGreaterThan(1)
  expect(server.writes[1].operation_id).toBe(operation)
  server.failWrites = false; server.value = location('p2', 'b10', 5)
  await page.getByRole('button', { name: '重试保存位置' }).click()
  await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
  const count = server.writes.length
  await page.waitForTimeout(1100); expect(server.writes).toHaveLength(count)
  server.value = location('p2', 'b11', 6)
  await page.getByRole('button', { name: '以本地位置继续并保存' }).click()
  await expect.poll(() => server.writes.length).toBe(count + 1)
  await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
  await page.getByRole('button', { name: '以本地位置继续并保存' }).click()
  await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
  expect(server.value?.point_id).toBe('p1')
})

test('offline draft survives reopening and reconnects only after verified identity', async ({ page }) => {
  const server = await setup(page)
  await page.goto('./#/review?point=p1')
  await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
  await page.context().setOffline(true)
  await scrollTo(page, 'p1-b9')
  await expect(page.getByText('离线，位置尚未同步')).toBeVisible()
  const count = server.writes.length
  const draft = await page.evaluate(() => localStorage.getItem('studyloop_position:A:book:v1'))
  expect(JSON.parse(draft!).candidate.block_id).toBe('p1-b9')
  await page.evaluate(() => { window.location.hash = '/' })
  await expect(page.getByRole('heading', { name: '知识点1', exact: true })).toHaveCount(0)
  await page.context().setOffline(false)
  await page.goto('./#/review')
  await expect.poll(() => server.writes.length).toBeGreaterThan(count)
  await expect.poll(() => server.value?.block_id).toBe('p1-b9')
  await page.getByRole('button', { name: '继续上次阅读' }).click()
  await assertRestored(page, server.value!)
})

test('unavailable storage is visible and invalid historic anchors never write their fallback', async ({ page }) => {
  const server = await setup(page, { initial: location('p1', 'missing') })
  await page.addInitScript(() => { const original = Storage.prototype.setItem; Storage.prototype.setItem = function(k, v) { if (k.startsWith('studyloop_position:')) throw new Error('blocked'); original.call(this, k, v) } })
  await page.goto('./#/review')
  await page.getByRole('button', { name: '继续上次阅读' }).click()
  await expect(page.getByText('原来的段落位置已失效，已返回该知识点开头。')).toBeVisible()
  await page.waitForTimeout(1200); expect(server.writes).toHaveLength(0)
  await page.goto('./#/review')
  await page.waitForTimeout(1100); expect(server.writes).toHaveLength(0)
  await page.getByRole('button', { name: '继续上次阅读' }).click()
  await expect(page.getByText('原来的段落位置已失效，已返回该知识点开头。')).toBeVisible()
  await scrollTo(page, 'p1-b5')
  await expect(page.getByText(/浏览器本地暂存不可用/)).toBeVisible()
  await expect.poll(() => server.value?.block_id).toBe('p1-b5')
})

test('unavailable knowledge point returns to directory instead of an unrelated point', async ({ page }) => {
  const server = await setup(page, { initial: location('missing') })
  await page.goto('./#/review')
  await page.getByRole('button', { name: '继续上次阅读' }).click()
  await expect(page.getByText('上次知识点暂不可用，请从目录重新选择。')).toBeVisible()
  await expect(page.getByRole('heading', { name: '从一个知识点开始' })).toBeVisible()
  expect(server.writes).toHaveLength(0)
})


test('late account A save cannot restore private state in account B, and A draft remains isolated', async ({ page }) => {
  const server = await setup(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.handler = async r => { await gate; await r.fulfill({ json: { position: location('p1', 'b20', 1) } }) }
  await page.goto('./#/review?point=p1')
  await expect.poll(() => server.writes.length).toBe(1)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await page.getByLabel('邮箱', { exact: true }).fill('B@example.com')
  await page.getByLabel('密码', { exact: true }).fill('example password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.goto('./#/review')
  await expect(page.getByText('尚无阅读记录', { exact: true })).toBeVisible()
  release(); await page.waitForTimeout(200)
  await expect(page.getByRole('button', { name: '继续上次阅读' })).toHaveCount(0)
  expect(server.writes).toHaveLength(1)
  expect(await page.evaluate(() => localStorage.getItem('studyloop_position:A:book:v1'))).not.toBeNull()
  expect(await page.evaluate(() => localStorage.getItem('studyloop_position:B:book:v1'))).toBeNull()
})


test('continuous scrolling initiates a save within five seconds without waiting for a pause', async ({ page }) => {
  const server = await setup(page)
  await page.goto('./#/review?point=p1')
  await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
  const before = server.writes.length
  for (let i = 1; i <= 8; i++) { await scrollTo(page, `p1-b${i}`); await page.waitForTimeout(700) }
  expect(server.writes.length).toBeGreaterThan(before)
  expect(server.writes.at(-1).block_id).not.toBe('p1-b0')
})


for (const changed of [false, true]) test(`old successful replay cannot replace a newer server position (new local candidate: ${changed})`, async ({ page }) => {
  const server = await setup(page, { initial: location('p2', 'b10', 9) })
  const old = location('p1', 'b0', 1)
  const operation = { point_id: old.point_id, block_id: old.block_id, offset: old.offset, content_version: old.content_version, expected_revision: 0, operation_id: '12345678-1234-4234-8234-123456789012' }
  await page.addInitScript(({ operation, changed }) => localStorage.setItem('studyloop_position:A:book:v1', JSON.stringify({ candidate: { ...operation, block_id: changed ? 'p1-b8' : operation.block_id }, baseRevision: 0, operation })), { operation, changed })
  server.handler = r => r.fulfill({ json: { position: old } })
  await page.goto('./#/review')
  await expect.poll(() => server.writes.length).toBe(1)
  if (changed) {
    await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
    await page.getByRole('button', { name: '使用服务器位置' }).click()
  } else {
    await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '继续上次阅读' }).click()
  }
  await assertRestored(page, location('p2', 'b10', 9))
})

test('a delayed conflict save cannot navigate after account switch or a newer explicit selection', async ({ page }) => {
  const server = await setup(page, { initial: location('p2', 'b4', 2) })
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.handler = async r => {
    if (server.writes.length === 1) return r.fulfill({ status: 409, json: { position: location('p2', 'b5', 3), message: '冲突' } })
    await gate
    await r.fulfill({ json: { position: location('p1', 'b0', 4) } })
  }
  await page.goto('./#/review?point=p1')
  await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
  await page.getByRole('button', { name: '以本地位置继续并保存' }).click()
  await expect.poll(() => server.writes.length).toBe(2)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('B@example.com')
  await page.getByLabel('密码', { exact: true }).fill('example password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.goto('./#/profile')
  await expect(page).toHaveURL(/#\/profile$/)
  release(); await page.waitForTimeout(250)
  await expect(page).toHaveURL(/#\/profile$/)
})
