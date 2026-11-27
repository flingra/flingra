import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { EmptyState, ErrorState } from '@/components/ui/state-message'
import { PageSpinner } from '@/components/ui/spinner'
import { listThreads } from '@/lib/api/chat'

export function MessagesInboxPage() {
  const { data: threads = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['chat-threads'],
    queryFn: listThreads,
  })

  if (isLoading) return <PageSpinner label="Loading messages" />

  return (
    <section className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink-900">Messages</h1>
        <p className="mt-1 text-sm text-ink-500">Your conversations and new connections.</p>
      </header>

      {isError ? (
        <ErrorState
          title="Couldn't load your conversations"
          action={{ label: 'Try again', onClick: () => void refetch() }}
        />
      ) : threads.length === 0 ? (
        <div className="space-y-4">
          <EmptyState
            title="No conversations yet"
            description="When you show interest in someone or they show interest in you, your conversation will appear here."
          />
          <Link
            to="/discover"
            className="mx-auto flex w-fit items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-800"
          >
            Discover people <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      ) : (
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
      )}
    </section>
  )
}
