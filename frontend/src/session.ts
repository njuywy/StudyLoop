import { ref } from 'vue'

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'https://124.220.147.193/api/v1').replace(/\/$/, '')

export type Profile = { id: string; email: string; nickname: string; role: string }
const storedToken = sessionStorage.getItem('studyloop_session') || ''
const storedExpiry = Date.parse(sessionStorage.getItem('studyloop_session_expires_at') || '')
export const token = ref(storedToken && storedExpiry > Date.now() ? storedToken : '')
export const profile = ref<Profile | null>(null)
export const sessionExpired = ref(Boolean(storedToken && storedExpiry <= Date.now()))
let expiryTimer: ReturnType<typeof setTimeout> | undefined
let sessionVersion = 0

function expireSession() {
  clearSession()
  sessionExpired.value = true
}

function scheduleExpiry(expiresAt: number) {
  const scheduledVersion = sessionVersion
  expiryTimer = setTimeout(() => {
    if (sessionVersion === scheduledVersion) expireSession()
  }, Math.max(0, expiresAt - Date.now()))
}

if (!token.value) {
  sessionStorage.removeItem('studyloop_session')
  sessionStorage.removeItem('studyloop_session_expires_at')
} else {
  scheduleExpiry(storedExpiry)
}

export function clearSession() {
  sessionVersion++
  sessionStorage.removeItem('studyloop_session')
  sessionStorage.removeItem('studyloop_session_expires_at')
  if (expiryTimer) clearTimeout(expiryTimer)
  expiryTimer = undefined
  token.value = ''
  profile.value = null
  sessionExpired.value = false
}

export function saveSession(value: string, user: Profile, expiresAt: string) {
  sessionVersion++
  sessionStorage.setItem('studyloop_session', value)
  sessionStorage.setItem('studyloop_session_expires_at', expiresAt)
  token.value = value
  profile.value = user
  sessionExpired.value = false
  if (expiryTimer) clearTimeout(expiryTimer)
  scheduleExpiry(Date.parse(expiresAt))
}

type Result<T> = { ok: true; data: T } | { ok: false; status: number; message: string }

async function request<T>(path: string, options: RequestInit = {}, useToken = true): Promise<Result<T>> {
  const requestToken = token.value
  const requestVersion = sessionVersion
  const isCurrentSession = () => !useToken || (sessionVersion === requestVersion && token.value === requestToken)
  const stale = (): Result<T> => ({ ok: false, status: -1, message: '' })
  try {
    const response = await fetch(`${apiBase}${path}`, {
      ...options, cache: 'no-store', signal: AbortSignal.timeout(15000),
      headers: { ...(options.headers || {}), ...(useToken ? { Authorization: `Bearer ${requestToken}` } : {}) },
    })
    if (!isCurrentSession()) return stale()
    const data: unknown = await response.json()
    if (!isCurrentSession()) return stale()
    if (response.status === 401 && useToken) clearSession()
    if (!response.ok) {
      const code = typeof data === 'object' && data !== null && 'code' in data ? data.code : ''
      return { ok: false, status: response.status, message: code === 'RATE_LIMITED' ? '登录尝试过于频繁，请稍后重试。' : response.status === 401 ? '邮箱或密码错误，或登录状态已失效。' : '请求暂未完成，请稍后重试。' }
    }
    return { ok: true, data: data as T }
  } catch {
    if (!isCurrentSession()) return stale()
    return { ok: false, status: 0, message: '网络连接暂不可用，请检查网络后重试。' }
  }
}

export async function login(email: string, password: string) {
  const requestVersion = sessionVersion
  const result = await request<{ token: string; expires_at: string; user: Profile }>(
    '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: email.trim(), password }) }, false,
  )
  if (requestVersion !== sessionVersion) return { ok: false as const, status: -1, message: '登录状态已变化，请重试。' }
  if (result.ok) saveSession(result.data.token, result.data.user, result.data.expires_at)
  return result
}

export async function loadProfile() {
  const requestVersion = sessionVersion
  const result = await request<Profile>('/me')
  if (result.ok && requestVersion !== sessionVersion) return { ok: false as const, status: -1, message: '' }
  if (result.ok) profile.value = result.data
  return result
}

export async function logout() {
  if (!token.value) return { ok: true as const }
  const logoutToken = token.value
  const result = await request<{ code: string }>('/auth/logout', { method: 'POST' })
  if (token.value && token.value !== logoutToken) return { ok: true as const, superseded: true }
  if (result.ok || result.status === 401) {
    if (token.value) clearSession()
    return { ok: true as const }
  }
  if (result.status === -1) return { ok: true as const, superseded: true }
  return { ok: false as const, message: result.message }
}
