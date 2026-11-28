import { apiRequest, ensureCsrfHeaders, resolveMediaUrl } from './client'
import { type CoinPackage } from './types'

export interface CallSession {
  callId: string
  callerId: string
  calleeId: string
  callType: 'audio' | 'video'
  status: 'ringing' | 'connecting' | 'active' | 'declined' | 'ended'
  liveKitUrl: string | null
  token: string | null
  creditBalance: number | null
}

export interface IncomingCall {
  callId: string
  callerId: string
  callerName: string
  callerPhoto: string | null
  callerIdentity: 'man' | 'woman' | 'private'
  callType: 'audio' | 'video'
  status: 'ringing'
  createdAt: string
}

export interface CallHistoryItem {
  callId: string
  participantId: string
  participantName: string
  participantPhoto: string | null
  participantIdentity: 'man' | 'woman' | 'private'
  callType: 'audio' | 'video'
  direction: 'incoming' | 'outgoing'
  status: 'completed' | 'missed' | 'no-answer' | 'declined'
  createdAt: string
  startedAt: string | null
  endedAt: string | null
  durationSeconds: number
}

export const CALL_CREDIT_COST_PER_MINUTE = 1
export const CALL_CREDIT_TICK_SECONDS = 60
export const CALL_CREDIT_COST_PER_TICK = 1
export const LOW_CREDIT_WARNING_THRESHOLD = 3

export async function getCoinPriceNaira(): Promise<number> {
  const result = await apiRequest<{ priceNaira: number }>('/calls/coin-price')
  return result.priceNaira
}

export async function setCoinPriceNaira(priceNaira: number): Promise<number> {
  const result = await apiRequest<{ priceNaira: number }>('/admin/call-credits/price', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ priceNaira }),
  })
  return result.priceNaira
}

export async function listCoinPackages(): Promise<CoinPackage[]> {
  return apiRequest<CoinPackage[]>('/calls/coin-packages')
}

export async function getCallCreditBalance(): Promise<number> {
  const result = await apiRequest<{ coins: number }>('/calls/credits')
  return result.coins
}

export async function buyCallCredits(coins: number): Promise<{ coins: number; balanceNaira: number }> {
  return apiRequest('/calls/credits/purchase', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID(), ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ coins }),
  })
}

export async function startCall(targetId: string, callType: 'audio' | 'video' = 'video'): Promise<CallSession> {
  return apiRequest('/calls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID(), ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ targetId, callType }),
  })
}

export async function listIncomingCalls(): Promise<IncomingCall[]> {
  const calls = await apiRequest<IncomingCall[]>('/calls/incoming')
  return calls.map((call) => ({
    ...call,
    callerPhoto: call.callerPhoto ? resolveMediaUrl(call.callerPhoto) : null,
  }))
}

export async function listCallHistory(): Promise<CallHistoryItem[]> {
  const calls = await apiRequest<CallHistoryItem[]>('/calls/history')
  return calls.map((call) => ({
    ...call,
    participantPhoto: call.participantPhoto ? resolveMediaUrl(call.participantPhoto) : null,
  }))
}

export async function acceptCall(callId: string): Promise<CallSession> {
  return apiRequest(`/calls/${encodeURIComponent(callId)}/accept`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function declineCall(callId: string): Promise<void> {
  await apiRequest<void>(`/calls/${encodeURIComponent(callId)}/decline`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function markCallConnected(callId: string): Promise<CallSession> {
  return apiRequest(`/calls/${encodeURIComponent(callId)}/connected`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function heartbeatCall(callId: string): Promise<CallSession> {
  return apiRequest(`/calls/${encodeURIComponent(callId)}/heartbeat`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function getCallToken(callId: string): Promise<{ url: string; token: string }> {
  return apiRequest(`/calls/${encodeURIComponent(callId)}/token`, { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function getCall(callId: string): Promise<CallSession> {
  return apiRequest(`/calls/${encodeURIComponent(callId)}`)
}

export async function endCall(callId: string): Promise<void> {
  await apiRequest<void>(`/calls/${encodeURIComponent(callId)}`, { method: 'DELETE', headers: await ensureCsrfHeaders() })
}
