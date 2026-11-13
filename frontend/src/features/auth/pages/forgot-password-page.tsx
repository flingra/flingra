import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { requestPasswordReset } from '@/lib/api/auth'

const schema = z.object({ identifier: z.string().min(1, 'Enter your email or mobile number.') })
type FormValues = z.infer<typeof schema>

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    await requestPasswordReset(values.identifier)
    setSent(true)
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold text-ink-900">Reset your password</h1>
      <p className="mt-1 text-sm text-ink-500">We'll send recovery instructions if an account matches.</p>

      <Card className="mt-6">
        {sent ? (
          <p role="status" className="text-sm text-ink-700">
            If an account matches those details, recovery instructions will be sent. Check your email or
            phone.
          </p>
        ) : (
          <form className="flex flex-col gap-5" onSubmit={handleSubmit(onSubmit)} noValidate>
            <Field id="identifier" label="Email or mobile number" error={errors.identifier?.message}>
              <Input id="identifier" autoComplete="username" aria-invalid={!!errors.identifier} {...register('identifier')} />
            </Field>
            <Button type="submit" loading={isSubmitting}>
              Send instructions
            </Button>
          </form>
        )}
      </Card>

      <p className="mt-6 text-center text-sm text-ink-500">
        <Link to="/login" className="font-semibold text-primary-600 hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  )
}
