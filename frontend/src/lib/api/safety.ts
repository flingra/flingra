import { delay } from './client'
import { adminReviewStore, blockedStore, emergencyContactStore, PROFILES, reportStore, safetyCheckInStore } from './mock-db'
import { ApiError, type AdminReviewRequest, type BlockedAccount, type EmergencyContact, type ReportReason, type SafetyCheckIn } from './types'

export interface ReportInput {
  targetId: string
  reason: ReportReason
  description?: string
  alsoBlock: boolean
}

export async function reportMember(input: ReportInput): Promise<void> {
  await delay(undefined, 700)
  reportStore.reports = [
    ...reportStore.reports,
    { id: `report-${reportStore.reports.length + 1}`, targetId: input.targetId, reason: input.reason },
  ]
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
  await delay(undefined, 500)
  const profile = PROFILES.find((item) => item.id === targetId)

  if (!blockedStore.blocked.some((item) => item.id === targetId)) {
    blockedStore.blocked = [
      {
        id: targetId,
        displayName: profile?.displayName ?? 'Member',
        photo: profile?.photos[0] ?? null,
        blockedAt: new Date().toISOString(),
      },
      ...blockedStore.blocked,
    ]
  }

  const review: AdminReviewRequest = {
    id: `review-${Date.now()}`,
    targetId,
    targetName: profile?.displayName ?? 'Member',
    reason: 'Blocked by a member',
    createdAt: new Date().toISOString(),
  }
  adminReviewStore.requests = [review, ...adminReviewStore.requests]
}

export async function unblockMember(targetId: string): Promise<void> {
  await delay(undefined, 500)
  blockedStore.blocked = blockedStore.blocked.filter((item) => item.id !== targetId)
}

export async function listBlocked(): Promise<BlockedAccount[]> {
  await delay(null, 400)
  return blockedStore.blocked
}

export interface EmergencyContactInput {
  name: string
  phone: string
  relationship: string
}

export async function listEmergencyContacts(): Promise<EmergencyContact[]> {
  await delay(null, 300)
  return emergencyContactStore.contacts
}

export async function addEmergencyContact(input: EmergencyContactInput): Promise<EmergencyContact> {
  await delay(null, 500)
  if (!input.name.trim() || !input.phone.trim()) {
    throw new ApiError('INVALID_CONTACT', 'Enter a name and phone number.')
  }
  const contact: EmergencyContact = { id: `contact-${Date.now()}`, ...input }
  emergencyContactStore.contacts = [...emergencyContactStore.contacts, contact]
  return contact
}

export async function removeEmergencyContact(id: string): Promise<void> {
  await delay(undefined, 400)
  emergencyContactStore.contacts = emergencyContactStore.contacts.filter((item) => item.id !== id)
}

export async function listSafetyCheckIns(): Promise<SafetyCheckIn[]> {
  await delay(null, 300)
  return [...safetyCheckInStore.checkIns].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

/**
 * Simulates alerting emergency contacts — no real SMS/call goes out from this mock
 * frontend. A real integration (Termii, Twilio, etc.) is backend work.
 */
export async function notifyEmergencyContacts(message: string, locationLink?: string): Promise<SafetyCheckIn> {
  await delay(null, 800)
  if (emergencyContactStore.contacts.length === 0) {
    throw new ApiError('NO_CONTACTS', 'Add at least one emergency contact first.')
  }
  const checkIn: SafetyCheckIn = {
    id: `checkin-${Date.now()}`,
    message: message.trim() || "I'm meeting someone from Flingra. Checking in for my safety.",
    notifiedContacts: emergencyContactStore.contacts.map((contact) => contact.name),
    locationLink,
    createdAt: new Date().toISOString(),
  }
  safetyCheckInStore.checkIns = [checkIn, ...safetyCheckInStore.checkIns]
  return checkIn
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
