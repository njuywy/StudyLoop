<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { submitAuth } from '../api'

const email = ref('')
const pending = ref(false)
const accepted = ref(false)
const message = ref('')

async function submit() {
  if (pending.value) return
  pending.value = true
  message.value = ''
  const result = await submitAuth('request-password-reset', { email: email.value.trim() })
  pending.value = false
  accepted.value = result.ok
  message.value = result.message
}
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">找回学习的入口</span><h1>忘记密码</h1><p>通过已验证邮箱，重新设置你的密码。</p></div>
    <div class="auth-card">
      <form @submit.prevent="submit">
        <label for="reset-email">邮箱</label>
        <input id="reset-email" v-model="email" type="email" autocomplete="email" required maxlength="320" :disabled="pending">
        <p class="field-help">重置链接 30 分钟内有效，仅可使用一次。请同时检查垃圾邮件。</p>
        <p v-if="message" :role="accepted ? 'status' : 'alert'" class="form-message" :class="{ neutral: accepted }">{{ message }}</p>
        <button class="primary-button" type="submit" :disabled="pending" :aria-busy="pending">{{ pending ? '正在提交…' : '发送重置邮件' }}</button>
      </form>
      <RouterLink class="text-link" to="/login">返回登录</RouterLink>
    </div>
  </section>
</template>
