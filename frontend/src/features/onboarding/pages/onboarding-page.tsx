import { type ChangeEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Camera, KeyRound, Mail, MapPin as MapPinIcon, QrCode } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { MapBackground } from '@/components/ui/map-background'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { Chip } from '@/components/ui/chip'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/ui/avatar'
import { ProgressSteps } from '@/components/ui/progress-steps'
import { useToast } from '@/components/ui/toast'
import { getOwnProfile, saveOwnProfile, uploadPhoto } from '@/lib/api/profiles'
import type { AudiencePreference } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

const DEMO_2FA_CODE = '123456'

const INTERESTS = [
  'Afrobeats',
  'Photography',
  'Football',
  'Cooking',
  'Tech',
  'Fashion',
  'Hiking',
  'Movies',
  'Books',
  'Travel',
  'Fitness',
  'Gaming',
  'Comedy',
  'Dancing',
  'Art',
  'Music festivals',
  'Nightlife',
  'Fine dining',
  'Volunteering',
  'Faith & spirituality',
  'Entrepreneurship',
  'Cars',
  'Pets',
  'Wine & cocktails',
  'Yoga',
  'Poetry',
  'Anime',
  'Politics & current affairs',
]
const AREAS = ['Lekki, Lagos', 'Yaba, Lagos', 'Wuse, Abuja', 'GRA, Port Harcourt', 'Bodija, Ibadan', 'Asokoro, Abuja']

interface Draft {
  displayName: string
  photo: string | null
  bio: string
  identity: 'man' | 'woman' | 'private'
  showIdentity: boolean
  wantsToDiscover: AudiencePreference
  discoverableBy: AudiencePreference
  interests: string[]
  area: string
  useBrowserLocation: boolean
  maxDistanceKm: number
}

