import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Landmark } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { formatNaira } from '@/lib/utils'
import { getWalletBalance } from '@/lib/api/wallet'
import { getBankAccount, listPayoutBanks, listPayoutRequests, requestPayout, saveBankAccount } from '@/lib/api/payout'
import { ApiError } from '@/lib/api/types'

export function PayoutPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const { data: balance } = useQuery({ queryKey: ['wallet-balance'], queryFn: getWalletBalance })
  const { data: bankAccount, isLoading: bankLoading } = useQuery({ queryKey: ['bank-account'], queryFn: getBankAccount })
  const { data: payouts, isLoading: payoutsLoading } = useQuery({ queryKey: ['payout-requests'], queryFn: listPayoutRequests })

  const [bankCode, setBankCode] = useState('')
  const [banks, setBanks] = useState<{ code: string; name: string }[]>([])
  const [accountNumber, setAccountNumber] = useState('')
  const [accountName, setAccountName] = useState('')
  const [savingAccount, setSavingAccount] = useState(false)
  const [editingAccount, setEditingAccount] = useState(false)
  const [bankError, setBankError] = useState<string | null>(null)

  const [amount, setAmount] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [payoutError, setPayoutError] = useState<string | null>(null)

  useEffect(() => {
    if (!bankAccount) return
    setAccountNumber('')
    setAccountName(bankAccount.accountName)
  }, [bankAccount])

  useEffect(() => {
    listPayoutBanks().then(setBanks).catch(() => setBanks([]))
  }, [])

  async function handleSaveBank() {
    setBankError(null)
    setSavingAccount(true)
    try {
      await saveBankAccount({ accountNumber, bankCode })
      await queryClient.invalidateQueries({ queryKey: ['bank-account'] })
      setEditingAccount(false)
      showToast({ title: 'Bank account saved', variant: 'success' })
    } catch (err) {
      setBankError(err instanceof ApiError ? err.message : 'Could not save your bank account. Try again.')
    } finally {
      setSavingAccount(false)
    }
  }

  async function handleRequestPayout() {
    setPayoutError(null)
    setRequesting(true)
    try {
      await requestPayout(Number(amount))
      await queryClient.invalidateQueries({ queryKey: ['payout-requests'] })
      await queryClient.invalidateQueries({ queryKey: ['wallet-balance'] })
      await queryClient.invalidateQueries({ queryKey: ['wallet-transactions'] })
      showToast({ title: 'Payout requested', description: "We'll send it to your bank account.", variant: 'success' })
      setAmount('')
    } catch (err) {
      setPayoutError(err instanceof ApiError ? err.message : 'Could not request a payout. Try again.')
    } finally {
      setRequesting(false)
    }
  }

  const showBankForm = editingAccount || (!bankLoading && !bankAccount)

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Link to="/wallet" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Wallet
      </Link>

      <h1 className="mt-4 text-2xl font-bold text-ink-900">Payout</h1>
      <p className="mt-1 text-sm text-ink-500">Withdraw your wallet balance to your bank account.</p>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <Landmark className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Bank account</h2>
        </div>

        {bankLoading ? (
          <PageSpinner label="Loading bank account" />
        ) : showBankForm ? (
          <div className="mt-4 flex flex-col gap-4">
            <Field id="bank-name" label="Bank name">
              <select
                id="bank-name"
                value={bankCode}
                onChange={(event) => {
                  setBankCode(event.target.value)
                }}
                className="h-11 w-full rounded-xl border border-ink-200 bg-white px-3 text-sm text-ink-900"
              >
                <option value="">Select a bank</option>
                {banks.map((bank) => (
                  <option key={bank.code} value={bank.code}>{bank.name}</option>
                ))}
              </select>
            </Field>
            <Field id="account-number" label="Account number">
              <Input
                id="account-number"
                value={accountNumber}
                onChange={(event) => setAccountNumber(event.target.value)}
                inputMode="numeric"
                maxLength={10}
              />
            </Field>
            <Field id="account-name" label="Account name">
              <Input id="account-name" value={accountName} onChange={(event) => setAccountName(event.target.value)} />
            </Field>
            {bankError && <p role="alert" className="text-sm font-medium text-danger">{bankError}</p>}
            <div className="flex gap-3">
              {bankAccount && (
                <Button variant="secondary" className="flex-1" onClick={() => setEditingAccount(false)}>
                  Cancel
                </Button>
              )}
              <Button className="flex-1" loading={savingAccount} onClick={handleSaveBank}>
                Save
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 flex items-center justify-between rounded-2xl bg-ink-50 p-4">
            <div>
              <p className="font-semibold text-ink-900">{bankAccount?.bankName}</p>
              <p className="text-sm text-ink-500">
                {bankAccount?.accountName} · {bankAccount?.accountNumberMasked}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => setEditingAccount(true)}>
              Edit
            </Button>
          </div>
        )}
      </Card>

      <Card className="mt-6">
        <h2 className="text-lg font-bold text-ink-900">Request a payout</h2>
        <p className="mt-1 text-sm text-ink-500">Available balance: {formatNaira(balance ?? 0)}</p>
        <div className="mt-4 flex flex-col gap-4">
          <Field id="payout-amount" label="Amount (₦)">
            <Input id="payout-amount" type="number" min={100} value={amount} onChange={(event) => setAmount(event.target.value)} />
          </Field>
          {payoutError && <p role="alert" className="text-sm font-medium text-danger">{payoutError}</p>}
          <Button loading={requesting} disabled={!amount || Number(amount) <= 0} onClick={handleRequestPayout}>
            Request payout
          </Button>
        </div>
      </Card>

      <div className="mt-8">
        <h2 className="text-lg font-bold text-ink-900">Payout history</h2>
        {payoutsLoading && <PageSpinner label="Loading payouts" />}
        {payouts && payouts.length === 0 && (
          <div className="mt-3">
            <EmptyState title="No payouts yet" description="Requested payouts show up here with their status." />
          </div>
        )}
        {payouts && payouts.length > 0 && (
          <ul className="mt-3 flex flex-col gap-3">
            {payouts.map((payout) => (
              <li key={payout.id} className="flex items-center justify-between rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                <div>
                  <p className="font-semibold text-ink-900">{formatNaira(payout.amountNaira)}</p>
                  <p className="text-xs text-ink-400">{new Date(payout.requestedAt).toLocaleDateString()}</p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    payout.status === 'completed' ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'
                  }`}
                >
                  {payout.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
