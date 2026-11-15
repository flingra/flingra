import { ApiError } from './types'

const API_BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('API_NOT_CONFIGURED', 'The frontend API URL is not configured.')
  }
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null
    throw new ApiError(body?.error?.code ?? 'REQUEST_FAILED', body?.error?.message ?? 'The request could not be completed.')
  }

  export function csrfHeaders(): HeadersInit {
    const token = document.cookie
      .split('; ')
      .find((cookie) => cookie.startsWith('flingra_csrf='))
      ?.slice('flingra_csrf='.length)
    return token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {}
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function delay<T>(value: T, ms = 500): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

export function fail(ms = 500): Promise<never> {
  return new Promise((_, reject) => setTimeout(reject, ms))
}
