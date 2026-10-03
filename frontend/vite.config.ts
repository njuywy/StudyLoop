import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  const apiUrl = new URL(env.VITE_API_BASE_URL || 'https://124.220.147.193/api/v1')
  if (
    !['http:', 'https:'].includes(apiUrl.protocol) ||
    apiUrl.username || apiUrl.password || apiUrl.search || apiUrl.hash ||
    (command === 'build' && apiUrl.protocol !== 'https:')
  ) {
    throw new Error('API base must be an HTTP(S) URL without credentials; production requires HTTPS')
  }
  return { plugins: [vue()], base: '/StudyLoop/' }
})
