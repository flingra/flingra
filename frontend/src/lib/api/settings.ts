import { delay } from './client'
import { CURRENT_ACCOUNT } from './mock-db'
import { ApiError } from './types'

export interface DeviceSession {
  id: string
  device: string
  lastActive: string
  current: boolean
}

const sessions: DeviceSession[] = [
  { id: 'session-current', device: 'This device · Chrome on macOS', lastActive: 'Active now', current: true },
  { id: 'session-2', device: 'Flingra app · iPhone', lastActive: '2 days ago', current: false },
]

export async function changePassword(currentPassword: string, _newPassword: string): Promise<void> {
  await delay(undefined, 700)
  if (currentPassword !== CURRENT_ACCOUNT.password) {
    throw new ApiError('WRONG_PASSWORD', 'Your current password is incorrect.')
  }
}

export async function listSessions(): Promise<DeviceSession[]> {
  await delay(null, 400)
  return sessions
}

export async function revokeSession(id: string): Promise<void> {
  await delay(undefined, 500)
  const index = sessions.findIndex((session) => session.id === id)
  if (index >= 0) sessions.splice(index, 1)
}

export async function requestDataExport(): Promise<void> {
  await delay(undefined, 600)
}

export async function requestAccountDeletion(): Promise<void> {
  await delay(undefined, 600)
}
