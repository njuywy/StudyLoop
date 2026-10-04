import type { Page, Route } from '@playwright/test'
import { test, expect } from './fixtures'

const api = 'https://124.220.147.193/api/v1'
const caseId = 'b10a696a1c6836149ed166d9e596741b'
const redId = '53690650542c40c55974bfca1ce256f9'
const books = [
  { id: redId, title: '红宝书', version: 'red-v1', point_count: 1, page_count: 232, coverage_label: '已上线首章（部分章节）' },
  { id: caseId, title: '案例冲刺宝典', version: 'case-v1', point_count: 1, page_count: 305, coverage_label: '全书内容已收录' },
]
const pointId = (id: string) => id === caseId ? 'case-point' : 'red-point'
async function setup(page: Page) {
  const server = { fail: false, empty: false, user: 'A', writes: [] as { book: string; body: any }[], positions: new Map<string, any>(), states: new Map<string, any>(), hold: null as null | ((route: Route) => Promise<void>) }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('seeded')) {
      sessionStorage.setItem('studyloop_session', 'session-A')
      sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 3600000).toISOString())
      sessionStorage.setItem('seeded', '1')
    }
  })
  await page.route(`${api}/**`, async r => {
    const url = new URL(r.request().url()), path = url.pathname.replace('/api/v1', '')
    const identity = () => ({ id: server.user, nickname: `读者${server.user}`, email: `${server.user}@example.com`, role: 'user' })
    if (path === '/health') return r.fulfill({ json: { status: 'ok', database: 'ok' } })
    if (path === '/me') return r.fulfill({ json: identity() })
    if (path === '/me/avatar') return r.fulfill({ status: 404, json: {} })
    if (path === '/auth/logout') return r.fulfill({ json: {} })
    if (path === '/auth/login') {
      server.user = r.request().postDataJSON().email[0]
      return r.fulfill({ json: { token: `session-${server.user}`, expires_at: new Date(Date.now() + 3600000).toISOString(), user: identity() } })
    }
    if (path === '/review/books') return r.fulfill({ status: server.fail ? 503 : 200, json: server.fail ? { message: '书架加载失败' } : { items: server.empty ? [] : books } })
    const id = path.match(/\/books\/([^/]+)/)?.[1]
    const book = books.find(b => b.id === id)
    if (path.endsWith('/toc')) return r.fulfill({ status: book ? 200 : 404, json: book ? { book, items: [{ id: pointId(id!), point_id: pointId(id!), parent_id: null, level: 1, title: `${book.title}知识点`, path: [`${book.title}知识点`], page: 8 }] } : { message: '指定资料不存在' } })
    if (path.endsWith('/position') && book) {
      if (server.hold) await server.hold(r)
      const key = `${server.user}:${id}`
      if (r.request().method() === 'GET') return r.fulfill({ json: { position: server.positions.get(key) || null } })
      const body = r.request().postDataJSON(); server.writes.push({ book: id!, body })
      expect(body.point_id).toBe(pointId(id!)); expect(body.content_version).toBe(book.version)
      const old = server.positions.get(key)
      if ((old?.revision || 0) !== body.expected_revision) return r.fulfill({ status: 409, json: { position: old } })
      const position = { ...body, revision: body.expected_revision + 1, updated_at: '2026-10-05T00:00:00Z' }
      server.positions.set(key, position); return r.fulfill({ json: { position } })
    }
    const p = path.match(/\/points\/([^/]+)/)?.[1]
    if (path.endsWith('/state') && p) {
      const key = `${server.user}:${p}`
      const state = server.states.get(key) || { point_id: p, bookmarked: false, mastery: 'unlearned', revision: 0 }
      if (r.request().method() === 'PATCH') {
        const body = r.request().postDataJSON()
        if (body.bookmarked !== undefined) state.bookmarked = body.bookmarked
        if (body.mastery !== undefined) state.mastery = body.mastery
        state.revision++; server.states.set(key, state)
      }
      return r.fulfill({ json: state })
    }
    if (path.endsWith('/points') && book) {
      const state = server.states.get(`${server.user}:${pointId(book.id)}`)
      const matches = state && (url.searchParams.get('filter') === 'bookmarked' ? state.bookmarked : state.mastery === 'needs_review')
      return r.fulfill({ json: { items: matches ? [{ ...state, title: `${book.title}知识点`, path: [book.title, `${book.title}知识点`] }] : [], total: matches ? 1 : 0, page: 1, page_size: 20 } })
    }
    if (path.startsWith('/review/points/')) {
      const owner = books.find(b => pointId(b.id) === p)
      return r.fulfill({ status: owner ? 200 : 404, json: owner ? { id: p, book_id: owner.id, version: owner.version, title: `${owner.title}知识点`, path: [owner.title, `${owner.title}知识点`], source_start: 8, source_end: 8, previous_id: null, next_id: null,
        blocks: Array.from({ length: 24 }, (_, i) => ({ id: `${p}-b${i}`, type: 'paragraph', text: `${owner.title}第${i}段：${'每份资料保留各自的阅读位置。'.repeat(12)}`, page: 8, bbox: [0, i * 20, 500, i * 20 + 20] })) } : { message: '知识点不存在' } })
    }
    return r.abort()
  })
  return server
}
async function enter(page: Page, title: string) {
  await page.getByRole('navigation', { name: '选择复习知识库' }).getByRole('link', { name: new RegExp(title) }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
}

test('shelf selects by ID, handles failure and empty state, and returns without auto-opening', async ({ page }) => {
  const server = await setup(page); server.fail = true
  await page.goto('./#/review')
  await expect(page.getByRole('alert')).toHaveText('书架加载失败')
  server.fail = false; server.empty = true
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByText('资料正在整理')).toBeVisible()
  server.empty = false; await page.getByRole('button', { name: '刷新知识库' }).click()
  await expect(page.getByRole('navigation', { name: '选择复习知识库' }).getByRole('link')).toHaveCount(2)
  await enter(page, '案例冲刺宝典')
  await expect(page).toHaveURL(new RegExp(`book=${caseId}`))
  await page.getByRole('link', { name: '返回知识库选择' }).click()
  await enter(page, '红宝书')
  await expect(page).toHaveURL(new RegExp(`book=${redId}`))
  await page.goBack(); await expect(page.getByRole('navigation', { name: '选择复习知识库' })).toBeVisible()
  await page.goForward(); await expect(page.getByRole('heading', { name: '红宝书', exact: true })).toBeVisible()
})

