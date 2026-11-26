import { ApiError } from './types'

const API_BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
let csrfToken: string | null = null

export type AdminRole = 'super_admin' | 'reviewer' | 'safety_admin' | 'auditor'
export interface AdminSession { adminId: string; email: string; role: AdminRole }
export interface AdminAccount { adminId: string; email: string; role: AdminRole; disabled: boolean; createdAt: string }
export interface ReviewItem {
  reviewId: string
  type: string
  accountId: string
  displayName: string | null
  status: string
  documentType: string | null
  createdAt: string
}
export interface SafetyReviewItem {
  reviewId: string
  targetId: string
  targetName: string | null
  reporterId: string | null
  reason: string
  status: string
  createdAt: string
}
export interface MeetupDisputeItem {
  paymentId: string
  fromId: string
  fromName: string | null
  toId: string
  toName: string | null
  amountNaira: number
  status: string
  reason: string | null
  createdAt: string
}

/** Both disputes and safety-review list responses are a dict of arrays (grouped or single-keyed) rather than the usual `{ items }` shape — flatten whatever's there instead of guessing the exact key. */
function flattenArrayDict<T>(payload: Record<string, unknown>): T[] {
  return Object.values(payload).filter((value): value is T[] => Array.isArray(value)).flat()
}

function csrfHeaders(): HeadersInit {
  if (csrfToken) return { 'X-CSRF-Token': csrfToken }
  const token = document.cookie.split('; ').find((cookie) => cookie.startsWith('flingra_admin_csrf='))?.split('=').slice(1).join('=')
  return token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {}
}

export async function adminRequest<T>(path: string, init: RequestInit = {}, retryCsrf = true): Promise<T> {
  if (!API_BASE_URL) throw new ApiError('API_NOT_CONFIGURED', 'The frontend API URL is not configured.')
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.method && init.method !== 'GET') Object.entries(csrfHeaders()).forEach(([key, value]) => headers.set(key, value))
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: 'include', headers })
  const responseCsrfToken = response.headers.get('X-CSRF-Token')
  if (responseCsrfToken) csrfToken = responseCsrfToken
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null
    if (retryCsrf && body?.error?.code === 'CSRF_FAILED') {
      await adminRequest('/admin/auth/session', {}, false)
      return adminRequest<T>(path, init, false)
    }
    throw new ApiError(body?.error?.code ?? 'REQUEST_FAILED', body?.error?.message ?? 'The request could not be completed.')
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** For the one admin endpoint that returns a raw file (the verification document image), not JSON. */
export async function adminRequestBlob(path: string): Promise<Blob> {
  if (!API_BASE_URL) throw new ApiError('API_NOT_CONFIGURED', 'The frontend API URL is not configured.')
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', headers: { Accept: '*/*' } })
  if (!response.ok) throw new ApiError('REQUEST_FAILED', 'Could not load the document.')
  return response.blob()
}

export const adminApi = {
  login: (body: { email: string; password: string }) => adminRequest<AdminSession>('/admin/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  session: () => adminRequest<AdminSession | null>('/admin/auth/session'),
  logout: async () => {
    await adminRequest<void>('/admin/auth/logout', { method: 'POST' })
    csrfToken = null
  },
  accounts: () => adminRequest<{ items: AdminAccount[]; nextOffset: number | null }>('/admin/admins'),
  createAccount: (body: { email: string; password: string; role: AdminRole }) => adminRequest<AdminAccount>('/admin/admins', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  updateAccount: (id: string, body: { role?: AdminRole; disabled?: boolean }) => adminRequest<AdminAccount>(`/admin/admins/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  reviews: () => adminRequest<{ items: ReviewItem[]; nextOffset: number | null }>('/admin/reviews'),
  getReview: (id: string) => adminRequest<Record<string, unknown>>(`/admin/reviews/${id}`),
  reviewDocumentBlob: (id: string) => adminRequestBlob(`/admin/reviews/${id}/document`),
  decide: (id: string, decision: 'approved' | 'rejected', reason: string) => adminRequest(`/admin/reviews/${id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason }) }),
  audit: (accountId: string) => adminRequest<{ items: Array<{ eventType: string; outcome: string; createdAt: string; metadata: unknown }> }>(`/admin/users/${accountId}/audit`),
  safetyReviews: async (status: 'open' | 'reviewed' | 'dismissed' | 'all' = 'open') =>
    flattenArrayDict<SafetyReviewItem>(await adminRequest<Record<string, unknown>>(`/admin/safety/reviews?status=${status}`)),
  decideSafetyReview: (id: string, decision: 'reviewed' | 'dismissed', reason: string) =>
    adminRequest(`/admin/safety/reviews/${id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason }) }),
  meetupDisputes: async () => flattenArrayDict<MeetupDisputeItem>(await adminRequest<Record<string, unknown>>('/admin/meetup-payments/disputes')),
  resolveMeetupDispute: (paymentId: string, resolution: 'release' | 'refund', reason: string) =>
    adminRequest(`/admin/meetup-payments/${paymentId}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution, reason }) }),
}
