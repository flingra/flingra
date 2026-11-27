import { apiRequest } from './client'

export interface RealtimeEvent {
  id: number
  type: string
  data: Record<string, unknown>
}

export interface RealtimeEventBatch {
  events: RealtimeEvent[]
  cursor: number
}

export async function listRealtimeEvents(after?: number): Promise<RealtimeEventBatch> {
  const query = after === undefined ? '' : `?after=${after}`
  return apiRequest<RealtimeEventBatch>(`/realtime/events${query}`)
}
