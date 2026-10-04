<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { loadProfile, request, token } from '../session'
import { useReadingPosition, locationAtViewport, scrollToLocation, type ReadingLocation } from '../readingPosition'
import type { KnowledgePoint, ReviewBook, TocNode } from '../review'
import ReviewContents from './ReviewContents.vue'
import ReviewImage from './ReviewImage.vue'

const route = useRoute()
const router = useRouter()
const books = ref<ReviewBook[]>([])
const book = ref<ReviewBook | null>(null)
const nodes = ref<TocNode[]>([])
const point = ref<KnowledgePoint | null>(null)
const loading = ref(false)
const error = ref('')
const directory = ref<HTMLDialogElement>()
const viewer = ref<HTMLDialogElement>()
const viewerPath = ref('')
const viewerTitle = ref('')
const sourcePage = ref(0)
const sourceMode = ref(false)
const title = ref<HTMLElement>()
const currentId = computed(() => typeof route.query.point === 'string' ? route.query.point : '')
let revision = 0
const position = useReadingPosition()
const { remote, draft, conflict, readError, storageError, saveError, saving, status, continuation } = position
const positionNotice = ref('')
let readingActive = false
let restoreTarget: ReadingLocation | null = null
let lastLocation: ReadingLocation | null = null
let resizeFrame = 0
function capturePosition() {
  if (!readingActive || !point.value || viewer.value?.open || directory.value?.open) return
  const location = locationAtViewport(point.value)
  if (location) { lastLocation = location; position.capture(location) }
}
function suspendReading() {
  readingActive = false; void position.flush()
}
async function activateReading(current: number) {
  await nextTick(); await document.fonts.ready
  await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  if (current !== revision || !point.value) return
  const target = restoreTarget; restoreTarget = null
  window.scrollTo({ top: 0, behavior: 'instant' })
  if (target && (target.content_version !== point.value.version || !scrollToLocation(target))) positionNotice.value = '原来的段落位置已失效，已返回该知识点开头。'
  await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  if (current !== revision || !point.value) return
  readingActive = true
  lastLocation = target && !positionNotice.value ? target : locationAtViewport(point.value)
  // Restoring history is not a new reading action; wait for actual reading.
  if (!target && !positionNotice.value) capturePosition()
}
async function continueReading(location = continuation.value) {
  if (!location) return
  positionNotice.value = ''
  if (!nodes.value.some(n => n.point_id === location.point_id)) {
    suspendReading(); restoreTarget = null; positionNotice.value = '上次知识点暂不可用，请从目录重新选择。'
    await router.push({ path: '/review', query: { book: book.value?.id } }); return
  }
  await select(location.point_id, location)
}
async function chooseServer() {
  readingActive = false
  const location = position.useServer()
  if (location) await continueReading(location)
}
async function chooseLocal() {
  readingActive = false
  const location = draft.value?.candidate
  await position.useLocal()
  if (!conflict.value && location) await continueReading(location)
}
function onVisibility() { if (document.hidden) void position.flush() }
function onResize() {
  if (!readingActive || !lastLocation) return
  const location = lastLocation
  const current = revision
  readingActive = false; cancelAnimationFrame(resizeFrame)
  resizeFrame = requestAnimationFrame(() => {
    if (current !== revision) return
    if (point.value?.id === location.point_id) scrollToLocation(location)
    requestAnimationFrame(() => { if (current === revision) readingActive = true })
  })
}
onMounted(() => {
  window.addEventListener('scroll', capturePosition, { passive: true })
  window.addEventListener('resize', onResize)
  window.addEventListener('online', position.connectionChanged)
  window.addEventListener('offline', position.connectionChanged)
  document.addEventListener('visibilitychange', onVisibility)
})

