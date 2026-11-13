import { type FormEvent, useState } from 'react'
import { Dialog } from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { reportMember } from '@/lib/api/safety'
import type { ReportReason } from '@/lib/api/types'
import { useToast } from '@/components/ui/toast'

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'fake-profile', label: 'Fake profile or impersonation' },
  { value: 'harassment', label: 'Harassment or abuse' },
  { value: 'inappropriate-content', label: 'Inappropriate content' },
  { value: 'underage', label: 'Appears to be under 18' },
  { value: 'other', label: 'Something else' },
]

interface ReportDialogProps {
  open: boolean
  onClose: () => void
  targetId: string
  targetName: string
  onBlocked?: () => void
}

export function ReportDialog({ open, onClose, targetId, targetName, onBlocked }: ReportDialogProps) {
  const { showToast } = useToast()
  const [reason, setReason] = useState<ReportReason>('fake-profile')
  const [description, setDescription] = useState('')
  const [alsoBlock, setAlsoBlock] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await reportMember({ targetId, reason, description: description || undefined, alsoBlock })
      showToast({ title: 'Report submitted', description: "We'll review this and take action if needed.", variant: 'success' })
      if (alsoBlock) onBlocked?.()
      setDescription('')
      setAlsoBlock(false)
      onClose()
    } catch {
      showToast({ title: 'Could not submit report', description: 'Check your connection and try again.', variant: 'error' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Report ${targetName}`} description="We review every report and never share your identity with the reported member.">
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <Field id="report-reason" label="Reason">
          <Select id="report-reason" value={reason} onChange={(event) => setReason(event.target.value as ReportReason)}>
            {REASONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field id="report-description" label="Details" optional hint="Up to 500 characters.">
          <Textarea
            id="report-description"
            maxLength={500}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <label className="flex items-start gap-3 text-sm text-ink-700">
          <Checkbox checked={alsoBlock} onChange={(event) => setAlsoBlock(event.target.checked)} />
          <span>Also block this account</span>
        </label>

        <div className="mt-2 flex gap-3">
          <Button type="button" variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" variant="destructive" loading={submitting} className="flex-1">
            Submit report
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
