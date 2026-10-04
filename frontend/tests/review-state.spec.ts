import type { Route } from '@playwright/test'
import { test, expect } from './fixtures'
const api = 'https://124.220.147.193/api/v1'
const initial = (id: string) => ({ point_id: id, bookmarked: false, mastery: 'unlearned', revision: 0 })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { if (!sessionStorage.getItem('state_seed')) { sessionStorage.setItem('studyloop_session', 'A'); sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 3600000).toISOString()); sessionStorage.setItem('state_seed', '1') } })
})
async function setup(page: any, count = 3) {
  const states = new Map<string, ReturnType<typeof initial>>(Array.from({ length: count }, (_, i) => [`p${i + 1}`, initial(`p${i + 1}`)]))
  const server = { states, writes: [] as any[], reads: 0, failList: false, failGet: false, user: 'A', handler: null as null | ((r: Route) => Promise<void>) }
  const book = { id: 'book', title: '复习资料', version: 'v1', point_count: count, page_count: count, coverage_label: '测试资料' }
  await page.route(`${api}/**`, async (r: Route) => {
    const url = new URL(r.request().url()), path = url.pathname
    if (path.endsWith('/health')) return r.fulfill({ json: { status: 'ok', database: 'ok' } })
    if (path.endsWith('/me')) return r.fulfill({ json: { id: server.user, nickname: `读者${server.user}`, email: `${server.user}@example.com`, role: 'user' } })
    if (path.endsWith('/avatar')) return r.fulfill({ status: 404, json: {} })
    if (path.endsWith('/auth/logout')) return r.fulfill({ json: {} })
    if (path.endsWith('/auth/login')) { server.user = 'B'; return r.fulfill({ json: { token: 'B', expires_at: new Date(Date.now() + 3600000).toISOString(), user: { id: 'B', nickname: '读者B', email: 'B@example.com', role: 'user' } } }) }
    if (path.endsWith('/position')) return r.request().method() === 'GET' ? r.fulfill({ json: { position: null } }) : r.fulfill({ json: { position: { ...r.request().postDataJSON(), revision: 1 } } })
    if (path.endsWith('/review/books')) return r.fulfill({ json: { items: [book] } })
    if (path.endsWith('/toc')) return r.fulfill({ json: { book, items: [...states.keys()].map((id, i) => ({ id, point_id: id, title: `知识点${i + 1}`, level: 1, parent_id: null, path: [`章节${i + 1}`, '同名条目'], page: i + 1 })) } })
    if (path.endsWith('/state')) {
      const id = path.split('/').at(-2)!
      if (r.request().method() === 'GET') { server.reads++; return r.fulfill({ status: server.failGet ? 503 : 200, json: server.failGet ? { message: '状态暂不可用' } : server.user === 'A' ? states.get(id) : initial(id) }) }
      const body = r.request().postDataJSON(); server.writes.push({ id, ...body })
      if (server.handler) return server.handler(r)
      const old = states.get(id)!
      if (old.revision !== body.expected_revision) return r.fulfill({ status: 409, json: { message: '发生冲突' } })
      const next = { ...old, ...(body.bookmarked !== undefined ? { bookmarked: body.bookmarked } : {}), ...(body.mastery !== undefined ? { mastery: body.mastery } : {}), revision: old.revision + 1 }
      states.set(id, next); return r.fulfill({ json: next })
    }
    if (path.endsWith('/points')) {
      if (server.failList) return r.fulfill({ status: 503, json: { message: '列表暂不可用' } })
      const matches = [...states.values()].filter(s => server.user === 'A' && (url.searchParams.get('filter') === 'bookmarked' ? s.bookmarked : s.mastery === 'needs_review'))
      const pageNumber = Math.min(Number(url.searchParams.get('page')) || 1, Math.max(1, Math.ceil(matches.length / 2)))
      return r.fulfill({ json: { items: matches.slice((pageNumber - 1) * 2, pageNumber * 2).map(s => ({ ...s, title: '同名条目', path: [`章节${s.point_id.slice(1)}`, '同名条目'] })), total: matches.length, page: pageNumber, page_size: 2 } })
    }
    if (path.includes('/review/points/')) {
      const id = path.split('/').at(-1)!, number = Number(id.slice(1))
      return r.fulfill({ json: { id, book_id: 'book', version: 'v1', title: `知识点${number}`, path: [`章节${number}`], source_start: 1, source_end: 1, previous_id: number > 1 ? `p${number-1}` : null, next_id: number < count ? `p${number+1}` : null, blocks: [{ id: 'b', type: 'paragraph', text: '只阅读不会自动改变掌握程度。', page: 1, bbox: [0, 0, 100, 100] }] } })
    }
    return r.abort()
  })
  return server
}

