const apiBase = (import.meta.env.VITE_API_BASE_URL || 'https://124.220.147.193/api/v1').replace(/\/$/, '')

const authMessages: Record<string, string> = {
  REGISTERED: '注册成功，请查看邮箱并在 24 小时内验证。验证后仍需单独登录。',
  ACCOUNT_EXISTS: '该邮箱已注册；尚未验证时，请使用重发验证邮件。',
  MAIL_UNAVAILABLE: '账号已保存，但验证邮件发送失败。请使用重发验证邮件重试。',
  VERIFICATION_REQUEST_ACCEPTED: '请求已受理。如账号符合验证条件，将收到邮件；请检查收件箱及垃圾邮件，重发至少间隔 60 秒。',
  MAIL_SERVICE_UNAVAILABLE: '邮件服务暂不可用，请 60 秒后重试。已有有效链接仍可使用。',
  EMAIL_VERIFIED: '邮箱验证成功。请前往登录页面登录。',
  INVALID_VERIFICATION_TOKEN: '验证链接无效、已使用或已过期，请重新申请邮件。',
  RATE_LIMITED: '请求过于频繁，请稍后重试。重发邮件至少间隔 60 秒。',
  INVALID_INPUT: '请检查邮箱、密码（12～128 个字符）和昵称（最多 30 个字符）。',
  DATABASE_UNAVAILABLE: '平台连接暂不可用，请稍后重试。',
}

export async function submitAuth(action: 'register' | 'resend-verification' | 'verify-email', body: object) {
  try {
    const response = await fetch(`${apiBase}/auth/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body), cache: 'no-store', signal: AbortSignal.timeout(125000),
    })
    const result: unknown = await response.json()
    const code = typeof result === 'object' && result !== null && 'code' in result && typeof result.code === 'string' ? result.code : ''
    return { ok: response.ok, code, message: authMessages[code] || '请求暂未完成，请稍后重试。' }
  } catch {
    return { ok: false, code: 'NETWORK_ERROR', message: '平台连接暂不可用，请稍后重试。若刚刚注册，请先检查邮箱或尝试重发验证邮件。' }
  }
}

export async function checkPlatformConnection(signal: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${apiBase}/health`, { signal, cache: 'no-store' })
    if (!response.ok) return false
    const body: unknown = await response.json()
    return typeof body === 'object' && body !== null && 'status' in body && body.status === 'ok'
  } catch {
    return false
  }
}
