import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { Drawer } from '@/components/ui/drawer'
import { Avatar } from '@/components/ui/avatar'
import { listMessages, sendMessage, simulateReply } from '@/lib/api/chat'

export function ChatDrawer({
  open,
  onClose,
  threadId,
  otherId,
  otherName,
  otherPhoto,
}: {
  open: boolean
  onClose: () => void
  threadId: string
  otherId: string
  otherName: string
  otherPhoto?: string
}) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const repliedRef = useRef(false)

  const { data: messages = [] } = useQuery({
    queryKey: ['chat-messages', threadId],
    queryFn: () => listMessages(threadId),
    enabled: open,
    refetchInterval: open ? 2000 : false,
  })

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length])

  useEffect(() => {
    if (!open || repliedRef.current || messages.length === 0) return
    repliedRef.current = true
    const timer = setTimeout(() => {
      simulateReply(threadId, otherId)
      queryClient.invalidateQueries({ queryKey: ['chat-messages', threadId] })
    }, 2500)
    return () => clearTimeout(timer)
  }, [open, messages.length, threadId, otherId, queryClient])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!text.trim() || sending) return
    setSending(true)
    try {
      await sendMessage(threadId, text.trim())
      setText('')
      await queryClient.invalidateQueries({ queryKey: ['chat-messages', threadId] })
    } finally {
      setSending(false)
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title={`Chat with ${otherName}`}>
      <div className="flex flex-col gap-4">
        <div ref={listRef} className="flex max-h-80 min-h-40 flex-col gap-2 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 py-8 text-center">
              <Avatar name={otherName} src={otherPhoto} size="lg" />
              <p className="text-sm text-ink-500">Say hi to {otherName} to start the conversation.</p>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${
                  message.authorId === otherId
                    ? 'self-start bg-ink-100 text-ink-800'
                    : 'self-end bg-primary-500 text-white'
                }`}
              >
                {message.text}
              </div>
            ))
          )}
        </div>
        <p className="text-center text-xs text-ink-400">
          Keep the conversation on Flingra. For your safety, avoid sharing contact details.
        </p>
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
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
    </Drawer>
  )
}
