import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { BadgeCheck, Clock3, FileText, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { getOwnProfile } from '@/lib/api/profiles'
import { IDENTITY_VERIFICATION_REQUIRED_EVENT } from '@/lib/api/client'
import type { VerificationStatus } from '@/lib/api/types'

const STATUS_CONTENT: Record<VerificationStatus, { title: string; description: string; icon: typeof ShieldAlert }> = {
  unverified: {
    title: 'Verify your identity to continue',
    description: 'Your identity document has not been submitted yet.',
    icon: FileText,
  },
  pending: {
    title: 'Your verification is under review',
    description: 'You can use this feature once our safety team approves your document. No further action is needed while it is being reviewed.',
    icon: Clock3,
  },
  verified: {
    title: 'Refresh your verification status',
    description: 'Your profile appears verified, but this request was blocked. Refresh the page and try again. Contact support if it continues.',
    icon: BadgeCheck,
  },
  rejected: {
    title: 'Please resubmit your identity document',
    description: 'Your last submission was not approved. Upload a clear, readable image of an accepted identity document.',
    icon: ShieldAlert,
  },
}

export function IdentityVerificationPrompt() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { data: profile, isError, isLoading } = useQuery({
    queryKey: ['own-profile'],
    queryFn: getOwnProfile,
    enabled: open,
    staleTime: 0,
    refetchOnMount: 'always',
  })

  useEffect(() => {
    const showPrompt = () => setOpen(true)
    window.addEventListener(IDENTITY_VERIFICATION_REQUIRED_EVENT, showPrompt)
    return () => window.removeEventListener(IDENTITY_VERIFICATION_REQUIRED_EVENT, showPrompt)
  }, [])

  const status = profile?.documentVerification ?? (isLoading || isError ? null : 'unverified')
  const content = status ? STATUS_CONTENT[status] : null
  const StatusIcon = content?.icon ?? ShieldAlert

  return (
    <Dialog
      open={open}
      onClose={() => setOpen(false)}
      title="Identity verification required"
      description="This feature is available after your identity has been approved."
    >
      <div className="flex items-start gap-3 rounded-2xl bg-primary-50 p-4">
        <StatusIcon className="mt-0.5 size-5 shrink-0 text-primary-700" aria-hidden="true" />
        <div>
          <h3 className="font-semibold text-ink-900">
            {content?.title ?? (isLoading ? 'Checking your verification status' : 'Verification status unavailable')}
          </h3>
          <p className="mt-1 text-sm text-ink-600">
            {content?.description ?? 'We could not load your status. Open Verification to check it.'}
          </p>
        </div>
      </div>

      {(status === 'unverified' || status === 'rejected') && (
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-ink-600">
          <li>Open your Verification page.</li>
          <li>Select NIN, BVN, or voter’s card and upload a clear photo where the details are readable.</li>
          <li>Wait for the safety team to review it; the feature unlocks after approval.</li>
        </ol>
      )}

      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={() => setOpen(false)}>
          Not now
        </Button>
        <Button
          onClick={() => {
            setOpen(false)
            navigate('/settings/verification')
          }}
        >
          Go to verification
        </Button>
      </div>
    </Dialog>
  )
}
