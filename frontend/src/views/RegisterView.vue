<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { submitAuth } from '../api'

const email = ref('')
const password = ref('')
const nickname = ref('')
const resend = ref(false)
const pending = ref(false)
const message = ref('')
const success = ref(false)
const neutral = ref(false)

function switchMode() {
  resend.value = !resend.value
  password.value = ''
  message.value = ''
}

async function submit() {
  if (pending.value) return
  message.value = ''
  success.value = false
  neutral.value = false
  if (!resend.value && (Array.from(password.value).length < 12 || Array.from(password.value).length > 128)) {
    message.value = '密码需要 12～128 个字符，空格也会保留。'
    return
  }
  if (!resend.value && Array.from(nickname.value.trim()).length > 30) {
    message.value = '昵称最多 30 个字符。'
    return
  }
  pending.value = true
  const result = await submitAuth(resend.value ? 'resend-verification' : 'register', resend.value
    ? { email: email.value.trim() }
    : { email: email.value.trim(), password: password.value, nickname: nickname.value.trim() || null })
  pending.value = false
  message.value = result.message
  neutral.value = result.code === 'VERIFICATION_REQUEST_ACCEPTED'
  success.value = result.ok && !neutral.value
  if (result.ok || result.code === 'MAIL_UNAVAILABLE' || result.code === 'ACCOUNT_EXISTS') {
    password.value = ''
    resend.value = true
  }
}
</script>

<template>
  <section class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">从一个账号开始</span><h1>{{ resend ? '重发验证邮件' : '注册账号' }}</h1><p>用邮箱连接你的学习空间。<br>验证邮箱后，你的账号便完成了第一步。</p></div>
    <div class="auth-card">
      <h2 class="auth-card-title">账号信息</h2>
      <form @submit.prevent="submit">
        <label for="email">邮箱</label>
        <input id="email" v-model="email" type="email" autocomplete="email" required maxlength="320" :disabled="pending" placeholder="you@example.com">
        <template v-if="!resend">
          <label for="password">密码</label>
          <input id="password" v-model="password" type="password" autocomplete="new-password" required :disabled="pending" aria-describedby="password-help">
          <p id="password-help" class="field-help">12～128 个字符，无需特定字符组合；空格也会保留。</p>
          <label for="nickname">昵称 <span class="optional">（可选）</span></label>
          <input id="nickname" v-model="nickname" type="text" autocomplete="nickname" :disabled="pending" placeholder="留空将使用“学习者”">
          <p class="field-help">最多 30 个字符，可以之后修改。</p>
        </template>
        <p v-else class="field-help">请检查收件箱与垃圾邮件。验证链接 24 小时内有效；重发至少间隔 60 秒。</p>
        <p v-if="message" :role="success || neutral ? 'status' : 'alert'" class="form-message" :class="{ success, neutral }">{{ message }}</p>
        <button type="submit" class="primary-button" :disabled="pending" :aria-busy="pending">{{ pending ? '正在提交…' : resend ? '发送验证邮件' : '注册并发送验证邮件' }}</button>
      </form>
      <button class="mode-button" :disabled="pending" @click="switchMode">{{ resend ? '返回注册' : '已注册但未收到邮件？重发验证邮件' }}</button>
      <RouterLink class="text-link" to="/login">返回登录入口</RouterLink>
    </div>
  </section>
</template>
