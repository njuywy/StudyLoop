<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { checkPlatformConnection } from './api'
import { logout, profile, token } from './session'
import { useRouter } from 'vue-router'

const router = useRouter()
const logoutError = ref('')

const status = ref<'checking' | 'ready' | 'unavailable'>('checking')
let controller: AbortController | undefined
let timeout: ReturnType<typeof setTimeout> | undefined

function focusContent() {
  document.getElementById('content')?.focus()
}

async function refreshConnection() {
  controller?.abort()
  if (timeout) clearTimeout(timeout)
  controller = new AbortController()
  status.value = 'checking'
  timeout = setTimeout(() => controller?.abort(), 5000)
  status.value = await checkPlatformConnection(controller.signal) ? 'ready' : 'unavailable'
  clearTimeout(timeout)
}

onMounted(refreshConnection)
onBeforeUnmount(() => {
  controller?.abort()
  if (timeout) clearTimeout(timeout)
})

async function signOut() {
  logoutError.value = ''
  const result = await logout()
  if (result.ok && !('superseded' in result)) await router.push('/login')
  else if (!result.ok) logoutError.value = result.message
}
</script>

<template>
  <a class="skip-link" href="#content" @click.prevent="focusContent">跳到主要内容</a>
  <header class="site-header">
    <div class="header-inner">
      <RouterLink class="brand" to="/" aria-label="StudyLoop 首页">
        <svg class="brand-mark" viewBox="0 0 36 36" aria-hidden="true"><path d="M26 11a11 11 0 1 0 2 12M25 5l2 7-7 1" /></svg>
        <span>Study<span class="brand-light">Loop</span><small>让知识，再次发生</small></span>
      </RouterLink>
      <nav aria-label="主要导航">
        <RouterLink to="/" exact-active-class="active">首页</RouterLink>
        <RouterLink to="/review">在线复习</RouterLink>
        <RouterLink to="/profile">个人中心</RouterLink>
      </nav>
      <div class="account-links">
        <template v-if="token"><RouterLink class="login-link" to="/profile">{{ profile?.nickname || '我的账号' }}</RouterLink><button class="mode-button" @click="signOut">退出</button></template>
        <template v-else><RouterLink class="login-link" to="/login">登录</RouterLink><RouterLink class="small-button" to="/register">注册账号 <span aria-hidden="true">↗</span></RouterLink></template>
      </div>
    </div>
  </header>
  <main id="content" tabindex="-1"><RouterView /></main>
  <p v-if="logoutError" role="alert" class="section-width form-message">{{ logoutError }}</p>
  <footer class="site-footer">
    <div><strong>StudyLoop</strong><span>慢一点，学得更扎实。</span></div>
    <div class="connection-area">
      <span class="connection" :class="status" role="status" aria-live="polite">
        <i aria-hidden="true"></i>
        {{ status === 'checking' ? '正在检查平台连接' : status === 'ready' ? '平台连接已就绪' : '平台连接暂不可用' }}
      </span>
      <button v-if="status === 'unavailable'" class="retry" @click="refreshConnection">重试</button>
    </div>
    <span class="footer-note">© {{ new Date().getFullYear() }} StudyLoop</span>
  </footer>
</template>