const initialDraft: Draft = {
  displayName: '',
  photo: null,
  bio: '',
  identity: 'private',
  showIdentity: false,
  wantsToDiscover: 'everyone',
  discoverableBy: 'everyone',
  interests: [],
  area: AREAS[0],
  useBrowserLocation: false,
  maxDistanceKm: 25,
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const setSession = useSessionStore((state) => state.setSession)
  const session = useSessionStore((state) => state.session)
  const { data: existingProfile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, retry: false })
  const isWoman = existingProfile?.identity === 'woman'
  const totalSteps = isWoman ? 5 : 4

  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<Draft>(initialDraft)
  const [uploading, setUploading] = useState(false)
  const [finishing, setFinishing] = useState(false)

  const [twoFactorMethod, setTwoFactorMethod] = useState<'email' | 'authenticator' | null>(null)
  const [codeSent, setCodeSent] = useState(false)
  const [twoFactorCode, setTwoFactorCode] = useState('')
  const [twoFactorError, setTwoFactorError] = useState<string | null>(null)

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  useEffect(() => {
    if (existingProfile && existingProfile.identity !== 'private') {
      setDraft((current) => (current.displayName ? current : { ...current, identity: existingProfile.identity }))
    }
  }, [existingProfile])

  function toggleInterest(interest: string) {
    setDraft((current) => ({
      ...current,
      interests: current.interests.includes(interest)
        ? current.interests.filter((item) => item !== interest)
        : [...current.interests, interest],
    }))
  }

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const url = await uploadPhoto(file)
      update('photo', url)
    } finally {
      setUploading(false)
    }
  }

  async function finish() {
    setFinishing(true)
    try {
      await saveOwnProfile({
        displayName: draft.displayName,
        bio: draft.bio,
        photos: draft.photo ? [draft.photo] : [],
        identity: draft.identity,
        showIdentity: draft.showIdentity,
        wantsToDiscover: draft.wantsToDiscover,
        discoverableBy: draft.discoverableBy,
        interests: draft.interests,
        area: draft.area,
        distanceKm: 0,
        moderationStatus: 'pending',
        onboardingComplete: true,
        ...(twoFactorMethod ? { twoFactorEnabled: true, twoFactorMethod } : {}),
      })
      if (session) setSession({ ...session, stage: 'active' })
      navigate('/discover')
    } finally {
      setFinishing(false)
    }
  }

  function handleVerifyTwoFactor() {
    setTwoFactorError(null)
    if (twoFactorCode.trim().length !== 6) {
      setTwoFactorError('Enter the 6-digit code.')
      return
    }
    if (twoFactorMethod === 'email' && twoFactorCode !== DEMO_2FA_CODE) {
      setTwoFactorError("That code didn't work. Check the digits and try again.")
      return
    }
    showToast({ title: 'Two-factor authentication enabled', variant: 'success' })
    finish()
  }

  const canContinueStep1 = draft.displayName.trim().length > 0

  return (
    <Card>
      <ProgressSteps current={step} total={totalSteps} label="Onboarding progress" />

      {step === 1 && (
        <div className="mt-6 flex flex-col gap-5">
          <div>
            <h1 className="text-xl font-bold text-ink-900">Create your profile</h1>
            <p className="mt-1 text-sm text-ink-500">This is what other members will see first.</p>
          </div>

          <div className="flex items-center gap-4">
            <Avatar name={draft.displayName || '?'} src={draft.photo ?? undefined} size="xl" />
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-ink-200 px-4 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50">
              <Camera className="size-4" aria-hidden="true" />
              {uploading ? 'Uploading…' : 'Add photo'}
              <input type="file" accept="image/*" className="sr-only" onChange={handlePhotoChange} disabled={uploading} />
            </label>
          </div>

          <Field id="displayName" label="Display name">
            <Input id="displayName" value={draft.displayName} onChange={(event) => update('displayName', event.target.value)} />
          </Field>

          <Field id="bio" label="Bio" optional hint={`${draft.bio.length}/280`}>
            <Textarea id="bio" maxLength={280} value={draft.bio} onChange={(event) => update('bio', event.target.value)} />
          </Field>

          <Button disabled={!canContinueStep1} onClick={() => setStep(2)}>
            Continue
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="mt-6 flex flex-col gap-5">
          <div>
            <h1 className="text-xl font-bold text-ink-900">Identity &amp; discovery</h1>
            <p className="mt-1 text-sm text-ink-500">
              Your identity stays private unless you choose to show it. This only controls who you see and
              who can see you.
            </p>
          </div>

          <Field id="identity" label="Your identity" optional hint="Private by default.">
            <Select id="identity" value={draft.identity} onChange={(event) => update('identity', event.target.value as Draft['identity'])}>
              <option value="private">Prefer not to say</option>
              <option value="man">Man</option>
              <option value="woman">Woman</option>
            </Select>
          </Field>

          <label className="flex items-center gap-3 text-sm text-ink-700">
            <Checkbox checked={draft.showIdentity} onChange={(event) => update('showIdentity', event.target.checked)} />
            Show my identity on my public profile
          </label>

          <Field id="wantsToDiscover" label="Who you want to discover">
            <Select
              id="wantsToDiscover"
              value={draft.wantsToDiscover}
              onChange={(event) => update('wantsToDiscover', event.target.value as AudiencePreference)}
            >
              <option value="everyone">Everyone</option>
              <option value="men">Men</option>
              <option value="women">Women</option>
            </Select>
          </Field>

          <Field id="discoverableBy" label="Who may discover you" hint="This controls discoverability, not screenshots or prior interactions.">
            <Select
              id="discoverableBy"
              value={draft.discoverableBy}
              onChange={(event) => update('discoverableBy', event.target.value as AudiencePreference)}
            >
              <option value="everyone">Everyone</option>
              <option value="men">Men</option>
              <option value="women">Women</option>
            </Select>
          </Field>

          <Field id="interests" label="Interests" optional>
            <div className="flex flex-wrap gap-2">
              {INTERESTS.map((interest) => (
                <Chip key={interest} selected={draft.interests.includes(interest)} onClick={() => toggleInterest(interest)}>
                  {interest}
                </Chip>
              ))}
            </div>
          </Field>

          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button className="flex-1" onClick={() => setStep(3)}>
              Continue
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="mt-6 flex flex-col gap-5">
          <div>
            <h1 className="text-xl font-bold text-ink-900">Location</h1>
            <p className="mt-1 text-sm text-ink-500">We only ever show an approximate area or distance.</p>
          </div>

          <Field id="area" label="Area">
            <Select id="area" value={draft.area} onChange={(event) => update('area', event.target.value)}>
              {AREAS.map((area) => (
                <option key={area} value={area}>
                  {area}
                </option>
              ))}
            </Select>
          </Field>

          <div className="relative h-32 overflow-hidden rounded-2xl" aria-hidden="true">
            <MapBackground className="absolute inset-0" />
            <div className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center">
              <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink-800 shadow-soft">{draft.area}</span>
              <MapPinIcon className="mt-1 size-6 fill-primary-500 text-primary-600" aria-hidden="true" />
            </div>
          </div>

          <label className="flex items-center gap-3 text-sm text-ink-700">
            <Checkbox checked={draft.useBrowserLocation} onChange={(event) => update('useBrowserLocation', event.target.checked)} />
            Use my browser location for more accurate distance (optional)
          </label>

          <Field id="maxDistanceKm" label="Discovery distance (km)">
            <Input
              id="maxDistanceKm"
              type="number"
              min={1}
              max={200}
              value={draft.maxDistanceKm}
              onChange={(event) => update('maxDistanceKm', Number(event.target.value))}
            />
          </Field>

          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setStep(2)}>
              Back
            </Button>
            <Button className="flex-1" onClick={() => setStep(4)}>
              Continue
            </Button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="mt-6 flex flex-col gap-5">
          <div>
            <h1 className="text-xl font-bold text-ink-900">Review &amp; finish</h1>
            <p className="mt-1 text-sm text-ink-500">Here's what other members will and won't see.</p>
          </div>

          <div className="rounded-2xl bg-ink-50 p-4">
            <p className="text-sm font-semibold text-ink-900">Public on your profile</p>
            <p className="mt-1 text-sm text-ink-600">
              {draft.displayName || 'Your name'} · {draft.area}
              {draft.showIdentity && draft.identity !== 'private' ? ` · ${draft.identity}` : ''}
            </p>
            {draft.interests.length > 0 && <p className="mt-1 text-sm text-ink-600">{draft.interests.join(', ')}</p>}
          </div>
          <div className="rounded-2xl bg-ink-50 p-4">
            <p className="text-sm font-semibold text-ink-900">Stays private</p>
            <p className="mt-1 text-sm text-ink-600">
              Exact location, who you chose to discover, and who may discover you.
              {!draft.showIdentity && ' Your identity selection.'}
            </p>
          </div>

          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setStep(3)}>
              Back
            </Button>
            {isWoman ? (
              <Button className="flex-1" onClick={() => setStep(5)}>
                Continue
              </Button>
            ) : (
              <Button className="flex-1" loading={finishing} onClick={finish}>
                Finish
              </Button>
            )}
          </div>
        </div>
      )}

      {step === 5 && isWoman && (
        <div className="mt-6 flex flex-col gap-5">
          <div>
            <h1 className="text-xl font-bold text-ink-900">Set up two-factor authentication</h1>
            <p className="mt-1 text-sm text-ink-500">
              Required for female accounts. This adds a second check when you sign in, on top of your password.
            </p>
          </div>

          {!twoFactorMethod && (
            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={() => setTwoFactorMethod('email')}
                className="flex cursor-pointer items-center gap-3 rounded-2xl border border-ink-200 p-4 text-left hover:border-primary-300 hover:bg-primary-50"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
                  <Mail className="size-5" aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-semibold text-ink-900">Email code</span>
                  <span className="block text-sm text-ink-500">We'll send a 6-digit code to your email each time you sign in.</span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => setTwoFactorMethod('authenticator')}
                className="flex cursor-pointer items-center gap-3 rounded-2xl border border-ink-200 p-4 text-left hover:border-primary-300 hover:bg-primary-50"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
                  <KeyRound className="size-5" aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-semibold text-ink-900">Authenticator app</span>
                  <span className="block text-sm text-ink-500">Scan a QR code with Google Authenticator or a similar app.</span>
                </span>
              </button>
            </div>
          )}

          {twoFactorMethod === 'email' && (
            <div className="flex flex-col gap-4">
              {!codeSent ? (
                <Button onClick={() => setCodeSent(true)}>
                  <Mail className="size-4" aria-hidden="true" /> Send code to my email
                </Button>
              ) : (
                <>
                  <p className="text-sm text-ink-500">
                    We sent a 6-digit code to your email. For this demo, the code is <strong>123456</strong>.
                  </p>
                  <Field id="twofactor-code" label="Verification code" error={twoFactorError ?? undefined}>
                    <Input
                      id="twofactor-code"
                      inputMode="numeric"
                      maxLength={6}
                      value={twoFactorCode}
                      onChange={(event) => setTwoFactorCode(event.target.value)}
                    />
                  </Field>
                </>
              )}
            </div>
          )}

          {twoFactorMethod === 'authenticator' && (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col items-center gap-3 rounded-2xl bg-ink-50 p-6">
                <span className="flex size-32 items-center justify-center rounded-2xl border-2 border-dashed border-ink-300 bg-white">
                  <QrCode className="size-16 text-ink-300" aria-hidden="true" />
                </span>
                <p className="text-center text-xs text-ink-500">
                  Scan this with Google Authenticator, or enter the setup key manually:{' '}
                  <span className="font-mono font-semibold text-ink-700">FLNG-DEMO-2FA-KEY</span>
                </p>
              </div>
              <Field id="twofactor-code" label="6-digit code from your app" error={twoFactorError ?? undefined}>
                <Input
                  id="twofactor-code"
                  inputMode="numeric"
                  maxLength={6}
                  value={twoFactorCode}
                  onChange={(event) => setTwoFactorCode(event.target.value)}
                />
              </Field>
            </div>
          )}

          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => {
                if (twoFactorMethod) {
                  setTwoFactorMethod(null)
                  setCodeSent(false)
                  setTwoFactorCode('')
                  setTwoFactorError(null)
                } else {
                  setStep(4)
                }
              }}
            >
              Back
            </Button>
            <Button
              className="flex-1"
              loading={finishing}
              disabled={!twoFactorMethod || (twoFactorMethod === 'email' && !codeSent)}
              onClick={handleVerifyTwoFactor}
            >
              Verify &amp; finish
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
