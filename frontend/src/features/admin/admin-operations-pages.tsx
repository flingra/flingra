import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatNaira } from '@/lib/utils'
import { adminApi, type AdminAuditEvent, type AdminPayout, type AdminPrivacyRequest, type AdminSafetyReport, type AdminUser } from '@/lib/api/admin'
import { ApiError } from '@/lib/api/types'

function messageFor(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

export function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function load(value = query) {
    try {
      setError(null)
      setUsers((await adminApi.users(value)).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load members.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function setStatus(user: AdminUser) {
    const status = user.accountStatus === 'active' ? 'suspended' : 'active'
    try {
      await adminApi.setUserStatus(user.accountId, status, status === 'active' ? 'Reactivated by administrator' : 'Suspended by administrator')
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to update member status.'))
    }
  }

  async function revokeSessions(user: AdminUser) {
    try {
      const { revokedCount } = await adminApi.revokeUserSessions(user.accountId)
      setError(null)
      window.alert(`Revoked ${revokedCount} session${revokedCount === 1 ? '' : 's'}.`)
    } catch (e) {
      setError(messageFor(e, 'Unable to revoke member sessions.'))
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setQuery(search.trim())
    void load(search.trim())
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Member accounts</h1>
    <Card className="mb-5">
      <form className="flex gap-3" onSubmit={submit}>
        <Input aria-label="Search members" placeholder="Email, display name, or account ID" value={search} onChange={(event) => setSearch(event.target.value)} />
        <Button type="submit">Search</Button>
      </form>
    </Card>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{users.map((user) => <Card key={user.accountId} className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="font-semibold">{user.displayName || user.email || user.accountId}</p>
        <p className="text-sm text-ink-500">{user.email || 'No email'} · {user.accountStatus} · profile {user.moderationStatus || 'n/a'} · ID {user.documentVerification || 'n/a'}</p>
        <p className="text-xs text-ink-400">{user.accountId}</p>
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => void revokeSessions(user)}>Revoke sessions</Button>
        {(user.accountStatus === 'active' || user.accountStatus === 'suspended' || user.accountStatus === 'banned') &&
          <Button size="sm" variant={user.accountStatus === 'active' ? 'destructive' : 'accent'} onClick={() => void setStatus(user)}>
            {user.accountStatus === 'active' ? 'Suspend' : 'Reactivate'}
          </Button>}
        {user.accountStatus === 'active' && <Button size="sm" variant="outline" onClick={async () => {
          try {
            await adminApi.setUserStatus(user.accountId, 'banned', 'Permanently banned by administrator')
            await load()
          } catch (e) {
            setError(messageFor(e, 'Unable to ban member.'))
          }
        }}>Ban</Button>}
      </div>
    </Card>)}</div>
    {users.length === 0 && !error && <Card>No members found.</Card>}
  </section>
}

export function AdminSafetyReportsPage() {
  const [reports, setReports] = useState<AdminSafetyReport[]>([])
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      setReports((await adminApi.safetyReports()).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load safety reports.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function decide(report: AdminSafetyReport, decision: 'reviewed' | 'dismissed') {
    try {
      await adminApi.decideSafetyReport(report.reportId, decision, `${decision === 'reviewed' ? 'Reviewed' : 'Dismissed'} by administrator`)
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to resolve safety report.'))
    }
  }

  return <section>
    <h1 className="mb-2 text-3xl font-bold">Safety reports</h1>
    <p className="mb-6 text-sm text-ink-500">Reports submitted directly by members. Reviewing a report does not automatically suspend its subject.</p>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{reports.map((report) => <Card key={report.reportId}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-semibold">{report.reason}: {report.targetName || report.targetId}</p>
          <p className="text-sm text-ink-500">Reported by {report.reporterName || report.reporterId} · {report.createdAt}</p>
          {report.description && <p className="mt-2 text-sm">{report.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => void decide(report, 'dismissed')}>Dismiss</Button>
          <Button size="sm" variant="accent" onClick={() => void decide(report, 'reviewed')}>Mark reviewed</Button>
        </div>
      </div>
    </Card>)}</div>
    {reports.length === 0 && !error && <Card>No open safety reports.</Card>}
  </section>
}

export function AdminPrivacyRequestsPage() {
  const [requests, setRequests] = useState<AdminPrivacyRequest[]>([])
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      setRequests((await adminApi.privacyRequests('all')).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load privacy requests.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function retry(item: AdminPrivacyRequest) {
    try {
      await adminApi.retryPrivacyRequest(item.requestId)
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to retry privacy request.'))
    }
  }

  return <section>
    <h1 className="mb-2 text-3xl font-bold">Privacy requests</h1>
    <p className="mb-6 text-sm text-ink-500">Failed requests can be re-queued. Account-deletion requests are not cancellable here.</p>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{requests.map((item) => <Card key={item.requestId} className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="font-semibold">{item.requestType.replaceAll('_', ' ')} · {item.status}</p>
        <p className="text-sm text-ink-500">{item.email || item.accountId} · requested {item.createdAt}</p>
        <p className="text-xs text-ink-400">{item.requestId}</p>
      </div>
      {item.status === 'failed' && <Button size="sm" onClick={() => void retry(item)}>Retry</Button>}
    </Card>)}</div>
    {requests.length === 0 && !error && <Card>No privacy requests.</Card>}
  </section>
}

export function AdminPayoutsPage() {
  const [payouts, setPayouts] = useState<AdminPayout[]>([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function load(filter = status) {
    try {
      setError(null)
      setPayouts((await adminApi.payouts(filter)).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load payouts.'))
    }
  }

  useEffect(() => { void load('') }, [])

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Payout operations</h1>
    <div className="mb-5 flex gap-3">
      <select aria-label="Payout status" className="rounded-xl border border-ink-200 px-3" value={status} onChange={(event) => { setStatus(event.target.value); void load(event.target.value) }}>
        <option value="">All statuses</option><option value="initiating">Initiating</option><option value="pending">Pending</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="reversed">Reversed</option>
      </select>
    </div>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{payouts.map((payout) => <Card key={payout.payoutId}>
      <p className="font-semibold">{formatNaira(payout.amountKobo / 100)} · {payout.status}</p>
      <p className="text-sm text-ink-500">{payout.email || payout.accountId} · {payout.reference}</p>
      <p className="text-xs text-ink-400">{payout.createdAt} {payout.transferCode ? `· transfer ${payout.transferCode}` : ''}</p>
    </Card>)}</div>
    {payouts.length === 0 && !error && <Card>No payouts match this filter.</Card>}
  </section>
}

export function AdminAuditEventsPage() {
  const [events, setEvents] = useState<AdminAuditEvent[]>([])
  const [accountId, setAccountId] = useState('')
  const [eventType, setEventType] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function load(event: FormEvent) {
    event.preventDefault()
    try {
      setError(null)
      setEvents((await adminApi.auditEvents({ accountId: accountId.trim() || undefined, eventType: eventType.trim() || undefined })).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load audit events.'))
    }
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Platform audit events</h1>
    <Card className="mb-5">
      <form className="grid gap-3 md:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void load(event)}>
        <Input placeholder="Account ID" value={accountId} onChange={(event) => setAccountId(event.target.value)} />
        <Input placeholder="Exact event type" value={eventType} onChange={(event) => setEventType(event.target.value)} />
        <Button type="submit">Search</Button>
      </form>
    </Card>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{events.map((event) => <Card key={event.id}>
      <div className="flex justify-between gap-4"><strong>{event.eventType}</strong><span className="text-sm text-ink-500">{event.outcome}</span></div>
      <p className="text-sm text-ink-500">{event.createdAt} · {event.actorType} {event.actorId || ''}</p>
      <p className="text-xs text-ink-400">Account {event.accountId || '—'} · Request {event.requestId}</p>
      <pre className="mt-2 overflow-auto text-xs">{typeof event.metadata === 'string' ? event.metadata : JSON.stringify(event.metadata)}</pre>
    </Card>)}</div>
    {events.length === 0 && !error && <Card>Search to view matching audit events.</Card>}
  </section>
}

export function AdminSecurityPage() {
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function loadStatus() {
    try { setMfaEnabled((await adminApi.mfaStatus()).enabled) }
    catch (e) { setError(messageFor(e, 'Unable to load admin security settings.')) }
  }

  useEffect(() => { void loadStatus() }, [])

  async function setup() {
    try {
      const result = await adminApi.setupMfa()
      setSecret(result.secret)
      setProvisioningUri(result.provisioningUri)
      setError(null)
      setNotice('Add this authenticator secret to your app, then enter its current code to enable MFA.')
    } catch (e) { setError(messageFor(e, 'Unable to begin MFA setup.')) }
  }

  async function toggleMfa(event: FormEvent) {
    event.preventDefault()
    try {
      const result = mfaEnabled ? await adminApi.disableMfa(code) : await adminApi.enableMfa(code)
      setMfaEnabled(result.enabled)
      setSecret(null)
      setProvisioningUri(null)
      setCode('')
      setError(null)
      setNotice(result.enabled ? 'Authenticator MFA is enabled.' : 'Authenticator MFA is disabled.')
    } catch (e) {
      setError(messageFor(e, 'Unable to update MFA settings.'))
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setError(null)
      setNotice('Password changed. Other active admin sessions were revoked.')
    } catch (e) { setError(messageFor(e, 'Unable to change password.')) }
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Admin security</h1>
    {error && <p className="mb-4 text-danger">{error}</p>}
    {notice && <p className="mb-4 text-sm text-primary-700">{notice}</p>}
    <Card className="mb-6">
      <h2 className="mb-2 text-lg font-bold">Authenticator MFA</h2>
      <p className="mb-4 text-sm text-ink-500">MFA is currently {mfaEnabled ? 'enabled' : 'disabled'} for this account.</p>
      {!mfaEnabled && !secret && <Button onClick={() => void setup()}>Set up MFA</Button>}
      {secret && <div className="mb-4 space-y-2 break-all text-sm">
        <p>Secret: <strong>{secret}</strong></p>
        <p>Authenticator URI: {provisioningUri}</p>
      </div>}
      {(mfaEnabled || secret) && <form className="flex flex-wrap gap-3" onSubmit={(event) => void toggleMfa(event)}>
        <Input aria-label="Authenticator code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6-digit code" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} required />
        <Button type="submit" variant={mfaEnabled ? 'destructive' : 'accent'}>{mfaEnabled ? 'Disable MFA' : 'Enable MFA'}</Button>
      </form>}
    </Card>
    <Card>
      <h2 className="mb-2 text-lg font-bold">Change password</h2>
      <form className="space-y-3" onSubmit={(event) => void changePassword(event)}>
        <Input type="password" autoComplete="current-password" placeholder="Current password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
        <Input type="password" autoComplete="new-password" minLength={14} placeholder="New password (14+ characters)" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
        <Button type="submit">Change password</Button>
      </form>
    </Card>
  </section>
}

export function AdminWalletAdjustmentsPage() {
  const [accountId, setAccountId] = useState('')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [ledger, setLedger] = useState<'wallet' | 'call_credits'>('wallet')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const adjustment = ledger === 'wallet' ? Math.round(Number(amount) * 100) : Number(amount)
    if (!Number.isFinite(adjustment) || !Number.isInteger(adjustment) || adjustment === 0 || !reason.trim()) {
      setError('Enter a non-zero amount and a reason.')
      return
    }
    try {
      const result = ledger === 'wallet'
        ? await adminApi.adjustWallet(accountId.trim(), adjustment, reason.trim())
        : await adminApi.adjustCallCredits(accountId.trim(), adjustment, reason.trim())
      setError(null)
      setSuccess(`Adjustment recorded. New balance: ${'balanceKobo' in result ? formatNaira(result.balanceKobo / 100) : result.balance} ${ledger === 'wallet' ? '₦' : 'coins'}.`)
      setAmount('')
      setReason('')
    } catch (e) {
      setError(messageFor(e, 'Unable to adjust wallet.'))
      setSuccess(null)
    }
  }

  return <section>
    <h1 className="mb-2 text-3xl font-bold">Balance adjustments</h1>
    <p className="mb-6 text-sm text-ink-500">Positive amounts credit the member; negative amounts debit. Every adjustment creates a ledger entry and audit event.</p>
    <Card>
      <form className="space-y-4" onSubmit={(event) => void submit(event)}>
        <Input aria-label="Account ID" placeholder="Member account ID" value={accountId} onChange={(event) => setAccountId(event.target.value)} required />
        <select aria-label="Balance type" className="w-full rounded-xl border border-ink-200 px-3 py-2" value={ledger} onChange={(event) => { setLedger(event.target.value as 'wallet' | 'call_credits'); setAmount('') }}>
          <option value="wallet">Wallet (₦)</option><option value="call_credits">Call-credit coins</option>
        </select>
        <Input aria-label="Adjustment amount" type="number" step={ledger === 'wallet' ? '0.01' : '1'} placeholder={ledger === 'wallet' ? 'Amount in ₦ (negative to debit)' : 'Number of coins (negative to debit)'} value={amount} onChange={(event) => setAmount(event.target.value)} required />
        <Input aria-label="Reason" placeholder="Reason for adjustment" value={reason} onChange={(event) => setReason(event.target.value)} required />
        {error && <p className="text-sm text-danger">{error}</p>}
        {success && <p className="text-sm text-success">{success}</p>}
        <Button type="submit">Record adjustment</Button>
      </form>
    </Card>
  </section>
}

export function AdminDashboardPage() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    adminApi.dashboard().then(setCounts).catch((e) => setError(messageFor(e, 'Unable to load admin dashboard.')))
  }, [])
  const labels: Record<string, string> = {
    pendingProfileReviews: 'Pending profile reviews',
    pendingDocumentReviews: 'Pending ID reviews',
    openSafetyReports: 'Open safety reports',
    openSafetyReviews: 'Open safety reviews',
    disputedMeetupPayments: 'Disputed meetup payments',
    pendingPayouts: 'Pending payouts',
    failedPrivacyRequests: 'Failed privacy requests',
    activeLiveStreams: 'Active live streams',
    activeCalls: 'Active calls',
    lockedAdminAccounts: 'Locked admin accounts',
  }
  return <section>
    <h1 className="mb-6 text-3xl font-bold">Operations dashboard</h1>
    {error && <p className="mb-4 text-danger">{error}</p>}
    {counts && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {Object.entries(labels).map(([key, label]) => <Card key={key}><p className="text-sm text-ink-500">{label}</p><p className="mt-2 text-3xl font-bold">{counts[key] ?? 0}</p></Card>)}
    </div>}
  </section>
}

export function AdminGiftCatalogPage() {
  const [gifts, setGifts] = useState<Array<{ id: string; name: string; emoji: string; priceKobo: number; active: boolean }>>([])
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [emoji, setEmoji] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      setGifts((await adminApi.giftCatalog()).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load gift catalog.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.createGift({ id: id.trim(), name: name.trim(), emoji, priceKobo: Math.round(Number(price) * 100) })
      setId(''); setName(''); setEmoji(''); setPrice('')
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to create gift.'))
    }
  }

  async function toggle(gift: typeof gifts[number]) {
    try {
      await adminApi.updateGift(gift.id, { active: !gift.active })
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to update gift.'))
    }
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Gift catalog</h1>
    <Card className="mb-6">
      <form className="grid gap-3 md:grid-cols-5" onSubmit={(event) => void create(event)}>
        <Input aria-label="Gift ID" placeholder="ID (e.g. sunflower)" value={id} onChange={(event) => setId(event.target.value)} required />
        <Input aria-label="Gift name" placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} required />
        <Input aria-label="Gift emoji" placeholder="Emoji" value={emoji} onChange={(event) => setEmoji(event.target.value)} required />
        <Input aria-label="Gift price in naira" type="number" min="1" step="0.01" placeholder="Price ₦" value={price} onChange={(event) => setPrice(event.target.value)} required />
        <Button type="submit">Add gift</Button>
      </form>
    </Card>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{gifts.map((gift) => <Card key={gift.id} className="flex items-center justify-between gap-4">
      <p className="font-semibold">{gift.emoji} {gift.name} <span className="text-sm font-normal text-ink-500">· {formatNaira(gift.priceKobo / 100)} · {gift.active ? 'active' : 'inactive'}</span></p>
      <Button size="sm" variant="outline" onClick={() => void toggle(gift)}>{gift.active ? 'Deactivate' : 'Activate'}</Button>
    </Card>)}</div>
  </section>
}

export function AdminSubscriptionsPage() {
  const [plans, setPlans] = useState<Awaited<ReturnType<typeof adminApi.subscriptionPlans>>['items']>([])
  const [subscriptions, setSubscriptions] = useState<Awaited<ReturnType<typeof adminApi.subscriptions>>['items']>([])
  const [accountId, setAccountId] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      const [planResult, subscriptionResult] = await Promise.all([adminApi.subscriptionPlans(), adminApi.subscriptions()])
      setPlans(planResult.items)
      setSubscriptions(subscriptionResult.items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load subscription data.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function updatePlan(id: string, active: boolean) {
    try { await adminApi.updateSubscriptionPlan(id, { active }); await load() }
    catch (e) { setError(messageFor(e, 'Unable to update subscription plan.')) }
  }

  async function grantVip(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.updateUserSubscription(accountId.trim(), 'vip', new Date(expiresAt).toISOString(), 'VIP access granted by administrator')
      setAccountId('')
      setExpiresAt('')
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to update member subscription.'))
    }
  }

  async function revokeVip(targetId: string) {
    try {
      await adminApi.updateUserSubscription(targetId, 'free', null, 'VIP access revoked by administrator')
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to update member subscription.'))
    }
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Subscriptions</h1>
    <Card className="mb-6">
      <h2 className="mb-3 text-lg font-bold">Plans</h2>
      <div className="space-y-3">{plans.map((plan) => <div key={plan.id} className="flex items-center justify-between gap-3">
        <p>{plan.name} · {plan.durationDays} days · {formatNaira(plan.priceKobo / 100)} · {plan.active ? 'active' : 'inactive'}</p>
        <Button size="sm" variant="outline" onClick={() => void updatePlan(plan.id, !plan.active)}>{plan.active ? 'Deactivate' : 'Activate'}</Button>
      </div>)}</div>
    </Card>
    <Card className="mb-6">
      <h2 className="mb-3 text-lg font-bold">Grant VIP</h2>
      <form className="grid gap-3 md:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void grantVip(event)}>
        <Input aria-label="Account ID" placeholder="Member account ID" value={accountId} onChange={(event) => setAccountId(event.target.value)} required />
        <Input aria-label="VIP expiry" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} required />
        <Button type="submit">Grant VIP</Button>
      </form>
    </Card>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <h2 className="mb-3 text-xl font-bold">Current VIP members</h2>
    <div className="space-y-3">{subscriptions.map((subscription) => <Card key={subscription.accountId} className="flex items-center justify-between gap-3">
      <div><p className="font-semibold">{subscription.displayName || subscription.email || subscription.accountId}</p><p className="text-sm text-ink-500">{subscription.email || subscription.accountId} · expires {subscription.expiresAt || 'not set'}</p></div>
      <Button size="sm" variant="outline" onClick={() => void revokeVip(subscription.accountId)}>Revoke VIP</Button>
    </Card>)}</div>
  </section>
}

export function AdminLiveStreamsPage() {
  const [streams, setStreams] = useState<Awaited<ReturnType<typeof adminApi.liveStreams>>['items']>([])
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      setStreams((await adminApi.liveStreams()).items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load live streams.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function end(streamId: string) {
    try {
      await adminApi.endLiveStream(streamId)
      await load()
    } catch (e) {
      setError(messageFor(e, 'Unable to end live stream.'))
    }
  }

  return <section>
    <h1 className="mb-2 text-3xl font-bold">Live-stream moderation</h1>
    <p className="mb-6 text-sm text-ink-500">Ending a stream closes the LiveKit room and records an audited moderation action.</p>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <div className="space-y-3">{streams.map((stream) => <Card key={stream.streamId} className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="font-semibold">{stream.title || 'Untitled stream'}</p><p className="text-sm text-ink-500">{stream.hostName || stream.hostId} · started {stream.startedAt}</p></div>
      <Button size="sm" variant="destructive" onClick={() => void end(stream.streamId)}>End stream</Button>
    </Card>)}</div>
    {streams.length === 0 && !error && <Card>No active streams.</Card>}
  </section>
}

export function AdminContentPage() {
  const [posts, setPosts] = useState<Awaited<ReturnType<typeof adminApi.contentPosts>>['items']>([])
  const [statuses, setStatuses] = useState<Awaited<ReturnType<typeof adminApi.contentStatuses>>['items']>([])
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setError(null)
      const [postResult, statusResult] = await Promise.all([adminApi.contentPosts(), adminApi.contentStatuses()])
      setPosts(postResult.items)
      setStatuses(statusResult.items)
    } catch (e) {
      setError(messageFor(e, 'Unable to load member content.'))
    }
  }

  useEffect(() => { void load() }, [])

  async function removePost(postId: string) {
    try { await adminApi.removePost(postId); await load() }
    catch (e) { setError(messageFor(e, 'Unable to remove post.')) }
  }
  async function removeStatus(statusId: string) {
    try { await adminApi.removeStatus(statusId); await load() }
    catch (e) { setError(messageFor(e, 'Unable to remove status.')) }
  }

  return <section>
    <h1 className="mb-6 text-3xl font-bold">Content moderation</h1>
    {error && <p className="mb-4 text-danger">{error}</p>}
    <h2 className="mb-3 text-xl font-bold">Posts</h2>
    <div className="mb-8 space-y-3">{posts.map((post) => <Card key={post.postId} className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="font-semibold">{post.authorName || post.authorId}</p><p className="text-sm text-ink-500">{post.caption || 'No caption'} · {post.createdAt}</p></div>
      <Button size="sm" variant="destructive" onClick={() => void removePost(post.postId)}>Remove post</Button>
    </Card>)}</div>
    <h2 className="mb-3 text-xl font-bold">Statuses</h2>
    <div className="space-y-3">{statuses.map((status) => <Card key={status.statusId} className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="font-semibold">{status.authorName || status.authorId}</p><p className="text-sm text-ink-500">{status.mediaKind} · expires {status.expiresAt}</p></div>
      <Button size="sm" variant="destructive" onClick={() => void removeStatus(status.statusId)}>Remove status</Button>
    </Card>)}</div>
  </section>
}
