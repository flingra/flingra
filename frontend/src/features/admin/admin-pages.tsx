import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog } from '@/components/ui/dialog'
import { formatNaira } from '@/lib/utils'
import { adminApi, type AdminRole, type MeetupDisputeItem, type ReviewItem, type SafetyReviewItem } from '@/lib/api/admin'
import { ApiError } from '@/lib/api/types'
import { useAdminStore } from '@/lib/stores/admin-store'
import { auditEventLabel, auditMetadataEntries, formatDate, humanize } from './admin-ui'

export function AdminLoginPage() {
  const setSession = useAdminStore((state) => state.setSession)
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [requiresMfa, setRequiresMfa] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  return <div className="flex min-h-screen items-center justify-center bg-ink-50 px-6"><Card className="w-full max-w-md"><h1 className="mb-2 text-2xl font-bold">Admin sign in</h1><p className="mb-6 text-sm text-ink-500">Use your Flingra administrator credentials.</p><form className="space-y-4" onSubmit={async (event) => { event.preventDefault(); setLoading(true); setError(null); try { setSession(await adminApi.login({ email, password, ...(requiresMfa ? { mfaCode } : {}) })); navigate('/admin') } catch (e) { if (e instanceof ApiError && ['ADMIN_MFA_REQUIRED', 'ADMIN_MFA_INVALID'].includes(e.code)) setRequiresMfa(true); setError(e instanceof ApiError ? e.message : 'Unable to sign in.') } finally { setLoading(false) } }}><Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required /><Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />{requiresMfa && <Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6-digit authenticator code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))} required />}{error && <p className="text-sm text-danger">{error}</p>}<Button className="w-full" type="submit" loading={loading}>Sign in</Button></form></Card></div>
}

