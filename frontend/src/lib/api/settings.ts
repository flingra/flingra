import { apiRequest, ensureCsrfHeaders } from './client'

export interface DeviceSession {
  id: string
  device: string
  lastActive: string
  current: boolean
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiRequest<void>('/settings/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ currentPassword, newPassword }),
  })
}

export async function listSessions(): Promise<DeviceSession[]> {
  return apiRequest<DeviceSession[]>('/settings/sessions')
}

export async function revokeSession(id: string): Promise<void> {
  await apiRequest<void>(`/settings/sessions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: await ensureCsrfHeaders(),
  })
}

export async function requestDataExport(): Promise<{ requestId: string; status: string }> {
  return apiRequest('/settings/data-export', { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function requestAccountDeletion(): Promise<{ requestId: string; status: string }> {
  return apiRequest('/settings/account/delete', { method: 'POST', headers: await ensureCsrfHeaders() })
}
