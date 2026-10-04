<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { changePassword, profile, saveNickname } from '../session'

const nickname = ref(profile.value?.nickname || '')
const nicknamePending = ref(false)
const nicknameMessage = ref('')
const nicknameSaved = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const passwordPending = ref(false)
const passwordMessage = ref('')
let active = true
onBeforeUnmount(() => { active = false })
watch(() => profile.value?.nickname, value => {
  if (!nicknamePending.value) nickname.value = value || ''
})

async function updateNickname() {
  if (nicknamePending.value) return
  nicknameSaved.value = false
  const value = nickname.value.trim()
  if (Array.from(value).length < 1 || Array.from(value).length > 30) {
    nicknameMessage.value = '昵称需要 1～30 个字符。'
    return
  }
  nicknamePending.value = true
  nicknameMessage.value = ''
  const result = await saveNickname(value)
  if (!active) return
  nicknamePending.value = false
  if (result.ok) {
    nickname.value = result.data.nickname
    nicknameSaved.value = true
    nicknameMessage.value = '昵称已保存。'
  } else nicknameMessage.value = result.message
}

async function updatePassword() {
  if (passwordPending.value) return
  if (Array.from(newPassword.value).length < 12 || Array.from(newPassword.value).length > 128) {
    passwordMessage.value = '新密码需要 12～128 个字符，空格也会保留。'
    return
  }
  passwordPending.value = true
  passwordMessage.value = ''
  const result = await changePassword(oldPassword.value, newPassword.value)
  if (!active) return
  passwordPending.value = false
  oldPassword.value = ''
  newPassword.value = ''
  if (!result.ok) passwordMessage.value = result.message
}
</script>

<template>
  <form @submit.prevent="updateNickname">
    <label for="profile-nickname">昵称</label>
    <input id="profile-nickname" v-model="nickname" type="text" autocomplete="nickname" required :disabled="nicknamePending">
    <p class="field-help">1～30 个字符，可以与其他用户重名。</p>
    <p v-if="nicknameMessage" :role="nicknameSaved ? 'status' : 'alert'" class="form-message" :class="{ success: nicknameSaved }">{{ nicknameMessage }}</p>
    <button class="primary-button" type="submit" :disabled="nicknamePending" :aria-busy="nicknamePending">{{ nicknamePending ? '正在保存…' : '保存昵称' }}</button>
  </form>
  <h2>修改密码</h2>
  <form @submit.prevent="updatePassword">
    <label for="old-password">旧密码</label>
    <input id="old-password" v-model="oldPassword" type="password" autocomplete="current-password" required :disabled="passwordPending">
    <label for="change-new-password">新密码</label>
    <input id="change-new-password" v-model="newPassword" type="password" autocomplete="new-password" required :disabled="passwordPending" aria-describedby="change-password-help">
    <p id="change-password-help" class="field-help">12～128 个字符，空格也会保留。成功后所有设备都需重新登录。</p>
    <p v-if="passwordMessage" role="alert" class="form-message">{{ passwordMessage }}</p>
    <button class="primary-button" type="submit" :disabled="passwordPending" :aria-busy="passwordPending">{{ passwordPending ? '正在更新…' : '修改密码并重新登录' }}</button>
  </form>
</template>
