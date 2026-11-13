import { delay } from './client'
import { GIFT_CATALOG, ownedGiftStore, receivedGiftStore, transactionStore, walletStore } from './mock-db'
import { ApiError, type GiftType, type OwnedGift, type ReceivedGift, type WalletTransaction } from './types'

export { GIFT_CATALOG }

export async function getWalletBalance(): Promise<number> {
  await delay(null, 200)
  return walletStore.balanceNaira
}

export async function listTransactions(): Promise<WalletTransaction[]> {
  await delay(null, 300)
  return [...transactionStore.transactions].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

function addTransaction(entry: Omit<WalletTransaction, 'id' | 'createdAt'>) {
  const transaction: WalletTransaction = { ...entry, id: `txn-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, createdAt: new Date().toISOString() }
  transactionStore.transactions = [...transactionStore.transactions, transaction]
}

export async function fundWallet(amountNaira: number): Promise<number> {
  await delay(null, 700)
  if (amountNaira <= 0) {
    throw new ApiError('INVALID_AMOUNT', 'Enter an amount greater than ₦0.')
  }
  walletStore.balanceNaira += amountNaira
  addTransaction({ type: 'top-up', amountNaira, description: 'Wallet top-up', status: 'completed' })
  return walletStore.balanceNaira
}

export async function getOwnedGifts(): Promise<{ gift: GiftType; quantity: number }[]> {
  await delay(null, 250)
  return ownedGiftStore.owned
    .map((owned) => ({ gift: GIFT_CATALOG.find((item) => item.id === owned.giftTypeId), quantity: owned.quantity }))
    .filter((item): item is { gift: GiftType; quantity: number } => Boolean(item.gift) && item.quantity > 0)
}

export async function buyGift(giftTypeId: string, quantity = 1): Promise<number> {
  await delay(null, 600)
  const gift = GIFT_CATALOG.find((item) => item.id === giftTypeId)
  if (!gift) throw new ApiError('GIFT_NOT_FOUND', 'That gift is not available.')

  const cost = gift.priceNaira * quantity
  if (walletStore.balanceNaira < cost) {
    throw new ApiError('INSUFFICIENT_BALANCE', 'Fund your wallet to buy this gift.')
  }

  walletStore.balanceNaira -= cost
  addTransaction({ type: 'gift-purchase', amountNaira: -cost, description: `Bought ${quantity}× ${gift.name} ${gift.emoji}`, status: 'completed' })

  const existing = ownedGiftStore.owned.find((item) => item.giftTypeId === giftTypeId)
  const next: OwnedGift[] = existing
    ? ownedGiftStore.owned.map((item) => (item.giftTypeId === giftTypeId ? { ...item, quantity: item.quantity + quantity } : item))
    : [...ownedGiftStore.owned, { giftTypeId, quantity }]
  ownedGiftStore.owned = next

  return walletStore.balanceNaira
}

/**
 * Spends one owned gift to send it to someone else (e.g. a livestream host).
 * This mock only ever has one logged-in account, so there's no other member's
 * wallet to credit — the spend already happened at purchase time; this just
 * decrements the sender's inventory for the chat/gift feed to display.
 */
export async function spendOwnedGift(giftTypeId: string): Promise<GiftType> {
  await delay(null, 300)
  const gift = GIFT_CATALOG.find((item) => item.id === giftTypeId)
  if (!gift) throw new ApiError('GIFT_NOT_FOUND', 'That gift is not available.')

  const owned = ownedGiftStore.owned.find((item) => item.giftTypeId === giftTypeId)
  if (!owned || owned.quantity <= 0) {
    throw new ApiError('GIFT_NOT_OWNED', `You don't have a ${gift.name} to send. Buy one from the gift shop.`)
  }

  ownedGiftStore.owned = ownedGiftStore.owned.map((item) =>
    item.giftTypeId === giftTypeId ? { ...item, quantity: item.quantity - 1 } : item,
  )
  return gift
}

/** Simulates a viewer gifting the signed-in account while they're hosting a stream. */
export function simulateReceivedGift(fromId: string, fromName: string) {
  const gift = GIFT_CATALOG[Math.floor(Math.random() * GIFT_CATALOG.length)]
  const received: ReceivedGift = {
    id: `gift-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    giftTypeId: gift.id,
    fromId,
    fromName,
    valueNaira: gift.priceNaira,
    redeemed: false,
    createdAt: new Date().toISOString(),
  }
  receivedGiftStore.gifts = [received, ...receivedGiftStore.gifts]
  return gift
}

export async function listReceivedGifts(): Promise<ReceivedGift[]> {
  await delay(null, 250)
  return [...receivedGiftStore.gifts].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

export async function redeemGift(giftId: string): Promise<void> {
  await delay(null, 500)
  const gift = receivedGiftStore.gifts.find((item) => item.id === giftId)
  if (!gift || gift.redeemed) return

  receivedGiftStore.gifts = receivedGiftStore.gifts.map((item) => (item.id === giftId ? { ...item, redeemed: true } : item))
  walletStore.balanceNaira += gift.valueNaira
  addTransaction({
    type: 'redemption',
    amountNaira: gift.valueNaira,
    description: `Redeemed ${GIFT_CATALOG.find((item) => item.id === gift.giftTypeId)?.name ?? 'gift'} from ${gift.fromName}`,
    status: 'completed',
  })
}

export async function redeemAllGifts(): Promise<number> {
  await delay(null, 700)
  const unredeemed = receivedGiftStore.gifts.filter((item) => !item.redeemed)
  if (unredeemed.length === 0) return 0

  const total = unredeemed.reduce((sum, item) => sum + item.valueNaira, 0)
  receivedGiftStore.gifts = receivedGiftStore.gifts.map((item) => (item.redeemed ? item : { ...item, redeemed: true }))
  walletStore.balanceNaira += total
  addTransaction({ type: 'redemption', amountNaira: total, description: `Redeemed ${unredeemed.length} gifts`, status: 'completed' })
  return total
}
