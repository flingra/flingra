import { delay } from './client'
import { bankAccountStore, payoutRequestStore, referralStore, transactionStore, walletStore } from './mock-db'
import { ApiError, type BankAccount, type PayoutRequest, type ReferralRecord, type WalletTransaction } from './types'

export async function getBankAccount(): Promise<BankAccount | null> {
  await delay(null, 250)
  return bankAccountStore.account
}

export async function saveBankAccount(account: BankAccount): Promise<void> {
  await delay(undefined, 600)
  if (!account.bankName.trim() || !account.accountNumber.trim() || !account.accountName.trim()) {
    throw new ApiError('INVALID_BANK_ACCOUNT', 'Fill in your bank name, account number and account name.')
  }
  bankAccountStore.account = account
}

export async function listReferrals(): Promise<ReferralRecord[]> {
  await delay(null, 300)
  return [...referralStore.referrals].sort((a, b) => b.joinedAt.localeCompare(a.joinedAt))
}

export async function listPayoutRequests(): Promise<PayoutRequest[]> {
  await delay(null, 300)
  return [...payoutRequestStore.requests].sort((a, b) => b.requestedAt.localeCompare(a.requestedAt))
}

export async function requestPayout(amountNaira: number): Promise<void> {
  await delay(null, 700)
  if (!bankAccountStore.account) {
    throw new ApiError('NO_BANK_ACCOUNT', 'Add your bank account before requesting a payout.')
  }
  if (amountNaira <= 0) {
    throw new ApiError('INVALID_AMOUNT', 'Enter an amount greater than ₦0.')
  }
  if (amountNaira > walletStore.balanceNaira) {
    throw new ApiError('INSUFFICIENT_BALANCE', "You can't withdraw more than your wallet balance.")
  }

  walletStore.balanceNaira -= amountNaira
  const request: PayoutRequest = {
    id: `payout-${Date.now()}`,
    amountNaira,
    status: 'pending',
    requestedAt: new Date().toISOString(),
  }
  payoutRequestStore.requests = [request, ...payoutRequestStore.requests]

  const transaction: WalletTransaction = {
    id: `txn-${Date.now()}`,
    type: 'payout',
    amountNaira: -amountNaira,
    description: `Payout requested to ${bankAccountStore.account.bankName}`,
    status: 'pending',
    createdAt: new Date().toISOString(),
  }
  transactionStore.transactions = [...transactionStore.transactions, transaction]
}
