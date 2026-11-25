import { apiRequest, ensureCsrfHeaders } from './client'
import { ApiError, type AccountStage, type Session } from './types'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const PENDING_SESSION_STORAGE_KEY = 'flingra:pending-session'

function readCachedSession(): Session | null {
  try {
    const value = window.localStorage.getItem(PENDING_SESSION_STORAGE_KEY)
    return value ? JSON.parse(value) as Session : null
  } catch {
    return null
  }
}

function writeCachedSession(session: Session | null) {
  if (!session) {
    window.localStorage.removeItem(PENDING_SESSION_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(PENDING_SESSION_STORAGE_KEY, JSON.stringify(session))
}

let cachedSession: Session | null = readCachedSession()

function setCachedSession(session: Session | null) {
  cachedSession = session
  writeCachedSession(session)
}

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
  setCachedSession({
    accountId: 'pending',
    maskedContact: maskContact(input.identifier),
    stage: result.stage,
  })
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
      prompt(listener: (notification: GooglePromptNotification) => void): void
    }
  }
}

interface GooglePromptNotification {
  isNotDisplayed(): boolean
  isSkippedMoment(): boolean
  isDismissedMoment(): boolean
  getNotDisplayedReason(): string
  getSkippedReason(): string
  getDismissedReason(): string
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

function googlePromptError(notification: GooglePromptNotification): ApiError {
  if (notification.isNotDisplayed()) {
    const reason = notification.getNotDisplayedReason()
    if (reason === 'unregistered_origin') {
      return new ApiError(
        'GOOGLE_ORIGIN_NOT_ALLOWED',
        'Google sign-in is not enabled for this website. Add this site to the OAuth client’s Authorized JavaScript origins.',
      )
    }
    if (reason === 'invalid_client') {
      return new ApiError(
        'GOOGLE_CLIENT_MISCONFIGURED',
        'Google sign-in is not configured correctly for this environment.',
      )
    }
    if (reason === 'browser_not_supported') {
      return new ApiError(
        'GOOGLE_BROWSER_UNSUPPORTED',
        'Google sign-in is not supported in this browser. Try a current browser or use email and password.',
      )
    }
    return new ApiError(
      'GOOGLE_PROMPT_NOT_DISPLAYED',
      'Google sign-in could not display its prompt. Check the OAuth client’s authorized website origins, or use email and password.',
    )
  }

  const reason = notification.isSkippedMoment()
    ? notification.getSkippedReason()
    : notification.getDismissedReason()
  if (reason === 'user_cancel' || reason === 'tap_outside') {
    return new ApiError('GOOGLE_CANCELLED', 'Google sign-in was cancelled. Try again or use email and password.')
  }
  if (reason === 'auto_cancel') {
    return new ApiError('GOOGLE_PROMPT_TIMEOUT', 'Google sign-in timed out. Try again or use email and password.')
  }
  if (reason === 'issuppressed_by_user') {
    return new ApiError(
      'GOOGLE_PROMPT_SUPPRESSED',
      'The Google sign-in prompt is suppressed by browser settings. Try again or use email and password.',
    )
  }
  return new ApiError('GOOGLE_SIGN_IN_INCOMPLETE', 'Google sign-in did not finish. Try again or use email and password.')
}

function normalizeGoogleSignInError(
  error: unknown,
  stage: 'prompt' | 'api',
): ApiError {
  if (error instanceof ApiError) return error
  if (error instanceof TypeError) {
    return new ApiError(
      stage === 'prompt' ? 'GOOGLE_BROWSER_NETWORK_ERROR' : 'GOOGLE_API_NETWORK_ERROR',
      stage === 'prompt'
        ? 'The browser could not complete Google sign-in. Check browser privacy settings or try another browser.'
        : 'Could not reach the Flingra API to finish Google sign-in. Check your connection and try again.',
    )
  }
  if (error instanceof Error) {
    return new ApiError(
      'GOOGLE_SIGN_IN_FAILED',
      `Google sign-in failed (${error.name}): ${error.message || 'unknown error'}`,
    )
  }
  return new ApiError('GOOGLE_SIGN_IN_FAILED', 'Google sign-in failed for an unknown reason.')
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
      if (
        !settled &&
        (notification.isNotDisplayed() ||
          notification.isSkippedMoment() ||
          notification.isDismissedMoment())
      ) {
        settled = true
        reject(googlePromptError(notification))
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
  setCachedSession(session)
  return session
}

export async function verifyContact(code: string): Promise<{ stage: AccountStage }> {
  const result = await apiRequest<{ stage: AccountStage }>('/auth/verify-contact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ code }),
  })
  if (cachedSession) setCachedSession({ ...cachedSession, stage: result.stage })
  return result
}

export async function resendCode(): Promise<void> {
  await apiRequest<void>('/auth/resend-code', { method: 'POST', headers: await ensureCsrfHeaders() })
}

export async function requestTwoFactorCode(): Promise<void> {
  await apiRequest<void>('/auth/2fa/email/request', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function verifyTwoFactorCode(code: string): Promise<void> {
  await apiRequest<void>('/auth/2fa/email/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ code: code.replace(/\D/g, '') }),
  })
}

export interface AuthenticatorSetup {
  secret: string
  otpauthUri: string
  qrDataUrl: string
}

export async function setupAuthenticator(): Promise<AuthenticatorSetup> {
  return apiRequest<AuthenticatorSetup>('/auth/2fa/authenticator/setup', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function verifyAuthenticator(code: string): Promise<void> {
  await apiRequest<void>('/auth/2fa/authenticator/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ code }),
  })
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
  setCachedSession(null)
}

export function currentSession(): Session | null {
  return cachedSession
}

export async function restoreSession(): Promise<Session | null> {
  const restored = await apiRequest<Session | null>('/auth/session')
  setCachedSession(restored)
  return restored
}

export async function completeOnboarding(): Promise<Session> {
  const session = await apiRequest<Session>('/auth/onboarding/complete', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
  setCachedSession(session)
  return session
}

export async function continueWithGoogle(input: GoogleAuthInput = {}): Promise<Session> {
  let google: { credential: string; nonce: string }
  try {
    google = await getGoogleCredential()
  } catch (error) {
    throw normalizeGoogleSignInError(error, 'prompt')
  }

  let session: Session
  try {
    session = await apiRequest<Session>('/auth/oauth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, ...google }),
    })
  } catch (error) {
    throw normalizeGoogleSignInError(error, 'api')
  }
  setCachedSession(session)
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
