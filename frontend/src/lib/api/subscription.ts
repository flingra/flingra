import { apiRequest, ensureCsrfHeaders } from './client'
import { type MemberProfile, type OwnProfile, type SubscriptionTier, type VipPlan } from './types'

export const VIP_PLANS: VipPlan[] = []

export interface SubscriptionStatus {
  tier: SubscriptionTier
  expiresAt?: string
}

export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  return apiRequest<SubscriptionStatus>('/subscriptions/me')
}

export async function listVipPlans(): Promise<VipPlan[]> {
  return apiRequest<VipPlan[]>('/subscriptions/plans')
}

export async function subscribeToVip(planId: string): Promise<SubscriptionStatus> {
  return apiRequest<SubscriptionStatus>('/subscriptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ planId }),
  })
}

/** A free member can view a VIP member, but can't message, call or pay them until they're VIP too. */
export function canInteract(viewer: OwnProfile | null | undefined, target: Pick<MemberProfile, 'subscriptionTier'>): boolean {
  return target.subscriptionTier !== 'vip' || viewer?.subscriptionTier === 'vip'
}
