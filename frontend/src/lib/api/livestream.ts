import { delay } from './client'
import { joinRequestStore, liveStreamStore, ownProfileStore, PROFILES, streamMessageStore } from './mock-db'
import { ApiError, type JoinRequest, type LiveStream, type StreamMessage } from './types'
import { simulateReceivedGift } from './wallet'

export const MAX_PARTICIPANTS = 5
export const PREVIEW_SECONDS = 10

export async function listLiveStreams(): Promise<LiveStream[]> {
  await delay(null, 400)
  return liveStreamStore.streams
}

export async function getLiveStream(id: string): Promise<LiveStream> {
  await delay(null, 250)
  const stream = liveStreamStore.streams.find((item) => item.id === id)
  if (!stream) {
    throw new ApiError('STREAM_NOT_FOUND', 'This stream has ended or is unavailable.')
  }
  return stream
}

export async function startStream(title: string): Promise<LiveStream> {
  await delay(null, 600)
  const profile = ownProfileStore.profile
  if (!profile) {
    throw new ApiError('NO_PROFILE', 'Finish your profile before going live.')
  }
  if (profile.identity !== 'woman') {
    throw new ApiError('LIVESTREAM_RESTRICTED', 'Livestreaming is available for female accounts only.')
  }
  const stream: LiveStream = {
    id: `stream-${Date.now()}`,
    hostId: 'me',
    hostName: profile.displayName,
    hostPhoto: profile.photos[0] ?? '',
    hostVideo: profile.videos?.[0]?.url,
    title: title.trim() || `${profile.displayName} is live`,
    startedAt: new Date().toISOString(),
    participantIds: ['me'],
  }
  liveStreamStore.streams = [stream, ...liveStreamStore.streams]
  return stream
}

export async function endStream(id: string): Promise<void> {
  await delay(undefined, 300)
  liveStreamStore.streams = liveStreamStore.streams.filter((item) => item.id !== id)
  joinRequestStore.requests = joinRequestStore.requests.filter((item) => item.streamId !== id)
}

export async function requestToJoin(streamId: string): Promise<void> {
  await delay(undefined, 300)
  const profile = ownProfileStore.profile
  const request: JoinRequest = {
    id: `req-${Date.now()}`,
    streamId,
    requesterId: 'me',
    requesterName: profile?.displayName ?? 'A viewer',
    requesterPhoto: profile?.photos[0] ?? '',
  }
  joinRequestStore.requests = [...joinRequestStore.requests, request]
}

export async function listJoinRequests(streamId: string): Promise<JoinRequest[]> {
  await delay(null, 200)
  return joinRequestStore.requests.filter((item) => item.streamId === streamId)
}

export async function respondToJoinRequest(requestId: string, accept: boolean): Promise<void> {
  await delay(undefined, 300)
  const request = joinRequestStore.requests.find((item) => item.id === requestId)
  joinRequestStore.requests = joinRequestStore.requests.filter((item) => item.id !== requestId)
  if (!request || !accept) return

  const stream = liveStreamStore.streams.find((item) => item.id === request.streamId)
  if (!stream || stream.participantIds.length >= MAX_PARTICIPANTS) return
  liveStreamStore.streams = liveStreamStore.streams.map((item) =>
    item.id === stream.id ? { ...item, participantIds: [...item.participantIds, request.requesterId] } : item,
  )
}

export async function listParticipants(streamId: string): Promise<{ id: string; name: string; photo: string }[]> {
  await delay(null, 150)
  const stream = liveStreamStore.streams.find((item) => item.id === streamId)
  if (!stream) return []
  return stream.participantIds.map((id) => {
    if (id === 'me') {
      const profile = ownProfileStore.profile
      return { id, name: profile?.displayName ?? 'You', photo: profile?.photos[0] ?? '' }
    }
    const member = PROFILES.find((item) => item.id === id)
    return { id, name: member?.displayName ?? 'Guest', photo: member?.photos[0] ?? '' }
  })
}

