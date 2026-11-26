import { apiRequest, ensureCsrfHeaders } from './client'
import { type GiftType, type MeetupPayment, type OwnedGift, type ReceivedGift, type WalletTransaction } from './types'

export const GIFT_CATALOG: GiftType[] = []

export async function getWalletBalance(): Promise<number> {
  const result = await apiRequest<{ balanceNaira: number }>('/wallet/balance')
  return result.balanceNaira
}

export async function listTransactions(): Promise<WalletTransaction[]> {
  return apiRequest<WalletTransaction[]>('/wallet/transactions')
}

export async function fundWallet(amountNaira: number): Promise<{ reference: string; authorizationUrl: string; amountNaira: number }> {
  return apiRequest('/wallet/top-ups', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ amountNaira }),
  })
}

export async function verifyWalletTopUp(reference: string): Promise<{ status: 'pending' | 'success'; reference: string; balanceNaira?: number }> {
  return apiRequest('/wallet/top-ups/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ reference }),
  })
}

export async function listGiftCatalog(): Promise<GiftType[]> {
  return apiRequest<GiftType[]>('/wallet/gifts/catalog')
}

export async function getOwnedGifts(): Promise<{ gift: GiftType; quantity: number }[]> {
  const [catalog, owned] = await Promise.all([
    listGiftCatalog(),
    apiRequest<OwnedGift[]>('/wallet/gifts/owned'),
  ])
  return owned
    .map((item) => ({ gift: catalog.find((gift) => gift.id === item.giftTypeId), quantity: item.quantity }))
    .filter((item): item is { gift: GiftType; quantity: number } => Boolean(item.gift) && item.quantity > 0)
}

export async function buyGift(giftTypeId: string, quantity = 1): Promise<number> {
  const result = await apiRequest<{ balanceNaira: number }>('/wallet/gifts/buy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ giftTypeId, quantity }),
  })
  return result.balanceNaira
}

export async function spendOwnedGift(giftTypeId: string, recipientId: string): Promise<GiftType> {
  const result = await apiRequest<{ giftId: string; name: string; emoji: string }>(`/wallet/gifts/${encodeURIComponent(giftTypeId)}/spend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ recipientId }),
  })
  return { id: result.giftId, name: result.name, emoji: result.emoji, priceNaira: 0 }
}

export async function listReceivedGifts(): Promise<ReceivedGift[]> {
  return apiRequest<ReceivedGift[]>('/wallet/gifts/received')
}

export async function redeemGift(giftId: string): Promise<void> {
  await apiRequest<void>(`/wallet/gifts/${encodeURIComponent(giftId)}/redeem`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function redeemAllGifts(): Promise<number> {
  const result = await apiRequest<{ amountNaira: number }>('/wallet/gifts/redeem-all', {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
  return result.amountNaira
}

export async function listMeetupPayments(): Promise<MeetupPayment[]> {
  return []
}

export async function proposeMeetupPayment(_toId: string, _toName: string, _amountNaira: number): Promise<MeetupPayment> {
  throw new Error('Meetup proposals must be created through a chat thread.')
}

export async function getMeetupPayment(paymentId: string): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}`)
}

export async function acceptMeetupPayment(paymentId: string): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}/accept`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function declineMeetupPayment(paymentId: string): Promise<void> {
  await apiRequest<void>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}/decline`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function confirmMeetupPayment(paymentId: string): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}/release`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function refundMeetupPayment(paymentId: string): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}/refund`, {
    method: 'POST',
    headers: await ensureCsrfHeaders(),
  })
}

export async function disputeMeetupPayment(paymentId: string, reason: string): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/meetup-payments/${encodeURIComponent(paymentId)}/disputes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ reason }),
  })
}

export async function unlockVideo(url: string): Promise<{ url: string; unlocked: boolean; priceNaira: number }> {
  return apiRequest('/videos/unlock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ url }),
  })
}

export function isVideoUnlocked(_url: string): boolean {
  return false
}