function clear() {
  readingActive = false; restoreTarget = null; lastLocation = null; position.clear()
  revision++; books.value = []; book.value = null; nodes.value = []; point.value = null
  closeViewer(); directory.value?.close()
}
function closeViewer() { viewer.value?.close(); viewerPath.value = ''; sourceMode.value = false }
function sourcePath(page: number) { return `/review/books/${book.value?.id}/source/pages/${page}` }
function showSource(page: number) {
  sourceMode.value = true; sourcePage.value = page; viewerTitle.value = `PDF 原文 · 第 ${page} 页`
  viewerPath.value = sourcePath(page)
  if (!viewer.value?.open) viewer.value?.showModal()
}
function showFigure(assetId: string, alt: string) {
  sourceMode.value = false; viewerTitle.value = alt
  viewerPath.value = `/review/books/${book.value?.id}/assets/${assetId}`
  viewer.value?.showModal()
}
async function select(id: string, restore: ReadingLocation | null = null) {
  suspendReading(); restoreTarget = restore; positionNotice.value = ''
  directory.value?.close()
  if (id === currentId.value) { await activateReading(revision); return }
  await router.push({ path: '/review', query: { book: book.value?.id, point: id } })
}
async function refresh() {
  suspendReading()
  const current = ++revision
  loading.value = true; error.value = ''; point.value = null; closeViewer()
  const identity = await loadProfile()
  if (current !== revision) return
  if (!identity.ok) {
    loading.value = false
    if (identity.status !== -1 && identity.status !== 401) error.value = identity.message
    return
  }
  const listing = await request<{ items: ReviewBook[] }>('/review/books')
  if (current !== revision) return
  if (!listing.ok) { loading.value = false; error.value = listing.message; return }
  books.value = listing.data.items
  const bookId = typeof route.query.book === 'string' ? route.query.book : books.value[0]?.id
  if (!bookId) { loading.value = false; return }
  const result = await request<{ book: ReviewBook; items: TocNode[] }>(`/review/books/${encodeURIComponent(bookId)}/toc`)
  if (current !== revision) return
  if (!result.ok) { loading.value = false; error.value = result.message; return }
  book.value = result.data.book; nodes.value = result.data.items
  await position.initialize(identity.data.id, book.value)
  if (current !== revision) return
  if (currentId.value) {
    const content = await request<KnowledgePoint>(`/review/points/${encodeURIComponent(currentId.value)}`)
    if (current !== revision) return
    if (!content.ok) {
      if (restoreTarget && content.status === 404) {
        restoreTarget = null; positionNotice.value = '上次知识点暂不可用，请从目录重新选择。'
      } else error.value = content.message
    }
    else if (content.data.book_id !== bookId) error.value = '知识点与当前资料不匹配，请返回目录。'
    else point.value = content.data
  }
  loading.value = false
  await nextTick()
  if (current === revision && currentId.value) {
    title.value?.focus({ preventScroll: true })
    await activateReading(current)
  }
}
watch(() => route.fullPath, refresh, { immediate: true })
watch(token, () => { clear(); if (token.value) void refresh() })
onBeforeUnmount(() => {
  suspendReading(); clear(); cancelAnimationFrame(resizeFrame)
  window.removeEventListener('scroll', capturePosition)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('online', position.connectionChanged)
  window.removeEventListener('offline', position.connectionChanged)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <section class="review-shell section-width">
    <header class="review-intro"><div><span class="section-kicker">一次回顾，一点收获</span><h1>在线复习</h1><p>沿着章节，重新连接你的知识。</p></div><span class="reader-label">知识点阅读</span></header>
    <div v-if="loading" class="reading-state" role="status">正在读取复习资料…</div>
    <div v-else-if="error" class="reading-state"><p role="alert">{{ error }}</p><button class="small-button" @click="refresh">重试</button><RouterLink class="text-link" to="/review">返回资料目录</RouterLink></div>
    <div v-else-if="!book" class="reading-state"><h2>资料正在整理</h2><p>暂时没有可阅读的资料，请稍后再来。</p></div>
    <template v-else>
      <div class="book-strip"><div><h2>{{ book.title }}</h2><p>{{ book.coverage_label }} · {{ book.point_count }} 个知识点</p></div><button class="small-button mobile-contents" @click="directory?.showModal()">章节目录</button></div>
      <div class="position-panel" aria-label="阅读位置">
        <div class="position-actions"><span role="status">{{ status }}</span><button v-if="continuation" class="small-button" @click="continueReading()">继续上次阅读</button><button v-if="readError" class="small-button" @click="position.reload">重试读取位置</button><button v-else-if="saveError && !conflict" class="small-button" :disabled="saving" @click="position.flush">重试保存位置</button></div>
        <p v-if="storageError" role="alert">{{ storageError }}</p><p v-if="positionNotice" role="status">{{ positionNotice }}</p>
        <div v-if="conflict" class="position-conflict" role="alert"><p>其他设备已更新阅读位置。选择前不会覆盖任一记录。</p><p>服务器：{{ nodes.find(n => n.point_id === remote?.point_id)?.title || '暂无记录' }}</p><p>本地：{{ nodes.find(n => n.point_id === draft?.candidate.point_id)?.title || '原知识点暂不可用' }}</p><div class="position-actions"><button class="small-button" :disabled="!!readError" @click="chooseServer">使用服务器位置</button><button class="small-button" :disabled="saving || !!readError" @click="chooseLocal">以本地位置继续并保存</button></div></div>
      </div>
      <div class="reading-layout">
        <aside class="desktop-contents" aria-label="章节目录"><h3>章节目录</h3><ReviewContents :nodes="nodes" :current="point?.id" @select="select" /></aside>
        <article class="reading-paper">
          <template v-if="point">
            <p class="reading-path">{{ point.path.slice(0, -1).join(' / ') }}</p>
            <h2 ref="title" tabindex="-1" class="point-title">{{ point.title }}</h2>
            <div class="reading-tools"><span>原文 {{ point.source_start }}<template v-if="point.source_end !== point.source_start">–{{ point.source_end }}</template> 页</span><button class="small-button" @click="showSource(point.source_start)">查看 PDF 原文</button></div>
            <div class="reading-body">
              <template v-for="block in point.blocks" :key="block.id">
                <p v-if="block.type === 'paragraph'" :id="`block-${block.id}`" :data-block-id="block.id">{{ block.text }}</p>
                <figure v-else :id="`block-${block.id}`" :data-block-id="block.id">
                  <ReviewImage :path="`/review/books/${book.id}/assets/${block.asset_id}`" :alt="block.alt || '知识点图表'" :width="block.width" :height="block.height" />
                  <figcaption><span>{{ block.alt }}</span><button class="text-link" @click="showFigure(block.asset_id!, block.alt || '知识点图表')">放大图表</button></figcaption>
                </figure>
              </template>
            </div>
            <nav class="point-pagination" aria-label="知识点翻篇"><button class="small-button" :disabled="!point.previous_id" @click="point.previous_id && select(point.previous_id)">← 上一篇</button><button class="small-button" :disabled="!point.next_id" @click="point.next_id && select(point.next_id)">下一篇 →</button></nav>
          </template>
          <div v-else class="reading-welcome"><span aria-hidden="true" class="welcome-symbol">↺</span><h2>从一个知识点开始</h2><p>选择章节，阅读要点与例题。遇到图表可以放大，也可以随时对照 PDF 原文。</p><button v-if="nodes.some(n => n.point_id)" class="primary-button" @click="select(nodes.find(n => n.point_id)!.point_id!)">开始阅读 →</button></div>
        </article>
      </div>
    </template>
    <dialog ref="directory" class="directory-dialog"><div class="dialog-bar"><h2>章节目录</h2><button class="small-button" autofocus @click="directory?.close()">关闭目录</button></div><ReviewContents :nodes="nodes" :current="point?.id" @select="select" /></dialog>
    <dialog ref="viewer" class="source-dialog" @close="viewerPath = ''; sourceMode = false">
      <div class="dialog-bar"><h2>{{ viewerTitle }}</h2><button class="small-button" autofocus @click="closeViewer">关闭对照</button></div>
      <div v-if="sourceMode && point" class="source-controls"><button class="small-button" :disabled="sourcePage <= point.source_start" @click="showSource(sourcePage - 1)">上一页</button><span>{{ sourcePage }} / {{ point.source_end }}</span><button class="small-button" :disabled="sourcePage >= point.source_end" @click="showSource(sourcePage + 1)">下一页</button></div>
      <p class="zoom-hint">可在图像区域横向滚动查看细节。</p>
      <div class="source-scroll"><ReviewImage v-if="viewerPath" :path="viewerPath" :alt="viewerTitle" /></div>
    </dialog>
  </section>
</template>

<style scoped>
.position-panel { margin: -6px 0 22px; padding: 16px 20px; border: 1px solid #dce4d8; border-radius: 12px; background: #f7f8f0; font-size: 13px; line-height: 1.8; }
.position-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.position-actions > span { margin-right: auto; }
.position-panel p { margin: 8px 0; }
.position-conflict { border-top: 1px solid #dce4d8; margin-top: 12px; padding-top: 8px; }
.review-shell { padding-top: 36px; padding-bottom: 60px; }
.review-intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 26px; }
.review-intro h1 { font-size: clamp(27px, 4vw, 36px); margin: 8px 0; }
.review-intro p { color: #67725f; margin: 0; }
.reader-label { border-radius: 100px; padding: 9px 15px; background: #e7eddc; color: #53684b; font-size: 13px; white-space: nowrap; }
.book-strip { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 21px 25px; background: #e8eedf; border: 1px solid #d7e0d0; border-radius: 16px; margin-bottom: 22px; }
.book-strip h2 { font-size: 20px; margin: 0 0 8px; }
.book-strip p { font-size: 13px; line-height: 1.8; color: #62705a; margin: 0; }
.reading-layout { display: grid; grid-template-columns: 270px minmax(0, 1fr); gap: 24px; align-items: start; }
.desktop-contents { position: sticky; top: 18px; max-height: calc(100vh - 36px); overflow: auto; padding: 15px 12px; border: 1px solid #dce4d8; background: #f7f8f0; border-radius: 14px; }
.desktop-contents h3 { font-size: 15px; padding: 0 8px 10px; margin: 0; }
.reading-paper, .reading-state { padding: clamp(20px, 3vw, 42px); background: #fffefa; border: 1px solid #e0e4d9; border-radius: 16px; min-width: 0; }
.reading-path { font-size: 12px; color: #737d6b; line-height: 1.8; overflow-wrap: anywhere; }
.point-title { font-size: clamp(20px, 2.5vw, 28px); line-height: 1.7; margin: 12px 0 20px; overflow-wrap: anywhere; }
.point-title:focus { outline: none; }
.reading-tools { display: flex; align-items: center; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding-bottom: 24px; border-bottom: 1px solid #e6e9df; font-size: 12px; color: #76806e; }
.reading-body { padding: 15px 0 28px; font-size: 16px; line-height: 2.1; color: #35432f; overflow-wrap: anywhere; }
.reading-body p { margin: 10px 0; }
figure { margin: 26px 0; padding: 10px; background: white; border: 1px solid #e5e8df; border-radius: 10px; }
figcaption { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 12px; color: #6b7664; padding-top: 10px; }
figcaption button { border: 0; background: transparent; cursor: pointer; }
.point-pagination { display: flex; justify-content: space-between; border-top: 1px solid #e6e9df; padding-top: 24px; gap: 12px; }
.reading-welcome { padding: 48px 0; text-align: center; }
.reading-welcome h2 { font-size: 24px; }
.reading-welcome p { max-width: 420px; margin: 20px auto 30px; color: #718069; line-height: 2; }
.welcome-symbol { display: block; font-size: 70px; color: #789764; }
dialog { border: 1px solid #d7dfce; border-radius: 16px; padding: 20px; color: #35432f; background: #fffefa; max-height: 88vh; }
dialog::backdrop { background: #20301899; }
.dialog-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.dialog-bar h2 { font-size: 18px; margin: 0; }
.dialog-bar button { flex-shrink: 0; }
.directory-dialog { width: min(380px, calc(100vw - 28px)); }
.source-dialog { width: min(1000px, calc(100vw - 28px)); }
.source-scroll { overflow: auto; max-height: 63vh; }
.source-scroll :deep(.private-image) { min-width: 850px; }
.source-controls { display: flex; justify-content: center; align-items: center; gap: 16px; }
.zoom-hint { font-size: 12px; color: #75826e; }
.mobile-contents { display: none; }
@media (max-width: 900px) { .reading-layout { grid-template-columns: 1fr; }.desktop-contents { display: none; }.mobile-contents { display: block; flex-shrink: 0; }.reader-label { display: none; }.book-strip { padding: 18px; }.reading-body { font-size: 16px; } }
</style>
