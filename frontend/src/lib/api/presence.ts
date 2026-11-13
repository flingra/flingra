import { STATUSES, liveStreamStore, statusStore } from './mock-db'

/**
 * Synchronous read of a member's status/live state for avatar decoration. Not
 * wrapped in `delay()` like the rest of the mock API: this backs a purely
 * visual indicator rendered for every avatar on screen, not a data fetch.
 */
export function getPresence(authorId: string) {
  const hasStatus =
    STATUSES.some((status) => status.authorId === authorId) || statusStore.statuses.some((status) => status.authorId === authorId)
  const stream = liveStreamStore.streams.find(
    (candidate) => candidate.hostId === authorId || candidate.participantIds.includes(authorId),
  )
  return { hasStatus, isLive: Boolean(stream), streamId: stream?.id }
}