export function AdminReviewsPage() {
  const adminRole = useAdminStore((state) => state.session?.role)
  const [items, setItems] = useState<ReviewItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [documentUrl, setDocumentUrl] = useState<string | null>(null)
  const [documentError, setDocumentError] = useState<string | null>(null)
  const [profilePhotoUrls, setProfilePhotoUrls] = useState<string[]>([])
  const [profilePhotoError, setProfilePhotoError] = useState<string | null>(null)
  const [selectedReview, setSelectedReview] = useState<Awaited<ReturnType<typeof adminApi.getReview>> | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [decisionLoading, setDecisionLoading] = useState(false)
  const detailsRequest = useRef(0)
  const load = () => adminApi.reviews().then((result) => setItems(result.items)).catch((e) => setError(e instanceof ApiError ? e.message : 'Unable to load reviews.'))
  useEffect(() => { void load() }, [])

  useEffect(() => () => {
    detailsRequest.current += 1
  }, [])

  function closeReview() {
    detailsRequest.current += 1
    setSelectedReview(null)
    setDetailsLoading(false)
    setDocumentUrl(null)
    setDocumentError(null)
    setProfilePhotoUrls([])
    setProfilePhotoError(null)
  }

  async function viewReview(reviewId: string) {
    closeReview()
    const requestId = ++detailsRequest.current
    setError(null)
    setDetailsLoading(true)
    try {
      const details = await adminApi.getReview(reviewId)
      if (requestId !== detailsRequest.current) return
      setSelectedReview(details)
      if (adminRole === 'super_admin') {
        setDocumentUrl(adminApi.reviewDocumentUrl(reviewId))
        const photoIds = details.photos
          .map((photo) => /^\/media\/([0-9a-f]{32})$/.exec(photo)?.[1] ?? null)
          .filter((mediaId): mediaId is string => mediaId !== null)
        setProfilePhotoUrls(photoIds.map((mediaId) => adminApi.reviewProfilePhotoUrl(reviewId, mediaId)))
      }
    } catch (e) {
      if (requestId === detailsRequest.current) {
        setError(e instanceof ApiError ? e.message : 'Unable to load review details.')
      }
    } finally {
      if (requestId === detailsRequest.current) setDetailsLoading(false)
    }
  }

  async function decideReview(decision: 'approved' | 'rejected') {
    if (!selectedReview) return
    setDecisionLoading(true)
    try {
      await adminApi.decide(
        selectedReview.reviewId,
        decision,
        `${decision === 'approved' ? 'Approved' : 'Rejected'} account verification by administrator`,
      )
      closeReview()
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Unable to resolve review.')
    } finally {
      setDecisionLoading(false)
    }
  }

  return (
    <section>
      <h1 className="mb-6 text-3xl font-bold">Account verification queue</h1>
      {error && <p className="mb-4 text-danger">{error}</p>}
      <div className="space-y-3">
        {items.length ? items.map((item) => (
          <Card key={item.reviewId} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold">{item.displayName || 'Unnamed profile'}</p>
              <p className="text-sm text-ink-500">
                {item.documentType || 'Identity document'} · {item.accountId}
              </p>
              <p className="text-xs text-ink-500">
                Profile: {item.profileStatus} · Document: {item.documentStatus}
              </p>
            </div>
            <Button size="sm" variant="accent" onClick={() => void viewReview(item.reviewId)}>
              Review account
            </Button>
          </Card>
        )) : <Card>No account verifications are waiting for review.</Card>}
      </div>

      <Dialog
        open={detailsLoading || selectedReview !== null}
        onClose={closeReview}
        title="Account verification"
        description="Review the account profile and submitted identity document together."
        className="max-w-3xl"
      >
        {detailsLoading && <p className="text-sm text-ink-500">Loading account details…</p>}
        {selectedReview && (
          <>
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <h3 className="mb-3 font-semibold text-ink-900">Account profile</h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                  <div><dt className="text-ink-500">Display name</dt><dd className="font-medium">{selectedReview.displayName || '—'}</dd></div>
                  <div><dt className="text-ink-500">Date of birth</dt><dd className="font-medium">{selectedReview.dateOfBirth}</dd></div>
                  <div><dt className="text-ink-500">Contact</dt><dd className="font-medium">{selectedReview.contact}</dd></div>
                  <div><dt className="text-ink-500">Identity</dt><dd className="font-medium">{selectedReview.identity}</dd></div>
                  <div><dt className="text-ink-500">Account status</dt><dd className="font-medium">{selectedReview.accountStatus}</dd></div>
                  <div><dt className="text-ink-500">Profile review</dt><dd className="font-medium">{selectedReview.profileStatus}</dd></div>
                  <div><dt className="text-ink-500">Document type</dt><dd className="font-medium">{selectedReview.documentType ?? '—'}</dd></div>
                  <div><dt className="text-ink-500">Document status</dt><dd className="font-medium">{selectedReview.documentStatus}</dd></div>
                </dl>
                <p className="mt-4 whitespace-pre-wrap text-sm text-ink-700">{selectedReview.bio || 'No bio provided.'}</p>
                <p className="mt-2 text-sm text-ink-500">Area: {selectedReview.area || 'Not provided'}</p>
                <p className="mt-1 break-all text-xs text-ink-400">Account ID: {selectedReview.accountId}</p>
                {adminRole === 'super_admin' && profilePhotoUrls.length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-2 text-sm font-medium text-ink-700">Profile photos</h4>
                    <div className="flex flex-wrap gap-2">
                      {profilePhotoUrls.map((url) => (
                        <img key={url} src={url} alt="Member profile" className="size-24 rounded-xl object-cover" onError={() => setProfilePhotoError('One or more profile photos could not be loaded.')} />
                      ))}
                    </div>
                  </div>
                )}
                {adminRole !== 'super_admin' && <p className="mt-4 text-sm text-ink-500">Sensitive uploads are available to super admins only.</p>}
                {profilePhotoError && <p className="mt-2 text-sm text-danger">{profilePhotoError}</p>}
              </div>
              <div>
                <h3 className="mb-3 font-semibold text-ink-900">Submitted identity document</h3>
                {documentError && <p className="text-sm text-danger">{documentError}</p>}
                {documentUrl && selectedReview.contentType.startsWith('image/') && (
                  <img
                    src={documentUrl}
                    alt={`Submitted ${selectedReview.documentType ?? 'identity'} document`}
                    className="max-h-[50vh] w-full rounded-xl bg-ink-50 object-contain"
                    onError={() => setDocumentError('Unable to display the identity document.')}
                  />
                )}
                {documentUrl && selectedReview.contentType === 'application/pdf' && (
                  <iframe title="Submitted identity document" src={documentUrl} className="h-[50vh] w-full rounded-xl border border-ink-100" />
                )}
                {adminRole !== 'super_admin' && <p className="text-sm text-ink-500">The identity document is available to super admins only.</p>}
                {documentUrl && !selectedReview.contentType.startsWith('image/') && selectedReview.contentType !== 'application/pdf' && (
                  <p className="text-sm text-ink-500">This document format cannot be previewed in the admin panel.</p>
                )}
                <p className="mt-2 text-xs text-ink-500">
                  Submitted {new Date(selectedReview.documentSubmittedAt).toLocaleString()} · {selectedReview.sizeBytes.toLocaleString()} bytes
                </p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" disabled={decisionLoading} onClick={() => void decideReview('rejected')}>
                Reject account
              </Button>
              <Button variant="accent" loading={decisionLoading} onClick={() => void decideReview('approved')}>
                Approve account
              </Button>
            </div>
          </>
        )}
      </Dialog>
    </section>
  )
}

