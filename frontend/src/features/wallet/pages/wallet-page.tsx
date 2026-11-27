import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Coins, Gift, Share2, Wallet as WalletIcon, Landmark, HeartHandshake } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import {
  acceptMeetupPayment,
  confirmMeetupPayment,
  declineMeetupPayment,
  fundWallet,
  getWalletBalance,
  listMeetupPayments,
  listTransactions,
  refundMeetupPayment,
  verifyWalletTopUp,
} from '@/lib/api/wallet'
import { getCallCreditBalance } from '@/lib/api/calls'
import { ApiError, type WalletTransactionType } from '@/lib/api/types'
import { useSessionStore } from '@/lib/stores/session-store'

const QUICK_AMOUNTS = [500, 1000, 5000, 10000]

const TRANSACTION_LABELS: Record<WalletTransactionType, string> = {
  'wallet-top-up': 'Wallet top-up',
  'gift-purchase': 'Gift purchase',
  'gift-received': 'Gift received',
  redemption: 'Gift redeemed',
  'referral-bonus': 'Referral bonus',
  'call-bonus': 'Call bonus',
  payout: 'Payout',
  'payout-refund': 'Payout refund',
  'admin-adjustment': 'Account adjustment',
  'meetup-payment-held': 'Meetup payment held',
  'meetup-payment-released': 'Meetup payment released',
  'meetup-payment-refunded': 'Meetup payment refunded',
  'video-unlock': 'Video unlocked',
  'video-sale': 'Video unlock earnings',
  'vip-subscription': 'VIP subscription',
  'coin-purchase': 'Call credit coins bought',
  'call-credit-spend': 'Call credit coins spent',
}

const LINKS = [
  { to: '/gifts/shop', icon: Gift, label: 'Gift shop', description: 'Buy gifts and view your collection' },
  { to: '/gifts/redeem', icon: WalletIcon, label: 'Redeem gifts', description: 'Trade received gifts for cash' },
  { to: '/referrals', icon: Share2, label: 'Referrals', description: 'Invite friends, track referrals' },
  { to: '/payout', icon: Landmark, label: 'Payout', description: 'Withdraw to your bank account' },
]

