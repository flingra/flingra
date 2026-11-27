import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { PageSpinner } from '@/components/ui/spinner'
import { useToast } from '@/components/ui/toast'
import {
  acceptInterestRequest,
  declineInterestRequest,
  listIncomingInterestRequests,
  listThreads,
} from '@/lib/api/chat'
import { ApiError } from '@/lib/api/types'

export function MessagesInboxPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [responding, setResponding] = useState<{ id: string; action: 'accept' | 'decline' } | null>(null)
  const {
    data: threads = [],
    isLoading: threadsLoading,
    isError: threadsError,
    refetch: refetchThreads,
  } = useQuery({
    queryKey: ['chat-threads'],
    queryFn: listThreads,
  })
  const {
    data: incomingRequests = [],
    isLoading: requestsLoading,
    isError: requestsError,
    refetch: refetchRequests,
  } = useQuery({
    queryKey: ['chat-interests'],
    queryFn: listIncomingInterestRequests,
  })

  async function handleInterestResponse(interestId: string, action: 'accept' | 'decline') {
    setResponding({ id: interestId, action })
    try {
      if (action === 'accept') {
        await acceptInterestRequest(interestId)
        showToast({ title: 'Interest accepted', description: 'You can now chat with this person.', variant: 'success' })
      } else {
        await declineInterestRequest(interestId)
        showToast({ title: 'Interest declined', variant: 'info' })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['chat-interests'] }),
        queryClient.invalidateQueries({ queryKey: ['chat-threads'] }),
      ])
    } catch (error) {
      showToast({
        title: action === 'accept' ? 'Could not accept interest' : 'Could not decline interest',
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setResponding(null)
    }
  }

  if (threadsLoading || requestsLoading) return <PageSpinner label="Loading messages" />

  return (
    <section className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink-900">Messages</h1>
        <p className="mt-1 text-sm text-ink-500">Your conversations and new connections.</p>
      </header>

      {requestsError && (
        <div className="mb-6">
          <ErrorState
            title="Couldn't load interest requests"
            action={{ label: 'Try again', onClick: () => void refetchRequests() }}
          />
        </div>
      )}

      {incomingRequests.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-bold text-ink-900">Interest requests</h2>
          <div className="divide-y divide-ink-100 overflow-hidden rounded-2xl border border-ink-100 bg-white">
            {incomingRequests.map((request) => {
              const isResponding = responding?.id === request.id
              const isBusy = responding !== null
              const date = new Date(request.createdAt)
              const dateLabel = Number.isNaN(date.getTime())
                ? ''
                : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

              return (
                <article key={request.id} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center">
                  <Avatar name={request.senderName} src={request.senderPhoto} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-semibold text-ink-900">{request.senderName} is interested in you</p>
                      {dateLabel && <span className="shrink-0 text-xs text-ink-400">{dateLabel}</span>}
                    </div>
                    <p className="mt-1 text-sm text-ink-500">Accept to start a conversation. You can decline if you’re not interested.</p>
                  </div>
                  <div className="flex gap-2 sm:shrink-0">
                    <Button
                      size="sm"
                      loading={isResponding && responding?.action === 'accept'}
                      disabled={isBusy}
                      onClick={() => void handleInterestResponse(request.id, 'accept')}
                    >
                      Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      loading={isResponding && responding?.action === 'decline'}
                      disabled={isBusy}
                      onClick={() => void handleInterestResponse(request.id, 'decline')}
                    >
                      Decline
                    </Button>
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      )}

      {threadsError ? (
        <ErrorState
          title="Couldn't load your conversations"
          action={{ label: 'Try again', onClick: () => void refetchThreads() }}
        />
      ) : threads.length === 0 && incomingRequests.length === 0 && !requestsError ? (
        <div className="space-y-4">
          <EmptyState
            title="No conversations yet"
            description="When an interest request is accepted, the conversation will appear here."
          />
          <Link
            to="/discover"
            className="mx-auto flex w-fit items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-800"
          >
            Discover people <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      ) : threads.length > 0 ? (
        <div className="divide-y divide-ink-100 overflow-hidden rounded-2xl border border-ink-100 bg-white">
          {threads.map((thread) => {
            const timestamp = new Date(thread.lastMessageAt)
            const dateLabel = Number.isNaN(timestamp.getTime())
              ? ''
              : timestamp.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

            return (
              <Link
                key={thread.id}
                to={`/messages/${encodeURIComponent(thread.id)}`}
                aria-label={`Open conversation with ${thread.otherName}`}
                className="flex items-center gap-3 px-4 py-4 transition-colors hover:bg-ink-50"
              >
                <Avatar name={thread.otherName} src={thread.otherPhoto} size="md" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-semibold text-ink-900">{thread.otherName}</span>
                    {dateLabel && <span className="shrink-0 text-xs text-ink-400">{dateLabel}</span>}
                  </span>
                  <span className="mt-1 block truncate text-sm text-ink-500">
                    {thread.lastMessage || 'Conversation started'}
                  </span>
                </span>
              </Link>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}
