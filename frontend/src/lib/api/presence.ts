import { apiRequest } from './client'

export async function getPresence(authorId: string): Promise<{ hasStatus: boolean; isLive: boolean; streamId?: string }> {
  return apiRequest(`/presence/${encodeURIComponent(authorId)}`)
}
