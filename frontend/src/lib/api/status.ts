import { apiRequest, uploadFile } from './client'
import { type Status } from './types'

export async function listNearbyStatuses(): Promise<Status[]> {
  return apiRequest<Status[]>('/statuses/nearby')
}

export async function createStatus(file: File): Promise<Status> {
  return uploadFile<Status>('/statuses', file)
}
