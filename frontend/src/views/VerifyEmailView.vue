<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { submitAuth } from '../api'

const route = useRoute()
const router = useRouter()
const token = computed(() => typeof route.query.token === 'string' ? route.query.token : '')
const pending = ref(false)
const success = ref(false)
const message = ref('')

async function verify() {
  if (pending.value || success.value || !token.value) return
  pending.value = true
  const result = await submitAuth('verify-email', { token: token.value })
  pending.value = false
  success.value = result.ok
  message.value = result.message
  if (result.ok || result.code === 'INVALID_VERIFICATION_TOKEN') {
    await router.replace({ path: '/verify-email' })
  }
}
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">确认属于你的邮箱</span><h1>验证邮箱</h1><p>完成验证，为下一次学习做好准备。</p></div>
    <div class="auth-card">
      <p v-if="message" :role="success ? 'status' : 'alert'" class="form-message" :class="{ success }">{{ message }}</p>
      <template v-if="!success && token">
        <p class="field-help">点击下方按钮完成邮箱验证。链接仅可使用一次，验证不会自动登录。</p>
        <button class="primary-button" :disabled="pending" :aria-busy="pending" @click="verify">{{ pending ? '正在验证…' : '确认验证邮箱' }}</button>
      </template>
      <p v-else-if="!success && !message" role="alert" class="form-message">缺少验证链接，请从邮件中打开完整链接，或重新申请验证邮件。</p>
      <RouterLink v-if="success" class="primary-button" to="/login">前往登录</RouterLink>
      <RouterLink v-else class="text-link" to="/register">注册或重发验证邮件</RouterLink>
    </div>
  </section>
</template>
