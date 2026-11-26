import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import { buyGift, getOwnedGifts, getWalletBalance, listGiftCatalog } from '@/lib/api/wallet'
import { ApiError } from '@/lib/api/types'

export function GiftShopPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const { data: balance } = useQuery({ queryKey: ['wallet-balance'], queryFn: getWalletBalance })
  const { data: owned } = useQuery({ queryKey: ['owned-gifts'], queryFn: getOwnedGifts })
  const { data: gifts = [] } = useQuery({ queryKey: ['gift-catalog'], queryFn: listGiftCatalog })

  async function handleBuy(giftTypeId: string) {
    try {
      await buyGift(giftTypeId, 1)
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      await queryClient.invalidateQueries({ queryKey: ['owned-gifts'] })
      showToast({ title: 'Gift purchased', variant: 'success' })
    } catch (err) {
      showToast({
        title: 'Could not buy gift',
        description: err instanceof ApiError ? err.message : 'Try again.',
        variant: 'error',
      })
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Link to="/wallet" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Wallet
      </Link>

      <div className="mt-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-ink-900">Gift shop</h1>
        <p className="text-sm font-semibold text-ink-700">Balance: {formatNaira(balance ?? 0)}</p>
      </div>
      <p className="mt-1 text-sm text-ink-500">Buy gifts here, then send them on a livestream or in chat.</p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {gifts.map((gift) => (
          <div key={gift.id} className="flex flex-col items-center gap-2 rounded-3xl border border-ink-100 bg-white p-5 text-center shadow-soft">
            <span className="text-4xl">{gift.emoji}</span>
            <p className="font-semibold text-ink-900">{gift.name}</p>
            <p className="text-sm text-ink-500">{formatNaira(gift.priceNaira)}</p>
            <Button size="sm" className="mt-1 w-full" onClick={() => handleBuy(gift.id)}>
              Buy
            </Button>
          </div>
        ))}
      </div>

      {owned && owned.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-bold text-ink-900">My gifts</h2>
          <div className="mt-3 flex flex-wrap gap-3">
            {owned.map(({ gift, quantity }) => (
              <div key={gift.id} className="flex items-center gap-2 rounded-full border border-ink-100 bg-white px-4 py-2 shadow-soft">
                <span className="text-xl">{gift.emoji}</span>
                <span className="text-sm font-semibold text-ink-800">
                  {gift.name} × {quantity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
