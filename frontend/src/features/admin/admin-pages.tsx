import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog } from '@/components/ui/dialog'
import { formatNaira } from '@/lib/utils'
import { adminApi, type AdminRole, type MeetupDisputeItem, type ReviewItem, type SafetyReviewItem } from '@/lib/api/admin'
import { ApiError } from '@/lib/api/types'
import { useAdminStore } from '@/lib/stores/admin-store'

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
  const [items, setItems] = useState<ReviewItem[]>([]); const [error, setError] = useState<string | null>(null)
  const [documentUrl, setDocumentUrl] = useState<string | null>(null); const [documentError, setDocumentError] = useState<string | null>(null)
  const [selectedReview, setSelectedReview] = useState<Record<string, unknown> | null>(null)
  const load = () => adminApi.reviews().then((result) => setItems(result.items)).catch((e) => setError(e instanceof ApiError ? e.message : 'Unable to load reviews.'))
  useEffect(() => { void load() }, [])
  function closeDocument() { if (documentUrl) URL.revokeObjectURL(documentUrl); setDocumentUrl(null); setDocumentError(null) }
  async function viewReview(reviewId: string) {
    try { setSelectedReview(await adminApi.getReview(reviewId)) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to load review details.') }
  }
  async function decideReview(reviewId: string, decision: 'approved' | 'rejected') {
    try { await adminApi.decide(reviewId, decision, `${decision === 'approved' ? 'Approved' : 'Rejected'} by administrator`); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to resolve review.') }
  }
  async function viewDocument(reviewId: string) {
    setDocumentError(null)
    try { setDocumentUrl(URL.createObjectURL(await adminApi.reviewDocumentBlob(reviewId))) }
    catch (e) { setDocumentError(e instanceof ApiError ? e.message : 'Unable to load document.') }
  }
  return <section><h1 className="mb-6 text-3xl font-bold">Review queue</h1>{error && <p className="mb-4 text-danger">{error}</p>}<div className="space-y-3">{items.length ? items.map((item) => <Card key={item.reviewId} className="flex items-center justify-between"><div><p className="font-semibold">{item.displayName || 'Unnamed profile'}</p><p className="text-sm text-ink-500">{item.type} · {item.documentType || 'Profile'} · {item.accountId}</p></div><div className="flex gap-2"><Button size="sm" variant="ghost" onClick={() => void viewReview(item.reviewId)}>Details</Button>{item.documentType && <Button size="sm" variant="ghost" onClick={() => viewDocument(item.reviewId)}>View document</Button>}<Button size="sm" variant="accent" onClick={() => void decideReview(item.reviewId, 'approved')}>Approve</Button><Button size="sm" variant="outline" onClick={() => void decideReview(item.reviewId, 'rejected')}>Reject</Button></div></Card>) : <Card>No pending reviews.</Card>}</div>
    <Dialog open={selectedReview !== null} onClose={() => setSelectedReview(null)} title="Review details">
      {selectedReview && <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap text-sm">{JSON.stringify(selectedReview, null, 2)}</pre>}
    </Dialog>
    <Dialog open={Boolean(documentUrl) || Boolean(documentError)} onClose={closeDocument} title="Verification document">
      {documentError ? <p className="text-sm text-danger">{documentError}</p> : documentUrl && <img src={documentUrl} alt="Submitted verification document" className="max-h-[70vh] w-full rounded-xl object-contain" />}
    </Dialog>
  </section>
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
  return <section><h1 className="mb-6 text-3xl font-bold">Admin accounts</h1><Card className="mb-6"><form className="grid gap-3 md:grid-cols-4" onSubmit={async (e) => { e.preventDefault(); try { await adminApi.createAccount({ email, password, role }); setEmail(''); setPassword(''); await load() } catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to create admin.') } }}><Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required /><Input type="password" minLength={14} placeholder="Password (14+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required /><select className="rounded-xl border border-ink-200 px-3" value={role} onChange={(e) => setRole(e.target.value as AdminRole)}><option value="reviewer">Reviewer</option><option value="safety_admin">Safety admin</option><option value="auditor">Auditor</option><option value="super_admin">Super admin</option></select><Button type="submit">Add admin</Button></form>{error && <p className="mt-3 text-sm text-danger">{error}</p>}</Card><div className="space-y-3">{accounts.map((account) => <Card key={account.adminId} className="flex flex-wrap items-center justify-between gap-3"><span>{account.email}</span><div className="flex items-center gap-3"><select aria-label={`Role for ${account.email}`} className="rounded-xl border border-ink-200 px-3 py-2 text-sm" value={account.role} onChange={(e) => void updateAccount(account.adminId, { role: e.target.value as AdminRole })}><option value="reviewer">Reviewer</option><option value="safety_admin">Safety admin</option><option value="auditor">Auditor</option><option value="super_admin">Super admin</option></select><span className="text-sm text-ink-500">{account.disabled ? 'disabled' : 'active'}</span><Button size="sm" variant="outline" onClick={() => void updateAccount(account.adminId, { disabled: !account.disabled })}>{account.disabled ? 'Enable' : 'Disable'}</Button></div></Card>)}</div></section>
}

export function AdminAuditPage() {
  const [accountId, setAccountId] = useState(''); const [events, setEvents] = useState<Array<{ eventType: string; outcome: string; createdAt: string }>>([]); const [error, setError] = useState<string | null>(null)
  return <section><h1 className="mb-6 text-3xl font-bold">User audit history</h1><Card><form className="flex gap-3" onSubmit={async (e) => { e.preventDefault(); try { setError(null); const result = await adminApi.audit(accountId); setEvents(result.items) } catch (e) { setError(e instanceof ApiError ? e.message : 'Unable to load audit history.') } }}><Input placeholder="Account ID" value={accountId} onChange={(e) => setAccountId(e.target.value)} required /><Button type="submit">View audit</Button></form></Card>{error && <p className="mt-4 text-danger">{error}</p>}<div className="mt-6 space-y-3">{events.map((event, index) => <Card key={`${event.eventType}-${index}`}><div className="flex justify-between"><strong>{event.eventType}</strong><span className="text-sm text-ink-500">{event.outcome}</span></div><p className="text-sm text-ink-500">{event.createdAt}</p></Card>)}</div></section>
}
