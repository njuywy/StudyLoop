<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from 'vue'
import { request, token } from '../session'
import type { PointState, Mastery } from '../review'
const props = defineProps<{ pointId: string; initial?: PointState; disabled?: boolean }>()
const emit = defineEmits<{ changed: [state: PointState]; busy: [value: boolean] }>()
const state = ref<PointState | null>(null)
const loading = ref(false)
const saving = ref(false)
const needsReload = ref(false)
const message = ref('')
const selectId = useId()
let revision = 0
async function reload(preserveMessage = false) {
  const current = ++revision
  loading.value = true
  if (!preserveMessage) message.value = ''
  const result = await request<PointState>(`/me/review/points/${encodeURIComponent(props.pointId)}/state`)
  if (current !== revision) return
  loading.value = false
  if (result.ok) { state.value = result.data; needsReload.value = false; emit('changed', result.data) }
  else { needsReload.value = true; message.value = result.message || '状态读取失败，请重试。' }
}
async function save(change: { bookmarked?: boolean; mastery?: Mastery }) {
  if (!state.value || saving.value || loading.value || needsReload.value || props.disabled) return
  const current = revision
  saving.value = true; emit('busy', true); message.value = ''
  const result = await request<PointState>(`/me/review/points/${encodeURIComponent(props.pointId)}/state`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...change, expected_revision: state.value.revision, operation_id: crypto.randomUUID() }),
  })
  if (current !== revision) return
  if (result.ok) { saving.value = false; emit('busy', false); state.value = result.data; message.value = '已保存'; emit('changed', result.data); return }
  needsReload.value = true
  if (result.status === 409) message.value = '其他设备已更新状态，请刷新状态后重新选择。'
  else if (result.status === 0 || result.status >= 500) {
    message.value = '保存结果尚未确认，正在重新读取；请根据读取的状态重新操作。'
    const confirmation = reload(true)
    const confirmationRevision = revision
    await confirmation
    if (confirmationRevision !== revision) return
  } else message.value = result.message || '保存未完成，请重新读取状态。'
  saving.value = false; emit('busy', false)
}
function choose(event: Event) {
  const select = event.target as HTMLSelectElement
  const chosen = select.value as Mastery
  select.value = state.value?.mastery || 'unlearned'
  if (chosen !== state.value?.mastery) void save({ mastery: chosen })
}
watch([() => props.pointId, () => props.initial, token], () => {
  revision++; state.value = null; loading.value = false; saving.value = false; needsReload.value = false; message.value = ''
  if (!token.value) return
  if (props.initial) state.value = props.initial
  else void reload()
}, { immediate: true })
onBeforeUnmount(() => { revision++; if (saving.value) emit('busy', false) })
</script>
<template>
  <div class="point-state" aria-label="知识点复习状态">
    <p v-if="loading" role="status">正在读取复习状态…</p>
    <div v-if="state" class="state-controls">
      <button class="small-button" :disabled="saving || loading || needsReload || disabled" :aria-pressed="state.bookmarked" @click="save({ bookmarked: !state.bookmarked })">{{ state.bookmarked ? '★ 已收藏 · 取消收藏' : '☆ 收藏知识点' }}</button>
      <label :for="selectId">掌握程度</label><select :id="selectId" :value="state.mastery" :disabled="saving || loading || needsReload || disabled" @change="choose"><option value="unlearned">未学习</option><option value="needs_review">需复习</option><option value="mastered">已掌握</option></select>
    </div>
    <p v-if="saving" role="status">正在保存复习状态…</p><p v-else-if="message" role="status">{{ message }}</p>
    <button v-if="needsReload && !loading" class="small-button" @click="reload()">重新读取状态</button>
  </div>
</template>
<style scoped>
.point-state { padding: 16px 0; min-height: 94px; font-size: 13px; color: #53684b; }
.state-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.state-controls label { margin-left: auto; }
select { padding: 10px; background: #fffefa; color: #35432f; border: 1px solid #cdd8c3; border-radius: 8px; font: inherit; }
p { margin: 8px 0; line-height: 1.8; }
@media (max-width: 600px) { .point-state { min-height: 132px; }.state-controls > button { width: 100%; }.state-controls label { margin-left: 0; } }
</style>
