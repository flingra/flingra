import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { cn } from '@/lib/utils'
import { GIFT_CATALOG } from '@/lib/api/wallet'
import type { StreamMessage } from '@/lib/api/types'

export function ChatPanel({
  messages,
  onSend,
  disabled,
  placeholder,
}: {
  messages: StreamMessage[]
  onSend: (text: string) => void
  disabled: boolean
  placeholder: string
}) {
  const [text, setText] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  return (
    <div className="flex w-full max-w-sm flex-col gap-2">
      <div ref={listRef} className="flex max-h-36 flex-col gap-1 overflow-y-auto pr-1">
        {messages.slice(-30).map((message) => {
          const gift = message.kind === 'gift' ? GIFT_CATALOG.find((item) => item.id === message.giftId) : undefined
          return (
            <p key={message.id} className="text-sm leading-snug drop-shadow-sm">
              <span className="font-semibold text-white">{message.authorName}</span>{' '}
              <span className={cn(message.kind === 'gift' ? 'font-semibold text-amber-300' : 'text-white/90')}>
                {gift ? `sent ${gift.emoji} ${gift.name}` : message.text}
              </span>
            </p>
          )
        })}
      </div>
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="max-h-20 flex-1 resize-none rounded-full bg-white/15 px-4 py-2 text-sm text-white placeholder:text-white/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          aria-label="Send message"
          className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-white/20 text-white transition-colors hover:bg-white/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send className="size-4" aria-hidden="true" />
        </button>
      </form>
    </div>
  )
}
