import { delay } from './client'
import { ownProfileStore, transactionStore, VIP_PLANS, walletStore } from './mock-db'
import { ApiError, type MemberProfile, type OwnProfile, type SubscriptionTier, type WalletTransaction } from './types'

export { VIP_PLANS }

const DAY_MS = 86_400_000

export interface SubscriptionStatus {
  tier: SubscriptionTier
  expiresAt?: string
}

export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  await delay(null, 200)
  const profile = ownProfileStore.profile
  const expired = profile?.vipExpiresAt && new Date(profile.vipExpiresAt) < new Date()
  return { tier: expired ? 'free' : (profile?.subscriptionTier ?? 'free'), expiresAt: profile?.vipExpiresAt }
}

export async function subscribeToVip(planId: string): Promise<SubscriptionStatus> {
  await delay(null, 700)
  const plan = VIP_PLANS.find((item) => item.id === planId)
  if (!plan) {
    throw new ApiError('PLAN_NOT_FOUND', 'That plan is not available.')
  }
  if (!ownProfileStore.profile) {
    throw new ApiError('NO_PROFILE', 'Finish onboarding before subscribing.')
  }
  if (walletStore.balanceNaira < plan.priceNaira) {
    throw new ApiError('INSUFFICIENT_BALANCE', 'Fund your wallet to subscribe.')
  }

  walletStore.balanceNaira -= plan.priceNaira

  const currentExpiry = ownProfileStore.profile.vipExpiresAt
  const base = currentExpiry && new Date(currentExpiry) > new Date() ? new Date(currentExpiry) : new Date()
  const expiresAt = new Date(base.getTime() + plan.durationDays * DAY_MS).toISOString()
  ownProfileStore.profile = { ...ownProfileStore.profile, subscriptionTier: 'vip', vipExpiresAt: expiresAt }

  const transaction: WalletTransaction = {
    id: `txn-${Date.now()}-vip`,
    type: 'vip-subscription',
    amountNaira: -plan.priceNaira,
    description: `VIP subscription — ${plan.name}`,
    status: 'completed',
    createdAt: new Date().toISOString(),
  }
  transactionStore.transactions = [...transactionStore.transactions, transaction]

  return { tier: 'vip', expiresAt }
}

/** A free member can view a VIP member, but can't message, call or pay them until they're VIP too. */
export function canInteract(viewer: OwnProfile | null | undefined, target: Pick<MemberProfile, 'subscriptionTier'>): boolean {
  return target.subscriptionTier !== 'vip' || viewer?.subscriptionTier === 'vip'
}
