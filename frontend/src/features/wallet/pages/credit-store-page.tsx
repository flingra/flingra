import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Coins, PhoneCall } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import { getOwnProfile } from '@/lib/api/profiles'
import { buyCallCredits, getCallCreditBalance, listCoinPackages } from '@/lib/api/calls'
import { getWalletBalance } from '@/lib/api/wallet'
import { ApiError } from '@/lib/api/types'

export function CreditStorePage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const { data: ownProfile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, retry: false })
  const { data: packages } = useQuery({ queryKey: ['coin-packages'], queryFn: listCoinPackages })
  const { data: credits } = useQuery({ queryKey: ['call-credits'], queryFn: getCallCreditBalance })
  const { data: walletBalance } = useQuery({ queryKey: ['wallet-balance'], queryFn: getWalletBalance })

  const canBuy = ownProfile?.identity === 'man'

  async function handleBuy(coins: number) {
    try {
      await buyCallCredits(coins)
      await queryClient.invalidateQueries({ queryKey: ['call-credits'] })
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      showToast({ title: `Bought ${coins} call credit coins`, variant: 'success' })
    } catch (err) {
      showToast({
        title: 'Could not buy call credits',
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
        <h1 className="text-2xl font-bold text-ink-900">Call credits</h1>
        <p className="flex items-center gap-1.5 text-sm font-semibold text-ink-700">
          <Coins className="size-4 text-primary-500" aria-hidden="true" /> {credits ?? 0} coins
        </p>
      </div>
      <p className="mt-1 text-sm text-ink-500">
        <PhoneCall className="mr-1 inline size-3.5" aria-hidden="true" />
        Each coin covers one started minute of voice or video calls. Choose a 10, 15, or 30-minute pack and pay using your wallet balance
        ({formatNaira(walletBalance ?? 0)} available).
      </p>

      {!canBuy && (
        <div className="mt-6 rounded-2xl bg-ink-50 p-4 text-sm text-ink-600">
          Call credits are bought by male accounts to call female members. Women call for free.
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {packages?.map((pkg) => (
          <div key={pkg.coins} className="flex flex-col items-center gap-2 rounded-3xl border border-ink-100 bg-white p-5 text-center shadow-soft">
            <Coins className="size-7 text-primary-500" aria-hidden="true" />
            <p className="font-semibold text-ink-900">{pkg.coins} minutes</p>
            <p className="text-sm text-ink-500">{formatNaira(pkg.priceNaira)}</p>
            <Button size="sm" className="mt-1 w-full" disabled={!canBuy} onClick={() => handleBuy(pkg.coins)}>
              Buy
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
