<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { request, token } from '../session'
const props = defineProps<{ path: string; alt: string; width?: number; height?: number }>()
const src = ref('')
const error = ref('')
const loading = ref(false)
let revision = 0
function clear() { if (src.value) URL.revokeObjectURL(src.value); src.value = '' }
async function load() {
  const current = ++revision
  clear(); error.value = ''; loading.value = true
  if (!token.value) { loading.value = false; return }
  const result = await request<Blob>(props.path, {}, true, true)
  if (revision !== current) return
  loading.value = false
  if (result.ok) src.value = URL.createObjectURL(result.data)
  else if (result.status !== -1 && result.status !== 401) error.value = result.message
}
watch([() => props.path, token], load, { immediate: true })
onBeforeUnmount(() => { revision++; clear() })
</script>
<template>
  <div class="private-image" :style="width && height ? { aspectRatio: `${width} / ${height}` } : undefined">
    <img v-if="src" :src="src" :alt="alt" :width="width" :height="height">
    <p v-else-if="loading" role="status">正在读取图片…</p>
    <div v-else-if="error"><p role="alert">{{ error }}</p><button class="small-button" @click.stop="load">重试图片</button></div>
  </div>
</template>
<style scoped>
.private-image { width: 100%; min-height: 32px; }
img { display: block; width: 100%; height: auto; }
p { font-size: 14px; color: #697363; }
</style>
