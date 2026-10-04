<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <section class="coming-soon section-width">
    <div class="coming-mark" aria-hidden="true">↺</div>
    <span class="section-kicker">{{ route.meta.label }}</span>
    <h1>{{ route.meta.title }}</h1>
    <p>暂时无法找到这个页面。<br>回到首页，继续探索你的学习空间。</p>
    <RouterLink class="primary-button" to="/">返回首页 <span aria-hidden="true">→</span></RouterLink>
  </section>
</template>
