import { test, expect } from './fixtures'
const api = 'https://124.220.147.193/api/v1'
const book = { id: 'book', title: '测试复习资料', version: 'v1', point_count: 2, page_count: 3, coverage_label: '已上线部分章节' }
const user = { id: 'reader', nickname: '阅读者', email: 'reader@example.com', role: 'user' }
const nodes = [
  { id: 'root', title: '第一章', parent_id: null, point_id: null, level: 1, path: ['第一章'], page: 1 },
  { id: 'p1', title: '第一个知识点', parent_id: 'root', point_id: 'p1', level: 2, path: ['第一章', '第一个知识点'], page: 1 },
  { id: 'p2', title: '第二个知识点', parent_id: 'root', point_id: 'p2', level: 2, path: ['第一章', '第二个知识点'], page: 3 },
]
const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64')

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('review_seeded')) {
      sessionStorage.setItem('studyloop_session', 'reader-session')
      sessionStorage.setItem('studyloop_session_expires_at', new Date(Date.now() + 3600000).toISOString())
      sessionStorage.setItem('review_seeded', 'yes')
    }
  })
  await page.route(`${api}/me`, r => r.fulfill({ json: user }))
  await page.route(`${api}/health`, r => r.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.route(`${api}/review/**`, r => {
    expect(r.request().headers()['authorization']).toBe('Bearer reader-session')
    const path = new URL(r.request().url()).pathname
    if (path.endsWith('/books')) return r.fulfill({ json: { items: [book] } })
    if (path.endsWith('/toc')) return r.fulfill({ json: { book, items: nodes } })
    if (path.includes('/assets/') || path.includes('/source/pages/')) return r.fulfill({ contentType: 'image/png', body: pixel })
    const id = path.split('/').at(-1)!
    const node = nodes.find(n => n.id === id)
    if (!node) return r.fulfill({ status: 404, json: { message: '知识点不存在' } })
    return r.fulfill({ json: {
      id, book_id: 'book', version: 'v1', title: node.title, path: node.path,
      source_start: id === 'p1' ? 1 : 3, source_end: id === 'p1' ? 2 : 3,
      previous_id: id === 'p1' ? null : 'p1', next_id: id === 'p1' ? 'p2' : null,
      blocks: [{ id: `text-${id}`, type: 'paragraph', text: `正文 ${id}`, page: 1, bbox: [54, 100, 540, 130] },
        { id: `figure-${id}`, type: 'figure', asset_id: 'image.jpg', alt: '示例图表', width: 600, height: 200, page: 1, bbox: [54, 140, 540, 300] }],
    } })
  })
})

test('knowledge deep link, source comparison, figure dialog and chapter boundaries', async ({ page }) => {
  await page.goto('./#/review?book=book&point=p1')
  await expect(page.getByRole('heading', { name: '第一个知识点', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '← 上一篇' })).toBeDisabled()
  await page.getByRole('button', { name: '查看 PDF 原文' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading')).toHaveText('PDF 原文 · 第 1 页')
  await dialog.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(dialog.getByRole('heading')).toHaveText('PDF 原文 · 第 2 页')
  await expect(dialog.getByRole('button', { name: '下一页', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '查看 PDF 原文' })).toBeFocused()
  await page.getByRole('button', { name: '放大图表' }).click()
  await expect(dialog.getByRole('img')).toBeVisible()
  await dialog.getByRole('button', { name: '关闭对照' }).click()
  await page.getByRole('button', { name: '下一篇 →' }).click()
  await expect(page.getByRole('heading', { name: '第二个知识点', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下一篇 →' })).toBeDisabled()
  await page.reload()
  await expect(page.getByText('正文 p2', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('picture failure can retry without discarding text; 401 clears private content', async ({ page }) => {
  let fail = true
  await page.route(`${api}/review/books/book/assets/**`, r => fail ? r.fulfill({ status: 503, json: { message: '图片暂不可用' } }) : r.fulfill({ contentType: 'image/png', body: pixel }))
  await page.goto('./#/review?book=book&point=p1')
  await expect(page.getByRole('alert')).toContainText('图片暂不可用')
  await expect(page.getByText('正文 p1', { exact: true })).toBeVisible()
  fail = false
  await page.getByRole('button', { name: '重试图片' }).click()
  await expect(page.getByRole('img', { name: '示例图表' })).toBeVisible()
  await page.route(`${api}/review/points/p2`, r => r.fulfill({ status: 401, json: { message: '登录已失效' } }))
  await page.getByRole('button', { name: '下一篇 →' }).click()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByText('正文 p1', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('studyloop_session'))).toBeNull()
})

test('late content response after logout cannot restore private reader', async ({ page }) => {
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let requested = false
  await page.route(`${api}/review/points/p1`, async r => {
    requested = true; await held
    await r.fulfill({ json: { id: 'p1', title: '迟到的私有内容', book_id: 'book', blocks: [] } })
  })
  await page.route(`${api}/auth/logout`, r => r.fulfill({ json: { code: 'LOGGED_OUT' } }))
  await page.goto('./#/review?book=book&point=p1')
  await expect.poll(() => requested).toBe(true)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  release()
  await expect(page.getByRole('heading', { name: '登录 StudyLoop' })).toBeVisible()
  await expect(page.getByText('迟到的私有内容')).toHaveCount(0)
})