/** Decorative "who's watching" strip: a stable subset of members not already broadcasting. */
export async function listStreamViewers(streamId: string): Promise<{ id: string; name: string; photo: string }[]> {
  await delay(null, 150)
  const stream = liveStreamStore.streams.find((item) => item.id === streamId)
  if (!stream) return []
  return PROFILES.filter((profile) => !stream.participantIds.includes(profile.id))
    .slice(0, 5)
    .map((profile) => ({ id: profile.id, name: profile.displayName, photo: profile.photos[0] ?? '' }))
}

export async function listStreamMessages(streamId: string): Promise<StreamMessage[]> {
  await delay(null, 150)
  return streamMessageStore.messages.filter((item) => item.streamId === streamId)
}

export async function sendStreamMessage(
  streamId: string,
  text: string,
  kind: StreamMessage['kind'] = 'message',
  giftId?: string,
): Promise<void> {
  await delay(undefined, 150)
  const profile = ownProfileStore.profile
  const message: StreamMessage = {
    id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    streamId,
    authorId: 'me',
    authorName: profile?.displayName ?? 'You',
    kind,
    text,
    giftId,
    createdAt: new Date().toISOString(),
  }
  streamMessageStore.messages = [...streamMessageStore.messages, message]
}

/** Simulates another member asking to join, so the host's accept/decline flow is testable solo. */
export function simulateJoinRequest(streamId: string) {
  const stream = liveStreamStore.streams.find((item) => item.id === streamId)
  if (!stream) return
  const candidates = PROFILES.filter(
    (profile) =>
      !stream.participantIds.includes(profile.id) &&
      !joinRequestStore.requests.some((request) => request.streamId === streamId && request.requesterId === profile.id),
  )
  if (candidates.length === 0) return
  const pick = candidates[Math.floor(Math.random() * candidates.length)]
  const request: JoinRequest = {
    id: `req-sim-${Date.now()}`,
    streamId,
    requesterId: pick.id,
    requesterName: pick.displayName,
    requesterPhoto: pick.photos[0] ?? '',
  }
  joinRequestStore.requests = [...joinRequestStore.requests, request]
}

/** Simulates a viewer sending the host a gift, crediting her received-gifts for redemption. */
export function simulateIncomingGift(streamId: string) {
  const stream = liveStreamStore.streams.find((item) => item.id === streamId)
  if (!stream) return
  const pool = PROFILES.filter((profile) => profile.id !== stream.hostId)
  const pick = pool[Math.floor(Math.random() * pool.length)]
  if (!pick) return
  const gift = simulateReceivedGift(pick.id, pick.displayName)
  const message: StreamMessage = {
    id: `msg-gift-${Date.now()}`,
    streamId,
    authorId: pick.id,
    authorName: pick.displayName,
    kind: 'gift',
    text: `sent ${gift.name}`,
    giftId: gift.id,
    createdAt: new Date().toISOString(),
  }
  streamMessageStore.messages = [...streamMessageStore.messages, message]
}

const CHAT_SAMPLES = ['🔥🔥🔥', 'Hiii from Lagos!', 'This is fun', 'Love this energy', '😂😂😂', 'Wya from?']

/** Simulates other viewers chatting so the feed feels alive without a second real user. */
export function simulateIncomingMessage(streamId: string) {
  const stream = liveStreamStore.streams.find((item) => item.id === streamId)
  if (!stream) return
  const pool = PROFILES.filter((profile) => profile.id !== stream.hostId)
  const pick = pool[Math.floor(Math.random() * pool.length)]
  if (!pick) return
  const message: StreamMessage = {
    id: `msg-sim-${Date.now()}`,
    streamId,
    authorId: pick.id,
    authorName: pick.displayName,
    kind: 'message',
    text: CHAT_SAMPLES[Math.floor(Math.random() * CHAT_SAMPLES.length)],
    createdAt: new Date().toISOString(),
  }
  streamMessageStore.messages = [...streamMessageStore.messages, message]
}
