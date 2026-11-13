import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { KeyRound, Monitor } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { PasswordInput } from '@/components/ui/password-input'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { useToast } from '@/components/ui/toast'
import { changePassword, listSessions, revokeSession } from '@/lib/api/settings'
import { ApiError } from '@/lib/api/types'

const schema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password.'),
    newPassword: z.string().min(8, 'Use at least 8 characters.'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: 'Passwords must match.',
    path: ['confirmPassword'],
  })

type FormValues = z.infer<typeof schema>

export function SecurityPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<string | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const { data: sessions, isLoading } = useQuery({ queryKey: ['sessions'], queryFn: listSessions })
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      await changePassword(values.currentPassword, values.newPassword)
      reset()
      showToast({ title: 'Password updated', variant: 'success' })
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Something went wrong. Try again.')
    }
  }

  async function handleRevoke(id: string) {
    setRevokingId(id)
    try {
      await revokeSession(id)
      await queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Security</h1>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <KeyRound className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Change password</h2>
        </div>
        <form className="mt-4 flex flex-col gap-5" onSubmit={handleSubmit(onSubmit)} noValidate>
          {formError && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {formError}
            </p>
          )}
          <Field id="currentPassword" label="Current password" error={errors.currentPassword?.message}>
            <PasswordInput id="currentPassword" autoComplete="current-password" aria-invalid={!!errors.currentPassword} {...register('currentPassword')} />
          </Field>
          <Field id="newPassword" label="New password" error={errors.newPassword?.message}>
            <PasswordInput id="newPassword" autoComplete="new-password" aria-invalid={!!errors.newPassword} {...register('newPassword')} />
          </Field>
          <Field id="confirmPassword" label="Confirm new password" error={errors.confirmPassword?.message}>
            <PasswordInput id="confirmPassword" autoComplete="new-password" aria-invalid={!!errors.confirmPassword} {...register('confirmPassword')} />
          </Field>
          <Button type="submit" loading={isSubmitting}>
            Update password
          </Button>
        </form>
      </Card>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <Monitor className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Active sessions</h2>
        </div>
        {isLoading && <PageSpinner label="Loading sessions" />}
        <ul className="mt-4 flex flex-col gap-3">
          {sessions?.map((session) => (
            <li key={session.id} className="flex items-center gap-3 rounded-2xl border border-ink-100 p-4 transition-shadow hover:shadow-soft">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-ink-50 text-ink-500">
                <Monitor className="size-4" aria-hidden="true" />
              </span>
              <div className="flex-1">
                <p className="flex items-center gap-2 font-medium text-ink-800">
                  {session.device}
                  {session.current && (
                    <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-semibold text-success">This device</span>
                  )}
                </p>
                <p className="text-sm text-ink-500">{session.lastActive}</p>
              </div>
              {!session.current && (
                <Button variant="outline" size="sm" loading={revokingId === session.id} onClick={() => handleRevoke(session.id)}>
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
