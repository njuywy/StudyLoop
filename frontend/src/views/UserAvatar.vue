<script setup lang="ts">
import { avatarUrl } from '../session'
</script>

<template>
  <img v-if="avatarUrl" class="user-avatar" :src="avatarUrl" alt="我的头像" />
  <svg v-else class="user-avatar default-avatar" viewBox="0 0 40 40" role="img" aria-label="默认头像"><circle cx="20" cy="14" r="7" /><path d="M7 36a13 13 0 0 1 26 0" /></svg>
</template>
