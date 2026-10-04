<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { avatarError, avatarSaving, loadAvatar, uploadAvatar } from '../session'
import UserAvatar from './UserAvatar.vue'

const chosen = ref<File>()
const error = ref('')
const message = ref('')
let active = true
onBeforeUnmount(() => { active = false })

function choose(event: Event) {
  chosen.value = (event.target as HTMLInputElement).files?.[0]
  error.value = ''
  message.value = ''
}

async function submit() {
  error.value = ''
  message.value = ''
  const file = chosen.value
  if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2097152 || !file.size) {
    error.value = '请选择不超过 2 MiB 的 JPEG、PNG 或 WebP。'
    return
  }
  const result = await uploadAvatar(file)
  if (!active || (!result.ok && result.status === -1)) return
  if (result.ok) message.value = '头像已更新。'
  else error.value = result.message
}
</script>

<template>
  <form class="avatar-editor" @submit.prevent="submit">
    <h3>个人头像</h3>
    <UserAvatar />
    <p v-if="avatarError" role="alert">{{ avatarError }} <button type="button" class="text-link" @click="loadAvatar">重试读取头像</button></p>
    <label for="avatar-file">选择头像</label>
    <input id="avatar-file" type="file" accept="image/jpeg,image/png,image/webp" :disabled="avatarSaving" @change="choose" />
    <p class="field-hint">JPEG、PNG 或 WebP，最大 2 MiB，累计像素不超过 1600 万。</p>
    <p v-if="error" class="form-message" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <button class="mode-button" type="submit" :disabled="avatarSaving">{{ avatarSaving ? '正在上传…' : '上传头像' }}</button>
  </form>
</template>
