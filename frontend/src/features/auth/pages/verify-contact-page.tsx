import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { AuthPageShell } from '../components/auth-page-shell'
import { resendCode, verifyContact } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'
import { useToast } from '@/components/ui/toast'

export function VerifyContactPage() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const session = useSessionStore((state) => state.session)
  const setSession = useSessionStore((state) => state.setSession)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => setCooldown((value) => value - 1), 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const { stage } = await verifyContact(code)
      if (session) setSession({ ...session, stage })
      navigate(stage === 'needs-onboarding' ? '/onboarding' : '/discover')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function onResend() {
    setError(null)
    try {
      await resendCode()
      setCooldown(30)
      showToast({ title: 'Code sent', description: 'Check your email or phone for a new code.', variant: 'success' })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to resend the code. Try again.')
    }
  }

  return (
    <AuthPageShell
      title="Verify your contact"
      subtitle={`We sent a 6-digit code to ${session?.maskedContact ?? 'your contact'}.`}
      footer={
        <Link to="/login" className="font-semibold text-primary-600 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <Card className="transition-shadow duration-300 hover:shadow-float">
        <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
          {error && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {error}
            </p>
          )}

          <Field id="code" label="Verification code" error={undefined}>
            <Input
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </Field>

          <Button type="submit" loading={submitting}>
            Verify
          </Button>

          <Button type="button" variant="ghost" onClick={onResend} disabled={cooldown > 0}>
            {cooldown > 0 ? `Resend code (${cooldown}s)` : 'Resend code'}
          </Button>
        </form>
      </Card>
    </AuthPageShell>
  )
}
