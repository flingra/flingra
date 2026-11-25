import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Coins } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import { getCoinPriceNaira, listCoinPackages, setCoinPriceNaira } from '@/lib/api/calls'
import { ApiError } from '@/lib/api/types'

/** Super-admin only — gated by `AdminRoute`/role at the route level, same as the Admins page. */
export function AdminCoinPricingPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [price, setPrice] = useState('')
  const [saving, setSaving] = useState(false)

  const { data: currentPrice } = useQuery({ queryKey: ['coin-price'], queryFn: getCoinPriceNaira })
  const { data: packages } = useQuery({ queryKey: ['coin-packages'], queryFn: listCoinPackages })

  async function handleSave() {
    setSaving(true)
    try {
      await setCoinPriceNaira(Number(price))
      await queryClient.invalidateQueries({ queryKey: ['coin-price'] })
      await queryClient.invalidateQueries({ queryKey: ['coin-packages'] })
      showToast({ title: 'Coin price updated', variant: 'success' })
      setPrice('')
    } catch (err) {
      showToast({
        title: 'Could not update coin price',
        description: err instanceof ApiError ? err.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section>
      <h1 className="mb-2 text-3xl font-bold">Call credit coin pricing</h1>
      <p className="mb-6 text-sm text-ink-500">Sets the ₦ price of one call-credit coin (one started call minute), store-wide.</p>

      <Card className="mb-6 flex items-center gap-3">
        <Coins className="size-6 text-primary-500" aria-hidden="true" />
        <p className="text-sm font-semibold text-ink-900">Current price: {formatNaira(currentPrice ?? 0)} per coin</p>
      </Card>

      <Card>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:gap-3">
          <Field id="coin-price" label="New price per coin (₦)" className="flex-1">
            <Input id="coin-price" type="number" min={1} value={price} onChange={(event) => setPrice(event.target.value)} />
          </Field>
          <Button loading={saving} disabled={!price || Number(price) <= 0} onClick={handleSave}>
            Save price
          </Button>
        </div>
      </Card>

      {packages && packages.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-1 text-lg font-bold text-ink-900">Store preview</h2>
          <p className="mb-3 text-sm text-ink-500">What buyers will see in the call credit store at this price.</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {packages.map((pkg) => (
              <Card key={pkg.coins} className="text-center">
                <p className="font-semibold text-ink-900">{pkg.coins} minutes</p>
                <p className="text-sm text-ink-500">{formatNaira(pkg.priceNaira)}</p>
              </Card>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
