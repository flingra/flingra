import { apiRequest, ensureCsrfHeaders } from './client'
import { type BankAccount, type PayoutRequest, type ReferralRecord } from './types'

export async function getBankAccount(): Promise<BankAccount | null> {
  return apiRequest<BankAccount | null>('/payout/bank-account')
}

export async function listPayoutBanks(): Promise<{ code: string; name: string }[]> {
  return apiRequest<{ code: string; name: string }[]>('/payout/banks')
}

export async function saveBankAccount(account: { accountNumber: string; bankCode: string }): Promise<BankAccount> {
  return apiRequest<BankAccount>('/payout/bank-account', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify(account),
  })
}

export async function listReferrals(): Promise<ReferralRecord[]> {
  return apiRequest<ReferralRecord[]>('/referrals')
}

export async function getReferralCode(): Promise<{ code: string }> {
  return apiRequest<{ code: string }>('/referrals/code')
}

export async function listPayoutRequests(): Promise<PayoutRequest[]> {
  return apiRequest<PayoutRequest[]>('/payouts')
}

export async function requestPayout(amountNaira: number): Promise<PayoutRequest> {
  const key = crypto.randomUUID()
  return apiRequest<PayoutRequest>('/payouts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key, ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ amountNaira }),
  })
}
