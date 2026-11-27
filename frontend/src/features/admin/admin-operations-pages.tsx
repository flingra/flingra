import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  ClipboardCheck, Gift, HeartHandshake, KeyRound, LockKeyhole, Newspaper, Phone, Radio, ScrollText,
  Search, ShieldAlert, UserRound, Users, Wallet, type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatNaira } from '@/lib/utils'
import { adminApi, type AdminAuditEvent, type AdminPayout, type AdminPrivacyRequest, type AdminSafetyReport, type AdminUser } from '@/lib/api/admin'
import { useAdminStore } from '@/lib/stores/admin-store'
import {
  Async, Badge, CopyButton, EmptyState, Field, PageHeader, Panel, Segmented, Select, StatusBadge, Table, Td,
  formatDate, humanize, useConfirm, useFeedback,
} from './admin-ui'

/* ------------------------------------------------------------------ Members */

const USER_STATUS_REASONS = {
  active: 'Reactivated by administrator',
  suspended: 'Suspended by administrator',
  banned: 'Permanently banned by administrator',
} as const

export function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function load(value = query) {
    try {
      clear()
      setUsers((await adminApi.users(value)).items)
    } catch (e) {
      fail(e, 'Unable to load members.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function changeStatus(user: AdminUser, status: keyof typeof USER_STATUS_REASONS) {
    const name = user.displayName || user.email || user.accountId
    if (status !== 'active') {
      const banning = status === 'banned'
      const ok = await confirm({
        title: `${banning ? 'Ban' : 'Suspend'} ${name}?`,
        description: banning ? 'The member permanently loses access to Flingra.' : 'The member can’t use Flingra until you reactivate the account.',
        confirmLabel: banning ? 'Ban member' : 'Suspend member',
        tone: 'danger',
      })
      if (!ok) return
    }
    try {
      await adminApi.setUserStatus(user.accountId, status, USER_STATUS_REASONS[status])
      await load()
      notify(`${name} is now ${status}.`)
    } catch (e) {
      fail(e, 'Unable to update member status.')
    }
  }

  async function revokeSessions(user: AdminUser) {
    const name = user.displayName || user.email || user.accountId
    const ok = await confirm({ title: 'Revoke all sessions?', description: `${name} will be signed out on every device.`, confirmLabel: 'Revoke sessions', tone: 'danger' })
    if (!ok) return
    try {
      const { revokedCount } = await adminApi.revokeUserSessions(user.accountId)
      notify(`Revoked ${revokedCount} session${revokedCount === 1 ? '' : 's'} for ${name}.`)
    } catch (e) {
      fail(e, 'Unable to revoke member sessions.')
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setQuery(search.trim())
    void load(search.trim())
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Members" description="Search member accounts, check their review status, and manage access." />
      <form className="flex gap-3" onSubmit={submit}>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
          <Input aria-label="Search members" className="pl-9" placeholder="Email, display name or account ID" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <Button type="submit">Search</Button>
      </form>
      {banner}
      <Async loading={loading} count={users.length} failed={!!error} empty={<EmptyState icon={Users} title="No members found" description="Try a different email, name or account ID." />}>
        <Panel flush title={`${users.length} ${users.length === 1 ? 'member' : 'members'}`}>
          <Table head={['Member', 'Account', 'Profile review', 'ID check', 'Actions']} actions>
            {users.map((user) => {
              const active = user.accountStatus === 'active'
              const manageable = active || user.accountStatus === 'suspended' || user.accountStatus === 'banned'
              return (
                <tr key={user.accountId} className="hover:bg-ink-50">
                  <Td>
                    <p className="font-medium text-ink-900">{user.displayName || user.email || user.accountId}</p>
                    {user.displayName && <p className="text-ink-500">{user.email || 'No email'}</p>}
                    <p className="font-mono text-xs text-ink-400">{user.accountId}</p>
                  </Td>
                  <Td><StatusBadge status={user.accountStatus} /></Td>
                  <Td><StatusBadge status={user.moderationStatus} /></Td>
                  <Td><StatusBadge status={user.documentVerification} /></Td>
                  <Td right>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => void revokeSessions(user)}>Revoke sessions</Button>
                      {manageable && (active
                        ? <Button size="sm" variant="outline" onClick={() => void changeStatus(user, 'suspended')}>Suspend</Button>
                        : <Button size="sm" variant="accent" onClick={() => void changeStatus(user, 'active')}>Reactivate</Button>)}
                      {active && <Button size="sm" variant="destructive" onClick={() => void changeStatus(user, 'banned')}>Ban</Button>}
                    </div>
                  </Td>
                </tr>
              )
            })}
          </Table>
        </Panel>
      </Async>
      {dialog}
    </section>
  )
}

/* ------------------------------------------------------------ Safety reports */

export function AdminSafetyReportsPage() {
  const [reports, setReports] = useState<AdminSafetyReport[]>([])
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()

  async function load() {
    try {
      clear()
      setReports((await adminApi.safetyReports()).items)
    } catch (e) {
      fail(e, 'Unable to load safety reports.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function decide(report: AdminSafetyReport, decision: 'reviewed' | 'dismissed') {
    try {
      await adminApi.decideSafetyReport(report.reportId, decision, `${decision === 'reviewed' ? 'Reviewed' : 'Dismissed'} by administrator`)
      await load()
      notify(decision === 'reviewed' ? 'Report marked as reviewed.' : 'Report dismissed.')
    } catch (e) {
      fail(e, 'Unable to resolve safety report.')
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Safety reports" description="Reports submitted directly by members. Reviewing a report doesn’t automatically suspend its subject." />
      {banner}
      <Async loading={loading} count={reports.length} failed={!!error} empty={<EmptyState icon={ShieldAlert} title="No open safety reports" description="New member reports will appear here." />}>
        <div className="space-y-4">
          {reports.map((report) => (
            <Panel key={report.reportId}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="warning">{humanize(report.reason)}</Badge>
                    <h2 className="font-medium text-ink-900">{report.targetName || report.targetId}</h2>
                  </div>
                  <p className="mt-1 text-sm text-ink-500">Reported by {report.reporterName || report.reporterId}</p>
                </div>
                <time className="text-sm text-ink-500">{formatDate(report.createdAt)}</time>
              </div>
              {report.description && <p className="mt-3 rounded-lg bg-ink-50 px-4 py-3 text-sm text-ink-900">{report.description}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => void decide(report, 'dismissed')}>Dismiss</Button>
                <Button size="sm" variant="accent" onClick={() => void decide(report, 'reviewed')}>Mark reviewed</Button>
              </div>
            </Panel>
          ))}
        </div>
      </Async>
    </section>
  )
}

/* ---------------------------------------------------------- Privacy requests */

export function AdminPrivacyRequestsPage() {
  const [requests, setRequests] = useState<AdminPrivacyRequest[]>([])
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()

  async function load() {
    try {
      clear()
      setRequests((await adminApi.privacyRequests('all')).items)
    } catch (e) {
      fail(e, 'Unable to load privacy requests.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function retry(item: AdminPrivacyRequest) {
    try {
      await adminApi.retryPrivacyRequest(item.requestId)
      await load()
      notify('Request re-queued.')
    } catch (e) {
      fail(e, 'Unable to retry privacy request.')
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Privacy requests" description="Failed requests can be re-queued. Account-deletion requests can’t be cancelled here." />
      {banner}
      <Async loading={loading} count={requests.length} failed={!!error} empty={<EmptyState icon={LockKeyhole} title="No privacy requests" description="Data export and deletion requests will appear here." />}>
        <Panel flush title={`${requests.length} ${requests.length === 1 ? 'request' : 'requests'}`}>
          <Table head={['Request', 'Status', 'Member', 'Requested', 'Actions']} actions>
            {requests.map((item) => (
              <tr key={item.requestId} className="hover:bg-ink-50">
                <Td>
                  <p className="font-medium text-ink-900">{humanize(item.requestType)}</p>
                  <p className="font-mono text-xs text-ink-400">{item.requestId}</p>
                </Td>
                <Td><StatusBadge status={item.status} /></Td>
                <Td className="text-ink-600">{item.email || item.accountId}</Td>
                <Td className="text-ink-600">{formatDate(item.createdAt)}</Td>
                <Td right>{item.status === 'failed' && <Button size="sm" onClick={() => void retry(item)}>Retry</Button>}</Td>
              </tr>
            ))}
          </Table>
        </Panel>
      </Async>
    </section>
  )
}

/* ------------------------------------------------------------------ Payouts */

export function AdminPayoutsPage() {
  const [payouts, setPayouts] = useState<AdminPayout[]>([])
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const { error, clear, fail, banner } = useFeedback()

  async function load(filter = status) {
    try {
      clear()
      setPayouts((await adminApi.payouts(filter)).items)
    } catch (e) {
      fail(e, 'Unable to load payouts.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load('') }, [])

  return (
    <section className="space-y-6">
      <PageHeader
        title="Payouts"
        description="Track member withdrawals and their transfer status."
        actions={
          <Select aria-label="Filter by status" className="w-48" value={status} onChange={(event) => { setStatus(event.target.value); void load(event.target.value) }}>
            <option value="">All statuses</option>
            <option value="initiating">Initiating</option>
            <option value="pending">Pending</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="reversed">Reversed</option>
          </Select>
        }
      />
      {banner}
      <Async loading={loading} count={payouts.length} failed={!!error} empty={<EmptyState icon={Wallet} title="No payouts match this filter" description="Try a different status." />}>
        <Panel flush title={`${payouts.length} ${payouts.length === 1 ? 'payout' : 'payouts'}`}>
          <Table head={['Amount', 'Status', 'Member', 'Reference', 'Created']}>
            {payouts.map((payout) => (
              <tr key={payout.payoutId} className="hover:bg-ink-50">
                <Td className="font-medium tabular-nums text-ink-900">{formatNaira(payout.amountKobo / 100)}</Td>
                <Td><StatusBadge status={payout.status} /></Td>
                <Td className="text-ink-600">{payout.email || payout.accountId}</Td>
                <Td>
                  <p className="font-mono text-xs text-ink-600">{payout.reference}</p>
                  {payout.transferCode && <p className="font-mono text-xs text-ink-400">Transfer {payout.transferCode}</p>}
                </Td>
                <Td className="text-ink-600">{formatDate(payout.createdAt)}</Td>
              </tr>
            ))}
          </Table>
        </Panel>
      </Async>
    </section>
  )
}

/* ------------------------------------------------------------- Platform audit */

function formatMetadata(metadata: unknown) {
  if (metadata == null || metadata === '') return ''
  const text = typeof metadata === 'string' ? metadata : JSON.stringify(metadata, null, 2)
  return text === '{}' ? '' : text
}

export function AdminAuditEventsPage() {
  const [events, setEvents] = useState<AdminAuditEvent[]>([])
  const [accountId, setAccountId] = useState('')
  const [eventType, setEventType] = useState('')
  const [searched, setSearched] = useState(false)
  const [busy, setBusy] = useState(false)
  const { error, clear, fail, banner } = useFeedback()

  async function load(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      clear()
      setEvents((await adminApi.auditEvents({ accountId: accountId.trim() || undefined, eventType: eventType.trim() || undefined })).items)
      setSearched(true)
    } catch (e) {
      fail(e, 'Unable to load audit events.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Platform audit" description="Search recorded platform events by account or exact event type." />
      <Panel>
        <form className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end" onSubmit={(event) => void load(event)}>
          <Field label="Account ID"><Input className="font-mono" placeholder="Optional" value={accountId} onChange={(event) => setAccountId(event.target.value)} /></Field>
          <Field label="Event type"><Input className="font-mono" placeholder="Exact match, optional" value={eventType} onChange={(event) => setEventType(event.target.value)} /></Field>
          <Button type="submit" disabled={busy}>{busy ? 'Searching…' : 'Search'}</Button>
        </form>
      </Panel>
      {banner}
      {!searched ? (
        !error && <EmptyState icon={ScrollText} title="Search the audit log" description="Enter an account ID, an event type, or both to see matching events." />
      ) : (
        <Async loading={false} count={events.length} failed={!!error} empty={<EmptyState icon={ScrollText} title="No matching events" description="Check the account ID and event type, then search again." />}>
          <Panel flush title={`${events.length} ${events.length === 1 ? 'event' : 'events'}`}>
            <ul className="divide-y divide-ink-100">
              {events.map((event) => {
                const metadata = formatMetadata(event.metadata)
                return (
                  <li key={event.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-medium text-ink-900">{event.eventType}</span>
                        <StatusBadge status={event.outcome} />
                      </div>
                      <span className="text-sm text-ink-500">{formatDate(event.createdAt)}</span>
                    </div>
                    <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                      <div className="min-w-0"><dt className="text-ink-500">Actor</dt><dd className="truncate text-ink-900">{event.actorType} {event.actorId || ''}</dd></div>
                      <div className="min-w-0"><dt className="text-ink-500">Account</dt><dd className="truncate font-mono text-xs text-ink-900">{event.accountId || '—'}</dd></div>
                      <div className="min-w-0"><dt className="text-ink-500">Request</dt><dd className="truncate font-mono text-xs text-ink-900">{event.requestId}</dd></div>
                    </dl>
                    {metadata && (
                      <details className="mt-3 text-sm">
                        <summary className="cursor-pointer text-primary-700">View metadata</summary>
                        <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-ink-50 p-3 text-xs text-ink-900">{metadata}</pre>
                      </details>
                    )}
                  </li>
                )
              })}
            </ul>
          </Panel>
        </Async>
      )}
    </section>
  )
}

/* ----------------------------------------------------------------- Security */

export function AdminSecurityPage() {
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const { clear, notify, fail, banner } = useFeedback()

  async function loadStatus() {
    try { setMfaEnabled((await adminApi.mfaStatus()).enabled) }
    catch (e) { fail(e, 'Unable to load admin security settings.') }
  }

  useEffect(() => { void loadStatus() }, [])

  async function setup() {
    try {
      const result = await adminApi.setupMfa()
      setSecret(result.secret)
      setProvisioningUri(result.provisioningUri)
      clear()
    } catch (e) { fail(e, 'Unable to begin MFA setup.') }
  }

  async function toggleMfa(event: FormEvent) {
    event.preventDefault()
    try {
      const result = mfaEnabled ? await adminApi.disableMfa(code) : await adminApi.enableMfa(code)
      setMfaEnabled(result.enabled)
      setSecret(null)
      setProvisioningUri(null)
      setCode('')
      notify(result.enabled ? 'Authenticator MFA is enabled.' : 'Authenticator MFA is disabled.')
    } catch (e) {
      fail(e, 'Unable to update MFA settings.')
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      notify('Password changed. Other active admin sessions were revoked.')
    } catch (e) { fail(e, 'Unable to change password.') }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Security" description="Protect your admin account with an authenticator app and a strong password." />
      {banner}
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Panel
          title="Authenticator MFA"
          description="Require a one-time code from an authenticator app when you sign in."
          actions={<Badge tone={mfaEnabled ? 'success' : 'neutral'}>{mfaEnabled ? 'Enabled' : 'Disabled'}</Badge>}
        >
          <div className="space-y-4">
            {!mfaEnabled && !secret && <Button onClick={() => void setup()}>Set up MFA</Button>}
            {secret && (
              <div className="space-y-3">
                <p className="text-sm text-ink-600">Add this secret to your authenticator app, then enter the 6-digit code it shows.</p>
                <div className="flex items-center justify-between gap-3 rounded-lg bg-ink-50 px-4 py-3">
                  <code className="break-all font-mono text-sm text-ink-900">{secret}</code>
                  <CopyButton value={secret} />
                </div>
                {provisioningUri && (
                  <details className="text-sm">
                    <summary className="cursor-pointer text-primary-700">Show authenticator URI</summary>
                    <p className="mt-2 break-all rounded-lg bg-ink-50 p-3 font-mono text-xs text-ink-600">{provisioningUri}</p>
                  </details>
                )}
              </div>
            )}
            {(mfaEnabled || secret) && (
              <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => void toggleMfa(event)}>
                <Field label="Authenticator code">
                  <Input className="w-40 text-center font-mono tracking-widest" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} required />
                </Field>
                <Button type="submit" variant={mfaEnabled ? 'destructive' : 'accent'}>{mfaEnabled ? 'Disable MFA' : 'Enable MFA'}</Button>
              </form>
            )}
            {mfaEnabled && <p className="text-xs text-ink-500">Enter a current code to disable MFA.</p>}
          </div>
        </Panel>
        <Panel title="Change password" description="Other active admin sessions are signed out when you change it.">
          <form className="space-y-4" onSubmit={(event) => void changePassword(event)}>
            <Field label="Current password"><Input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></Field>
            <Field label="New password" hint="At least 14 characters."><Input type="password" autoComplete="new-password" minLength={14} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></Field>
            <Button type="submit">Change password</Button>
          </form>
        </Panel>
      </div>
    </section>
  )
}

/* -------------------------------------------------------- Wallet adjustments */

export function AdminWalletAdjustmentsPage() {
  const [accountId, setAccountId] = useState('')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [ledger, setLedger] = useState<'wallet' | 'call_credits'>('wallet')
  const [busy, setBusy] = useState(false)
  const { notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function submit(event: FormEvent) {
    event.preventDefault()
    const adjustment = ledger === 'wallet' ? Math.round(Number(amount) * 100) : Number(amount)
    if (!Number.isFinite(adjustment) || !Number.isInteger(adjustment) || adjustment === 0 || !reason.trim()) {
      fail(null, 'Enter a non-zero amount and a reason.')
      return
    }
    const credit = adjustment > 0
    const size = ledger === 'wallet' ? formatNaira(Math.abs(adjustment) / 100) : `${Math.abs(adjustment)} coins`
    const ok = await confirm({
      title: `${credit ? 'Credit' : 'Debit'} ${size}?`,
      description: <>This will {credit ? 'add to' : 'deduct from'} the balance of <span className="font-mono">{accountId.trim()}</span> and create a ledger entry and an audit event.</>,
      confirmLabel: credit ? 'Record credit' : 'Record debit',
      tone: credit ? 'default' : 'danger',
    })
    if (!ok) return
    setBusy(true)
    try {
      const result = ledger === 'wallet'
        ? await adminApi.adjustWallet(accountId.trim(), adjustment, reason.trim())
        : await adminApi.adjustCallCredits(accountId.trim(), adjustment, reason.trim())
      notify(`Adjustment recorded. New balance: ${'balanceKobo' in result ? formatNaira(result.balanceKobo / 100) : `${result.balance} coins`}.`)
      setAmount('')
      setReason('')
    } catch (e) {
      fail(e, 'Unable to adjust wallet.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Wallet adjustments" description="Positive amounts credit the member and negative amounts debit. Every adjustment creates a ledger entry and an audit event." />
      {banner}
      <Panel className="max-w-2xl">
        <form className="space-y-5" onSubmit={(event) => void submit(event)}>
          <div>
            <p className="mb-1.5 text-sm font-medium text-ink-900">Balance</p>
            <Segmented
              label="Balance type"
              value={ledger}
              onChange={(value) => { setLedger(value); setAmount('') }}
              options={[{ value: 'wallet', label: 'Wallet (₦)' }, { value: 'call_credits', label: 'Call-credit coins' }]}
            />
          </div>
          <Field label="Member account ID"><Input className="font-mono" value={accountId} onChange={(event) => setAccountId(event.target.value)} required /></Field>
          <Field label={ledger === 'wallet' ? 'Amount (₦)' : 'Amount (coins)'} hint="Use a negative number to debit.">
            <Input type="number" step={ledger === 'wallet' ? '0.01' : '1'} value={amount} onChange={(event) => setAmount(event.target.value)} required />
          </Field>
          <Field label="Reason" hint="Saved with the ledger entry and audit event."><Input value={reason} onChange={(event) => setReason(event.target.value)} required /></Field>
          <Button type="submit" disabled={busy}>{busy ? 'Recording…' : 'Record adjustment'}</Button>
        </form>
      </Panel>
      {dialog}
    </section>
  )
}

/* ---------------------------------------------------------------- Dashboard */

type Stat = { key: string; label: string; icon: LucideIcon; to?: string; roles?: string[] }

const REVIEW = ['super_admin', 'reviewer']
const SAFETY = ['super_admin', 'safety_admin']
const SUPER = ['super_admin']

const ATTENTION: Stat[] = [
  { key: 'pendingAccountVerifications', label: 'Pending account verifications', icon: UserRound, to: '/admin/reviews', roles: REVIEW },
  { key: 'openSafetyReports', label: 'Open safety reports', icon: ShieldAlert, to: '/admin/safety-reports', roles: SAFETY },
  { key: 'openSafetyReviews', label: 'Open safety reviews', icon: ClipboardCheck, to: '/admin/safety-reviews', roles: SAFETY },
  { key: 'disputedMeetupPayments', label: 'Disputed meetup payments', icon: HeartHandshake, to: '/admin/meetup-disputes', roles: SUPER },
  { key: 'pendingPayouts', label: 'Pending payouts', icon: Wallet, to: '/admin/payouts', roles: SUPER },
  { key: 'failedPrivacyRequests', label: 'Failed privacy requests', icon: LockKeyhole, to: '/admin/privacy-requests', roles: SUPER },
  { key: 'lockedAdminAccounts', label: 'Locked admin accounts', icon: KeyRound, to: '/admin/admins', roles: SUPER },
]

const LIVE: Stat[] = [
  { key: 'activeLiveStreams', label: 'Active live streams', icon: Radio, to: '/admin/live-streams', roles: SAFETY },
  { key: 'activeCalls', label: 'Active calls', icon: Phone },
]

function StatCard({ stat, value, linked, live }: { stat: Stat; value?: number; linked: boolean; live?: boolean }) {
  const Icon = stat.icon
  const count = value ?? 0
  const body = (
    <>
      <div className="flex items-center justify-between">
        <div className="grid size-9 place-items-center rounded-lg bg-ink-100 text-ink-600"><Icon className="size-4" /></div>
        {count > 0 && <span aria-hidden className={`size-2 rounded-full ${live ? 'bg-emerald-500' : 'bg-amber-500'}`} />}
      </div>
      <p className={`mt-4 text-3xl font-semibold tabular-nums ${count > 0 ? 'text-ink-900' : 'text-ink-400'}`}>{value === undefined ? '–' : count}</p>
      <p className="mt-1 text-sm text-ink-600">{stat.label}</p>
    </>
  )
  const base = 'block rounded-xl border border-ink-100 bg-white p-5'
  return linked && stat.to
    ? <Link to={stat.to} className={`${base} outline-none transition-colors hover:border-ink-200 hover:bg-ink-50 focus-visible:ring-2 focus-visible:ring-primary-500`}>{body}</Link>
    : <div className={base}>{body}</div>
}

export function AdminDashboardPage() {
  const role = useAdminStore((state) => state.session?.role) ?? ''
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const { fail, banner } = useFeedback()

  useEffect(() => {
    adminApi.dashboard().then(setCounts).catch((e) => fail(e, 'Unable to load admin dashboard.'))
  }, [])

  const group = (title: string, stats: Stat[], live?: boolean) => (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.key} stat={stat} value={counts ? counts[stat.key] ?? 0 : undefined} live={live} linked={(stat.roles ?? []).includes(role)} />
        ))}
      </div>
    </div>
  )

  return (
    <section className="space-y-8">
      <PageHeader title="Operations dashboard" description="Queues that need a decision, and what’s happening on the platform right now." />
      {banner}
      {group('Needs attention', ATTENTION)}
      {group('Happening now', LIVE, true)}
    </section>
  )
}

/* ------------------------------------------------------------- Gift catalog */

type Gift = { id: string; name: string; emoji: string; priceKobo: number; active: boolean }

export function AdminGiftCatalogPage() {
  const [gifts, setGifts] = useState<Gift[]>([])
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [emoji, setEmoji] = useState('')
  const [price, setPrice] = useState('')
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()

  async function load() {
    try {
      clear()
      setGifts((await adminApi.giftCatalog()).items)
    } catch (e) {
      fail(e, 'Unable to load gift catalog.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.createGift({ id: id.trim(), name: name.trim(), emoji, priceKobo: Math.round(Number(price) * 100) })
      setId(''); setName(''); setEmoji(''); setPrice('')
      await load()
      notify('Gift added to the catalog.')
    } catch (e) {
      fail(e, 'Unable to create gift.')
    }
  }

  async function toggle(gift: Gift) {
    try {
      await adminApi.updateGift(gift.id, { active: !gift.active })
      await load()
    } catch (e) {
      fail(e, 'Unable to update gift.')
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Gift catalog" description="Gifts members can send. Deactivating a gift hides it without deleting it." />
      <Panel title="Add a gift">
        <form className="grid gap-4 md:grid-cols-[1fr_1.4fr_6rem_9rem_auto] md:items-end" onSubmit={(event) => void create(event)}>
          <Field label="Gift ID"><Input placeholder="sunflower" value={id} onChange={(event) => setId(event.target.value)} required /></Field>
          <Field label="Name"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field>
          <Field label="Emoji"><Input value={emoji} onChange={(event) => setEmoji(event.target.value)} required /></Field>
          <Field label="Price (₦)"><Input type="number" min="1" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} required /></Field>
          <Button type="submit">Add gift</Button>
        </form>
      </Panel>
      {banner}
      <Async loading={loading} count={gifts.length} failed={!!error} empty={<EmptyState icon={Gift} title="No gifts yet" description="Add the first gift above." />}>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {gifts.map((gift) => (
            <li key={gift.id} className={`rounded-xl border border-ink-100 bg-white p-5 ${gift.active ? '' : 'opacity-70'}`}>
              <div className="flex items-start justify-between">
                <span aria-hidden className="text-4xl leading-none">{gift.emoji}</span>
                <Badge tone={gift.active ? 'success' : 'neutral'}>{gift.active ? 'Active' : 'Inactive'}</Badge>
              </div>
              <p className="mt-4 font-medium text-ink-900">{gift.name}</p>
              <p className="font-mono text-xs text-ink-400">{gift.id}</p>
              <div className="mt-4 flex items-center justify-between gap-3">
                <p className="text-lg font-semibold tabular-nums text-ink-900">{formatNaira(gift.priceKobo / 100)}</p>
                <Button size="sm" variant="outline" onClick={() => void toggle(gift)}>{gift.active ? 'Deactivate' : 'Activate'}</Button>
              </div>
            </li>
          ))}
        </ul>
      </Async>
    </section>
  )
}

/* ------------------------------------------------------------ Subscriptions */

export function AdminSubscriptionsPage() {
  const [plans, setPlans] = useState<Awaited<ReturnType<typeof adminApi.subscriptionPlans>>['items']>([])
  const [subscriptions, setSubscriptions] = useState<Awaited<ReturnType<typeof adminApi.subscriptions>>['items']>([])
  const [accountId, setAccountId] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [loading, setLoading] = useState(true)
  const { clear, notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function load() {
    try {
      clear()
      const [planResult, subscriptionResult] = await Promise.all([adminApi.subscriptionPlans(), adminApi.subscriptions()])
      setPlans(planResult.items)
      setSubscriptions(subscriptionResult.items)
    } catch (e) {
      fail(e, 'Unable to load subscription data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function updatePlan(id: string, active: boolean) {
    try { await adminApi.updateSubscriptionPlan(id, { active }); await load() }
    catch (e) { fail(e, 'Unable to update subscription plan.') }
  }

  async function grantVip(event: FormEvent) {
    event.preventDefault()
    try {
      await adminApi.updateUserSubscription(accountId.trim(), 'vip', new Date(expiresAt).toISOString(), 'VIP access granted by administrator')
      setAccountId('')
      setExpiresAt('')
      await load()
      notify('VIP access granted.')
    } catch (e) {
      fail(e, 'Unable to update member subscription.')
    }
  }

  async function revokeVip(targetId: string, name: string) {
    const ok = await confirm({ title: `Revoke VIP for ${name}?`, description: 'The member returns to the free plan immediately.', confirmLabel: 'Revoke VIP', tone: 'danger' })
    if (!ok) return
    try {
      await adminApi.updateUserSubscription(targetId, 'free', null, 'VIP access revoked by administrator')
      await load()
      notify('VIP access revoked.')
    } catch (e) {
      fail(e, 'Unable to update member subscription.')
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Subscriptions" description="Manage VIP plans and grant or revoke access for individual members." />
      {banner}
      <Panel flush title="Plans">
        {loading ? <p className="px-5 py-6 text-sm text-ink-500">Loading plans…</p> : (
          <Table head={['Plan', 'Duration', 'Price', 'Status', 'Actions']} actions>
            {plans.map((plan) => (
              <tr key={plan.id} className="hover:bg-ink-50">
                <Td className="font-medium text-ink-900">{plan.name}</Td>
                <Td className="text-ink-600">{plan.durationDays} days</Td>
                <Td className="tabular-nums text-ink-600">{formatNaira(plan.priceKobo / 100)}</Td>
                <Td><Badge tone={plan.active ? 'success' : 'neutral'}>{plan.active ? 'Active' : 'Inactive'}</Badge></Td>
                <Td right><Button size="sm" variant="outline" onClick={() => void updatePlan(plan.id, !plan.active)}>{plan.active ? 'Deactivate' : 'Activate'}</Button></Td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
      <Panel title="Grant VIP" description="Gives a member VIP access until the date you choose.">
        <form className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end" onSubmit={(event) => void grantVip(event)}>
          <Field label="Member account ID"><Input className="font-mono" value={accountId} onChange={(event) => setAccountId(event.target.value)} required /></Field>
          <Field label="VIP expires"><Input type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} required /></Field>
          <Button type="submit">Grant VIP</Button>
        </form>
      </Panel>
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-ink-900">Current VIP members</h2>
        <Async loading={loading} count={subscriptions.length} empty={<EmptyState icon={Users} title="No VIP members" description="Members with VIP access will appear here." />}>
          <Panel flush>
            <Table head={['Member', 'Expires', 'Actions']} actions>
              {subscriptions.map((subscription) => {
                const name = subscription.displayName || subscription.email || subscription.accountId
                return (
                  <tr key={subscription.accountId} className="hover:bg-ink-50">
                    <Td>
                      <p className="font-medium text-ink-900">{name}</p>
                      {subscription.displayName && <p className="text-ink-500">{subscription.email || subscription.accountId}</p>}
                    </Td>
                    <Td className="text-ink-600">{formatDate(subscription.expiresAt) === '—' ? 'Not set' : formatDate(subscription.expiresAt)}</Td>
                    <Td right><Button size="sm" variant="outline" onClick={() => void revokeVip(subscription.accountId, name)}>Revoke VIP</Button></Td>
                  </tr>
                )
              })}
            </Table>
          </Panel>
        </Async>
      </div>
      {dialog}
    </section>
  )
}

/* ------------------------------------------------------------- Live streams */

export function AdminLiveStreamsPage() {
  const [streams, setStreams] = useState<Awaited<ReturnType<typeof adminApi.liveStreams>>['items']>([])
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function load() {
    try {
      clear()
      setStreams((await adminApi.liveStreams()).items)
    } catch (e) {
      fail(e, 'Unable to load live streams.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function end(streamId: string, title: string) {
    const ok = await confirm({ title: `End “${title}”?`, description: 'The LiveKit room closes and everyone watching is disconnected. The action is audited.', confirmLabel: 'End stream', tone: 'danger' })
    if (!ok) return
    try {
      await adminApi.endLiveStream(streamId)
      await load()
      notify('Stream ended.')
    } catch (e) {
      fail(e, 'Unable to end live stream.')
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Live streams" description="Ending a stream closes the LiveKit room and records an audited moderation action." />
      {banner}
      <Async loading={loading} count={streams.length} failed={!!error} empty={<EmptyState icon={Radio} title="No active streams" description="Streams that are live right now will appear here." />}>
        <Panel flush title={`${streams.length} live now`}>
          <ul className="divide-y divide-ink-100">
            {streams.map((stream) => {
              const title = stream.title || 'Untitled stream'
              return (
                <li key={stream.streamId} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge tone="danger">Live</Badge>
                      <p className="truncate font-medium text-ink-900">{title}</p>
                    </div>
                    <p className="mt-1 text-sm text-ink-500">Hosted by {stream.hostName || stream.hostId}, started {formatDate(stream.startedAt)}</p>
                  </div>
                  <Button size="sm" variant="destructive" onClick={() => void end(stream.streamId, title)}>End stream</Button>
                </li>
              )
            })}
          </ul>
        </Panel>
      </Async>
      {dialog}
    </section>
  )
}

/* ------------------------------------------------------------------ Content */

export function AdminContentPage() {
  const [posts, setPosts] = useState<Awaited<ReturnType<typeof adminApi.contentPosts>>['items']>([])
  const [statuses, setStatuses] = useState<Awaited<ReturnType<typeof adminApi.contentStatuses>>['items']>([])
  const [tab, setTab] = useState<'posts' | 'statuses'>('posts')
  const [loading, setLoading] = useState(true)
  const { error, clear, notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function load() {
    try {
      clear()
      const [postResult, statusResult] = await Promise.all([adminApi.contentPosts(), adminApi.contentStatuses()])
      setPosts(postResult.items)
      setStatuses(statusResult.items)
    } catch (e) {
      fail(e, 'Unable to load member content.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function remove(kind: 'post' | 'status', id: string) {
    const ok = await confirm({ title: `Remove this ${kind}?`, description: `The ${kind} will no longer be visible to members.`, confirmLabel: `Remove ${kind}`, tone: 'danger' })
    if (!ok) return
    try {
      await (kind === 'post' ? adminApi.removePost(id) : adminApi.removeStatus(id))
      await load()
      notify(`${humanize(kind)} removed.`)
    } catch (e) {
      fail(e, `Unable to remove ${kind}.`)
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader
        title="Content"
        description="Remove member posts and statuses that break the community rules."
        actions={
          <Segmented
            label="Content type"
            value={tab}
            onChange={setTab}
            options={[{ value: 'posts', label: `Posts (${posts.length})` }, { value: 'statuses', label: `Statuses (${statuses.length})` }]}
          />
        }
      />
      {banner}
      {tab === 'posts' ? (
        <Async loading={loading} count={posts.length} failed={!!error} empty={<EmptyState icon={Newspaper} title="No posts" description="Member posts will appear here." />}>
          <Panel flush>
            <ul className="divide-y divide-ink-100">
              {posts.map((post) => (
                <li key={post.postId} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink-900">{post.authorName || post.authorId}</p>
                    <p className="mt-0.5 line-clamp-2 text-sm text-ink-600">{post.caption || 'No caption'}</p>
                    <p className="mt-1 text-xs text-ink-500">{formatDate(post.createdAt)}</p>
                  </div>
                  <Button size="sm" variant="destructive" onClick={() => void remove('post', post.postId)}>Remove post</Button>
                </li>
              ))}
            </ul>
          </Panel>
        </Async>
      ) : (
        <Async loading={loading} count={statuses.length} failed={!!error} empty={<EmptyState icon={Newspaper} title="No statuses" description="Active member statuses will appear here." />}>
          <Panel flush>
            <ul className="divide-y divide-ink-100">
              {statuses.map((status) => (
                <li key={status.statusId} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-ink-900">{status.authorName || status.authorId}</p>
                      <Badge>{humanize(status.mediaKind)}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-ink-500">Expires {formatDate(status.expiresAt)}</p>
                  </div>
                  <Button size="sm" variant="destructive" onClick={() => void remove('status', status.statusId)}>Remove status</Button>
                </li>
              ))}
            </ul>
          </Panel>
        </Async>
      )}
      {dialog}
    </section>
  )
}