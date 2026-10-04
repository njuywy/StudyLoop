<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { login } from '../session'

const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const pending = ref(false)
const message = ref(route.query.changed === '1' ? '密码已更新，请使用新密码重新登录。' : route.query.expired === '1' ? '登录状态已失效，请重新登录。' : '')

async function submit() {
  if (pending.value) return
  pending.value = true
  message.value = ''
  const result = await login(email.value, password.value)
  pending.value = false
  password.value = ''
  if (!result.ok) {
    message.value = result.message
    return
  }
  const target = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  await router.replace(/^\/(?:profile|review|admin\/users)(?:[?#]|$)/.test(target) ? target : '/')
}
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">欢迎回来</span><h1>登录 StudyLoop</h1><p>完成邮箱验证后，继续你的学习旅程。</p></div>
    <div class="auth-card">
      <form @submit.prevent="submit">
        <label for="login-email">邮箱</label>
        <input id="login-email" v-model="email" type="email" autocomplete="email" required :disabled="pending">
        <label for="login-password">密码</label>
        <input id="login-password" v-model="password" type="password" autocomplete="current-password" required :disabled="pending">
        <p v-if="message" role="alert" class="form-message">{{ message }}</p>
        <button class="primary-button" type="submit" :disabled="pending" :aria-busy="pending">{{ pending ? '正在登录…' : '登录' }}</button>
      </form>
      <RouterLink class="text-link" to="/forgot-password">忘记密码？通过邮箱找回</RouterLink>
      <RouterLink class="text-link" to="/register">还没有账号？注册并验证邮箱</RouterLink>
    </div>
  </section>
</template>
