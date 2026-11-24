import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Download, Eye } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { PageSpinner } from '@/components/ui/spinner'
import { useToast } from '@/components/ui/toast'
import { useSignOut } from '@/lib/hooks/use-sign-out'
import { getOwnProfile, saveOwnProfile } from '@/lib/api/profiles'
import { requestAccountDeletion, requestDataExport } from '@/lib/api/settings'
import type { AudiencePreference } from '@/lib/api/types'

export function PrivacyPage() {
  const { showToast } = useToast()
  const { signOutAndRedirect } = useSignOut()
  const { data, isLoading } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile })

  const [wantsToDiscover, setWantsToDiscover] = useState<AudiencePreference>('everyone')
  const [discoverableBy, setDiscoverableBy] = useState<AudiencePreference>('everyone')
  const [saving, setSaving] = useState(false)
  const [exportRequested, setExportRequested] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteConfirmed, setDeleteConfirmed] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (!data) return
    setWantsToDiscover(data.wantsToDiscover)
    setDiscoverableBy(data.discoverableBy)
  }, [data])

  async function handleSavePreferences() {
    setSaving(true)
    try {
      await saveOwnProfile({ wantsToDiscover, discoverableBy })
      showToast({ title: 'Preferences saved', variant: 'success' })
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    await requestDataExport()
    setExportRequested(true)
    showToast({ title: 'Export requested', description: "We'll email you a copy of your data.", variant: 'success' })
  }

  async function handleDelete() {
    setDeleting(true)
    try {
      await requestAccountDeletion()
      await signOutAndRedirect('/')
      showToast({ title: 'Account deletion requested', variant: 'info' })
    } finally {
      setDeleting(false)
    }
  }

  if (isLoading) return <PageSpinner label="Loading privacy settings" />

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Privacy &amp; data</h1>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <Eye className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Discovery visibility</h2>
        </div>
        <p className="mt-3 text-sm text-ink-500">
          Controls discoverability only. It doesn't affect screenshots or past interactions.
        </p>
        <div className="mt-4 flex flex-col gap-5">
          <Field id="wantsToDiscover" label="Who you want to discover">
            <Select id="wantsToDiscover" value={wantsToDiscover} onChange={(event) => setWantsToDiscover(event.target.value as AudiencePreference)}>
              <option value="everyone">Everyone</option>
              <option value="men">Men</option>
              <option value="women">Women</option>
            </Select>
          </Field>
          <Field id="discoverableBy" label="Who may discover you">
            <Select id="discoverableBy" value={discoverableBy} onChange={(event) => setDiscoverableBy(event.target.value as AudiencePreference)}>
              <option value="everyone">Everyone</option>
              <option value="men">Men</option>
              <option value="women">Women</option>
            </Select>
          </Field>
          <Button onClick={handleSavePreferences} loading={saving}>
            Save preferences
          </Button>
        </div>
      </Card>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <Download className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Your data</h2>
        </div>
        <p className="mt-3 text-sm text-ink-500">Request a copy of the data linked to your account.</p>
        <Button variant="outline" className="mt-4" onClick={handleExport} disabled={exportRequested}>
          {exportRequested ? 'Export requested' : 'Request data export'}
        </Button>
      </Card>

      <Card className="mt-6 border-danger/20">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger">
            <AlertTriangle className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-danger">Delete account</h2>
        </div>
        <p className="mt-3 text-sm text-ink-500">
          This permanently removes your profile from discovery. Some records may be retained where required
          by law.
        </p>
        <Button variant="destructive" className="mt-4" onClick={() => setDeleteOpen(true)}>
          Delete account
        </Button>
      </Card>

      <Dialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete your account?"
        description="Your profile will stop appearing in discovery immediately. This action can't be undone from the app."
      >
        <label className="flex items-start gap-3 text-sm text-ink-700">
          <Checkbox checked={deleteConfirmed} onChange={(event) => setDeleteConfirmed(event.target.checked)} />
          I understand this is permanent and I want to delete my account.
        </label>
        <div className="mt-5 flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" className="flex-1" disabled={!deleteConfirmed} loading={deleting} onClick={handleDelete}>
            Delete my account
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
