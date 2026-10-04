<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import type { TocNode } from '../review'
const props = defineProps<{ nodes: TocNode[]; parent?: string | null; current?: string; expanded?: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const query = ref('')
const expandedContainer = ref('')
const container = ref<HTMLElement>()
const inputId = useId()
watch(() => props.current, () => { expandedContainer.value = '' })
const children = computed(() => props.nodes.filter(n => n.parent_id === (props.parent ?? null)))
const matches = computed(() => props.nodes.filter(n => n.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())))
function activeBranch(id: string): boolean {
  let node = props.nodes.find(n => n.id === (props.expanded || expandedContainer.value)) || props.nodes.find(n => n.point_id === props.current)
  while (node) {
    if (node.id === id) return true
    node = props.nodes.find(n => n.id === node?.parent_id)
  }
  return !props.current
}
async function choose(node: TocNode) {
  if (node.point_id) { emit('select', node.point_id); return }
  expandedContainer.value = node.id
  query.value = ''
  await nextTick()
  const summary = container.value?.querySelector<HTMLElement>(`[data-node-id="${CSS.escape(node.id)}"] > details > summary`)
  summary?.focus()
  summary?.scrollIntoView({ block: 'nearest' })
}
</script>
<template>
  <div ref="container">
  <div v-if="!parent" class="contents-search"><label :for="inputId">搜索章节或知识点标题</label><input :id="inputId" v-model="query" type="search" placeholder="例如：数据流图、UML" autocomplete="off"><p v-if="query.trim()" role="status">{{ matches.length ? `找到 ${matches.length} 个标题` : '没有匹配的标题，请换个关键词。' }}</p></div>
  <ul v-if="!parent && query.trim()" class="contents-list search-results">
    <li v-for="node in matches" :key="node.id"><button @click="choose(node)">{{ node.title }}<small>{{ node.path.slice(0, -1).join(' / ') || '章节' }}<template v-if="!node.point_id"> · 展开目录</template></small></button></li>
  </ul>
  <ul v-else class="contents-list">
    <li v-for="node in children" :key="node.id" :data-node-id="node.id">
      <details v-if="nodes.some(n => n.parent_id === node.id)" :open="activeBranch(node.id)">
        <summary>{{ node.title }}</summary>
        <button v-if="node.point_id" :aria-current="current === node.point_id ? 'location' : undefined" @click="emit('select', node.point_id)">阅读本节引言</button>
        <ReviewContents :nodes="nodes" :parent="node.id" :current="current" :expanded="expanded || expandedContainer" @select="emit('select', $event)" />
      </details>
      <button v-else-if="node.point_id" :aria-current="current === node.point_id ? 'location' : undefined" @click="emit('select', node.point_id)">{{ node.title }}</button>
    </li>
  </ul>
  </div>
</template>
<style scoped>
.contents-list { list-style: none; padding: 0; margin: 0; }
.contents-list .contents-list { padding-left: 10px; border-left: 1px solid #dce4d8; margin-left: 5px; }
li { margin: 5px 0; }
summary, button { cursor: pointer; font: inherit; font-size: 13px; line-height: 1.8; padding: 8px; border-radius: 8px; overflow-wrap: anywhere; }
summary { color: #40553b; font-weight: 600; }
button { display: block; width: 100%; border: 0; text-align: left; background: transparent; color: #55604f; }
button:hover, button[aria-current] { color: #264a28; background: #e4eddf; }
.contents-search { padding: 0 4px 12px; }
.contents-search label { display: block; font-size: 12px; color: #64745a; margin-bottom: 8px; }
.contents-search input { width: 100%; min-width: 0; padding: 10px; border: 1px solid #cad7c0; background: #fffefa; border-radius: 8px; font: inherit; font-size: 13px; }
.contents-search p, .search-results small { display: block; font-size: 11px; line-height: 1.8; color: #73816a; }
</style>
