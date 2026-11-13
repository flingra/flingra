import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Copy } from 'lucide-react'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { useSessionStore } from '@/lib/stores/session-store'
import { formatNaira } from '@/lib/utils'
import { listReferrals } from '@/lib/api/payout'

export function ReferralsPage() {
  const { showToast } = useToast()
  const session = useSessionStore((state) => state.session)
  const { data: referrals, isLoading } = useQuery({ queryKey: ['referrals'], queryFn: listReferrals })

  const code = `FLINGRA-${(session?.accountId ?? 'me').toUpperCase()}`
  const total = referrals?.reduce((sum, referral) => sum + referral.bonusNaira, 0) ?? 0

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code)
      showToast({ title: 'Referral code copied', variant: 'success' })
    } catch {
      showToast({ title: 'Could not copy', description: 'Copy the code manually.', variant: 'error' })
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Link to="/wallet" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Wallet
      </Link>

      <h1 className="mt-4 text-2xl font-bold text-ink-900">Referrals</h1>
      <p className="mt-1 text-sm text-ink-500">Share your code. When a friend joins and verifies their account, you earn a bonus.</p>

      <div className="mt-6 flex items-center justify-between gap-3 rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
        <span className="font-mono text-sm font-semibold text-ink-900">{code}</span>
        <button
          type="button"
          onClick={handleCopy}
          aria-label="Copy referral code"
          className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary-50 text-primary-600 hover:bg-primary-100"
        >
          <Copy className="size-4" aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 rounded-2xl bg-primary-50 p-4 text-center">
        <p className="text-sm text-primary-700">Total referral bonus earned</p>
        <p className="text-2xl font-extrabold text-primary-800">{formatNaira(total)}</p>
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-bold text-ink-900">Your referrals</h2>
        {isLoading && <PageSpinner label="Loading referrals" />}
        {referrals && referrals.length === 0 && (
          <div className="mt-3">
            <EmptyState title="No referrals yet" description="Invite friends with your code to start earning." />
          </div>
        )}
        {referrals && referrals.length > 0 && (
          <ul className="mt-3 flex flex-col gap-3">
            {referrals.map((referral) => (
              <li key={referral.id} className="flex items-center justify-between rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                <div>
                  <p className="font-semibold text-ink-900">{referral.referredName}</p>
                  <p className="text-xs text-ink-400">Joined {new Date(referral.joinedAt).toLocaleDateString()}</p>
                </div>
                <span className="font-semibold text-success">+{formatNaira(referral.bonusNaira)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
