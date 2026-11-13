import { delay } from './client'
import { adminReviewStore, blockedStore, PROFILES, reportStore } from './mock-db'
import type { AdminReviewRequest, BlockedAccount, ReportReason } from './types'

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
