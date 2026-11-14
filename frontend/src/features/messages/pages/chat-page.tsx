import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, Loader2, Paperclip, Send } from 'lucide-react'
import { Avatar } from '@/components/ui/avatar'
import { PageSpinner } from '@/components/ui/spinner'
import { ErrorState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import { listMessages, listThreads, sendMessage, simulateReply, uploadChatAttachment } from '@/lib/api/chat'
import { ApiError } from '@/lib/api/types'
import { cn } from '@/lib/utils'

export function ChatPage() {
  const { threadId = '' } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [uploadingAttachment, setUploadingAttachment] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const repliedRef = useRef(false)

  const { data: threads, isLoading: threadsLoading } = useQuery({ queryKey: ['chat-threads'], queryFn: listThreads })
  const thread = threads?.find((item) => item.id === threadId)

  const { data: messages = [] } = useQuery({
    queryKey: ['chat-messages', threadId],
    queryFn: () => listMessages(threadId),
    enabled: !!thread,
    refetchInterval: 2000,
  })

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length])

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ['chat-messages', threadId] })
    await queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
  }

  // Scheduled once, right after the first message goes out, rather than reactively off
  // query state — react-query gives the thread object a new reference on every refetch,
  // which would otherwise cancel-and-reschedule (or silently drop) this timer.
  function maybeScheduleReply(otherId: string) {
    if (repliedRef.current) return
    repliedRef.current = true
    setTimeout(() => {
      simulateReply(threadId, otherId)
      queryClient.invalidateQueries({ queryKey: ['chat-messages', threadId] })
      queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
    }, 2500)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!text.trim() || sending || !thread) return
    setSending(true)
    try {
      await sendMessage(threadId, text.trim())
      setText('')
      await refresh()
      maybeScheduleReply(thread.otherId)
    } finally {
      setSending(false)
    }
  }

  async function handleAttachment(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file || !thread) return
    setUploadingAttachment(true)
    try {
      const attachment = await uploadChatAttachment(file)
      await sendMessage(threadId, text.trim(), attachment)
      setText('')
      await refresh()
      maybeScheduleReply(thread.otherId)
    } catch (error) {
      showToast({
        title: "Couldn't send attachment",
        description: error instanceof ApiError ? error.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setUploadingAttachment(false)
      event.target.value = ''
    }
  }

  if (threadsLoading) return <PageSpinner label="Loading chat" />
  if (!thread) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <ErrorState title="Conversation unavailable" description="This chat may have ended or doesn't exist." />
      </div>
    )
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-4rem-7rem)] max-w-2xl flex-col px-4 sm:px-6">
      <div className="flex items-center gap-3 border-b border-ink-100 py-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Back"
          className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full text-ink-600 hover:bg-ink-100"
        >
          <ArrowLeft className="size-4.5" aria-hidden="true" />
        </button>
        <Avatar name={thread.otherName} src={thread.otherPhoto} size="md" />
        <p className="truncate font-bold text-ink-900">{thread.otherName}</p>
      </div>

      <div ref={listRef} className="flex flex-1 flex-col gap-2 overflow-y-auto py-4">
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
            <Avatar name={thread.otherName} src={thread.otherPhoto} size="lg" />
            <p className="text-sm text-ink-500">Say hi to {thread.otherName} to start the conversation.</p>
          </div>
        ) : (
          messages.map((message) => {
            const fromOther = message.authorId === thread.otherId
            return (
              <div key={message.id} className={cn('flex max-w-[75%] flex-col gap-1', fromOther ? 'self-start items-start' : 'self-end items-end')}>
                {message.attachment &&
                  (message.attachment.type === 'image' ? (
                    <img
                      src={message.attachment.url}
                      alt={message.attachment.name}
                      className="max-h-64 rounded-2xl border border-ink-100 object-cover"
                    />
                  ) : message.attachment.type === 'video' ? (
                    // eslint-disable-next-line jsx-a11y/media-has-caption
                    <video src={message.attachment.url} controls className="max-h-64 rounded-2xl border border-ink-100" />
                  ) : (
                    <a
                      href={message.attachment.url}
                      download={message.attachment.name}
                      className="flex items-center gap-2 rounded-2xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm font-medium text-ink-700 hover:bg-ink-50"
                    >
                      <FileText className="size-4 shrink-0" aria-hidden="true" />
                      <span className="truncate">{message.attachment.name}</span>
                    </a>
                  ))}
                {message.text && (
                  <div
                    className={cn(
                      'rounded-2xl px-3.5 py-2 text-sm',
                      fromOther ? 'bg-ink-100 text-ink-800' : 'bg-primary-500 text-white',
                    )}
                  >
                    {message.text}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      <div className="border-t border-ink-100 pb-3 pt-3">
        <p className="pb-2 text-center text-xs text-ink-400">
          Keep the conversation on Flingra. For your safety, avoid sharing contact details.
        </p>
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,video/*,.pdf,.doc,.docx"
            className="sr-only"
            onChange={handleAttachment}
            disabled={uploadingAttachment}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadingAttachment}
            aria-label="Attach a file"
            className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-ink-100 text-ink-600 transition-colors hover:bg-ink-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploadingAttachment ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Paperclip className="size-4" aria-hidden="true" />}
          </button>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Type a message..."
            className="h-12 flex-1 rounded-full border border-transparent bg-ink-50 px-4 text-base text-ink-900 placeholder:text-ink-400 focus-visible:border-primary-400 focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200"
          />
          <button
            type="submit"
            disabled={!text.trim() || sending}
            aria-label="Send message"
            className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary-500 text-white transition-colors hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="size-4" aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  )
}