test('legacy point and list links resolve the correct book; invalid targets never fall back', async ({ page }) => {
  await setup(page)
  await page.goto('./#/review?point=case-point')
  await expect(page.getByRole('heading', { name: '案例冲刺宝典知识点', exact: true })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`book=${caseId}`))
  await page.goto('./#/review?list=bookmarked')
  await expect(page.getByText('还没有收藏')).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`book=${caseId}`))
  await page.goto(`./#/review?book=${redId}&point=case-point`)
  await expect(page.getByRole('alert')).toContainText('知识点与当前资料不匹配')
  await page.goto('./#/review?book=missing')
  await expect(page.getByRole('alert')).toHaveText('指定资料不存在')
  await page.getByRole('link', { name: '返回知识库选择' }).click()
  await enter(page, '红宝书'); await page.getByRole('button', { name: '开始阅读' }).click()
  await page.reload(); await expect(page.getByRole('heading', { name: '红宝书知识点', exact: true })).toBeVisible()
})

test('two books retain independent locations, favorites and mastery through switching', async ({ page }) => {
  const server = await setup(page)
  for (const book of books) {
    await page.goto('./#/review'); await enter(page, book.title)
    await page.getByRole('button', { name: '开始阅读' }).click()
    await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '☆ 收藏知识点', exact: true }).click()
    await page.getByLabel('掌握程度', { exact: true }).selectOption(book.id === redId ? 'needs_review' : 'mastered')
    const block = `${pointId(book.id)}-b10`
    await page.evaluate(id => { const e = document.getElementById(`block-${id}`)!; window.scrollTo(0, scrollY + e.getBoundingClientRect().top - 80) }, block)
    await expect.poll(() => server.positions.get(`A:${book.id}`)?.block_id).toBe(block)
  }
  for (const book of books) {
    await page.goto('./#/review'); await enter(page, book.title)
    await page.getByRole('button', { name: '继续上次阅读' }).click()
    await expect(page.getByRole('heading', { name: `${book.title}知识点`, exact: true })).toBeAttached()
    await expect.poll(() => page.evaluate(id => Math.abs(document.getElementById(`block-${id}-b10`)!.getBoundingClientRect().top - 80), pointId(book.id))).toBeLessThan(5)
    await page.getByRole('link', { name: '我的收藏', exact: true }).click()
    await expect(page.getByRole('button', { name: `${book.title}知识点`, exact: true })).toBeVisible()
    await page.getByRole('link', { name: '待复习', exact: true }).click()
    if (book.id === redId) await expect(page.getByRole('button', { name: '红宝书知识点', exact: true })).toBeVisible()
    else await expect(page.getByText('暂时没有待复习内容')).toBeVisible()
  }
})

