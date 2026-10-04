<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { submitAuth } from '../api'
import { clearSession, token as sessionToken } from '../session'

const route = useRoute()
const router = useRouter()
const resetToken = computed(() => typeof route.query.token === 'string' ? route.query.token : '')
const password = ref('')
const pending = ref(false)
const success = ref(false)
const message = ref('')
let submission = 0

watch(resetToken, next => {
  submission++
  pending.value = false
  password.value = ''
  if (next || !success.value) {
    success.value = false
    message.value = ''
  }
})
onBeforeUnmount(() => { submission++ })

async function submit() {
  if (pending.value || success.value || !resetToken.value) return
  if (Array.from(password.value).length < 12 || Array.from(password.value).length > 128) {
    message.value = '密码需要 12～128 个字符，空格也会保留。'
    return
  }
  const currentSubmission = ++submission
  const currentSession = sessionToken.value
  pending.value = true
  message.value = ''
  const result = await submitAuth('reset-password', { token: resetToken.value, new_password: password.value })
  if (submission !== currentSubmission) return
  pending.value = false
  password.value = ''
  success.value = result.ok
  message.value = result.message
  if (result.ok) {
    if (sessionToken.value === currentSession) clearSession()
    await router.replace({ path: '/reset-password' })
  }
}
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">重新开始，继续学习</span><h1>重置密码</h1><p>设置新密码后，请重新登录。</p></div>
    <div class="auth-card">
      <h2 class="auth-card-title">设置新密码</h2>
      <p v-if="message" :role="success ? 'status' : 'alert'" class="form-message" :class="{ success }">{{ message }}</p>
      <form v-if="!success && resetToken" @submit.prevent="submit">
        <label for="new-password">新密码</label>
        <input id="new-password" v-model="password" type="password" autocomplete="new-password" required :disabled="pending" aria-describedby="reset-password-help">
        <p id="reset-password-help" class="field-help">12～128 个字符，无需特定字符组合；空格也会保留。仅打开此页面不会修改密码。</p>
        <button class="primary-button" type="submit" :disabled="pending" :aria-busy="pending">{{ pending ? '正在更新…' : '确认重置密码' }}</button>
      </form>
      <p v-else-if="!success && !message" role="alert" class="form-message">缺少重置链接，请从邮件打开完整链接，或重新申请找回密码。</p>
      <RouterLink v-if="success" class="primary-button" to="/login">重新登录</RouterLink>
      <RouterLink v-else class="text-link" to="/forgot-password">重新申请找回密码</RouterLink>
    </div>
  </section>
</template>
