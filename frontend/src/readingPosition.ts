import { computed, ref } from 'vue'
import { request } from './session'
import type { KnowledgePoint, ReviewBook } from './review'

export type ReadingLocation = { point_id: string; block_id: string; offset: number; content_version: string }
export type ReadingPosition = ReadingLocation & { revision: number; updated_at: string }
type Write = ReadingLocation & { expected_revision: number; operation_id: string }
type Draft = { candidate: ReadingLocation; baseRevision: number | null; operation: Write | null }
const samePlace = (a: ReadingLocation, b: ReadingLocation) => a.point_id === b.point_id && a.block_id === b.block_id && a.offset === b.offset && a.content_version === b.content_version

// One coordinator per reader. Pending operations survive navigation and unknown
// network results; only a verified account may read its own local draft.
export function useReadingPosition() {
  const remote = ref<ReadingPosition | null>(null)
  const draft = ref<Draft | null>(null)
  const conflict = ref(false)
  const readError = ref('')
  const storageError = ref('')
  const saveError = ref('')
  const saving = ref(false)
  const loaded = ref(false)
  const online = ref(navigator.onLine)
  let key = '', path = '', version = '', epoch = 0
  let pauseTimer: ReturnType<typeof setTimeout> | undefined
  let maxTimer: ReturnType<typeof setTimeout> | undefined
  const status = computed(() => conflict.value ? '阅读位置有冲突，请选择' : readError.value ? '上次位置读取失败，自动同步已暂停' : saving.value ? '正在保存阅读位置…' : draft.value ? !online.value ? '离线，位置尚未同步' : saveError.value || '位置待同步' : remote.value ? '阅读位置已同步' : '尚无阅读记录')
  const continuation = computed(() => draft.value?.candidate || remote.value)
  function cancelTimers() { clearTimeout(pauseTimer); clearTimeout(maxTimer); pauseTimer = maxTimer = undefined }
  function persist() {
    if (!key) return
    try {
      if (draft.value) localStorage.setItem(key, JSON.stringify(draft.value))
      else localStorage.removeItem(key)
      storageError.value = ''
    } catch { storageError.value = '浏览器本地暂存不可用；未同步的位置在关闭后可能丢失。' }
  }
  function clear() {
    epoch++; cancelTimers(); key = ''; path = ''; version = ''
    remote.value = null; draft.value = null; conflict.value = false
    loaded.value = false; saving.value = false; readError.value = ''; saveError.value = ''; storageError.value = ''
  }
  async function initialize(userId: string, book: ReviewBook) {
    const nextKey = `studyloop_position:${userId}:${book.id}:${book.version}`
    if (key === nextKey) return
    clear(); key = nextKey; version = book.version; path = `/me/review/books/${encodeURIComponent(book.id)}/position`
    try {
      const raw = localStorage.getItem(key)
      if (raw) {
        const saved = JSON.parse(raw) as Draft
        const validLocation = (x: ReadingLocation) => x && typeof x.point_id === 'string' && typeof x.block_id === 'string' && Number.isFinite(x.offset) && x.offset >= 0 && x.offset <= 1 && x.content_version === version
        if (validLocation(saved.candidate) && (saved.baseRevision === null || Number.isSafeInteger(saved.baseRevision) && saved.baseRevision >= 0) && (!saved.operation || validLocation(saved.operation) && Number.isSafeInteger(saved.operation.expected_revision) && typeof saved.operation.operation_id === 'string')) draft.value = saved
        else storageError.value = '本地阅读记录不可用，请使用服务器位置。'
      }
    } catch { storageError.value = '浏览器本地暂存不可用；未同步的位置在关闭后可能丢失。' }
    await reload()
  }
  async function reload() {
    if (!path) return
    const current = epoch
    const result = await request<{ position: ReadingPosition | null }>(path)
    if (current !== epoch) return
    if (!result.ok) { loaded.value = false; readError.value = result.message; return }
    remote.value = result.data.position; loaded.value = true; readError.value = ''
    if (draft.value && draft.value.baseRevision === null) {
      if (remote.value) { conflict.value = true; return }
      draft.value.baseRevision = 0; persist()
    }
    if (draft.value && !conflict.value) void flush()
  }
  function capture(location: ReadingLocation) {
    if (!key || conflict.value || location.content_version !== version) return
    if (draft.value && samePlace(draft.value.candidate, location) || !draft.value && remote.value && samePlace(remote.value, location)) return
    if (draft.value) draft.value.candidate = location
    else draft.value = { candidate: location, baseRevision: loaded.value ? remote.value?.revision || 0 : null, operation: null }
    persist()
    clearTimeout(pauseTimer); pauseTimer = setTimeout(() => void flush(), 1000)
    if (!maxTimer) maxTimer = setTimeout(() => void flush(), 5000)
  }
  async function flush() {
    cancelTimers(); online.value = navigator.onLine
    if (!path || !loaded.value || conflict.value || saving.value || !draft.value || !online.value || draft.value.baseRevision === null) return
    const current = epoch
    if (!draft.value.operation) draft.value.operation = { ...draft.value.candidate, expected_revision: draft.value.baseRevision, operation_id: crypto.randomUUID() }
    const operation = { ...draft.value.operation }
    persist(); saving.value = true; saveError.value = ''
    const result = await request<{ position: ReadingPosition }>(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(operation), keepalive: true })
    if (current !== epoch) return
    saving.value = false
    if (!result.ok) {
      if (result.status === 409) {
        conflict.value = true
        const data = result.data as { position?: ReadingPosition | null } | undefined
        if (data && 'position' in data) remote.value = data.position || null
        else { await reload(); if (current !== epoch) return }
      } else {
        if ((result.status === 404 || result.status === 422) && draft.value) draft.value.operation = null
        saveError.value = result.status === 404 || result.status === 422 ? '原位置已失效，请重新选择知识点；服务器记录未被覆盖。' : '保存尚未确认，请重试；本地位置仍保留。'
        persist()
      }
      return
    }
    const newerRemote = remote.value && remote.value.revision > result.data.position.revision
    if (!newerRemote) remote.value = result.data.position
    if (draft.value) {
      if (samePlace(draft.value.candidate, operation)) draft.value = null
      else { draft.value.baseRevision = result.data.position.revision; draft.value.operation = null; if (newerRemote) conflict.value = true }
    }
    persist()
    if (draft.value) pauseTimer = setTimeout(() => void flush(), 1000)
  }
  async function useLocal() {
    if (!draft.value || !loaded.value) return
    draft.value.baseRevision = remote.value?.revision || 0; draft.value.operation = null
    conflict.value = false; persist(); await flush()
  }
  function useServer() {
    if (!loaded.value) return
    draft.value = null; conflict.value = false; saveError.value = ''; persist()
    return remote.value
  }
  function connectionChanged() { online.value = navigator.onLine; if (online.value) { if (loaded.value) void flush(); else void reload() } }
  return { remote, draft, conflict, readError, storageError, saveError, saving, loaded, status, continuation, initialize, reload, capture, flush, useLocal, useServer, connectionChanged, clear }
}

export function locationAtViewport(point: KnowledgePoint): ReadingLocation | null {
  const blocks = [...document.querySelectorAll<HTMLElement>('.reading-body [data-block-id]')]
  const block = blocks.find(b => b.getBoundingClientRect().bottom > 80) || blocks.at(-1)
  if (!block) return null
  const rect = block.getBoundingClientRect()
  return { point_id: point.id, block_id: block.dataset.blockId!, offset: Math.max(0, Math.min(1, (80 - rect.top) / Math.max(1, rect.height))), content_version: point.version }
}
export function scrollToLocation(location: ReadingLocation): boolean {
  const block = document.getElementById(`block-${location.block_id}`)
  if (!block) return false
  const rect = block.getBoundingClientRect()
  window.scrollTo({ top: window.scrollY + rect.top + rect.height * location.offset - 80, behavior: 'instant' })
  return true
}
