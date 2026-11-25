import { delay } from './client'
import { callCreditStore, coinPriceStore, COIN_PACKAGE_SIZES, ownProfileStore, transactionStore, walletStore } from './mock-db'
import { ApiError, type CoinPackage, type WalletTransaction } from './types'

/** One call-credit coin covers one started minute of voice/video call time. */
export const CALL_CREDIT_COST_PER_MINUTE = 1
export const CALL_CREDIT_TICK_SECONDS = 60
export const CALL_CREDIT_COST_PER_TICK = Math.round((CALL_CREDIT_COST_PER_MINUTE / 60) * CALL_CREDIT_TICK_SECONDS)

/** Balance a caller is considered "running low" at — used to trigger the private in-call warning. */
export const LOW_CREDIT_WARNING_THRESHOLD = 3

function addTransaction(entry: Omit<WalletTransaction, 'id' | 'createdAt'>) {
  const transaction: WalletTransaction = {
    ...entry,
    id: `txn-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    createdAt: new Date().toISOString(),
  }
  transactionStore.transactions = [...transactionStore.transactions, transaction]
}

export async function getCoinPriceNaira(): Promise<number> {
  await delay(null, 200)
  return coinPriceStore.priceNaira
}

/**
 * Admin-only: sets the ₦ price of one call-credit coin for every future purchase.
 * The admin boundary is enforced by the real admin session/role (`AdminRoute`,
 * `lib/stores/admin-store.ts`) at the route layer — the same way `adminApi.decide`
 * and the other admin actions trust the session rather than re-checking a flag here.
 */
export async function setCoinPriceNaira(priceNaira: number): Promise<number> {
  await delay(null, 500)
  if (priceNaira <= 0) {
    throw new ApiError('INVALID_AMOUNT', 'Enter a coin price greater than ₦0.')
  }
  coinPriceStore.priceNaira = priceNaira
  return priceNaira
}

export async function listCoinPackages(): Promise<CoinPackage[]> {
  await delay(null, 200)
  const priceNaira = coinPriceStore.priceNaira
  return COIN_PACKAGE_SIZES.map((coins) => ({ coins, priceNaira: coins * priceNaira }))
}

export async function getCallCreditBalance(): Promise<number> {
  await delay(null, 150)
  return callCreditStore.coins
}

/**
 * Buys call-credit coins with the wallet's Naira balance, at the admin-set price per coin.
 * Only male accounts need to buy credits — calls only spend credits on the male side of a
 * call, the same asymmetric economy as meetup payments (men pay, women earn free).
 */
export async function buyCallCredits(coins: number): Promise<{ coins: number; balanceNaira: number }> {
  await delay(null, 600)
  const profile = ownProfileStore.profile
  if (!profile || profile.identity !== 'man') {
    throw new ApiError('BUYER_RESTRICTED', 'Only male accounts can buy call credits.')
  }
  if (coins <= 0) {
    throw new ApiError('INVALID_AMOUNT', 'Enter a coin amount greater than 0.')
  }
  const cost = coins * coinPriceStore.priceNaira
  if (walletStore.balanceNaira < cost) {
    throw new ApiError('INSUFFICIENT_BALANCE', 'Fund your wallet to buy call credits.')
  }

  walletStore.balanceNaira -= cost
  callCreditStore.coins += coins
  addTransaction({
    type: 'coin-purchase',
    amountNaira: -cost,
    description: `Bought ${coins} call credit coin${coins === 1 ? '' : 's'}`,
    status: 'completed',
  })
  return { coins: callCreditStore.coins, balanceNaira: walletStore.balanceNaira }
}

/**
 * Spends call credits while a call is connected (called once per minute from the call screen).
 * Clamps at 0 rather than going negative — the caller checks the returned balance and ends
 * the call once it hits 0. Not wrapped in the usual network `delay()`: this runs on a local
 * interval during a live call and must never add latency to the tick.
 */
export function spendCallCredits(amount = CALL_CREDIT_COST_PER_TICK): number {
  const next = Math.max(0, callCreditStore.coins - amount)
  const spent = callCreditStore.coins - next
  callCreditStore.coins = next
  if (spent > 0) {
    addTransaction({
      type: 'call-credit-spend',
      amountNaira: 0,
      description: `Spent ${spent} call credit coin${spent === 1 ? '' : 's'} on a call`,
      status: 'completed',
    })
  }
  return next
}
