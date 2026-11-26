import { apiRequest, ensureCsrfHeaders } from './client'
import { type JoinRequest, type LiveStream, type StreamMessage, type SubscriptionTier } from './types'

export const MAX_PARTICIPANTS = 5
export const PREVIEW_SECONDS = 10

export interface LiveStreamWithHost extends LiveStream {
  hostArea: string
  hostDistanceKm: number
  hostSubscriptionTier: SubscriptionTier
}

export async function listLiveStreams(): Promise<LiveStream[]> {
  return apiRequest<LiveStream[]>('/live-streams')
}

export async function listLiveStreamsNearby(): Promise<LiveStreamWithHost[]> {
  return apiRequest<LiveStreamWithHost[]>('/live-streams/nearby')
}

export async function getLiveStream(id: string): Promise<LiveStream> {
  return apiRequest<LiveStream>(`/live-streams/${encodeURIComponent(id)}`)
}

export async function startStream(title: string): Promise<LiveStream & { liveKitUrl: string; token: string }> {
  return apiRequest('/live-streams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ title }),
  })
}

export async function getStreamToken(streamId: string): Promise<{ url: string; token: string }> {
  return apiRequest(`/live-streams/${encodeURIComponent(streamId)}/token`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function heartbeatStream(streamId: string): Promise<void> {
  await apiRequest<void>(`/live-streams/${encodeURIComponent(streamId)}/heartbeat`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function endStream(id: string): Promise<void> {
  await apiRequest<void>(`/live-streams/${encodeURIComponent(id)}`, { method: 'DELETE', headers: await ensureCsrfHeaders() })
}

export async function requestToJoin(streamId: string): Promise<void> {
  await apiRequest<void>(`/live-streams/${encodeURIComponent(streamId)}/join-requests`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function listJoinRequests(streamId: string): Promise<JoinRequest[]> {
  return apiRequest<JoinRequest[]>(`/live-streams/${encodeURIComponent(streamId)}/join-requests`)
}

export async function respondToJoinRequest(streamId: string, requestId: string, accept: boolean): Promise<void> {
  await apiRequest<void>(`/live-streams/${encodeURIComponent(streamId)}/join-requests/${encodeURIComponent(requestId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ accept }),
  })
}

export async function leaveStream(streamId: string): Promise<void> {
  await apiRequest<void>(`/live-streams/${encodeURIComponent(streamId)}/participants/me`, { method: 'DELETE', headers: await ensureCsrfHeaders() })
}

export async function listParticipants(streamId: string): Promise<{ id: string; name: string; photo: string }[]> {
  return apiRequest(`/live-streams/${encodeURIComponent(streamId)}/participants`)
}

export async function listStreamViewers(streamId: string): Promise<{ id: string; name: string; photo: string }[]> {
  return apiRequest(`/live-streams/${encodeURIComponent(streamId)}/viewers`)
}

export async function listStreamMessages(streamId: string): Promise<StreamMessage[]> {
  return apiRequest<StreamMessage[]>(`/live-streams/${encodeURIComponent(streamId)}/messages`)
}

export async function sendStreamMessage(
  streamId: string,
  text: string,
  kind: StreamMessage['kind'] = 'message',
  giftId?: string,
): Promise<StreamMessage> {
  return apiRequest<StreamMessage>(`/live-streams/${encodeURIComponent(streamId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ text, kind, giftId }),
  })
}
