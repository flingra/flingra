import { delay } from './client'
import { ownProfileStore, STATUSES, statusStore } from './mock-db'
import { ApiError, type Status } from './types'

const MAX_STATUS_VIDEO_SECONDS = 50

function readVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(video.src)
      resolve(video.duration)
    }
    video.onerror = () => {
      URL.revokeObjectURL(video.src)
      reject(new ApiError('VIDEO_UNREADABLE', "We couldn't read that video. Try a different file."))
    }
    video.src = URL.createObjectURL(file)
  })
}

export async function listNearbyStatuses(): Promise<Status[]> {
  await delay(null, 400)
  return [...STATUSES, ...statusStore.statuses]
}

export async function createStatus(file: File): Promise<Status> {
  const kind = file.type.startsWith('video/') ? 'video' : 'image'

  if (kind === 'video') {
    const duration = await readVideoDuration(file)
    if (duration > MAX_STATUS_VIDEO_SECONDS) {
      throw new ApiError('STATUS_VIDEO_TOO_LONG', `Status videos must be ${MAX_STATUS_VIDEO_SECONDS} seconds or shorter.`)
    }
  }

  await delay(null, 700)
  const profile = ownProfileStore.profile
  const status: Status = {
    id: `status-me-${Date.now()}`,
    authorId: 'me',
    authorName: profile?.displayName ?? 'You',
    authorPhoto: profile?.photos[0] ?? '',
    media: URL.createObjectURL(file),
    kind,
    createdAt: new Date().toISOString(),
  }
  statusStore.statuses = [status, ...statusStore.statuses]
  return status
}
