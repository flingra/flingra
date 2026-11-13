import { delay } from './client'
import { CURRENT_ACCOUNT, ownProfileStore, PROFILES, sessionStore } from './mock-db'
import { applyReferralCode } from './payout'
import { saveOwnProfile } from './profiles'
import { ApiError, type AccountStage, type Session } from './types'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function minAgeDate(sex: 'man' | 'woman') {
  const date = new Date()
  date.setFullYear(date.getFullYear() - (sex === 'woman' ? 21 : 18))
  return date
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
  await delay(null, 700)

  if (!input.acceptedTerms) {
    throw new ApiError('TERMS_REQUIRED', 'Accept the terms and privacy notice to continue.')
  }
  // Women sign up with email only, and the minimum age is 21 (vs. 18 generally)
  // — a deliberate, stricter safety threshold for this account type.
  if (input.sex === 'woman' && !EMAIL_PATTERN.test(input.identifier)) {
    throw new ApiError('EMAIL_REQUIRED', 'Enter a valid email address.')
  }
  if (new Date(input.dateOfBirth) > minAgeDate(input.sex)) {
    throw new ApiError(
      'INELIGIBLE_AGE',
      input.sex === 'woman'
        ? 'Flingra requires female accounts to be 21 or older.'
        : 'Flingra is only available to adults 18 and older.',
    )
  }
  if (input.identifier.toLowerCase() === CURRENT_ACCOUNT.identifier) {
    throw new ApiError(
      'ACCOUNT_EXISTS',
      'If an account already exists for these details, sign in instead or reset your password.',
    )
  }

  sessionStore.session = { accountId: 'me', maskedContact: CURRENT_ACCOUNT.maskedContact, stage: 'needs-verification' }
  // Seed a draft profile immediately so the account's sex is set before
  // onboarding (needed for the livestream gender gate and other sex-specific
  // rules), while the public "identity" display preference stays editable later.
  await saveOwnProfile({ identity: input.sex })
  if (input.referralCode) applyReferralCode(input.referralCode)
  return { stage: 'needs-verification' }
}

export interface SignInInput {
  identifier: string
  password: string
}

export async function signIn(input: SignInInput): Promise<Session> {
  await delay(null, 600)

  if (input.identifier.toLowerCase().includes('locked')) {
    throw new ApiError('ACCOUNT_LOCKED', 'Too many attempts. Try again later or reset your password.')
  }
  if (input.identifier.toLowerCase() !== CURRENT_ACCOUNT.identifier || input.password !== CURRENT_ACCOUNT.password) {
    throw new ApiError('INVALID_CREDENTIALS', "That email/password combination doesn't match our records.")
  }

  const stage: AccountStage = ownProfileStore.profile?.onboardingComplete ? 'active' : 'needs-onboarding'
  const session: Session = { accountId: 'me', maskedContact: CURRENT_ACCOUNT.maskedContact, stage }
  sessionStore.session = session
  return session
}

export async function verifyContact(code: string): Promise<{ stage: AccountStage }> {
  await delay(null, 500)
  if (code !== CURRENT_ACCOUNT.verificationCode) {
    throw new ApiError('INVALID_CODE', "That code didn't work. Check the digits and try again.")
  }
  const stage: AccountStage = ownProfileStore.profile?.onboardingComplete ? 'active' : 'needs-onboarding'
  if (sessionStore.session) sessionStore.session = { ...sessionStore.session, stage }
  return { stage }
}

export async function resendCode(): Promise<void> {
  await delay(undefined, 400)
}

export async function requestPasswordReset(_identifier: string): Promise<void> {
  await delay(undefined, 600)
}

export async function resetPassword(token: string, _password: string): Promise<void> {
  await delay(undefined, 600)
  if (token === 'expired') {
    throw new ApiError('TOKEN_EXPIRED', 'This reset link has expired. Request a new one.')
  }
}

export async function signOut(): Promise<void> {
  await delay(undefined, 300)
  sessionStore.session = null
}

export function currentSession(): Session | null {
  return sessionStore.session
}

/** Marks the persisted session active once onboarding finishes, so a page reload doesn't bounce back to it. */
export function completeOnboarding(): Session | null {
  if (sessionStore.session) {
    sessionStore.session = { ...sessionStore.session, stage: 'active' }
  }
  return sessionStore.session
}

export async function continueWithGoogle(): Promise<{ stage: AccountStage }> {
  await delay(null, 900)
  const stage: AccountStage = ownProfileStore.profile?.onboardingComplete ? 'active' : 'needs-onboarding'
  sessionStore.session = { accountId: 'me', maskedContact: 'demo.google@gmail.com', stage }
  return { stage }
}

export function seedSignedInSession() {
  sessionStore.session = { accountId: 'me', maskedContact: CURRENT_ACCOUNT.maskedContact, stage: 'active' }
  ownProfileStore.profile = {
    ...PROFILES[0],
    id: 'me',
    displayName: 'Jide',
    moderationStatus: 'approved',
    onboardingComplete: true,
  }
}
