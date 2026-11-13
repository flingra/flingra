import { create } from 'zustand'
import { currentSession } from '@/lib/api/auth'
import type { Session } from '@/lib/api/types'

interface SessionState {
  session: Session | null
  setSession: (session: Session | null) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  session: currentSession(),
  setSession: (session) => set({ session }),
}))
