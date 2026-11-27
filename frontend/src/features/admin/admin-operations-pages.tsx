import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { RemoteTrack, Room as LiveKitRoom } from 'livekit-client'
import {
  ClipboardCheck, Gift, HeartHandshake, KeyRound, LockKeyhole, Newspaper, Phone, Radio, ScrollText,
  Search, ShieldAlert, UserRound, Users, Wallet, type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { formatNaira } from '@/lib/utils'
import { adminApi, type AdminAuditEvent, type AdminDashboardSummary, type AdminPayout, type AdminPrivacyRequest, type AdminSafetyReport, type AdminUser, type AdminUserDetails, type AdminUserMedia, type AdminUserWallet } from '@/lib/api/admin'
import { useAdminStore } from '@/lib/stores/admin-store'
import {
  Async, Badge, CopyButton, EmptyState, Field, PageHeader, Panel, Segmented, Select, StatusBadge, Table, Td,
  auditEventLabel, auditMetadataEntries, formatDate, humanize, useConfirm, useFeedback,
} from './admin-ui'

/* ------------------------------------------------------------------ Members */

const USER_STATUS_REASONS = {
  active: 'Reactivated by administrator',
  suspended: 'Suspended by administrator',
  banned: 'Permanently banned by administrator',
} as const

export function AdminUsersPage() {
  const role = useAdminStore((state) => state.session?.role)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [memberDetails, setMemberDetails] = useState<AdminUserDetails | null>(null)
  const [wallet, setWallet] = useState<AdminUserWallet | null>(null)
  const [media, setMedia] = useState<AdminUserMedia[]>([])
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState<string | null>(null)
  const [mediaErrors, setMediaErrors] = useState<Record<string, string>>({})
  const [mediaReasons, setMediaReasons] = useState<Record<string, string>>({})
  const [pendingMediaRemoval, setPendingMediaRemoval] = useState<string | null>(null)
  const detailsRequest = useRef(0)
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

  async function viewDetails(user: AdminUser) {
    const requestId = ++detailsRequest.current
    setSelectedUser(user)
    setMemberDetails(null)
    setWallet(null)
    setMedia([])
    setDetailsError(null)
    setMediaErrors({})
    setMediaReasons({})
    setPendingMediaRemoval(null)
    setDetailsLoading(true)
    try {
      const [details, walletResult, mediaResult] = await Promise.all([
        adminApi.userDetails(user.accountId),
        adminApi.userWallet(user.accountId),
        role === 'super_admin' ? adminApi.userMedia(user.accountId) : Promise.resolve({ items: [] }),
      ])
      if (requestId !== detailsRequest.current) return
      setMemberDetails(details)
      setWallet(walletResult)
      setMedia(mediaResult.items)
    } catch (e) {
      if (requestId === detailsRequest.current) {
        setDetailsError(e instanceof Error ? e.message : 'Unable to load member details.')
      }
    } finally {
      if (requestId === detailsRequest.current) setDetailsLoading(false)
    }
  }

  function closeDetails() {
    detailsRequest.current += 1
    setSelectedUser(null)
    setDetailsLoading(false)
  }

  async function removeUpload(item: AdminUserMedia) {
    if (!memberDetails) return
    const reason = mediaReasons[item.mediaId]?.trim()
    if (!reason) {
      setDetailsError('Enter why this upload should be removed.')
      return
    }
    if (pendingMediaRemoval !== item.mediaId) {
      setPendingMediaRemoval(item.mediaId)
      return
    }
    try {
      await adminApi.removeUserMedia(memberDetails.accountId, item.mediaId, reason)
      setMedia((current) => current.filter((upload) => upload.mediaId !== item.mediaId))
      setPendingMediaRemoval(null)
      setMediaReasons((current) => ({ ...current, [item.mediaId]: '' }))
      setDetailsError(null)
    } catch (e) {
      setDetailsError(e instanceof Error ? e.message : 'Unable to remove this upload.')
    }
  }

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
                      <Button size="sm" variant="outline" onClick={() => void viewDetails(user)}>View details</Button>
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
      <Dialog
        open={selectedUser !== null}
        onClose={closeDetails}
        title={memberDetails?.displayName || selectedUser?.displayName || 'Member details'}
        description="Account, profile, wallet history, and moderation context."
        className="max-w-6xl"
      >
        {detailsLoading && <p className="text-sm text-ink-500">Loading member details…</p>}
        {detailsError && <p role="alert" className="text-sm text-danger">{detailsError}</p>}
        {memberDetails && (
          <div className="space-y-6">
            <section>
              <h3 className="mb-3 text-sm font-semibold text-ink-900">Account and profile</h3>
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {[
                  ['Email', memberDetails.email],
                  ['Contact', memberDetails.contact],
                  ['Username', memberDetails.username],
                  ['Account status', memberDetails.accountStatus],
                  ['Email verified', memberDetails.emailVerified ? 'Yes' : 'No'],
                  ['Date of birth', memberDetails.dateOfBirth],
                  ['Gender', memberDetails.gender],
                  ['Identity', memberDetails.identity],
                  ['Age range', memberDetails.ageRange],
                  ['Location', memberDetails.area],
                  ['Interests', memberDetails.interests?.join(', ')],
                  ['Profile review', memberDetails.moderationStatus],
                  ['Identity check', memberDetails.documentVerification],
                  ['Document type', memberDetails.documentType],
                  ['Subscription', memberDetails.subscriptionTier],
                  ['VIP expires', formatDate(memberDetails.vipExpiresAt)],
                  ['Profile complete', memberDetails.onboardingComplete === null ? null : memberDetails.onboardingComplete ? 'Yes' : 'No'],
                  ['Discoverable by', memberDetails.discoverableBy],
                  ['Interested in', memberDetails.wantsToDiscover],
                  ['Identity visible', memberDetails.showIdentity === null ? null : memberDetails.showIdentity ? 'Yes' : 'No'],
                  ['Joined', formatDate(memberDetails.createdAt)],
                  ['Last account update', formatDate(memberDetails.updatedAt)],
                  ['Terms accepted', memberDetails.termsVersion],
                  ['Privacy policy', memberDetails.privacyVersion],
                  ['Emergency contact', memberDetails.emergencyContactName],
                  ['Emergency phone', memberDetails.emergencyContactPhone],
                ].filter((field): field is [string, string] => typeof field[1] === 'string' && field[1].length > 0).map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <dt className="text-ink-500">{label}</dt>
                    <dd className="break-words font-medium text-ink-900">{label === 'Account status' || label.endsWith('check') || label === 'Subscription' ? humanize(value) : value}</dd>
                  </div>
                ))}
              </dl>
              {memberDetails.bio && (
                <div className="mt-4">
                  <p className="text-sm text-ink-500">About</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-ink-900">{memberDetails.bio}</p>
                </div>
              )}
            </section>

            {wallet && (
              <section>
                <h3 className="mb-3 text-sm font-semibold text-ink-900">Wallet and spending</h3>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ['Wallet balance', formatNaira(wallet.walletBalanceKobo / 100)],
                    ['Wallet spent', formatNaira(wallet.walletSpentKobo / 100)],
                    ['Call-credit balance', `${wallet.callCreditBalance.toLocaleString()} coins`],
                    ['Call credits spent', `${wallet.callCreditsSpent.toLocaleString()} coins`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg bg-ink-50 p-3">
                      <p className="text-xs text-ink-500">{label}</p>
                      <p className="mt-1 text-lg font-semibold tabular-nums text-ink-900">{value}</p>
                    </div>
                  ))}
                </div>
                <h4 className="mb-2 mt-4 text-sm font-medium text-ink-800">Recent transactions</h4>
                {wallet.transactions.length ? (
                  <ul className="max-h-64 divide-y divide-ink-100 overflow-y-auto rounded-lg border border-ink-100">
                    {wallet.transactions.map((transaction, index) => {
                      const spent = transaction.amount < 0
                      const amount = transaction.ledger === 'wallet'
                        ? formatNaira(Math.abs(transaction.amount) / 100)
                        : `${Math.abs(transaction.amount).toLocaleString()} coins`
                      return (
                        <li key={`${transaction.createdAt}-${transaction.transactionType}-${index}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
                          <div>
                            <p className="font-medium text-ink-900">{transaction.description}</p>
                            <p className="text-xs text-ink-500">{humanize(transaction.ledger)} · {humanize(transaction.transactionType)} · {formatDate(transaction.createdAt)}</p>
                          </div>
                          <p className={`font-semibold tabular-nums ${spent ? 'text-red-700' : 'text-emerald-700'}`}>{spent ? '−' : '+'}{amount}</p>
                        </li>
                      )
                    })}
                  </ul>
                ) : <p className="text-sm text-ink-500">No wallet or call-credit transactions yet.</p>}
              </section>
            )}

            {role === 'super_admin' && (
              <section>
                <h3 className="mb-3 text-sm font-semibold text-ink-900">Private uploads</h3>
                <p className="mb-3 text-xs text-ink-500">Access is restricted to super admins and each opened upload is recorded in the audit history.</p>
                {media.length ? (
                  <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {media.map((item) => {
                      const src = adminApi.userMediaUrl(memberDetails.accountId, item.mediaId)
                      return (
                        <li key={item.mediaId} className="overflow-hidden rounded-lg border border-ink-100">
                          {item.contentType.startsWith('image/') && <img src={src} alt={`${humanize(item.purpose)} upload`} className="aspect-video w-full bg-ink-50 object-contain" loading="lazy" onError={() => setMediaErrors((current) => ({ ...current, [item.mediaId]: 'Preview could not be loaded.' }))} />}
                          {item.contentType.startsWith('video/') && <video src={src} controls playsInline preload="metadata" className="aspect-video w-full bg-ink-900" onError={() => setMediaErrors((current) => ({ ...current, [item.mediaId]: 'Video could not be loaded.' }))} />}
                          {item.contentType === 'application/pdf' && <iframe title={`${humanize(item.purpose)} document`} src={src} className="aspect-video w-full bg-ink-50" />}
                          {!item.contentType.startsWith('image/') && !item.contentType.startsWith('video/') && item.contentType !== 'application/pdf' && (
                            <div className="grid aspect-video place-items-center bg-ink-50 px-4 text-center text-sm text-ink-500">Preview unavailable for {item.contentType}</div>
                          )}
                          <div className="p-3">
                            <p className="font-medium text-ink-900">{humanize(item.purpose)}</p>
                            <p className="mt-1 text-xs text-ink-500">{formatDate(item.createdAt)} · {(item.sizeBytes / 1024).toFixed(0)} KB</p>
                            {mediaErrors[item.mediaId] && <p role="alert" className="mt-1 text-xs text-danger">{mediaErrors[item.mediaId]}</p>}
                            {item.contentType.startsWith('image/') || item.contentType.startsWith('video/') ? (
                              <div className="mt-3 space-y-2">
                                <Input
                                  aria-label={`Removal reason for ${humanize(item.purpose)}`}
                                  placeholder="Reason for removal"
                                  value={mediaReasons[item.mediaId] ?? ''}
                                  onChange={(event) => setMediaReasons((current) => ({ ...current, [item.mediaId]: event.target.value }))}
                                />
                                <div className="flex gap-2">
                                  <Button size="sm" variant="destructive" onClick={() => void removeUpload(item)}>
                                    {pendingMediaRemoval === item.mediaId ? 'Confirm removal' : 'Remove upload'}
                                  </Button>
                                  {pendingMediaRemoval === item.mediaId && <Button size="sm" variant="outline" onClick={() => setPendingMediaRemoval(null)}>Cancel</Button>}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                ) : <p className="text-sm text-ink-500">No stored uploads are available for this member.</p>}
              </section>
            )}
          </div>
        )}
      </Dialog>
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
                const metadata = auditMetadataEntries(event.metadata)
                return (
                  <li key={event.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-ink-900">{auditEventLabel(event.eventType)}</span>
                        <StatusBadge status={event.outcome} />
                      </div>
                      <span className="text-sm text-ink-500">{formatDate(event.createdAt)}</span>
                    </div>
                    <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                      <div className="min-w-0"><dt className="text-ink-500">Who</dt><dd className="truncate text-ink-900">{event.actorName || humanize(event.actorType)}</dd></div>
                      <div className="min-w-0"><dt className="text-ink-500">Member</dt><dd className="truncate text-ink-900">{event.accountName || (event.accountId ? 'Member account' : 'Platform')}</dd></div>
                    </dl>
                    {metadata.length > 0 && (
                      <dl className="mt-3 grid gap-x-6 gap-y-2 rounded-lg bg-ink-50 p-3 text-sm sm:grid-cols-2">
                        {metadata.map((entry) => (
                          <div key={entry.label}>
                            <dt className="text-ink-500">{entry.label}</dt>
                            <dd className="break-words text-ink-900">{entry.value}</dd>
                          </div>
                        ))}
                      </dl>
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

const REVIEW = ['super_admin', 'admin', 'reviewer']
const SAFETY = ['super_admin', 'admin', 'safety_admin']
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

const OVERVIEW_METRICS: {
  key: string
  label: string
  format?: (value: number) => string
  roles?: string[]
}[] = [
  { key: 'registeredMembers', label: 'Total members' },
  { key: 'activeAccounts', label: 'Active accounts' },
  { key: 'activeMembersLast30Days', label: 'Active in last 30 days' },
  { key: 'newMembersLast30Days', label: 'New members · 30 days' },
  { key: 'activeVipMembers', label: 'Active VIP members' },
  {
    key: 'walletFundingLast30DaysKobo',
    label: 'Wallet funding · 30 days',
    format: (kobo) => formatNaira(kobo / 100),
    roles: SUPER,
  },
]

function dashboardCount(summary: AdminDashboardSummary | null, key: string) {
  const value = summary?.[key]
  return typeof value === 'number' ? value : undefined
}

export function AdminDashboardPage() {
  const role = useAdminStore((state) => state.session?.role) ?? ''
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null)
  const { fail, banner } = useFeedback()

  useEffect(() => {
    adminApi.dashboard().then(setSummary).catch((e) => fail(e, 'Unable to load admin dashboard.'))
  }, [])

  const overviewMetrics = OVERVIEW_METRICS.filter(
    (metric) =>
      (!metric.roles || metric.roles.includes(role)) &&
      (summary === null || dashboardCount(summary, metric.key) !== undefined),
  )
  const attentionStats = ATTENTION.filter(
    (stat) => summary === null || dashboardCount(summary, stat.key) !== undefined,
  )
  const totalAttention = summary
    ? attentionStats.reduce((total, stat) => total + (dashboardCount(summary, stat.key) ?? 0), 0)
    : undefined
  const largestQueue = Math.max(
    1,
    ...attentionStats.map((stat) => dashboardCount(summary, stat.key) ?? 0),
  )
  const activityMetrics = [
    { key: 'postsLast30Days', label: 'Posts · last 30 days' },
    { key: 'activeStatuses', label: 'Active statuses' },
    ...LIVE.map(({ key, label }) => ({ key, label })),
  ].filter((metric) => summary === null || dashboardCount(summary, metric.key) !== undefined)
  const signupTrend = summary?.memberSignupsByDay ?? []
  const signupPeak = Math.max(0, ...signupTrend.map((day) => day.count))
  const signupTotal = signupTrend.reduce((total, day) => total + day.count, 0)

  return (
    <section className="space-y-8">
      <PageHeader title="Platform overview" description="Membership, growth, engagement, and operational work across Flingra." />
      {banner}
      {overviewMetrics.length > 0 && (
        <section aria-labelledby="admin-membership-heading" className="space-y-3">
          <h2 id="admin-membership-heading" className="text-lg font-semibold text-ink-900">Membership</h2>
          <div className="grid grid-cols-2 border-y border-ink-200 sm:grid-cols-3 xl:grid-cols-6">
            {overviewMetrics.map((metric) => {
              const value = dashboardCount(summary, metric.key)
              return (
                <div key={metric.key} className="border-l border-ink-100 px-4 py-4 first:border-l-0">
                  <p className="text-2xl font-semibold tabular-nums text-ink-900">
                    {value === undefined ? '—' : metric.format?.(value) ?? value.toLocaleString()}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-ink-500">{metric.label}</p>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-ink-400">
            Total members excludes accounts requested for deletion; active members are based on recorded session activity.
          </p>
        </section>
      )}

      {signupTrend.length > 0 && (
        <section aria-labelledby="admin-signups-heading" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="admin-signups-heading" className="text-lg font-semibold text-ink-900">Member growth</h2>
              <p className="mt-1 text-sm text-ink-500">New account registrations per day · last 30 days.</p>
            </div>
            <p className="text-sm font-medium tabular-nums text-ink-700">
              {signupTotal.toLocaleString()} signups
              {signupPeak > 0 && <span className="ml-2 text-ink-400">· peak {signupPeak}/day</span>}
            </p>
          </div>
          <div
            className="flex h-36 items-end gap-1 border-b border-ink-200 px-1"
            role="img"
            aria-label={`Daily member signups for the last 30 days, ${signupTotal} total`}
          >
            {signupTrend.map((day) => (
              <div
                key={day.date}
                className="flex h-full min-w-0 flex-1 items-end"
                title={`${new Date(`${day.date}T00:00:00`).toLocaleDateString()}: ${day.count} signups`}
              >
                <span
                  className="w-full rounded-t-sm bg-primary-500/80"
                  style={{ height: signupPeak === 0 ? '0%' : `${Math.max((day.count / signupPeak) * 100, day.count > 0 ? 3 : 0)}%` }}
                />
              </div>
            ))}
          </div>
          {signupTrend.length > 0 && (
            <div className="flex justify-between text-xs text-ink-400">
              <span>{new Date(`${signupTrend[0].date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
              <span>{new Date(`${signupTrend[signupTrend.length - 1].date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
            </div>
          )}
        </section>
      )}

      {activityMetrics.length > 0 && (
        <section aria-labelledby="admin-activity-heading" className="space-y-3">
          <h2 id="admin-activity-heading" className="text-lg font-semibold text-ink-900">Engagement & live activity</h2>
          <div className="grid grid-cols-2 border-y border-ink-200 sm:grid-cols-4">
            {activityMetrics.map((metric) => {
              const value = dashboardCount(summary, metric.key)
              return (
                <div key={metric.key} className="border-l border-ink-100 px-4 py-4 first:border-l-0">
                  <p className="text-2xl font-semibold tabular-nums text-ink-900">
                    {value === undefined ? '—' : value.toLocaleString()}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-ink-500">{metric.label}</p>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <section aria-labelledby="admin-queues-heading" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 id="admin-queues-heading" className="text-lg font-semibold text-ink-900">Needs attention</h2>
            <p className="mt-1 text-sm text-ink-500">Work waiting in each operational queue.</p>
          </div>
          <span className="text-sm text-ink-500">
            {totalAttention === undefined ? '—' : totalAttention.toLocaleString()} open items · {attentionStats.length} queues
          </span>
        </div>
        <div className="divide-y divide-ink-100 border-y border-ink-100">
          {attentionStats.map((stat) => {
            const Icon = stat.icon
            const value = dashboardCount(summary, stat.key)
            const content = (
              <>
                <span className="flex min-w-0 items-center gap-3">
                  <Icon className="size-4 shrink-0 text-ink-400" aria-hidden="true" />
                  <span className="truncate font-medium text-ink-800">{stat.label}</span>
                </span>
                <span className="flex items-center gap-4">
                  <span
                    className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-ink-100 sm:block"
                    role="progressbar"
                    aria-label={`${stat.label} relative queue size`}
                    aria-valuemin={0}
                    aria-valuemax={largestQueue}
                    aria-valuenow={value ?? 0}
                  >
                    <span
                      className="block h-full rounded-full bg-primary-500"
                      style={{ width: `${((value ?? 0) / largestQueue) * 100}%` }}
                    />
                  </span>
                  <span className="w-10 text-right font-semibold tabular-nums text-ink-900">
                    {value === undefined ? '—' : value.toLocaleString()}
                  </span>
                </span>
              </>
            )
            const href = (stat.roles ?? []).includes(role) ? stat.to : undefined
            return href ? (
              <Link
                key={stat.key}
                to={href}
                className="flex min-h-14 items-center justify-between gap-4 px-2 outline-none transition-colors hover:bg-ink-50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
              >
                {content}
              </Link>
            ) : (
              <div key={stat.key} className="flex min-h-14 items-center justify-between gap-4 px-2">
                {content}
              </div>
            )
          })}
        </div>
      </section>
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

function AdminLiveMonitor({ streamId }: { streamId: string }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLDivElement>(null)
  const [videoTrack, setVideoTrack] = useState<RemoteTrack | null>(null)
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'failed'>('connecting')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let room: LiveKitRoom | null = null

    async function connect() {
      try {
        const [{ Room, RoomEvent, Track }, credentials] = await Promise.all([
          import('livekit-client'),
          adminApi.liveMonitorToken(streamId),
        ])
        if (cancelled) return
        room = new Room({ adaptiveStream: true, dynacast: true })
        room.on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === Track.Kind.Video) {
            setVideoTrack(track)
          } else if (track.kind === Track.Kind.Audio) {
            const element = track.attach()
            if (element instanceof HTMLAudioElement && audioRef.current) {
              element.autoplay = true
              audioRef.current.appendChild(element)
            }
          }
        })
        room.on(RoomEvent.TrackUnsubscribed, (track) => {
          track.detach().forEach((element) => element.remove())
          if (track.kind === Track.Kind.Video) setVideoTrack(null)
        })
        room.on(RoomEvent.Disconnected, () => {
          if (!cancelled) {
            setConnectionState('failed')
            setError('The live media connection ended.')
          }
        })
        await room.connect(credentials.url, credentials.token)
        if (!cancelled) setConnectionState('connected')
      } catch (e) {
        if (!cancelled) {
          setConnectionState('failed')
          setError(e instanceof Error ? e.message : 'Unable to connect to the live stream.')
        }
        room?.removeAllListeners()
        await room?.disconnect()
      }
    }

    void connect()
    return () => {
      cancelled = true
      room?.removeAllListeners()
      void room?.disconnect()
    }
  }, [streamId])

  useEffect(() => {
    if (!videoTrack || !videoRef.current) return
    videoTrack.attach(videoRef.current)
    return () => { videoTrack.detach(videoRef.current!) }
  }, [videoTrack])

  return (
    <div className="space-y-2">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-ink-950">
        <video ref={videoRef} autoPlay playsInline className="size-full object-contain" />
        {connectionState === 'connecting' && <p className="absolute inset-0 grid place-items-center text-sm text-white">Connecting to live video…</p>}
        {connectionState === 'connected' && !videoTrack && <p className="absolute inset-0 grid place-items-center text-sm text-white">Waiting for the streamer’s camera…</p>}
        {error && <p role="alert" className="absolute inset-x-0 bottom-0 bg-red-950/90 p-3 text-sm text-white">{error}</p>}
      </div>
      <div ref={audioRef} className="hidden" aria-hidden="true" />
      <p className="text-xs text-ink-500">Live monitor · read-only</p>
    </div>
  )
}

export function AdminLiveStreamsPage() {
  const [streams, setStreams] = useState<Awaited<ReturnType<typeof adminApi.liveStreams>>['items']>([])
  const [loading, setLoading] = useState(true)
  const [monitoring, setMonitoring] = useState<string | null>(null)
  const [warningReasons, setWarningReasons] = useState<Record<string, string>>({})
  const { error, clear, notify, fail, banner } = useFeedback()
  const { confirm, dialog } = useConfirm()

  async function load(showLoading = true) {
    try {
      if (showLoading) clear()
      setStreams((await adminApi.liveStreams()).items)
    } catch (e) {
      fail(e, 'Unable to load live streams.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => { void load(false) }, 5000)
    return () => window.clearInterval(timer)
  }, [])

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

  async function sendWarning(streamId: string, severity: 'warning' | 'violation') {
    const reason = warningReasons[streamId]?.trim()
    if (!reason) {
      fail(null, 'Enter a reason before sending a warning.')
      return
    }
    try {
      await adminApi.warnLiveStream(streamId, severity, reason)
      setWarningReasons((current) => ({ ...current, [streamId]: '' }))
      notify(`${severity === 'violation' ? 'Violation warning' : 'Warning'} sent to the live room.`)
    } catch (e) {
      fail(e, 'Unable to send the live warning.')
    }
  }

  async function changeHostStatus(stream: { streamId: string; hostId: string; hostName: string | null; title: string }, status: 'suspended' | 'banned') {
    const name = stream.hostName || 'this member'
    const action = status === 'banned' ? 'ban' : 'suspend'
    const ok = await confirm({
      title: `${status === 'banned' ? 'Ban' : 'Suspend'} ${name}?`,
      description: `This will end “${stream.title || 'Untitled stream'}” and ${action} the host’s account.`,
      confirmLabel: status === 'banned' ? 'End and ban' : 'End and suspend',
      tone: 'danger',
    })
    if (!ok) return
    try {
      await adminApi.endLiveStream(stream.streamId)
      await adminApi.setUserStatus(stream.hostId, status, `Live stream moderation: ${status} by administrator`)
      setMonitoring((current) => current === stream.streamId ? null : current)
      await load()
      notify(`${name} was ${status} and their stream was ended.`)
    } catch (e) {
      fail(e, `Unable to ${action} the host.`)
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Live streams" description="Monitor live video and audio, send warnings into the room, or take account action. The list refreshes automatically." />
      {banner}
      <Async loading={loading} count={streams.length} failed={!!error} empty={<EmptyState icon={Radio} title="No active streams" description="Streams that are live right now will appear here." />}>
        <div className="space-y-4">
            {streams.map((stream) => {
              const title = stream.title || 'Untitled stream'
              return (
                <Panel key={stream.streamId} flush title={`${stream.hostName || 'Member'} · ${title}`} actions={<Badge tone="danger">Live now</Badge>}>
                  <div className="space-y-4 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm text-ink-500">Started {formatDate(stream.startedAt)}</p>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" onClick={() => setMonitoring((current) => current === stream.streamId ? null : stream.streamId)}>
                          {monitoring === stream.streamId ? 'Stop monitoring' : 'Monitor live'}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => void end(stream.streamId, title)}>End stream</Button>
                        <Button size="sm" variant="outline" onClick={() => void changeHostStatus(stream, 'suspended')}>Suspend host</Button>
                        <Button size="sm" variant="destructive" onClick={() => void changeHostStatus(stream, 'banned')}>Ban host</Button>
                      </div>
                    </div>
                    {monitoring === stream.streamId && <AdminLiveMonitor streamId={stream.streamId} />}
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <Input
                        aria-label={`Warning reason for ${stream.hostName || 'stream'}`}
                        placeholder="Describe the issue for the streamer"
                        value={warningReasons[stream.streamId] ?? ''}
                        onChange={(event) => setWarningReasons((current) => ({ ...current, [stream.streamId]: event.target.value }))}
                      />
                      <Button size="sm" variant="outline" onClick={() => void sendWarning(stream.streamId, 'warning')}>Send warning</Button>
                      <Button size="sm" variant="destructive" onClick={() => void sendWarning(stream.streamId, 'violation')}>Violation warning</Button>
                    </div>
                  </div>
                </Panel>
              )
            })}
        </div>
      </Async>
      {dialog}
    </section>
  )
}

/* ------------------------------------------------------------------ Content */

export function AdminContentPage() {
  const role = useAdminStore((state) => state.session?.role)
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
                    {role === 'super_admin' && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(post.photos ?? []).map((photo) => {
                          const mediaId = /^\/media\/([0-9a-f]{32})$/.exec(photo)?.[1]
                          return mediaId ? <img key={mediaId} src={adminApi.userMediaUrl(post.authorId, mediaId)} alt="Post upload" className="size-24 rounded-lg bg-ink-50 object-cover" loading="lazy" /> : null
                        })}
                        {post.videoUrl && (() => {
                          const mediaId = /^\/media\/([0-9a-f]{32})$/.exec(post.videoUrl)?.[1]
                          return mediaId ? <video key={mediaId} src={adminApi.userMediaUrl(post.authorId, mediaId)} controls playsInline preload="metadata" className="aspect-video w-48 rounded-lg bg-ink-900" /> : null
                        })()}
                      </div>
                    )}
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
                    {role === 'super_admin' && status.mediaUrl && (() => {
                      const mediaId = /^\/media\/([0-9a-f]{32})$/.exec(status.mediaUrl)?.[1]
                      if (!mediaId) return null
                      const src = adminApi.userMediaUrl(status.authorId, mediaId)
                      return status.mediaKind === 'video'
                        ? <video src={src} controls playsInline preload="metadata" className="mt-3 aspect-video w-64 rounded-lg bg-ink-900" />
                        : <img src={src} alt="Status upload" className="mt-3 size-36 rounded-lg bg-ink-50 object-cover" loading="lazy" />
                    })()}
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