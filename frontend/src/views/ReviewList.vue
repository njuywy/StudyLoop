<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { request, token } from '../session'
import type { PointState } from '../review'
import ReviewState from './ReviewState.vue'
type Item = PointState & { title: string; path: string[] }
type Listing = { items: Item[]; total: number; page: number; page_size: number }
const props = defineProps<{ bookId: string; filter: 'bookmarked' | 'needs_review' }>()
const emit = defineEmits<{ select: [id: string] }>()
const result = ref<Listing | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const page = ref(1)
const heading = ref<HTMLElement>()
const title = computed(() => props.filter === 'bookmarked' ? '我的收藏' : '待复习')
let revision = 0
async function load(target = page.value) {
  const current = ++revision
  loading.value = true; error.value = ''; page.value = target
  const response = await request<Listing>(`/me/review/books/${encodeURIComponent(props.bookId)}/points?filter=${props.filter}&page=${target}`)
  if (current !== revision) return
  loading.value = false
  if (response.ok) { result.value = response.data; page.value = response.data.page }
  else error.value = response.message || '列表读取失败，请重试。'
}
async function turn(target: number) { await load(target); heading.value?.focus() }
watch([() => props.bookId, () => props.filter, token], () => {
  revision++; result.value = null; page.value = 1
  if (token.value) void load(1)
}, { immediate: true })
onBeforeUnmount(() => { revision++ })
</script>
<template>
  <section class="private-list" :aria-label="title">
    <header><div><h2 ref="heading" tabindex="-1">{{ title }}</h2><p>{{ filter === 'bookmarked' ? '收藏感兴趣的知识点，随时回到原文。' : '这里只展示手动标记为“需复习”的知识点。' }}</p></div><button class="small-button" :disabled="loading || saving" @click="load()">刷新列表</button></header>
    <p v-if="loading" role="status">正在读取{{ title }}…</p>
    <div v-else-if="error"><p role="alert">{{ error }}</p><button class="small-button" @click="load()">重试列表</button></div>
    <template v-else-if="result">
      <div v-if="!result.total" class="list-empty"><h3>{{ filter === 'bookmarked' ? '还没有收藏' : '暂时没有待复习内容' }}</h3><p>{{ filter === 'bookmarked' ? '在阅读页点击收藏，就能在这里找到它。' : '阅读时将掌握程度改为“需复习”，便会加入这里。' }}</p></div>
      <ul v-else><li v-for="item in result.items" :key="item.point_id"><p class="list-path">{{ item.path.slice(0, -1).join(' / ') }}</p><button class="point-link" @click="emit('select', item.point_id)">{{ item.title }} <span aria-hidden="true">→</span></button><ReviewState :point-id="item.point_id" :initial="item" :disabled="saving || loading" @busy="saving = $event" @changed="turn(page)" /></li></ul>
      <nav v-if="result.total" aria-label="私人列表分页"><button class="small-button" :disabled="page <= 1 || loading || saving" @click="turn(page - 1)">上一页列表</button><span>第 {{ page }} / {{ Math.ceil(result.total / result.page_size) }} 页 · {{ result.total }} 项</span><button class="small-button" :disabled="page * result.page_size >= result.total || loading || saving" @click="turn(page + 1)">下一页列表</button></nav>
    </template>
  </section>
</template>
<style scoped>
.private-list { padding: clamp(20px, 3vw, 36px); border: 1px solid #dce4d8; border-radius: 16px; background: #fffefa; }
header { display: flex; justify-content: space-between; align-items: start; gap: 14px; }
header h2 { margin: 0 0 10px; font-size: 24px; } header p, .list-empty p { color: #68795e; font-size: 14px; line-height: 1.9; }
header > button { flex-shrink: 0; } ul { list-style: none; padding: 0; margin: 20px 0; }
li { border-top: 1px solid #e1e7da; padding: 18px 0 0; }
.list-path { font-size: 12px; color: #738268; line-height: 1.8; overflow-wrap: anywhere; }
.point-link { display: block; width: 100%; text-align: left; padding: 5px 0; border: 0; background: none; color: #284a3b; font: inherit; font-size: 18px; line-height: 1.7; font-weight: 600; cursor: pointer; overflow-wrap: anywhere; }
.list-empty { text-align: center; padding: 40px 10px; }
nav { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; font-size: 13px; color: #65785a; }
</style>