export function AdminSafetyReviewsPage() {
  const [items, setItems] = useState<SafetyReviewItem[]>([]); const [error, setError] = useState<string | null>(null)
  const load = () => adminApi.safetyReviews().then(setItems).catch((e) => setError(e instanceof ApiError ? e.message : 'Unable to load safety reviews.'))
  async function decide(id: string, decision: 'reviewed' | 'dismissed') {
    try { await adminApi.decideSafetyReview(id, decision, `${decision === 'dismissed' ? 'Dismissed' : 'Reviewed and actioned'} by administrator`); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to resolve safety review.') }
  }
  useEffect(() => { void load() }, [])
  return <section><h1 className="mb-2 text-3xl font-bold">Safety reviews</h1><p className="mb-6 text-sm text-ink-500">Filed automatically whenever a member blocks someone — repeat or serious reports can lead to a ban.</p>{error && <p className="mb-4 text-danger">{error}</p>}<div className="space-y-3">{items.length ? items.map((item) => <Card key={item.reviewId} className="flex items-center justify-between"><div><p className="font-semibold">{item.targetName || item.targetId}</p><p className="text-sm text-ink-500">{item.reason}{item.requesterName ? ` · requested by ${item.requesterName}` : ` · requested by ${item.requesterId}`}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => void decide(item.reviewId, 'dismissed')}>Dismiss</Button><Button size="sm" variant="destructive" onClick={() => void decide(item.reviewId, 'reviewed')}>Mark reviewed</Button></div></Card>) : <Card>No open safety reviews.</Card>}</div></section>
}

export function AdminMeetupDisputesPage() {
  const [items, setItems] = useState<MeetupDisputeItem[]>([]); const [error, setError] = useState<string | null>(null)
  const load = () => adminApi.meetupDisputes().then(setItems).catch((e) => setError(e instanceof ApiError ? e.message : 'Unable to load disputes.'))
  async function resolve(id: string, resolution: 'release' | 'refund') {
    try { await adminApi.resolveMeetupDispute(id, resolution, `${resolution === 'refund' ? 'Refunded payer' : 'Released to recipient'} by administrator`); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to resolve dispute.') }
  }
  useEffect(() => { void load() }, [])
  return <section><h1 className="mb-2 text-3xl font-bold">Meetup payment disputes</h1><p className="mb-6 text-sm text-ink-500">Held meetup payments either party has disputed — release pays the recipient, refund returns the payer.</p>{error && <p className="mb-4 text-danger">{error}</p>}<div className="space-y-3">{items.length ? items.map((item) => <Card key={item.id} className="flex items-center justify-between"><div><p className="font-semibold">{item.payerName} → {item.recipientName}</p><p className="text-sm text-ink-500">{formatNaira(item.amountNaira)}{item.reason ? ` · ${item.reason}` : ''}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => void resolve(item.id, 'refund')}>Refund payer</Button><Button size="sm" variant="accent" onClick={() => void resolve(item.id, 'release')}>Release to recipient</Button></div></Card>) : <Card>No open disputes.</Card>}</div></section>
}

