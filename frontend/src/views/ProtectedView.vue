<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { loadProfile, profile } from '../session'
import ProfileEditor from './ProfileEditor.vue'
import AvatarEditor from './AvatarEditor.vue'
import UserAvatar from './UserAvatar.vue'

const route = useRoute()
const isProfile = computed(() => route.matched.some(record => record.path === '/profile'))
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
  <section v-if="isProfile" class="profile-section section-width">
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
  <section v-else class="review-section section-width">
    <div class="review-heading"><span class="section-kicker">你的学习空间</span><h1>在线复习</h1><p>让知识，再次发生。</p></div>
    <div class="review-placeholder">
      <p v-if="busy" role="status">正在读取账号信息…</p>
      <template v-else-if="error"><p role="alert" class="form-message">{{ error }}</p><button class="small-button" @click="refresh">重试</button></template>
      <template v-else-if="profile">
        <div class="review-symbol" aria-hidden="true">↺</div><span class="review-stage">建设中</span>
        <h2>欢迎回来，{{ profile.nickname }}</h2><p class="review-status">在线复习功能正在建设中。</p>
        <p class="review-description">让每一次回顾，都成为新的进步。<br>你可以先完善个人资料，为之后的学习做好准备。</p>
        <RouterLink class="primary-button" to="/profile">返回个人中心 <span aria-hidden="true">→</span></RouterLink>
      </template>
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
.review-section { padding-top: 44px; padding-bottom: 56px; }
.review-heading h1 { font-size: clamp(28px, 3vw, 36px); margin: 8px 0; }
.review-heading > p { font-size: 14px; color: #647260; margin: 0 0 28px; }
.review-placeholder { padding: 48px 30px; text-align: center; border: 1px solid #dce4d8; border-radius: 20px; background: #fffefa; overflow-wrap: anywhere; }
.review-symbol { display: grid; place-items: center; width: 90px; height: 90px; border-radius: 26px; background: #eaf0e5; color: #53794c; font-size: 52px; margin: 0 auto 18px; }
.review-stage { display: inline-block; padding: 5px 12px; border-radius: 20px; background: #edf2e9; color: #526957; font-size: 12px; }
.review-placeholder h2 { font-size: 24px; line-height: 1.7; font-weight: 600; margin-top: 24px; }
.review-status { font-size: 16px; margin: 14px 0; }
.review-description { font-size: 14px; color: #647260; line-height: 1.9; margin: 0 0 28px; }
@media (max-width: 640px) { .review-section { padding-top: 28px; padding-bottom: 36px; }.review-placeholder { padding: 32px 24px; }.review-placeholder h2 { font-size: 21px; } }
</style>
