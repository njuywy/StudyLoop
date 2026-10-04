<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { loadProfile, profile } from '../session'
import ProfileEditor from './ProfileEditor.vue'
import AvatarEditor from './AvatarEditor.vue'
import UserAvatar from './UserAvatar.vue'

const route = useRoute()
const busy = ref(true)
const error = ref('')
let refreshVersion = 0

onBeforeUnmount(() => { refreshVersion++ })

async function refresh() {
  const currentRefresh = ++refreshVersion
  busy.value = true
  error.value = ''
  const result = await loadProfile()
  if (currentRefresh !== refreshVersion || (!result.ok && result.status === -1)) return
  busy.value = false
  if (!result.ok) {
    if (result.status !== 401) error.value = result.message
  }
}

watch(() => route.path, refresh, { immediate: true })
</script>

<template>
  <section v-if="route.path === '/profile'" class="profile-section section-width">
    <div class="profile-heading"><div><span class="section-kicker">你的学习空间</span><h1>个人中心</h1><p>让这个空间，更像你自己。</p></div><RouterLink class="text-link" to="/review">前往在线复习 <span aria-hidden="true">→</span></RouterLink></div>
    <div v-if="busy" class="profile-state" role="status">正在读取账号信息…</div>
    <div v-else-if="error" class="profile-state"><p role="alert" class="form-message">{{ error }}</p><button class="small-button" @click="refresh">重试</button></div>
    <div v-else-if="profile" class="profile-layout">
      <aside class="account-overview" aria-labelledby="account-overview-title">
        <span class="section-kicker" id="account-overview-title">账户概览</span>
        <UserAvatar />
        <h2>你好，{{ profile.nickname }}</h2>
        <p class="account-email">邮箱：{{ profile.email }}</p>
        <span class="account-badge">{{ profile.role === 'admin' ? '管理员' : '学习者' }}</span>
        <div class="account-note"><span aria-hidden="true">↺</span><p>学习是一场与自己的相遇，<br>从照顾好你的空间开始。</p></div>
      </aside>
      <div class="profile-forms"><ProfileEditor><AvatarEditor /></ProfileEditor></div>
    </div>
  </section>
  <section v-else class="auth-section section-width">
    <div class="auth-intro"><span class="section-kicker">你的学习空间</span><h1>在线复习</h1><p>让知识，再次发生。</p></div>
    <div class="auth-card">
      <p v-if="busy" role="status">正在读取账号信息…</p>
      <template v-else-if="error"><p role="alert" class="form-message">{{ error }}</p><button class="mode-button" @click="refresh">重试</button></template>
      <template v-else-if="profile"><h2>欢迎回来，{{ profile.nickname }}</h2><p>在线复习功能正在建设中。</p><RouterLink class="text-link" to="/profile">返回个人中心</RouterLink></template>
    </div>
  </section>
</template>

<style scoped>
.profile-section { padding-top: 44px; padding-bottom: 56px; }
.profile-heading { display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 30px; }
.profile-heading h1 { font-size: clamp(28px, 3vw, 36px); margin: 8px 0; }
.profile-heading p { font-size: 14px; color: #647260; margin: 0; }
.profile-heading > a { flex-shrink: 0; }
.profile-layout { display: grid; grid-template-columns: minmax(0, 300px) minmax(0, 1fr); align-items: start; gap: 28px; }
.account-overview, .profile-state { padding: 30px; border: 1px solid #dce4d8; background: #fffefa; border-radius: 18px; }
.account-overview { background: #eaf0e5; text-align: center; overflow-wrap: anywhere; }
.account-overview :deep(.user-avatar) { display: block; width: 88px; height: 88px; margin: 26px auto 18px; border: 5px solid #fffefa; }
.account-overview h2 { font-size: 22px; line-height: 1.6; font-weight: 600; }
.account-email { font-size: 14px; color: #526957; line-height: 1.8; margin: 12px 0 18px; }
.account-badge { display: inline-block; font-size: 12px; color: #315e45; background: #fffefa; border-radius: 20px; padding: 6px 14px; }
.account-note { border-top: 1px solid #d1dec9; margin-top: 28px; padding-top: 24px; color: #526957; }
.account-note > span { font-size: 32px; }
.account-note p { font-size: 13px; line-height: 1.9; margin-bottom: 0; }
.profile-forms { display: grid; gap: 24px; min-width: 0; }
@media (max-width: 800px) {
  .profile-layout { grid-template-columns: minmax(0, 1fr); gap: 20px; }
  .account-overview { text-align: left; position: relative; padding: 24px; padding-left: 116px; }
  .account-overview :deep(.user-avatar) { position: absolute; left: 24px; top: 26px; width: 68px; height: 68px; margin: 0; }
  .account-overview h2 { font-size: 21px; }
  .account-email { margin: 8px 0 12px; }
  .account-note { display: none; }
}
@media (max-width: 480px) {
  .profile-section { padding-top: 28px; padding-bottom: 36px; }
  .profile-heading { align-items: flex-start; flex-direction: column; gap: 16px; margin-bottom: 24px; }
  .account-overview { padding: 22px; }
  .account-overview :deep(.user-avatar) { position: static; margin: 18px 0 12px; }
}
</style>
