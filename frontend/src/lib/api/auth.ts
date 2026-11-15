import { apiRequest, ensureCsrfHeaders } from './client'
import { ApiError, type AccountStage, type Session } from './types'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
let cachedSession: Session | null = null

export interface SignUpInput {
  sex: 'man' | 'woman'
  identifier: string
  password: string
  dateOfBirth: string
  acceptedTerms: boolean
  referralCode?: string
}

export async function signUp(input: SignUpInput): Promise<{ stage: AccountStage }> {
  const result = await apiRequest<{ stage: AccountStage }>('/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sex: input.sex,
      identifier: input.identifier,
      password: input.password,
      dateOfBirth: input.dateOfBirth,
      acceptedTerms: input.acceptedTerms,
      referralCode: input.referralCode,
    }),
  })
  cachedSession = {
    accountId: 'pending',
    maskedContact: maskContact(input.identifier),
    stage: result.stage,
  }
  return result
}

export interface SignInInput {
  identifier: string
  password: string
}

interface GoogleIdentityServices {
  accounts: {
    id: {
      initialize(options: {
        client_id: string
        callback: (response: { credential: string }) => void
        nonce: string
        auto_select?: boolean
        cancel_on_tap_outside?: boolean
      }): void
      prompt(listener: (notification: { isNotDisplayed(): boolean; isSkippedMoment(): boolean }) => void): void
    }
  }
}

declare global {
  interface Window {
    google?: GoogleIdentityServices
  }
}

interface GoogleAuthInput {
  sex?: 'man' | 'woman'
  dateOfBirth?: string
  acceptedTerms?: boolean
  referralCode?: string
}

function googleNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(24))
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

let googleScriptPromise: Promise<void> | null = null

function loadGoogleIdentityServices(): Promise<void> {
  if (window.google) return Promise.resolve()
  if (!googleScriptPromise) {
    googleScriptPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>('script[data-google-identity-services]')
      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true })
        existing.addEventListener('error', () => reject(new ApiError('GOOGLE_UNAVAILABLE', 'Google sign-in is unavailable.')), {
          once: true,
        })
        return
      }
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.dataset.googleIdentityServices = 'true'
      script.onload = () => resolve()
      script.onerror = () => reject(new ApiError('GOOGLE_UNAVAILABLE', 'Google sign-in is unavailable.'))
      document.head.appendChild(script)
    })
  }
  return googleScriptPromise
}

async function getGoogleCredential(): Promise<{ credential: string; nonce: string }> {
  const config = await apiRequest<{ clientId: string | null }>('/auth/oauth/google/config')
  if (!config.clientId) throw new ApiError('GOOGLE_UNAVAILABLE', 'Google sign-in is not configured.')
  await loadGoogleIdentityServices()
  const google = window.google
  if (!google) throw new ApiError('GOOGLE_UNAVAILABLE', 'Google sign-in is unavailable.')
  const nonce = googleNonce()
  return new Promise((resolve, reject) => {
    let settled = false
    google.accounts.id.initialize({
      client_id: config.clientId as string,
      nonce,
      cancel_on_tap_outside: true,
      callback: (response) => {
        settled = true
        resolve({ credential: response.credential, nonce })
      },
    })
    google.accounts.id.prompt((notification) => {
      if (!settled && (notification.isNotDisplayed() || notification.isSkippedMoment())) {
        settled = true
        reject(new ApiError('GOOGLE_CANCELLED', 'Google sign-in was cancelled.'))
      }
    })
  })
}

export async function signIn(input: SignInInput): Promise<Session> {
  const session = await apiRequest<Session>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  cachedSession = session
  return session
}

export async function verifyContact(code: string): Promise<{ stage: AccountStage }> {
  const result = await apiRequest<{ stage: AccountStage }>('/auth/verify-contact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ code }),
  })
  if (cachedSession) cachedSession = { ...cachedSession, stage: result.stage }
  return result
}

export async function resendCode(): Promise<void> {
  await apiRequest<void>('/auth/resend-code', { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function requestPasswordReset(identifier: string): Promise<void> {
  await apiRequest<void>('/auth/password/forgot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier }),
  })
}

export async function resetPassword(token: string, password: string): Promise<void> {
  await apiRequest<void>('/auth/password/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  })
}

export async function signOut(): Promise<void> {
  await apiRequest<void>('/auth/logout', { method: 'POST', headers: await ensureCsrfHeaders() })
  cachedSession = null
}

export function currentSession(): Session | null {
  return cachedSession
}

export async function restoreSession(): Promise<Session | null> {
  cachedSession = await apiRequest<Session | null>('/auth/session')
  return cachedSession
}

export async function completeOnboarding(): Promise<Session> {
  const session = await apiRequest<Session>('/auth/onboarding/complete', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
  cachedSession = session
  return session
}

export async function continueWithGoogle(input: GoogleAuthInput = {}): Promise<Session> {
  const google = await getGoogleCredential()
  const session = await apiRequest<Session>('/auth/oauth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...input, ...google }),
  })
  cachedSession = session
  return session
}

function maskContact(identifier: string): string {
  const normalized = identifier.trim().toLowerCase()
  if (EMAIL_PATTERN.test(normalized)) {
    const [local, domain] = normalized.split('@')
    return `${local.slice(0, 1)}•••@${domain}`
  }
  return normalized.length <= 4 ? '••••' : `${normalized.slice(0, 2)}••••${normalized.slice(-2)}`
}
