const apiBase = (import.meta.env.VITE_API_BASE_URL || 'https://124.220.147.193/api/v1').replace(/\/$/, '')

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
