import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import { listGiftCatalog, listReceivedGifts, redeemAllGifts, redeemGift } from '@/lib/api/wallet'
import { getBankAccount } from '@/lib/api/payout'

export function RedeemGiftsPage() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const { data: gifts, isLoading } = useQuery({ queryKey: ['received-gifts'], queryFn: listReceivedGifts })
  const { data: bankAccount } = useQuery({ queryKey: ['bank-account'], queryFn: getBankAccount })
  const { data: catalog = [] } = useQuery({ queryKey: ['gift-catalog'], queryFn: listGiftCatalog })

  const unredeemed = gifts?.filter((gift) => !gift.redeemed) ?? []
  const unredeemedTotal = unredeemed.reduce((sum, gift) => sum + gift.valueNaira, 0)

  async function ensureBankAccount() {
    if (bankAccount) return true
    showToast({ title: 'Add a bank account first', description: 'Redeemed gifts pay out to your bank account.', variant: 'info' })
    navigate('/payout')
    return false
  }

  async function handleRedeemOne(id: string) {
    if (!(await ensureBankAccount())) return
    await redeemGift(id)
    await queryClient.invalidateQueries({ queryKey: ['received-gifts'] })
    await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
    await queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] })
    showToast({ title: 'Gift redeemed', description: 'The value was added to your wallet balance.', variant: 'success' })
  }

  async function handleRedeemAll() {
    if (!(await ensureBankAccount())) return
    const total = await redeemAllGifts()
    await queryClient.invalidateQueries({ queryKey: ['received-gifts'] })
    await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
    await queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] })
    showToast({ title: 'Gifts redeemed', description: `${formatNaira(total)} added to your wallet balance.`, variant: 'success' })
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Link to="/wallet" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Wallet
      </Link>

      <h1 className="mt-4 text-2xl font-bold text-ink-900">Redeem gifts</h1>
      <p className="mt-1 text-sm text-ink-500">Trade gifts you've received for cash in your wallet, then withdraw from Payout.</p>

      {isLoading && <PageSpinner label="Loading gifts" />}

      {gifts && gifts.length === 0 && (
        <div className="mt-6">
          <EmptyState title="No gifts yet" description="Gifts sent to you during a livestream show up here." />
        </div>
      )}

      {unredeemed.length > 0 && (
        <div className="mt-6 flex items-center justify-between rounded-2xl bg-primary-50 p-4">
          <p className="text-sm font-semibold text-primary-800">{unredeemed.length} gifts worth {formatNaira(unredeemedTotal)}</p>
          <Button size="sm" onClick={handleRedeemAll}>
            Redeem all
          </Button>
        </div>
      )}

      {gifts && gifts.length > 0 && (
        <ul className="mt-4 flex flex-col gap-3">
          {gifts.map((received) => {
            const gift = catalog.find((item) => item.id === received.giftTypeId)
            return (
              <li key={received.id} className="flex items-center gap-3 rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                <span className="text-2xl">{gift?.emoji}</span>
                <div className="flex-1">
                  <p className="font-semibold text-ink-900">
                    {gift?.name} from {received.fromName}
                  </p>
                  <p className="text-sm text-ink-500">{formatNaira(received.valueNaira)}</p>
                </div>
                {received.redeemed ? (
                  <span className="rounded-full bg-success/10 px-3 py-1 text-xs font-semibold text-success">Redeemed</span>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => handleRedeemOne(received.id)}>
                    Redeem
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
