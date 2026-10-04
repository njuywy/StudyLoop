<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { loadProfile, profile } from '../session'

const route = useRoute()
const router = useRouter()
const busy = ref(true)
const error = ref('')

async function refresh() {
  busy.value = true
  error.value = ''
  const result = await loadProfile()
  busy.value = false
  if (!result.ok) {
    if (result.status === 401) {
      await router.replace({ path: '/login', query: { redirect: route.fullPath, expired: '1' } })
    } else {
      error.value = result.message
    }
  }
}

watch(() => route.path, refresh, { immediate: true })
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">你的学习空间</span><h1>{{ route.path === '/review' ? '在线复习' : '个人中心' }}</h1><p>让知识，再次发生。</p></div>
    <div class="auth-card">
      <p v-if="busy" role="status">正在读取账号信息…</p>
      <template v-else-if="error"><p role="alert" class="form-message">{{ error }}</p><button class="mode-button" @click="refresh">重试</button></template>
      <template v-else-if="profile">
        <template v-if="route.path === '/review'"><h2>欢迎回来，{{ profile.nickname }}</h2><p>在线复习功能正在建设中。</p></template>
        <template v-else><h2>你好，{{ profile.nickname }}</h2><p>邮箱：{{ profile.email }}</p><p>昵称：{{ profile.nickname }}</p><p class="field-help">资料维护与头像功能即将上线。</p></template>
        <RouterLink class="text-link" :to="route.path === '/review' ? '/profile' : '/review'">{{ route.path === '/review' ? '返回个人中心' : '前往在线复习' }}</RouterLink>
      </template>
    </div>
  </section>
</template>
