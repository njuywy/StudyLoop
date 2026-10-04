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
    <div class="admin-heading"><div><span class="section-kicker">平台管理</span><h1>用户管理</h1></div><button class="small-button" :disabled="pending" @click="refresh()">刷新列表</button></div>
    <p class="admin-note">禁用会结束该用户的所有会话；恢复后需要重新登录。</p>
    <p v-if="pending" class="admin-loading" role="status">正在处理…</p>
    <p v-if="message" class="form-message success" role="status">{{ message }}</p>
    <p v-if="error" role="alert" class="form-message">{{ error }}</p>
    <template v-if="users">
      <p class="admin-count">共 {{ users.total }} 个用户 · 第 {{ users.page }} 页</p>
      <p v-if="users.items.length === 0" class="admin-empty">本页没有用户。</p>
      <ul class="managed-users" aria-label="用户列表">
        <li v-for="user in users.items" :key="user.id" class="managed-user">
          <div class="managed-user-heading"><h2>{{ user.nickname }}</h2><span class="user-state" :class="{ disabled: !user.enabled }">{{ user.enabled ? '已启用' : '已禁用' }}</span></div><p class="managed-user-email">{{ user.email }}</p>
          <dl>
            <dt>ID</dt><dd>{{ user.id }}</dd>
            <dt>角色</dt><dd>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</dd>
            <dt>邮箱</dt><dd>{{ user.email_verified ? '已验证' : '未验证' }}</dd>
            <dt>注册时间</dt><dd>{{ new Date(user.created_at).toLocaleString('zh-CN') }}</dd>
          </dl>
          <button v-if="user.role === 'user'" class="small-button user-action" :class="{ disable: user.enabled }" :disabled="pending" @click="change(user)">{{ user.enabled ? '禁用用户' : '恢复用户' }}</button>
          <p v-else class="protected-user">管理员状态受保护</p>
        </li>
      </ul>
      <div class="pagination">
        <button class="small-button" :disabled="pending || users.page <= 1" @click="refresh(users.page - 1)">上一页</button>
        <button class="small-button" :disabled="pending || users.page * users.page_size >= users.total" @click="refresh(users.page + 1)">下一页</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.admin-section { padding-top: 44px; padding-bottom: 56px; }
.admin-heading { display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 24px; }
.admin-heading h1 { font-size: clamp(28px, 3vw, 36px); margin: 8px 0 0; }
.admin-heading button { flex-shrink: 0; color: #315e45; font-size: 14px; }
.admin-note { background: #eaf0e5; border: 1px solid #d8e2d2; border-radius: 12px; padding: 16px 20px; font-size: 14px; color: #526957; line-height: 1.9; }
.admin-loading, .admin-count { font-size: 14px; color: #647260; line-height: 1.9; }
.admin-count { margin: 26px 0 16px; }
.admin-empty { text-align: center; padding: 48px 24px; background: #fffefa; border: 1px solid #dce4d8; border-radius: 16px; color: #647260; }
.managed-users { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.managed-user { border: 1px solid #dce4d8; padding: 26px; border-radius: 16px; background: #fffefa; overflow-wrap: anywhere; min-width: 0; }
.managed-user-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.managed-user h2 { font-size: 20px; font-weight: 600; margin: 0; min-width: 0; line-height: 1.6; }
.user-state { font-size: 12px; flex-shrink: 0; padding: 5px 10px; color: #315e45; background: #edf3e7; border-radius: 20px; }
.user-state.disabled { color: #83503d; background: #f8eee6; }
.managed-user-email { font-size: 14px; line-height: 1.8; color: #647260; margin: 8px 0 20px; }
.managed-user dl { display: grid; grid-template-columns: 5em minmax(0, 1fr); gap: 12px; font-size: 13px; line-height: 1.7; padding-block: 18px; border-block: 1px solid #e5eadd; }
.managed-user dt { color: #647260; }
.managed-user dd { margin: 0; }
.user-action { margin-top: 8px; color: #315e45; font-size: 14px; }
.user-action.disable { color: #8c4d38; border-color: #e4cdc0; }
.protected-user { color: #647260; font-size: 13px; margin: 24px 0 12px; }
.pagination { display: flex; gap: 12px; justify-content: flex-end; padding-top: 10px; }
.pagination button { color: #315e45; font-size: 14px; }
@media (max-width: 700px) { .managed-users { grid-template-columns: minmax(0, 1fr); }.admin-section { padding-top: 28px; padding-bottom: 36px; }.managed-user { padding: 22px; }.pagination { justify-content: space-between; } }
</style>
