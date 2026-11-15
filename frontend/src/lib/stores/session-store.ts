import { create } from 'zustand'
import { currentSession } from '@/lib/api/auth'
import type { Session } from '@/lib/api/types'

interface SessionState {
  session: Session | null
  hydrated: boolean
  setSession: (session: Session | null) => void
  setHydrated: (hydrated: boolean) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  session: currentSession(),
  hydrated: false,
  setSession: (session) => set({ session }),
  setHydrated: (hydrated) => set({ hydrated }),
}))
