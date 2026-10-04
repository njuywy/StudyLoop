<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { avatarError, loadAvatar, loadProfile, profile, token } from '../session'
import UserAvatar from './UserAvatar.vue'

const busy = ref(false)
const error = ref('')
let refreshVersion = 0
onBeforeUnmount(() => { refreshVersion++ })

async function refresh() {
  const version = ++refreshVersion
  busy.value = true
  error.value = ''
  const result = await loadProfile()
  if (version !== refreshVersion || (!result.ok && result.status === -1)) return
  busy.value = false
  if (!result.ok && result.status !== 401) error.value = result.message
}

watch(token, value => {
  refreshVersion++
  busy.value = false
  error.value = ''
  if (value && !profile.value) void refresh()
}, { immediate: true })
</script>

<template>
  <section v-if="token" class="workspace section-width" aria-labelledby="workspace-title">
    <div class="workspace-heading"><div><span class="section-kicker">你的学习空间</span><h1 id="workspace-title">个人工作台</h1></div><span class="workspace-label">STUDY / REVISIT / GROW</span></div>
    <div v-if="busy" class="workspace-state" role="status">正在读取账号信息…</div>
    <div v-else-if="error" class="workspace-state"><p class="form-message" role="alert">{{ error }}</p><button class="small-button" @click="refresh">重试读取资料</button></div>
    <template v-else-if="profile">
      <div class="welcome-panel">
        <div class="welcome-identity"><UserAvatar /><div><span class="welcome-kicker">欢迎回来</span><h2>{{ profile.nickname }}</h2><p class="welcome-email">邮箱：{{ profile.email }}</p></div></div>
        <div class="welcome-message"><span aria-hidden="true">↺</span><p>给知识一次回响，<br>给自己一点成长。</p></div>
        <p v-if="avatarError" class="avatar-notice" role="alert">{{ avatarError }} <button class="retry" @click="loadAvatar">重试读取头像</button></p>
      </div>
      <div class="workspace-section-heading"><h2>从这里继续</h2><p>你的账号已就绪，学习空间正在慢慢生长。</p></div>
      <div class="workspace-grid">
        <RouterLink class="workspace-card review-card" to="/review"><span class="workspace-icon" aria-hidden="true">↺</span><span class="workspace-badge">建设中</span><h3>在线复习</h3><p>让学过的知识，再次变得清晰。<br>复习功能正在建设中，敬请期待。</p><span class="workspace-action">进入复习页面 <span aria-hidden="true">→</span></span></RouterLink>
        <RouterLink class="workspace-card" to="/profile"><span class="workspace-icon" aria-hidden="true">☺</span><h3>个人中心</h3><p>换一张头像，更新你的昵称，<br>也照顾好账号的安全。</p><span class="workspace-action">维护个人资料 <span aria-hidden="true">→</span></span></RouterLink>
        <RouterLink v-if="profile.role === 'admin'" class="workspace-card" to="/admin/users"><span class="workspace-icon" aria-hidden="true">☷</span><span class="workspace-badge">管理员</span><h3>用户管理</h3><p>查看平台用户，<br>管理账号的启用状态。</p><span class="workspace-action">管理用户 <span aria-hidden="true">→</span></span></RouterLink>
      </div>
      <p class="workspace-note">每一次回顾，都是新的开始。</p>
    </template>
  </section>
  <template v-else>
  <section class="hero section-width">
    <div class="hero-copy">
      <div class="eyebrow"><span></span> 一个关于持续学习的新开始</div>
      <h1>学过的知识，<br>值得<span class="accent-text">再见一面。</span></h1>
      <p class="hero-description">让每一次回顾，都成为新的进步。<br>StudyLoop 正在为你的在线复习旅程，搭好第一步。</p>
      <div class="hero-actions">
        <RouterLink class="primary-button" to="/review">探索在线复习 <span aria-hidden="true">→</span></RouterLink>
        <RouterLink class="text-link" to="/register">认识你的学习空间 <span aria-hidden="true">↗</span></RouterLink>
      </div>
      <div class="launch-note"><span class="note-dot"></span>邮箱注册与登录已开放 · 复习功能建设中</div>
    </div>
    <div class="study-visual" aria-hidden="true">
      <div class="visual-orbit orbit-one"></div><div class="visual-orbit orbit-two"></div>
      <span class="visual-spark spark-one">✳</span><span class="visual-spark spark-two">+</span>
      <div class="study-card">
        <div class="card-topline"><span>THE STUDY LOOP</span><span class="card-dot"></span></div>
        <div class="loop-illustration">
          <svg viewBox="0 0 240 160"><path class="loop-stroke" d="M61 92c-26 0-33-55 9-55 44 0 59 88 100 88 40 0 43-62 12-62-39 0-64 62-100 62"/><path class="loop-arrow" d="m74 116 10 10-14 7"/></svg>
          <span class="loop-label label-remember">理解</span><span class="loop-label label-revisit">回顾</span><span class="loop-label label-grow">内化</span>
        </div>
        <div class="card-quote">温故，而知新。</div><div class="card-rule"></div>
        <p>不是匆忙地向前，<br>而是让每一步，都留下回响。</p>
        <div class="card-bottomline"><span>LEARN. REVISIT. GROW.</span><span>↗</span></div>
      </div>
      <div class="floating-note"><span>↺</span><div>回顾，是学习的一部分<small>Make room for another look.</small></div></div>
    </div>
  </section>
  <section class="foundation section-width" aria-labelledby="foundation-title">
    <div class="section-heading"><div><span class="section-kicker">从这里开始</span><h2 id="foundation-title">为更好的复习，准备一个空间。</h2></div><span class="stage-label">首期建设中</span></div>
    <div class="feature-grid">
      <RouterLink class="feature-card" to="/register"><span class="feature-number">01 /</span><h3>拥有自己的账号 <span aria-hidden="true">↗</span></h3><p>邮箱注册并完成验证，<br>从一个属于你的账号开始。</p><span class="feature-tag">开始注册</span></RouterLink>
      <RouterLink class="feature-card" to="/profile"><span class="feature-number">02 /</span><h3>找到自己的节奏 <span aria-hidden="true">↗</span></h3><p>个人中心与资料维护，<br>让学习空间带上你的名字。</p><span class="feature-tag">维护资料</span></RouterLink>
      <RouterLink class="feature-card" to="/review"><span class="feature-number">03 /</span><h3>与知识再次相遇 <span aria-hidden="true">↗</span></h3><p>在线复习入口已预留，<br>接下来，一起把学习变成习惯。</p><span class="feature-tag">准备中</span></RouterLink>
    </div>
  </section>
  </template>
