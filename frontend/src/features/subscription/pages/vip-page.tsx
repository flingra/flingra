import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Crown } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button, buttonVariants } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { getOwnProfile, listVipProfiles } from '@/lib/api/profiles'
import { getWalletBalance } from '@/lib/api/wallet'
import { listVipPlans, subscribeToVip } from '@/lib/api/subscription'
import { ApiError } from '@/lib/api/types'
import { cn, formatNaira } from '@/lib/utils'
import { CircleCard } from '@/features/discovery/components/circle-card'

export function VipPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [planDialogOpen, setPlanDialogOpen] = useState(false)
  const [selectedPlanId, setSelectedPlanId] = useState('')
  const [subscribing, setSubscribing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [insufficientBalance, setInsufficientBalance] = useState(false)

  const { data: ownProfile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile })
  const { data: vipMembers, isLoading } = useQuery({ queryKey: ['vip-members'], queryFn: listVipProfiles })
  const { data: balance } = useQuery({ queryKey: ['wallet-balance'], queryFn: getWalletBalance })
  const { data: vipPlans = [] } = useQuery({ queryKey: ['vip-plans'], queryFn: listVipPlans })
  useEffect(() => {
    if (!selectedPlanId && vipPlans.length > 0) setSelectedPlanId(vipPlans[1]?.id ?? vipPlans[0].id)
  }, [vipPlans, selectedPlanId])

  const isVip = ownProfile?.subscriptionTier === 'vip'

  async function handleSubscribe() {
    setError(null)
    setInsufficientBalance(false)
    setSubscribing(true)
    try {
      await subscribeToVip(selectedPlanId)
      await queryClient.invalidateQueries({ queryKey: ['own-profile'] })
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      showToast({ title: 'Welcome to VIP', description: 'You can now interact with every VIP member.', variant: 'success' })
      setPlanDialogOpen(false)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
        setInsufficientBalance(true)
      }
      setError(err instanceof ApiError ? err.message : 'Could not subscribe. Try again.')
    } finally {
      setSubscribing(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
        <Crown className="size-6 text-amber-500" aria-hidden="true" /> VIP
      </h1>
      <p className="mt-1 text-sm text-ink-500">Priority matching and unlimited interaction with VIP members.</p>

      <Card className="mt-6 border-amber-300 bg-amber-400">
        <p className="text-sm font-semibold text-amber-950/70">Your plan</p>
        {isVip ? (
          <>
            <p className="mt-1 flex items-center gap-2 text-2xl font-extrabold text-amber-950">
              <Crown className="size-6" aria-hidden="true" /> VIP member
            </p>
            {ownProfile?.vipExpiresAt && (
              <p className="mt-1 text-sm font-medium text-amber-950/80">
                Expires {new Date(ownProfile.vipExpiresAt).toLocaleDateString()}
              </p>
            )}
            <Button
              variant="primary"
              className="mt-4 bg-ink-900 text-white hover:bg-ink-800"
              onClick={() => {
                setError(null)
                setInsufficientBalance(false)
                setPlanDialogOpen(true)
              }}
            >
              Extend VIP
            </Button>
          </>
        ) : (
          <>
            <p className="mt-1 text-2xl font-extrabold text-amber-950">Free</p>
            <p className="mt-2 text-sm font-medium text-amber-950/80">
              VIP members always match regardless of distance, and can message, call, and send meetup payments to any
              other VIP member.
            </p>
            <Button
              variant="primary"
              className="mt-4 bg-ink-900 text-white hover:bg-ink-800"
              onClick={() => {
                setError(null)
                setInsufficientBalance(false)
                setPlanDialogOpen(true)
              }}
            >
              Upgrade to VIP
            </Button>
          </>
        )}
      </Card>

      <h2 className="mt-8 text-lg font-bold text-ink-900">VIP members</h2>
      <p className="mt-1 text-sm text-ink-500">
        {isVip
          ? 'You can message, call, or send a meetup payment to any of these members.'
          : "You can view these profiles, but you'll need VIP to message, call, or send a meetup payment."}
      </p>

      {isLoading && <PageSpinner label="Loading VIP members" />}
      {vipMembers && vipMembers.length === 0 && (
        <div className="mt-4">
          <EmptyState title="No VIP members yet" description="Check back soon." />
        </div>
      )}
      {vipMembers && vipMembers.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {vipMembers.map((member) => (
            <CircleCard key={member.id} profile={member} showDistance={false} />
          ))}
        </div>
      )}

      <Dialog
        open={planDialogOpen}
        onClose={() => {
          setPlanDialogOpen(false)
          setError(null)
          setInsufficientBalance(false)
        }}
        title="Choose a VIP plan"
        description="This is a demo charge — it deducts from your wallet balance. No real payment is made."
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-500">
            Wallet balance: <span className="font-semibold text-ink-900">{formatNaira(balance ?? 0)}</span>
          </p>
          {error && !insufficientBalance && (
            <p role="alert" className="text-sm font-medium text-danger">
              {error}
            </p>
          )}
          {insufficientBalance && (
            <div className="flex items-center justify-between gap-3 rounded-2xl bg-danger/10 p-3">
              <p className="text-sm font-medium text-danger">Not enough balance — fund your wallet to continue.</p>
              <Link to="/wallet" className={cn(buttonVariants({ variant: 'destructive', size: 'sm' }), 'shrink-0')}>
                Fund wallet
              </Link>
            </div>
          )}
          {vipPlans.map((plan) => (
            <button
              key={plan.id}
              type="button"
              onClick={() => setSelectedPlanId(plan.id)}
              className={cn(
                'flex items-center justify-between rounded-2xl border p-4 text-left transition-colors',
                selectedPlanId === plan.id ? 'border-primary-500 bg-primary-50' : 'border-ink-200 hover:border-ink-300',
              )}
            >
              <div>
                <p className="font-semibold text-ink-900">{plan.name}</p>
                <p className="text-xs text-ink-500">{plan.durationDays} days</p>
              </div>
              <p className="font-bold text-ink-900">{formatNaira(plan.priceNaira)}</p>
            </button>
          ))}
          <Button loading={subscribing} onClick={handleSubscribe} className="mt-1">
            Subscribe
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
