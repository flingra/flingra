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
  sourceType: string
  sourceId: string
  targetId: string
  targetName: string | null
  requesterId: string
  requesterName: string | null
  reason: string
  status: string
  createdAt: string
}
export interface MeetupDisputeItem {
  id: string
  payerId: string
  payerName: string
  recipientId: string
  recipientName: string
  amountNaira: number
  reason: string
  openedBy: string
  createdAt: string
  updatedAt: string
}

export interface AdminUser {
  accountId: string
  email: string | null
  displayName: string | null
  accountStatus: string
  emailVerified: boolean
  moderationStatus: string | null
  documentVerification: string | null
  createdAt: string
}

export interface AdminSafetyReport {
  reportId: string
  reporterId: string
  reporterName: string | null
  targetId: string
  targetName: string | null
  reason: string
  description: string | null
  status: string
  createdAt: string
}

export interface AdminPrivacyRequest {
  requestId: string
  accountId: string
  email: string | null
  requestType: string
  status: string
  createdAt: string
  updatedAt: string
}

export interface AdminPayout {
  payoutId: string
  accountId: string
  email: string | null
  reference: string
  amountKobo: number
  status: string
  transferCode: string | null
  createdAt: string
  updatedAt: string
}

export interface AdminAuditEvent {
  id: string
  eventType: string
  actorType: string
  actorId: string | null
  accountId: string | null
  outcome: string
  requestId: string
  metadata: unknown
  createdAt: string
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
  login: (body: { email: string; password: string; mfaCode?: string }) => adminRequest<AdminSession>('/admin/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  session: () => adminRequest<AdminSession | null>('/admin/auth/session'),
  mfaStatus: () => adminRequest<{ enabled: boolean }>('/admin/auth/mfa/status'),
  setupMfa: () => adminRequest<{ secret: string; provisioningUri: string }>('/admin/auth/mfa/setup', { method: 'POST' }),
  enableMfa: (code: string) => adminRequest<{ enabled: boolean }>('/admin/auth/mfa/enable', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) }),
  disableMfa: (code: string) => adminRequest<{ enabled: boolean }>('/admin/auth/mfa/disable', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) }),
  changePassword: (currentPassword: string, newPassword: string) =>
    adminRequest<{ status: string }>('/admin/auth/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ currentPassword, newPassword }) }),
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
  safetyReviews: async (status: 'open' | 'reviewed' | 'dismissed' | 'all' = 'open') => {
    const response = await adminRequest<{ items: Array<Record<string, unknown>> }>(`/admin/safety/reviews?status=${status}`)
    return response.items.map((item) => ({
      reviewId: String(item.id),
      sourceType: String(item.sourceType),
      sourceId: String(item.sourceId),
      targetId: String(item.targetId),
      targetName: typeof item.targetName === 'string' ? item.targetName : null,
      requesterId: String(item.requesterId),
      requesterName: typeof item.requesterName === 'string' ? item.requesterName : null,
      reason: String(item.reason),
      status: String(item.status),
      createdAt: String(item.createdAt),
    })) as SafetyReviewItem[]
  },
  decideSafetyReview: (id: string, decision: 'reviewed' | 'dismissed', reason: string) =>
    adminRequest(`/admin/safety/reviews/${id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason }) }),
  meetupDisputes: async () => {
    const response = await adminRequest<{ items: MeetupDisputeItem[] }>('/admin/meetup-payments/disputes')
    return response.items
  },
  resolveMeetupDispute: (id: string, resolution: 'release' | 'refund', reason: string) =>
    adminRequest(`/admin/meetup-payments/${id}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution, reason }) }),
  users: (search = '') => adminRequest<{ items: AdminUser[]; nextOffset: number | null }>(`/admin/users${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  setUserStatus: (accountId: string, status: 'active' | 'suspended' | 'banned', reason: string) =>
    adminRequest(`/admin/users/${accountId}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, reason }) }),
  adjustWallet: (accountId: string, amountKobo: number, reason: string) =>
    adminRequest<{ accountId: string; balanceKobo: number }>(`/admin/users/${accountId}/wallet-adjustments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ amountKobo, reason }) }),
  adjustCallCredits: (accountId: string, amount: number, reason: string) =>
    adminRequest<{ accountId: string; balance: number }>(`/admin/users/${accountId}/call-credit-adjustments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ amount, reason }) }),
  dashboard: () =>
    adminRequest<Record<string, number>>('/admin/dashboard'),
  revokeUserSessions: (accountId: string) =>
    adminRequest<{ revokedCount: number }>(`/admin/users/${accountId}/sessions/revoke`, { method: 'POST' }),
  safetyReports: (status: 'open' | 'reviewed' | 'dismissed' | 'all' = 'open') =>
    adminRequest<{ items: AdminSafetyReport[]; nextOffset: number | null }>(`/admin/safety/reports?status=${status}`),
  decideSafetyReport: (reportId: string, decision: 'reviewed' | 'dismissed', reason: string) =>
    adminRequest(`/admin/safety/reports/${reportId}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason }) }),
  privacyRequests: (status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled' | 'all' = 'queued') =>
    adminRequest<{ items: AdminPrivacyRequest[]; nextOffset: number | null }>(`/admin/privacy/requests?status=${status}`),
  retryPrivacyRequest: (requestId: string) =>
    adminRequest(`/admin/privacy/requests/${requestId}/retry`, { method: 'POST' }),
  payouts: (status = '') =>
    adminRequest<{ items: AdminPayout[]; nextOffset: number | null }>(`/admin/payouts${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  giftCatalog: () =>
    adminRequest<{ items: Array<{ id: string; name: string; emoji: string; priceKobo: number; active: boolean }> }>('/admin/gift-catalog'),
  createGift: (body: { id: string; name: string; emoji: string; priceKobo: number }) =>
    adminRequest('/admin/gift-catalog', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, price_kobo: body.priceKobo }) }),
  updateGift: (id: string, body: { name?: string; emoji?: string; priceKobo?: number; active?: boolean }) =>
    adminRequest(`/admin/gift-catalog/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, price_kobo: body.priceKobo }) }),
  subscriptionPlans: () =>
    adminRequest<{ items: Array<{ id: string; name: string; durationDays: number; priceKobo: number; active: boolean }> }>('/admin/subscription-plans'),
  updateSubscriptionPlan: (id: string, body: { active?: boolean; name?: string; durationDays?: number; priceKobo?: number }) =>
    adminRequest(`/admin/subscription-plans/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, duration_days: body.durationDays, price_kobo: body.priceKobo }) }),
  subscriptions: () =>
    adminRequest<{ items: Array<{ accountId: string; email: string | null; displayName: string | null; tier: string; expiresAt: string | null }> }>('/admin/subscriptions'),
  updateUserSubscription: (accountId: string, tier: 'free' | 'vip', expiresAt: string | null, reason: string) =>
    adminRequest(`/admin/users/${accountId}/subscription`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tier, expires_at: expiresAt, reason }) }),
  liveStreams: () =>
    adminRequest<{ items: Array<{ streamId: string; hostId: string; hostName: string | null; title: string; status: string; startedAt: string }> }>('/admin/live-streams'),
  endLiveStream: (streamId: string) =>
    adminRequest(`/admin/live-streams/${streamId}/end`, { method: 'POST' }),
  contentPosts: () =>
    adminRequest<{ items: Array<{ postId: string; authorId: string; authorName: string | null; caption: string | null; createdAt: string }> }>('/admin/content/posts'),
  removePost: (postId: string) =>
    adminRequest(`/admin/content/posts/${postId}`, { method: 'DELETE' }),
  contentStatuses: () =>
    adminRequest<{ items: Array<{ statusId: string; authorId: string; authorName: string | null; mediaKind: string; createdAt: string; expiresAt: string }> }>('/admin/content/statuses'),
  removeStatus: (statusId: string) =>
    adminRequest(`/admin/content/statuses/${statusId}`, { method: 'DELETE' }),
  auditEvents: (params: { eventType?: string; outcome?: string; accountId?: string } = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1])))
    return adminRequest<{ items: AdminAuditEvent[]; nextOffset: number | null }>(`/admin/audit/events${query.size ? `?${query}` : ''}`)
  },
}
