<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { loadProfile, loadUsers, profile, setUserEnabled, type ManagedUser, type UserPage } from '../session'

const users = ref<UserPage | null>(null)
const pending = ref(true)
const error = ref('')
const message = ref('')
let active = true
let version = 0
onBeforeUnmount(() => { active = false; version++ })

async function refresh(page = users.value?.page || 1) {
  const attempt = ++version
  pending.value = true
  error.value = ''
  message.value = ''
  const identity = await loadProfile()
  if (!active || attempt !== version) return
  if (!identity.ok || profile.value?.role !== 'admin') {
    users.value = null
    pending.value = false
    error.value = identity.ok ? '仅管理员可以访问用户管理。' : identity.message
    return
  }
  const result = await loadUsers(page)
  if (!active || attempt !== version) return
  pending.value = false
  if (result.ok) users.value = result.data
  else {
    error.value = result.message
    if (result.status === 401 || result.status === 403) users.value = null
  }
}

async function change(user: ManagedUser) {
  if (pending.value) return
  pending.value = true
  error.value = ''
  message.value = ''
  const result = await setUserEnabled(user.id, !user.enabled)
  if (!active || (!result.ok && result.status === -1)) return
  pending.value = false
  if (result.ok) {
    if (users.value) users.value.items = users.value.items.map(row => row.id === user.id ? result.data : row)
    message.value = `${result.data.nickname}已${result.data.enabled ? '恢复，可重新登录' : '禁用，已有会话已失效'}。`
  } else {
    error.value = result.message
    if (result.status === 401 || result.status === 403) users.value = null
  }
}

void refresh()
</script>

<template>
  <section class="section-width admin-section">
    <span class="section-kicker">平台管理</span><h1>用户管理</h1>
    <p>禁用会结束该用户的所有会话；恢复后需要重新登录。</p>
    <p v-if="pending" role="status">正在处理…</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert" class="form-message">{{ error }}</p>
    <button class="mode-button" :disabled="pending" @click="refresh()">刷新列表</button>
    <template v-if="users">
      <p>共 {{ users.total }} 个用户 · 第 {{ users.page }} 页</p>
      <p v-if="users.items.length === 0">本页没有用户。</p>
      <ul class="managed-users" aria-label="用户列表">
        <li v-for="user in users.items" :key="user.id" class="managed-user">
          <h2>{{ user.nickname }}</h2><p>{{ user.email }}</p>
          <dl>
            <dt>ID</dt><dd>{{ user.id }}</dd>
            <dt>角色</dt><dd>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</dd>
            <dt>邮箱</dt><dd>{{ user.email_verified ? '已验证' : '未验证' }}</dd>
            <dt>状态</dt><dd>{{ user.enabled ? '已启用' : '已禁用' }}</dd>
            <dt>注册时间</dt><dd>{{ new Date(user.created_at).toLocaleString('zh-CN') }}</dd>
          </dl>
          <button v-if="user.role === 'user'" class="mode-button" :disabled="pending" @click="change(user)">{{ user.enabled ? '禁用用户' : '恢复用户' }}</button>
          <p v-else>管理员状态受保护</p>
        </li>
      </ul>
      <div class="pagination">
        <button class="mode-button" :disabled="pending || users.page <= 1" @click="refresh(users.page - 1)">上一页</button>
        <button class="mode-button" :disabled="pending || users.page * users.page_size >= users.total" @click="refresh(users.page + 1)">下一页</button>
      </div>
    </template>
  </section>
</template>
