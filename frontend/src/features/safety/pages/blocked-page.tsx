import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Avatar } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { listBlocked, unblockMember } from '@/lib/api/safety'
import { useToast } from '@/components/ui/toast'
import { useState } from 'react'

export function BlockedPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [pendingId, setPendingId] = useState<string | null>(null)
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ['blocked'], queryFn: listBlocked })

  async function handleUnblock(id: string, name: string) {
    setPendingId(id)
    try {
      await unblockMember(id)
      await queryClient.invalidateQueries({ queryKey: ['blocked'] })
      showToast({ title: `Unblocked ${name}`, variant: 'success' })
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-2xl font-bold text-ink-900">Blocked accounts</h1>
      <p className="mt-1 text-sm text-ink-500">Blocked members can't see your profile or contact you.</p>

      <div className="mt-6">
        {isLoading && <PageSpinner label="Loading blocked accounts" />}
        {isError && <ErrorState title="Couldn't load blocked accounts" action={{ label: 'Retry', onClick: () => refetch() }} />}
        {data && data.length === 0 && (
          <EmptyState title="No blocked accounts" description="Accounts you block will show up here." />
        )}
        {data && data.length > 0 && (
          <ul className="flex flex-col gap-3">
            {data.map((account) => (
              <li key={account.id} className="flex items-center gap-4 rounded-2xl border border-ink-100 bg-white p-4">
                <Avatar name={account.displayName} src={account.photo ?? undefined} />
                <span className="flex-1 font-semibold text-ink-900">{account.displayName}</span>
                <Button
                  variant="outline"
                  size="sm"
                  loading={pendingId === account.id}
                  onClick={() => handleUnblock(account.id, account.displayName)}
                >
                  Unblock
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