export function AdminAccountsPage() {
  const [accounts, setAccounts] = useState<Awaited<ReturnType<typeof adminApi.accounts>>['items']>([]); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [role, setRole] = useState<AdminRole>('reviewer'); const [error, setError] = useState<string | null>(null)
  const load = () => adminApi.accounts().then((result) => setAccounts(result.items)).catch((e) => setError(e instanceof ApiError ? e.message : 'Unable to load admins.'))
  useEffect(() => { void load() }, [])
  async function updateAccount(id: string, body: { role?: AdminRole; disabled?: boolean }) {
    try { await adminApi.updateAccount(id, body); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to update admin account.') }
  }
  return <section><h1 className="mb-6 text-3xl font-bold">Admin accounts</h1><Card className="mb-6"><form className="grid gap-3 md:grid-cols-4" onSubmit={async (e) => { e.preventDefault(); try { await adminApi.createAccount({ email, password, role }); setEmail(''); setPassword(''); await load() } catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to create admin.') } }}><Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required /><Input type="password" minLength={14} placeholder="Password (14+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required /><select className="rounded-xl border border-ink-200 px-3" value={role} onChange={(e) => setRole(e.target.value as AdminRole)}><option value="admin">Admin</option><option value="reviewer">Reviewer</option><option value="safety_admin">Safety admin</option><option value="auditor">Auditor</option><option value="super_admin">Super admin</option></select><Button type="submit">Add admin</Button></form>{error && <p className="mt-3 text-sm text-danger">{error}</p>}</Card><div className="space-y-3">{accounts.map((account) => <Card key={account.adminId} className="flex flex-wrap items-center justify-between gap-3"><span>{account.email}</span><div className="flex items-center gap-3"><select aria-label={`Role for ${account.email}`} className="rounded-xl border border-ink-200 px-3 py-2 text-sm" value={account.role} onChange={(e) => void updateAccount(account.adminId, { role: e.target.value as AdminRole })}><option value="admin">Admin</option><option value="reviewer">Reviewer</option><option value="safety_admin">Safety admin</option><option value="auditor">Auditor</option><option value="super_admin">Super admin</option></select><span className="text-sm text-ink-500">{account.disabled ? 'disabled' : 'active'}</span><Button size="sm" variant="outline" onClick={() => void updateAccount(account.adminId, { disabled: !account.disabled })}>{account.disabled ? 'Enable' : 'Disable'}</Button></div></Card>)}</div></section>
}

export function AdminAuditPage() {
  const [accountId, setAccountId] = useState('')
  const [events, setEvents] = useState<Array<{ eventType: string; outcome: string; createdAt: string; metadata: unknown }>>([])
  const [error, setError] = useState<string | null>(null)
  return (
    <section>
      <h1 className="mb-2 text-3xl font-bold">Member activity</h1>
      <p className="mb-6 text-sm text-ink-500">A readable history of security, account, and moderation activity for one member.</p>
      <Card>
        <form className="flex gap-3" onSubmit={async (event) => {
          event.preventDefault()
          try {
            setError(null)
            const result = await adminApi.audit(accountId)
            setEvents(result.items)
          } catch (e) {
            setError(e instanceof ApiError ? e.message : 'Unable to load member activity.')
          }
        }}>
          <Input aria-label="Member account ID" placeholder="Member account ID" value={accountId} onChange={(event) => setAccountId(event.target.value)} required />
          <Button type="submit">View activity</Button>
        </form>
      </Card>
      {error && <p className="mt-4 text-danger">{error}</p>}
      <div className="mt-6 space-y-3">
        {events.map((event, index) => {
          const metadata = auditMetadataEntries(event.metadata)
          return (
            <Card key={`${event.eventType}-${index}`}>
              <div className="flex flex-wrap justify-between gap-2">
                <strong>{auditEventLabel(event.eventType)}</strong>
                <span className="text-sm text-ink-500">{humanize(event.outcome)}</span>
              </div>
              <p className="mt-1 text-sm text-ink-500">{formatDate(event.createdAt)}</p>
              {metadata.length > 0 && (
                <dl className="mt-3 grid gap-x-6 gap-y-2 rounded-lg bg-ink-50 p-3 text-sm sm:grid-cols-2">
                  {metadata.map((entry) => (
                    <div key={entry.label}><dt className="text-ink-500">{entry.label}</dt><dd className="break-words text-ink-900">{entry.value}</dd></div>
                  ))}
                </dl>
              )}
            </Card>
          )
        })}
      </div>
    </section>
  )
}
