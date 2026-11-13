import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { PasswordInput } from '@/components/ui/password-input'
import { Button } from '@/components/ui/button'
import { resetPassword } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/types'

const schema = z
  .object({
    password: z.string().min(8, 'Use at least 8 characters.'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords must match.',
    path: ['confirmPassword'],
  })

type FormValues = z.infer<typeof schema>

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [done, setDone] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      await resetPassword(token, values.password)
      setDone(true)
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Something went wrong. Try again.')
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-ink-900">Set a new password</h1>

      <Card className="mt-6">
        {done ? (
          <div className="flex flex-col gap-4">
            <p role="status" className="text-sm text-ink-700">
              Your password has been reset. Sign in with your new password.
            </p>
            <Link to="/login" className="text-sm font-semibold text-primary-600 hover:underline">
              Go to sign in
            </Link>
          </div>
        ) : (
          <form className="flex flex-col gap-5" onSubmit={handleSubmit(onSubmit)} noValidate>
            {formError && (
              <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
                {formError}{' '}
                <Link to="/password/forgot" className="underline">
                  Request a new link
                </Link>
              </p>
            )}
            <Field id="password" label="New password" error={errors.password?.message}>
              <PasswordInput id="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register('password')} />
            </Field>
            <Field id="confirmPassword" label="Confirm new password" error={errors.confirmPassword?.message}>
              <PasswordInput
                id="confirmPassword"
                autoComplete="new-password"
                aria-invalid={!!errors.confirmPassword}
                {...register('confirmPassword')}
              />
            </Field>
            <Button type="submit" loading={isSubmitting}>
              Reset password
            </Button>
          </form>
        )}
      </Card>
    </div>
  )
}
