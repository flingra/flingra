import { create } from 'zustand'
import { adminApi, type AdminSession } from '@/lib/api/admin'

interface AdminState {
  session: AdminSession | null
  hydrated: boolean
  setSession: (session: AdminSession | null) => void
  restore: () => Promise<void>
  logout: () => Promise<void>
}

export const useAdminStore = create<AdminState>((set) => ({
  session: null,
  hydrated: false,
  setSession: (session) => set({ session }),
  restore: async () => {
    try { set({ session: await adminApi.session() }) } catch { set({ session: null }) } finally { set({ hydrated: true }) }
  },
  logout: async () => { await adminApi.logout(); set({ session: null }) },
}))