test('bookmarks and mastery are independent; private lists reflect confirmed membership', async ({ page }) => {
  const server = await setup(page)
  await page.goto('./#/review?point=p1')
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  expect(server.writes).toHaveLength(0)
  await page.getByRole('button', { name: '☆ 收藏知识点', exact: true }).click()
  await expect(page.getByRole('button', { name: /已收藏/ })).toBeVisible()
  expect(server.writes[0]).not.toHaveProperty('mastery')
  await page.getByLabel('掌握程度', { exact: true }).selectOption('needs_review')
  await expect.poll(() => server.states.get('p1')?.mastery).toBe('needs_review')
  expect(server.writes[1]).not.toHaveProperty('bookmarked')
  await page.getByRole('link', { name: '待复习', exact: true }).click()
  await expect(page.getByRole('button', { name: '同名条目', exact: true })).toBeVisible()
  await page.getByLabel('掌握程度', { exact: true }).selectOption('mastered')
  await expect(page.getByText('暂时没有待复习内容', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: '我的收藏', exact: true }).click()
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('mastered')
  await page.getByRole('button', { name: /取消收藏/ }).click()
  await expect(page.getByText('还没有收藏', { exact: true })).toBeVisible()
  expect(server.states.get('p1')?.mastery).toBe('mastered')
})

test('long lists keep paths, support failure retry, and clamp the final page after removal', async ({ page }) => {
  const server = await setup(page)
  for (const state of server.states.values()) state.bookmarked = true
  server.failList = true
  await page.goto('./#/review?book=book&list=bookmarked')
  await expect(page.getByRole('alert')).toHaveText('列表暂不可用')
  server.failList = false; await page.getByRole('button', { name: '重试列表' }).click()
  await expect(page.getByText('章节1', { exact: true })).toBeVisible()
  await expect(page.getByText('章节2', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一页列表' }).click()
  await expect(page.getByText('章节3', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /取消收藏/ }).click()
  await expect(page.getByText('第 1 / 1 页 · 2 项')).toBeVisible()
  await expect(page.getByRole('heading', { name: '我的收藏', exact: true })).toBeFocused()
  await page.getByRole('button', { name: '同名条目', exact: true }).nth(1).click()
  await expect(page).toHaveURL(/point=p2/)
  await expect(page.getByRole('heading', { name: '知识点2', exact: true })).toBeVisible()
})

test('pending saves disable controls, unknown results reread first, and conflicts require refresh', async ({ page }) => {
  const server = await setup(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.handler = async r => { await gate; server.states.set('p1', { ...initial('p1'), bookmarked: true, revision: 1 }); await r.abort() }
  await page.goto('./#/review?point=p1')
  await page.getByRole('button', { name: '☆ 收藏知识点', exact: true }).click()
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeDisabled()
  await expect(page.getByLabel('掌握程度', { exact: true })).toBeDisabled()
  expect(server.writes).toHaveLength(1)
  release()
  await expect(page.getByRole('button', { name: /已收藏/ })).toBeEnabled()
  expect(server.reads).toBe(2); expect(server.writes).toHaveLength(1)
  server.states.get('p1')!.revision = 2
  server.handler = null
  await page.getByLabel('掌握程度', { exact: true }).selectOption('mastered')
  await expect(page.getByText('其他设备已更新状态，请刷新状态后重新选择。')).toBeVisible()
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  await expect(page.getByLabel('掌握程度', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '重新读取状态' }).click()
  await expect(page.getByLabel('掌握程度', { exact: true })).toBeEnabled()
  await page.getByLabel('掌握程度', { exact: true }).selectOption('mastered')
  await expect.poll(() => server.states.get('p1')?.mastery).toBe('mastered')
})

test('failed confirmation read preserves confirmed values and blocks blind resubmission', async ({ page }) => {
  const server = await setup(page)
  await page.goto('./#/review?point=p1')
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeEnabled()
  server.handler = r => r.fulfill({ status: 503, json: { message: '未知结果' } }); server.failGet = true
  await page.getByRole('button', { name: '☆ 收藏知识点', exact: true }).click()
  await expect(page.getByText('状态暂不可用', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeDisabled()
  expect(server.writes).toHaveLength(1)
  server.failGet = false; server.handler = null
  await page.getByRole('button', { name: '重新读取状态' }).click()
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeEnabled()
})

test('late state save cannot appear on a different knowledge point or another account', async ({ page }) => {
  const server = await setup(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.handler = async r => { await gate; await r.fulfill({ json: { ...initial('p1'), bookmarked: true, mastery: 'mastered', revision: 1 } }) }
  await page.goto('./#/review?point=p1')
  await page.getByRole('button', { name: '☆ 收藏知识点', exact: true }).click()
  await page.getByRole('button', { name: '下一篇 →' }).click()
  await expect(page.getByRole('heading', { name: '知识点2', exact: true })).toBeVisible()
  release(); await page.waitForTimeout(100)
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('B@example.com'); await page.getByLabel('密码', { exact: true }).fill('example password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.goto('./#/review?book=book&list=bookmarked')
  await expect(page.getByText('还没有收藏', { exact: true })).toBeVisible()
})

test('late private state read after switching account cannot populate the new reader', async ({ page }) => {
  await setup(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let held = false
  await page.route(`${api}/me/review/points/p1/state`, async r => {
    if (r.request().headers().authorization === 'Bearer A') {
      held = true; await gate
      return r.fulfill({ json: { ...initial('p1'), bookmarked: true, mastery: 'mastered', revision: 7 } })
    }
    return r.fallback()
  })
  await page.goto('./#/review?point=p1')
  await expect.poll(() => held).toBe(true)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('B@example.com'); await page.getByLabel('密码', { exact: true }).fill('example password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.goto('./#/review?point=p1')
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  release(); await page.waitForTimeout(150)
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeEnabled()
})
