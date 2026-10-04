<script setup lang="ts">
import { computed } from 'vue'
import type { TocNode } from '../review'
const props = defineProps<{ nodes: TocNode[]; parent?: string | null; current?: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const children = computed(() => props.nodes.filter(n => n.parent_id === (props.parent ?? null)))
function activeBranch(id: string): boolean {
  let node = props.nodes.find(n => n.point_id === props.current)
  while (node) {
    if (node.id === id) return true
    node = props.nodes.find(n => n.id === node?.parent_id)
  }
  return !props.current
}
</script>
<template>
  <ul class="contents-list">
    <li v-for="node in children" :key="node.id">
      <details v-if="nodes.some(n => n.parent_id === node.id)" :open="activeBranch(node.id)">
        <summary>{{ node.title }}</summary>
        <button v-if="node.point_id" :aria-current="current === node.point_id ? 'location' : undefined" @click="emit('select', node.point_id)">阅读本节引言</button>
        <ReviewContents :nodes="nodes" :parent="node.id" :current="current" @select="emit('select', $event)" />
      </details>
      <button v-else-if="node.point_id" :aria-current="current === node.point_id ? 'location' : undefined" @click="emit('select', node.point_id)">{{ node.title }}</button>
    </li>
  </ul>
</template>
<style scoped>
.contents-list { list-style: none; padding: 0; margin: 0; }
.contents-list .contents-list { padding-left: 10px; border-left: 1px solid #dce4d8; margin-left: 5px; }
li { margin: 5px 0; }
summary, button { cursor: pointer; font: inherit; font-size: 13px; line-height: 1.8; padding: 8px; border-radius: 8px; overflow-wrap: anywhere; }
summary { color: #40553b; font-weight: 600; }
button { display: block; width: 100%; border: 0; text-align: left; background: transparent; color: #55604f; }
button:hover, button[aria-current] { color: #264a28; background: #e4eddf; }
</style>
