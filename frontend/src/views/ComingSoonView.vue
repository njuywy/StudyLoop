<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <section class="coming-soon section-width">
    <div class="coming-mark" aria-hidden="true">↺</div>
    <span class="section-kicker">{{ route.meta.label }}</span>
    <h1>{{ route.meta.title }}</h1>
    <p>我们正在搭建平台的基础能力。<br>这个入口已经为你留好，功能完成后即可使用。</p>
    <RouterLink class="primary-button" to="/">返回首页 <span aria-hidden="true">→</span></RouterLink>
  </section>
</template>
