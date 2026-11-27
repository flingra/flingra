import { apiRequest, ensureCsrfHeaders } from './client'
import { type BlockedAccount, type EmergencyContact, type ReportReason, type SafetyCheckIn } from './types'

export interface ReportInput {
  targetId: string
  reason: ReportReason
  description?: string
  alsoBlock: boolean
}

export async function reportMember(input: ReportInput): Promise<void> {
  await apiRequest<unknown>('/safety/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify(input),
  })
  if (input.alsoBlock) {
    await blockMember(input.targetId)
  }
}

/**
 * Blocking still happens immediately for the blocker's own protection — that's a
 * safety invariant, not something to trade away. On top of that, every block also
 * files an admin review request: repeat or serious reports can lead to the
 * reported account being banned after investigation.
 */
export async function blockMember(targetId: string): Promise<void> {
  await apiRequest<void>('/safety/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ targetId }),
  })
}

export async function unblockMember(targetId: string): Promise<void> {
  await apiRequest<void>(`/safety/blocks/${encodeURIComponent(targetId)}`, {
    method: 'DELETE',
    headers: await ensureCsrfHeaders(),
  })
}

export async function listBlocked(): Promise<BlockedAccount[]> {
  return apiRequest<BlockedAccount[]>('/safety/blocks')
}

export interface EmergencyContactInput {
  name: string
  phone: string
  relationship: string
}

export async function listEmergencyContacts(): Promise<EmergencyContact[]> {
  return apiRequest<EmergencyContact[]>('/safety/emergency-contacts')
}

export async function addEmergencyContact(input: EmergencyContactInput): Promise<EmergencyContact> {
  return apiRequest<EmergencyContact>('/safety/emergency-contacts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify(input),
  })
}

export async function removeEmergencyContact(id: string): Promise<void> {
  await apiRequest<void>(`/safety/emergency-contacts/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: await ensureCsrfHeaders(),
  })
}

export async function listSafetyCheckIns(): Promise<SafetyCheckIn[]> {
  return apiRequest<SafetyCheckIn[]>('/safety/check-ins')
}

/** Submits a safety check-in; contact delivery depends on the backend SMS provider configuration. */
export async function notifyEmergencyContacts(message: string, locationLink?: string): Promise<SafetyCheckIn> {
  return apiRequest<SafetyCheckIn>('/safety/check-ins', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ message: message.trim() || undefined, locationLink }),
  })
}

/** Wraps the browser Geolocation API as a promise; resolves `null` on denial/failure. */
export function getCurrentLocationLink(): Promise<string | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(null)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        resolve(`https://maps.google.com/?q=${latitude},${longitude}`)
      },
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000 },
    )
  })
}