export function WalletPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const accountId = useSessionStore((state) => state.session?.accountId)
  const [searchParams] = useSearchParams()
  const [fundOpen, setFundOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [funding, setFunding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paymentStatus, setPaymentStatus] = useState<'verifying' | 'pending' | 'success' | null>(null)
  const [paymentError, setPaymentError] = useState<string | null>(null)
  const paymentReference = searchParams.get('reference') ?? searchParams.get('trxref')

  const [resolvingId, setResolvingId] = useState<string | null>(null)

  const { data: balance, isLoading: balanceLoading } = useQuery({ queryKey: ['wallet-balance'], queryFn: getWalletBalance })
  const { data: transactions, isLoading: transactionsLoading } = useQuery({ queryKey: ['wallet-transactions'], queryFn: listTransactions })
  const { data: meetupPayments = [] } = useQuery({ queryKey: ['meetup-payments'], queryFn: listMeetupPayments })
  const { data: callCredits } = useQuery({ queryKey: ['call-credits'], queryFn: getCallCreditBalance })

  useEffect(() => {
    if (!paymentReference) {
      setPaymentStatus(null)
      setPaymentError(null)
      return
    }

    let active = true
    setPaymentStatus('verifying')
    setPaymentError(null)
    void verifyWalletTopUp(paymentReference)
      .then(async (result) => {
        if (!active) return
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ['wallet-balance'] }),
          queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] }),
        ])
        if (active) setPaymentStatus(result.status)
      })
      .catch((err: unknown) => {
        if (!active) return
        setPaymentStatus(null)
        setPaymentError(err instanceof ApiError ? err.message : 'Could not verify this payment. Try again later.')
      })

    return () => {
      active = false
    }
  }, [paymentReference, queryClient])

  async function refreshWallet() {
    await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
    await queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] })
    await queryClient.invalidateQueries({ queryKey: ['meetup-payments'] })
  }

  async function handleConfirmMeetup(paymentId: string) {
    setResolvingId(paymentId)
    try {
      await confirmMeetupPayment(paymentId)
      await refreshWallet()
      showToast({ title: 'Meetup confirmed', description: 'The held payment has been released.', variant: 'success' })
    } finally {
      setResolvingId(null)
    }
  }

  async function handleRefundMeetup(paymentId: string) {
    setResolvingId(paymentId)
    try {
      await refundMeetupPayment(paymentId)
      await refreshWallet()
      showToast({ title: 'Payment refunded', variant: 'success' })
    } finally {
      setResolvingId(null)
    }
  }

  async function handleAcceptMeetup(paymentId: string) {
    setResolvingId(paymentId)
    try {
      await acceptMeetupPayment(paymentId)
      await refreshWallet()
      showToast({ title: 'Proposal accepted', description: "It's now held until the meetup is confirmed.", variant: 'success' })
    } catch (error) {
      showToast({
        title: 'Could not accept proposal',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setResolvingId(null)
    }
  }

  async function handleDeclineMeetup(paymentId: string) {
    setResolvingId(paymentId)
    try {
      await declineMeetupPayment(paymentId)
      await refreshWallet()
      showToast({ title: 'Proposal declined', variant: 'info' })
    } finally {
      setResolvingId(null)
    }
  }

  async function handleFund(amountNaira: number) {
    setError(null)
    setFunding(true)
    try {
      const checkout = await fundWallet(amountNaira)
      const authorizationUrl = new URL(checkout.authorizationUrl)
      if (
        authorizationUrl.protocol !== 'https:'
        || (authorizationUrl.hostname !== 'paystack.com' && !authorizationUrl.hostname.endsWith('.paystack.com'))
      ) {
        throw new ApiError('INVALID_CHECKOUT_URL', 'Paystack returned an invalid checkout link.')
      }
      window.location.assign(authorizationUrl.toString())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not fund your wallet. Try again.')
    } finally {
      setFunding(false)
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">Wallet</h1>

      {paymentReference && (
        <div role="status" className="mt-4 rounded-2xl border border-ink-100 bg-white p-4 text-sm">
          {paymentError ? (
            <p className="text-danger">{paymentError}</p>
          ) : paymentStatus === 'verifying' ? (
            <p className="text-ink-700">Verifying your Paystack payment…</p>
          ) : paymentStatus === 'success' ? (
            <p className="font-medium text-success">Payment confirmed. Your wallet balance is up to date.</p>
          ) : paymentStatus === 'pending' ? (
            <p className="text-ink-700">Payment is still processing. Your wallet will update after Paystack confirms it.</p>
          ) : null}
        </div>
      )}

      <Card className="mt-6 bg-gradient-to-br from-primary-500 to-primary-600 text-white">
        <p className="text-sm font-medium text-white/80">Balance</p>
        {balanceLoading ? (
          <div className="mt-2 h-9 w-32 animate-pulse rounded-lg bg-white/20" />
        ) : (
          <p className="mt-1 text-3xl font-extrabold">{formatNaira(balance ?? 0)}</p>
        )}
        <Button variant="primary" className="mt-4 bg-white text-primary-700 hover:bg-white/90" onClick={() => setFundOpen(true)}>
          Fund wallet
        </Button>
      </Card>

      <Link
        to="/credits/shop"
        className="mt-4 flex items-center gap-3 rounded-3xl border border-ink-100 bg-white px-5 py-4 shadow-soft transition-colors hover:bg-ink-50"
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
          <Coins className="size-5" aria-hidden="true" />
        </span>
        <span className="flex-1">
          <span className="block font-medium text-ink-800">Call credits</span>
          <span className="block text-xs text-ink-500">{callCredits ?? 0} coins — spent on voice and video calls</span>
        </span>
        <ChevronRight className="size-4 text-ink-300" aria-hidden="true" />
      </Link>

      <div className="mt-4 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
        {LINKS.map(({ to, icon: Icon, label, description }, index) => (
          <Link
            key={to}
            to={to}
            className={`flex items-center gap-3 px-5 py-4 transition-colors hover:bg-ink-50 ${index < LINKS.length - 1 ? 'border-b border-ink-100' : ''}`}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="flex-1">
              <span className="block font-medium text-ink-800">{label}</span>
              <span className="block text-xs text-ink-500">{description}</span>
            </span>
            <ChevronRight className="size-4 text-ink-300" aria-hidden="true" />
          </Link>
        ))}
      </div>

      {meetupPayments && meetupPayments.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-bold text-ink-900">Meetup payments</h2>
          <p className="mt-1 text-sm text-ink-500">
            A proposal only charges once she accepts it. Accepted amounts stay held until you both confirm the meetup
            happened, then funds release.
          </p>
          <ul className="mt-3 flex flex-col gap-3">
            {meetupPayments.map((payment) => {
              const amIRecipient = payment.toId === accountId
              const counterpart = amIRecipient ? payment.fromName : payment.toName
              return (
                <li key={payment.id} className="rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
                        <HeartHandshake className="size-5" aria-hidden="true" />
                      </span>
                      <div>
                        <p className="font-semibold text-ink-900">
                          {amIRecipient ? `From ${counterpart}` : `To ${counterpart}`}
                        </p>
                        <p className="text-xs text-ink-400">{new Date(payment.createdAt).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-ink-900">{formatNaira(payment.amountNaira)}</p>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          payment.status === 'held' || payment.status === 'proposed'
                            ? 'bg-warning/10 text-warning'
                            : payment.status === 'released'
                              ? 'bg-success/10 text-success'
                              : 'bg-ink-100 text-ink-600'
                        }`}
                      >
                        {payment.status}
                      </span>
                    </div>
                  </div>
                  {payment.status === 'proposed' && amIRecipient && (
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1"
                        loading={resolvingId === payment.id}
                        onClick={() => handleAcceptMeetup(payment.id)}
                      >
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        loading={resolvingId === payment.id}
                        onClick={() => handleDeclineMeetup(payment.id)}
                      >
                        Decline
                      </Button>
                    </div>
                  )}
                  {payment.status === 'proposed' && !amIRecipient && (
                    <p className="mt-3 text-xs font-medium text-ink-400">Waiting for {counterpart} to respond.</p>
                  )}
                  {payment.status === 'held' && (
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1"
                        loading={resolvingId === payment.id}
                        onClick={() => handleConfirmMeetup(payment.id)}
                      >
                        Confirm meetup &amp; release
                      </Button>
                      {!amIRecipient && (
                        <Button
                          size="sm"
                          variant="outline"
                          loading={resolvingId === payment.id}
                          onClick={() => handleRefundMeetup(payment.id)}
                        >
                          Request refund
                        </Button>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-lg font-bold text-ink-900">Transactions</h2>
        {transactionsLoading && <PageSpinner label="Loading transactions" />}
        {transactions && transactions.length === 0 && (
          <div className="mt-3">
            <EmptyState title="No transactions yet" description="Funding, gifts and payouts will show up here." />
          </div>
        )}
        {transactions && transactions.length > 0 && (
          <div className="mt-3 overflow-hidden rounded-2xl border border-ink-100 bg-white shadow-soft">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-50 text-xs font-semibold uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => (
                  <tr key={transaction.id} className="border-t border-ink-100">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink-800">{transaction.description}</p>
                      <p className="text-xs text-ink-400">{TRANSACTION_LABELS[transaction.type]}</p>
                    </td>
                    <td className="px-4 py-3 text-ink-500">{new Date(transaction.createdAt).toLocaleDateString()}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          transaction.status === 'completed' ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'
                        }`}
                      >
                        {transaction.status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${transaction.amountNaira < 0 ? 'text-ink-700' : 'text-success'}`}>
                      {transaction.amountNaira < 0 ? '' : '+'}
                      {formatNaira(transaction.amountNaira)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Dialog open={fundOpen} onClose={() => setFundOpen(false)} title="Fund wallet" description="Complete payment securely on Paystack. Your balance updates after payment is confirmed.">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {QUICK_AMOUNTS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setAmount(String(value))}
                className="cursor-pointer rounded-full border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 hover:border-primary-300 hover:bg-primary-50"
              >
                {formatNaira(value)}
              </button>
            ))}
          </div>
          <Field id="fund-amount" label="Amount (₦)">
            <Input id="fund-amount" type="number" min={100} value={amount} onChange={(event) => setAmount(event.target.value)} />
          </Field>
          {error && <p role="alert" className="text-sm font-medium text-danger">{error}</p>}
          <Button loading={funding} disabled={!amount || Number(amount) <= 0} onClick={() => handleFund(Number(amount))}>
            Continue
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
