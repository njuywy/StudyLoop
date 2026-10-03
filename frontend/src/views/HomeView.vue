<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="hero section-width">
    <div class="hero-copy">
      <div class="eyebrow"><span></span> 一个关于持续学习的新开始</div>
      <h1>学过的知识，<br>值得<span class="accent-text">再见一面。</span></h1>
      <p class="hero-description">让每一次回顾，都成为新的进步。<br>StudyLoop 正在为你的在线复习旅程，搭好第一步。</p>
      <div class="hero-actions">
        <RouterLink class="primary-button" to="/review">探索在线复习 <span aria-hidden="true">→</span></RouterLink>
        <RouterLink class="text-link" to="/register">认识你的学习空间 <span aria-hidden="true">↗</span></RouterLink>
      </div>
      <div class="launch-note"><span class="note-dot"></span>平台基础建设中 · 账号与复习功能即将上线</div>
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
      <RouterLink class="feature-card" to="/register"><span class="feature-number">01 /</span><h3>拥有自己的账号 <span aria-hidden="true">↗</span></h3><p>邮箱注册与登录，<br>从一个属于你的账号开始。</p><span class="feature-tag">准备中</span></RouterLink>
      <RouterLink class="feature-card" to="/profile"><span class="feature-number">02 /</span><h3>找到自己的节奏 <span aria-hidden="true">↗</span></h3><p>个人中心与资料维护，<br>让学习空间带上你的名字。</p><span class="feature-tag">准备中</span></RouterLink>
      <RouterLink class="feature-card" to="/review"><span class="feature-number">03 /</span><h3>与知识再次相遇 <span aria-hidden="true">↗</span></h3><p>在线复习入口已预留，<br>接下来，一起把学习变成习惯。</p><span class="feature-tag">准备中</span></RouterLink>
    </div>
  </section>
</template>
