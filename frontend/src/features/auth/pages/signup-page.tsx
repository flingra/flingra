import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Checkbox } from '@/components/ui/checkbox'
import { Chip } from '@/components/ui/chip'
import { Button } from '@/components/ui/button'
import { GoogleButton } from '@/components/ui/google-button'
import { ProgressSteps } from '@/components/ui/progress-steps'
import { AuthPageShell } from '../components/auth-page-shell'
import { continueWithGoogle, currentSession, signUp } from '@/lib/api/auth'
import { ApiError, type AccountStage } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TOTAL_STEPS = 3

const STAGE_ROUTE: Record<AccountStage, string> = {
  'needs-verification': '/verify-contact',
  'needs-onboarding': '/onboarding',
  active: '/discover',
}

const schema = z
  .object({
    sex: z.enum(['woman', 'man'], { message: 'Choose an option to continue.' }),
    identifier: z.string().min(3, 'Enter your email or mobile number.'),
    password: z.string().min(8, 'Use at least 8 characters.'),
    confirmPassword: z.string(),
    dateOfBirth: z.string().min(1, 'Enter your date of birth.'),
    acceptedTerms: z.boolean().refine((value) => value === true, { message: 'Accept the terms to continue.' }),
    marketingOptIn: z.boolean().optional(),
    referralCode: z.string().optional(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords must match.',
    path: ['confirmPassword'],
  })
  .superRefine((data, ctx) => {
    if (data.sex === 'woman' && !EMAIL_PATTERN.test(data.identifier)) {
      ctx.addIssue({ code: 'custom', path: ['identifier'], message: 'Enter a valid email address.' })
    }
  })

type FormValues = z.infer<typeof schema>

const STEP_FIELDS: Record<number, (keyof FormValues)[]> = {
  1: ['sex'],
  2: ['identifier', 'password', 'confirmPassword'],
  3: ['dateOfBirth', 'acceptedTerms'],
}

export function SignUpPage() {
  const navigate = useNavigate()
  const setSession = useSessionStore((state) => state.setSession)
  const [formError, setFormError] = useState<string | null>(null)
  const [step, setStep] = useState(1)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googlePending, setGooglePending] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    watch,
    trigger,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const sex = watch('sex')

  async function goNext() {
    const fields = googlePending
      ? (step === 1 ? ['sex'] : ['dateOfBirth', 'acceptedTerms'])
      : STEP_FIELDS[step]
    const valid = await trigger(fields as (keyof FormValues)[])
    if (valid) setStep((current) => Math.min(googlePending ? 2 : TOTAL_STEPS, current + 1))
  }

  function goBack() {
    setFormError(null)
    setStep((current) => Math.max(1, current - 1))
  }

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      await signUp({
        sex: values.sex,
        identifier: values.identifier,
        password: values.password,
        dateOfBirth: values.dateOfBirth,
        acceptedTerms: values.acceptedTerms,
        referralCode: values.referralCode,
      })
      setSession(currentSession())
      navigate('/verify-contact')
    } catch (error) {
      if (error instanceof ApiError && (error.code === 'INELIGIBLE_AGE' || error.code === 'EMAIL_REQUIRED')) {
        setError(error.code === 'EMAIL_REQUIRED' ? 'identifier' : 'dateOfBirth', { message: error.message })
        setStep(error.code === 'EMAIL_REQUIRED' ? 2 : 3)
      } else if (error instanceof ApiError) {
        setFormError(error.message)
      } else {
        setFormError('Something went wrong. Check your connection and try again.')
      }
    }
  }

  async function handleGoogle() {
    setFormError(null)

    if (googlePending) {
      const valid = await trigger(['sex', 'dateOfBirth', 'acceptedTerms'])
      if (!valid) {
        setStep(watch('sex') ? 2 : 1)
        return
      }
    }

    setGoogleLoading(true)
    try {
      const values = watch()
      const session = await continueWithGoogle({
        sex: values.sex,
        dateOfBirth: values.dateOfBirth,
        acceptedTerms: values.acceptedTerms,
        referralCode: values.referralCode,
      })
      setSession(session)
      navigate(STAGE_ROUTE[session.stage])
    } catch (error) {
      if (error instanceof ApiError && error.code === 'GOOGLE_SIGNUP_REQUIRED') {
        setGooglePending(true)
        setStep(watch('sex') ? 2 : 1)
      } else {
        setFormError(error instanceof ApiError ? error.message : 'Google sign-in failed. Try again.')
      }
    } finally {
      setGoogleLoading(false)
    }
  }

  return (
    <AuthPageShell
      title="Create your account"
      subtitle="Flingra is for consenting adults."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-primary-600 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Card className="transition-shadow duration-300 hover:shadow-float">
        <div className="mb-5">
          <GoogleButton label="Sign up with Google" loading={googleLoading} onClick={handleGoogle} className="w-full" />
          <div className="mt-5 flex items-center gap-3 text-xs font-medium text-ink-400">
            <span className="h-px flex-1 bg-ink-100" />
            or create an account
            <span className="h-px flex-1 bg-ink-100" />
          </div>
        </div>

        {googlePending && (
          <div className="mb-5 rounded-xl bg-primary-50 px-4 py-3 text-sm text-primary-700">
            Google provides your verified email, so you do not need to enter an email or password here.
          </div>
        )}

        <ProgressSteps current={step} total={googlePending ? 2 : TOTAL_STEPS} label="Sign-up progress" />

        <form
          key={step}
          className="mt-6 flex animate-page-enter flex-col gap-5"
          onSubmit={step === TOTAL_STEPS ? handleSubmit(onSubmit) : (event) => event.preventDefault()}
          noValidate
        >
          {formError && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {formError}
            </p>
          )}

          {step === 1 && (
            <div>
              <p className="text-sm font-medium text-ink-800">I am signing up as</p>
              <div className="mt-2 flex gap-2">
                <Chip type="button" selected={sex === 'woman'} onClick={() => setValue('sex', 'woman', { shouldValidate: true })}>
                  Woman
                </Chip>
                <Chip type="button" selected={sex === 'man'} onClick={() => setValue('sex', 'man', { shouldValidate: true })}>
                  Man
                </Chip>
              </div>
              {errors.sex && (
                <p role="alert" className="mt-1.5 text-xs font-medium text-danger">
                  {errors.sex.message}
                </p>
              )}
            </div>
          )}

          {step === 2 && !googlePending && (
            <>
              <Field
                id="identifier"
                label={sex === 'woman' ? 'Email address' : 'Email or mobile number'}
                error={errors.identifier?.message}
              >
                <Input
                  id="identifier"
                  type={sex === 'woman' ? 'email' : 'text'}
                  autoComplete="username"
                  aria-invalid={!!errors.identifier}
                  {...register('identifier')}
                />
              </Field>

              <Field id="password" label="Password" error={errors.password?.message}>
                <PasswordInput id="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register('password')} />
              </Field>

              <Field id="confirmPassword" label="Confirm password" error={errors.confirmPassword?.message}>
                <PasswordInput
                  id="confirmPassword"
                  autoComplete="new-password"
                  aria-invalid={!!errors.confirmPassword}
                  {...register('confirmPassword')}
                />
              </Field>
            </>
          )}

          {googlePending && step === 2 && (
            <>
              <Field
                id="dateOfBirth"
                label="Date of birth"
                hint="You must be 21 or older to use Flingra."
                error={errors.dateOfBirth?.message}
              >
                <Input id="dateOfBirth" type="date" aria-invalid={!!errors.dateOfBirth} {...register('dateOfBirth')} />
              </Field>

              <label className="flex items-start gap-3 text-sm text-ink-700">
                <Checkbox {...register('acceptedTerms')} aria-invalid={!!errors.acceptedTerms} />
                <span>
                  I accept the{' '}
                  <Link to="/terms" className="font-semibold text-primary-600 hover:underline">
                    Terms
                  </Link>{' '}
                  and{' '}
                  <Link to="/privacy" className="font-semibold text-primary-600 hover:underline">
                    Privacy Notice
                  </Link>
                  .
                </span>
              </label>
              {errors.acceptedTerms && (
                <p role="alert" className="-mt-1 text-xs font-medium text-danger">
                  {errors.acceptedTerms.message}
                </p>
              )}

              <Field id="referralCode" label="Referral code" optional hint="Have a friend's code? Enter it to claim a signup bonus.">
                <Input id="referralCode" autoComplete="off" placeholder="FLINGRA-XXXX" {...register('referralCode')} />
              </Field>
            </>
          )}

          {step === 3 && (
            <>
              <Field
                id="dateOfBirth"
                label="Date of birth"
                hint="You must be 21 or older to use Flingra."
                error={errors.dateOfBirth?.message}
              >
                <Input id="dateOfBirth" type="date" aria-invalid={!!errors.dateOfBirth} {...register('dateOfBirth')} />
              </Field>

              <div className="flex flex-col gap-3">
                <label className="flex items-start gap-3 text-sm text-ink-700">
                  <Checkbox {...register('acceptedTerms')} aria-invalid={!!errors.acceptedTerms} />
                  <span>
                    I accept the{' '}
                    <Link to="/terms" className="font-semibold text-primary-600 hover:underline">
                      Terms
                    </Link>{' '}
                    and{' '}
                    <Link to="/privacy" className="font-semibold text-primary-600 hover:underline">
                      Privacy Notice
                    </Link>
                    .
                  </span>
                </label>
                {errors.acceptedTerms && (
                  <p role="alert" className="-mt-1 text-xs font-medium text-danger">
                    {errors.acceptedTerms.message}
                  </p>
                )}
                <label className="flex items-start gap-3 text-sm text-ink-700">
                  <Checkbox {...register('marketingOptIn')} />
                  <span>Send me product updates (optional)</span>
                </label>
              </div>

              <Field id="referralCode" label="Referral code" optional hint="Have a friend's code? Enter it to claim a signup bonus.">
                <Input id="referralCode" autoComplete="off" placeholder="FLINGRA-XXXX" {...register('referralCode')} />
              </Field>
            </>
          )}

          <div className="mt-1 flex gap-3">
            {step > 1 && (
              <Button type="button" variant="secondary" className="flex-1" onClick={goBack}>
                Back
              </Button>
            )}
            {googlePending ? (
              step < 2 ? (
                <Button type="button" className="flex-1" onClick={goNext}>
                  Continue
                </Button>
              ) : (
                <GoogleButton label="Finish with Google" loading={googleLoading} onClick={handleGoogle} className="flex-1" />
              )
            ) : step < TOTAL_STEPS ? (
              <Button type="button" className="flex-1" onClick={goNext}>
                Continue
              </Button>
            ) : (
              <Button type="submit" className="flex-1" loading={isSubmitting}>
                Create account
              </Button>
            )}
          </div>
        </form>
      </Card>
    </AuthPageShell>
  )
}
