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
import { Button } from '@/components/ui/button'
import { currentSession, signUp } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

const schema = z
  .object({
    identifier: z.string().min(3, 'Enter your email or mobile number.'),
    password: z.string().min(8, 'Use at least 8 characters.'),
    confirmPassword: z.string(),
    dateOfBirth: z.string().min(1, 'Enter your date of birth.'),
    acceptedTerms: z.boolean().refine((value) => value === true, { message: 'Accept the terms to continue.' }),
    marketingOptIn: z.boolean().optional(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords must match.',
    path: ['confirmPassword'],
  })

type FormValues = z.infer<typeof schema>

export function SignUpPage() {
  const navigate = useNavigate()
  const setSession = useSessionStore((state) => state.setSession)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      await signUp({
        identifier: values.identifier,
        password: values.password,
        dateOfBirth: values.dateOfBirth,
        acceptedTerms: values.acceptedTerms,
      })
      setSession(currentSession())
      navigate('/verify-contact')
    } catch (error) {
      if (error instanceof ApiError && error.code === 'INELIGIBLE_AGE') {
        setError('dateOfBirth', { message: error.message })
      } else if (error instanceof ApiError) {
        setFormError(error.message)
      } else {
        setFormError('Something went wrong. Check your connection and try again.')
      }
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-ink-900">Create your account</h1>
      <p className="mt-1 text-sm text-ink-500">Flingra is for consenting adults, 18 and older.</p>

      <Card className="mt-6">
        <form className="flex flex-col gap-5" onSubmit={handleSubmit(onSubmit)} noValidate>
          {formError && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {formError}
            </p>
          )}

          <Field id="identifier" label="Email or mobile number" error={errors.identifier?.message}>
            <Input
              id="identifier"
              type="text"
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

          <Field
            id="dateOfBirth"
            label="Date of birth"
            hint="You must be 18 or older to use Flingra."
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

          <Button type="submit" loading={isSubmitting} className="mt-1">
            Create account
          </Button>
        </form>
      </Card>

      <p className="mt-6 text-center text-sm text-ink-500">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-primary-600 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  )
}
