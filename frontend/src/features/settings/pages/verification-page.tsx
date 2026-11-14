import { type ChangeEvent, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BadgeCheck, Clock, FileText, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { PageSpinner } from '@/components/ui/spinner'
import { useToast } from '@/components/ui/toast'
import { getOwnProfile, uploadIdentityDocument } from '@/lib/api/profiles'
import type { VerificationDocumentType, VerificationStatus } from '@/lib/api/types'

const STATUS_COPY: Record<VerificationStatus, { label: string; className: string; icon: typeof ShieldCheck }> = {
  unverified: { label: 'Not started', className: 'bg-ink-100 text-ink-600', icon: ShieldAlert },
  pending: { label: 'Under review', className: 'bg-warning/10 text-warning', icon: Clock },
  verified: { label: 'Verified', className: 'bg-success/10 text-success', icon: ShieldCheck },
  rejected: { label: 'Rejected — resubmit', className: 'bg-danger/10 text-danger', icon: ShieldAlert },
}

function StatusBadge({ status }: { status: VerificationStatus }) {
  const { label, className, icon: Icon } = STATUS_COPY[status]
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${className}`}>
      <Icon className="size-3.5" aria-hidden="true" /> {label}
    </span>
  )
}

const DOCUMENT_LABELS: Record<VerificationDocumentType, string> = {
  NIN: 'National Identification Number (NIN) slip',
  BVN: 'Bank Verification Number (BVN) slip',
  'voters-card': "Voter's card",
}

export function VerificationPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { data: profile, isLoading } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile })

  const [documentType, setDocumentType] = useState<VerificationDocumentType>('NIN')
  const [uploading, setUploading] = useState(false)

  async function handleDocumentUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadIdentityDocument(file, documentType)
      await queryClient.invalidateQueries({ queryKey: ['own-profile'] })
      showToast({
        title: 'Document submitted',
        description: 'Our safety team typically reviews documents within 24 hours.',
        variant: 'success',
      })
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  if (isLoading || !profile) return <PageSpinner label="Loading verification status" />

  const isWoman = profile.identity === 'woman'

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Verification</h1>
      <p className="mt-1 text-sm text-ink-500">
        Verification keeps Flingra safe by confirming members are who they say they are.
      </p>

      {isWoman && (
        <Card className="mt-6">
          <div className="flex flex-wrap items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <BadgeCheck className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-bold text-ink-900">Government ID verification</h2>
              <p className="text-sm text-ink-500">Required for female accounts to confirm your identity and age.</p>
            </div>
            <StatusBadge status={profile.documentVerification ?? 'unverified'} />
          </div>

          <div className="mt-5 flex flex-col gap-4">
            <Select
              id="documentType"
              value={profile.documentType ?? documentType}
              onChange={(event) => setDocumentType(event.target.value as VerificationDocumentType)}
            >
              <option value="NIN">NIN</option>
              <option value="BVN">BVN</option>
              <option value="voters-card">Voter's card</option>
            </Select>
            <p className="text-xs text-ink-400">
              Upload a clear photo of your {DOCUMENT_LABELS[profile.documentType ?? documentType].toLowerCase()}. We
              only use this to confirm your identity and age — it's never shown on your profile.
            </p>
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-full border-2 border-dashed border-ink-200 px-4 py-6 text-sm font-semibold text-ink-500 hover:border-ink-300">
              <FileText className="size-4" aria-hidden="true" />
              {uploading ? 'Uploading…' : profile.documentVerification && profile.documentVerification !== 'unverified' ? 'Resubmit document' : 'Upload document'}
              <input type="file" accept="image/*" className="sr-only" onChange={handleDocumentUpload} disabled={uploading} />
            </label>
          </div>
        </Card>
      )}
    </div>
  )
}
