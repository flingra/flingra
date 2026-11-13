import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Button } from '@/components/ui/button'
import { GoogleButton } from '@/components/ui/google-button'
import { continueWithGoogle, seedSignedInSession, signIn } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

const schema = z.object({
  identifier: z.string().min(1, 'Enter your email or mobile number.'),
  password: z.string().min(1, 'Enter your password.'),
})

type FormValues = z.infer<typeof schema>

const STAGE_ROUTE = {
  'needs-verification': '/verify-contact',
  'needs-onboarding': '/onboarding',
  active: '/discover',
} as const

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const setSession = useSessionStore((state) => state.setSession)
  const [formError, setFormError] = useState<string | null>(null)
  const [googleLoading, setGoogleLoading] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      const session = await signIn(values)
      setSession(session)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && session.stage === 'active' ? from : STAGE_ROUTE[session.stage])
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Something went wrong. Try again.')
    }
  }

  function handleDemo() {
    seedSignedInSession()
    setSession({ accountId: 'me', maskedContact: 'y•••@example.com', stage: 'active' })
    navigate('/discover')
  }

  async function handleGoogle() {
    setFormError(null)
    setGoogleLoading(true)
    try {
      const { stage } = await continueWithGoogle()
      setSession({ accountId: 'me', maskedContact: 'demo.google@gmail.com', stage })
      navigate(STAGE_ROUTE[stage])
    } finally {
      setGoogleLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-ink-900">Sign in</h1>
      <p className="mt-1 text-sm text-ink-500">Welcome back to Flingra.</p>

      <Card className="mt-6">
        <GoogleButton label="Continue with Google" loading={googleLoading} onClick={handleGoogle} className="w-full" />

        <div className="my-5 flex items-center gap-3 text-xs font-medium text-ink-400">
          <span className="h-px flex-1 bg-ink-100" />
          or sign in with email
          <span className="h-px flex-1 bg-ink-100" />
        </div>

        <form className="flex flex-col gap-5" onSubmit={handleSubmit(onSubmit)} noValidate>
          {formError && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {formError}
            </p>
          )}

          <Field id="identifier" label="Email or mobile number" error={errors.identifier?.message}>
            <Input id="identifier" autoComplete="username" aria-invalid={!!errors.identifier} {...register('identifier')} />
          </Field>

          <Field id="password" label="Password" error={errors.password?.message}>
            <PasswordInput id="password" autoComplete="current-password" aria-invalid={!!errors.password} {...register('password')} />
          </Field>

          <div className="-mt-2 text-right">
            <Link to="/password/forgot" className="text-sm font-semibold text-primary-600 hover:underline">
              Forgot password?
            </Link>
          </div>

          <Button type="submit" loading={isSubmitting}>
            Sign in
          </Button>
        </form>
      </Card>

      <p className="mt-6 text-center text-xs text-ink-400">
        Demo credentials: you@example.com / Password1!
      </p>

      <p className="mt-3 text-center text-sm text-ink-500">
        New to Flingra?{' '}
        <Link to="/signup" className="font-semibold text-primary-600 hover:underline">
          Create an account
        </Link>
      </p>

      <p className="mt-2 text-center text-sm">
        <button type="button" onClick={handleDemo} className="cursor-pointer font-semibold text-ink-400 underline-offset-4 hover:text-ink-700 hover:underline">
          Continue with a demo profile
        </button>
      </p>
    </div>
  )
}