</template>

<style scoped>
.workspace { padding-top: 48px; padding-bottom: 48px; }
.workspace-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.workspace-heading h1 { margin: 8px 0 0; font-size: clamp(28px, 3vw, 36px); letter-spacing: -.8px; }
.workspace-label { font-size: 11px; letter-spacing: 2px; color: #6b7d70; }
.workspace-state { padding: 40px; background: #fffefa; border: 1px solid #dfe5dc; border-radius: 18px; }
.welcome-panel { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 28px; padding: 36px; background: #eaf0e5; border: 1px solid #d8e2d2; border-radius: 20px; }
.welcome-identity { display: flex; align-items: center; gap: 22px; min-width: 0; flex: 1; }
.welcome-identity > div { min-width: 0; }
.welcome-identity :deep(.user-avatar) { width: 76px; height: 76px; border: 4px solid #fffefa; }
.welcome-kicker { color: #526957; font-size: 14px; }
.welcome-identity h2 { font-size: 27px; font-weight: 650; overflow-wrap: anywhere; margin: 7px 0; }
.welcome-email { color: #526957; font-size: 14px; overflow-wrap: anywhere; margin: 0; }
.welcome-message { display: flex; align-items: center; gap: 16px; color: #526957; }
.welcome-message > span { font-size: 46px; color: #69876a; }
.welcome-message p { font-size: 14px; line-height: 1.9; }
.avatar-notice { flex-basis: 100%; margin: 0; font-size: 14px; }
.workspace-section-heading { margin: 36px 0 20px; }
.workspace-section-heading h2 { font-size: 22px; font-weight: 600; }
.workspace-section-heading p { font-size: 14px; color: #677365; line-height: 1.8; margin: 8px 0; }
.workspace-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr)); gap: 20px; }
.workspace-card { position: relative; display: flex; flex-direction: column; min-width: 0; border: 1px solid #dce4d8; background: #fffefa; border-radius: 16px; padding: 26px; transition: border-color .2s, box-shadow .2s; }
.workspace-card:hover { border-color: #8da68d; box-shadow: 0 8px 24px #263c3210; }
.workspace-icon { display: grid; place-items: center; width: 44px; height: 44px; background: #edf2e9; color: #315e45; border-radius: 12px; font-size: 27px; }
.workspace-badge { position: absolute; right: 24px; top: 31px; padding: 4px 9px; font-size: 12px; color: #526957; background: #eef2e9; border-radius: 20px; }
.workspace-card h3 { font-size: 20px; margin: 22px 0 10px; font-weight: 600; }
.workspace-card p { font-size: 14px; color: #647260; line-height: 1.9; margin: 0 0 26px; }
.workspace-action { display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid #e5eadd; padding-top: 18px; margin-top: auto; color: #315e45; font-size: 14px; font-weight: 550; }
.review-card { background: #f2f5ed; }
.workspace-note { text-align: center; color: #647260; font-size: 13px; margin: 32px 0 0; }
@media (max-width: 640px) {
  .workspace { padding-top: 28px; padding-bottom: 32px; }
  .workspace-heading { margin-bottom: 20px; }
  .workspace-label, .welcome-message { display: none; }
  .welcome-panel { padding: 24px 20px; }
  .welcome-identity { align-items: flex-start; gap: 14px; }
  .welcome-identity :deep(.user-avatar) { width: 56px; height: 56px; }
  .welcome-identity h2 { font-size: 22px; }
  .welcome-email { font-size: 13px; }
  .workspace-section-heading { margin-top: 28px; }
  .workspace-card { padding: 24px; }
}
</style>
