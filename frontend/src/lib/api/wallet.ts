import { delay } from './client'
import {
  GIFT_CATALOG,
  meetupPaymentStore,
  ownedGiftStore,
  ownProfileStore,
  PROFILES,
  receivedGiftStore,
  transactionStore,
  unlockedVideoStore,
  walletStore,
} from './mock-db'
import { ApiError, type GiftType, type MeetupPayment, type OwnedGift, type ReceivedGift, type WalletTransaction } from './types'

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

/**
 * In-person meetup payments. A male member's payment is held in escrow, not
 * credited immediately — it only releases once a meetup is confirmed. This mock
 * only has one real logged-in account, so a payment's "other side" (the recipient
 * crediting her own balance, or the sender releasing/refunding theirs) is modelled
 * from whichever role the signed-in account currently holds on that record.
 */
export async function listMeetupPayments(): Promise<MeetupPayment[]> {
  await delay(null, 300)
  return [...meetupPaymentStore.payments].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

export async function sendMeetupPayment(toId: string, toName: string, amountNaira: number): Promise<MeetupPayment> {
  await delay(null, 600)
  const payer = ownProfileStore.profile
  if (!payer || payer.identity !== 'man') {
    throw new ApiError('PAYER_RESTRICTED', 'Only male accounts can send a meetup payment.')
  }
  const recipient = PROFILES.find((item) => item.id === toId)
  if (!recipient || recipient.identity !== 'woman') {
    throw new ApiError('RECIPIENT_RESTRICTED', 'Meetup payments can only be sent to female members.')
  }
  if (amountNaira <= 0) {
    throw new ApiError('INVALID_AMOUNT', 'Enter an amount greater than ₦0.')
  }
  if (walletStore.balanceNaira < amountNaira) {
    throw new ApiError('INSUFFICIENT_BALANCE', 'Fund your wallet to send this payment.')
  }

  walletStore.balanceNaira -= amountNaira
  const payment: MeetupPayment = {
    id: `meetup-${Date.now()}`,
    fromId: 'me',
    fromName: payer.displayName,
    toId,
    toName,
    amountNaira,
    status: 'held',
    createdAt: new Date().toISOString(),
  }
  meetupPaymentStore.payments = [payment, ...meetupPaymentStore.payments]
  addTransaction({
    type: 'meetup-payment-held',
    amountNaira: -amountNaira,
    description: `₦${amountNaira.toLocaleString('en-NG')} held for meeting ${toName}`,
    status: 'pending',
  })
  return payment
}

/** Releases a held payment once the meetup happened. Either side can confirm. */
export async function confirmMeetupPayment(paymentId: string): Promise<void> {
  await delay(null, 500)
  const payment = meetupPaymentStore.payments.find((item) => item.id === paymentId)
  if (!payment || payment.status !== 'held') return

  meetupPaymentStore.payments = meetupPaymentStore.payments.map((item) =>
    item.id === paymentId ? { ...item, status: 'released', resolvedAt: new Date().toISOString() } : item,
  )

  if (payment.toId === 'me') {
    // We're the recipient: the escrowed amount lands in our own wallet now.
    walletStore.balanceNaira += payment.amountNaira
    addTransaction({
      type: 'meetup-payment-released',
      amountNaira: payment.amountNaira,
      description: `Meetup payment released from ${payment.fromName}`,
      status: 'completed',
    })
  } else {
    addTransaction({
      type: 'meetup-payment-released',
      amountNaira: 0,
      description: `Meetup payment to ${payment.toName} released`,
      status: 'completed',
    })
  }
}

/** Only the payer can request a refund, and only while the payment is still held. */
export async function refundMeetupPayment(paymentId: string): Promise<void> {
  await delay(null, 500)
  const payment = meetupPaymentStore.payments.find((item) => item.id === paymentId)
  if (!payment || payment.status !== 'held' || payment.fromId !== 'me') return

  meetupPaymentStore.payments = meetupPaymentStore.payments.map((item) =>
    item.id === paymentId ? { ...item, status: 'refunded', resolvedAt: new Date().toISOString() } : item,
  )
  walletStore.balanceNaira += payment.amountNaira
  addTransaction({
    type: 'meetup-payment-refunded',
    amountNaira: payment.amountNaira,
    description: `Refunded held payment to ${payment.toName}`,
    status: 'completed',
  })
}

export function isVideoUnlocked(url: string): boolean {
  return unlockedVideoStore.urls.includes(url)
}

export async function unlockVideo(url: string, priceNaira: number, authorName: string): Promise<void> {
  await delay(null, 600)
  if (isVideoUnlocked(url)) return
  if (walletStore.balanceNaira < priceNaira) {
    throw new ApiError('INSUFFICIENT_BALANCE', 'Fund your wallet to unlock this video.')
  }
  walletStore.balanceNaira -= priceNaira
  unlockedVideoStore.urls = [...unlockedVideoStore.urls, url]
  addTransaction({
    type: 'video-unlock',
    amountNaira: -priceNaira,
    description: `Unlocked a video from ${authorName}`,
    status: 'completed',
  })
}