test('pending old-book saves and conflict decisions cannot follow a new book', async ({ page }) => {
  const server = await setup(page)
  await page.goto(`./#/review?book=${caseId}&point=case-point`)
  await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let pending = false
  server.hold = async r => { if (r.request().method() === 'PUT' && r.request().url().includes(caseId)) { pending = true; await gate } }
  await page.locator('#block-case-point-b12').scrollIntoViewIfNeeded()
  await expect.poll(() => pending).toBe(true)
  await page.evaluate(id => { window.location.hash = `/review?book=${id}&point=red-point` }, redId)
  await expect(page.getByText('阅读位置已同步', { exact: true })).toBeVisible()
  release(); await expect.poll(() => server.writes.filter(w => w.book === caseId).length).toBe(2)
  await expect(page.getByRole('heading', { name: '红宝书知识点', exact: true })).toBeVisible()
  expect(server.positions.get(`A:${redId}`).point_id).toBe('red-point')
  await page.getByRole('link', { name: '返回知识库选择' }).click()
  await expect(page.getByText('阅读位置已同步', { exact: true })).toHaveCount(0)
  expect(server.writes.every(w => w.body.point_id === pointId(w.book))).toBe(true)
  // The old request's persisted operation is now stale. Its explicit conflict
  // resolution must also stay with that book if the reader moves on meanwhile.
  server.positions.get(`A:${caseId}`).revision = 9
  await enter(page, '案例冲刺宝典')
  await expect(page.getByText('阅读位置有冲突，请选择')).toBeVisible()
  let finish!: () => void
  const resolving = new Promise<void>(resolve => { finish = resolve })
  let resolvingStarted = false
  server.hold = async r => { if (r.request().method() === 'PUT' && r.request().url().includes(caseId)) { resolvingStarted = true; await resolving } }
  await page.getByRole('button', { name: '以本地位置继续并保存' }).click()
  await expect.poll(() => resolvingStarted).toBe(true)
  await page.getByRole('link', { name: '返回知识库选择' }).click()
  await enter(page, '红宝书')
  finish(); await expect.poll(() => server.positions.get(`A:${caseId}`).revision).toBe(10)
  await expect(page).toHaveURL(new RegExp(`book=${redId}$`))
  await expect(page.getByRole('heading', { name: '从一个知识点开始' })).toBeVisible()
})

test('an old book position read cannot populate a newly selected library', async ({ page }) => {
  const server = await setup(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let requested = false
  server.hold = async r => { if (r.request().method() === 'GET' && r.request().url().includes(caseId)) { requested = true; await gate } }
  await page.goto(`./#/review?book=${caseId}`)
  await expect.poll(() => requested).toBe(true)
  await page.getByRole('link', { name: '返回知识库选择' }).click()
  await enter(page, '红宝书')
  release()
  await expect(page.getByText('尚无阅读记录', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '案例冲刺宝典', exact: true })).toHaveCount(0)
})

test('login returns to a selected book and another account cannot inherit its private state', async ({ page }) => {
  const server = await setup(page)
  server.states.set('A:red-point', { point_id: 'red-point', bookmarked: true, mastery: 'needs_review', revision: 2 })
  await page.goto(`./#/review?book=${redId}&point=red-point`)
  await expect(page.getByRole('button', { name: /已收藏/ })).toBeVisible()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL(/#\/login$/)
  await page.goto(`./#/review?book=${redId}&point=red-point`)
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await page.getByLabel('邮箱', { exact: true }).fill('B@example.com')
  await page.getByLabel('密码', { exact: true }).fill('different-passphrase')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`book=${redId}&point=red-point`))
  await expect(page.getByRole('button', { name: '☆ 收藏知识点', exact: true })).toBeVisible()
  await expect(page.getByLabel('掌握程度', { exact: true })).toHaveValue('unlearned')
  expect(server.states.get('A:red-point').mastery).toBe('needs_review')
})
