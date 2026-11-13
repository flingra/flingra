import { delay } from './client'
import { chatThreadStore, directMessageStore, ownProfileStore } from './mock-db'
import type { ChatThread, DirectMessage } from './types'

export async function getOrCreateThread(otherId: string, otherName: string, otherPhoto: string): Promise<ChatThread> {
  await delay(null, 300)
  const existing = chatThreadStore.threads.find((thread) => thread.otherId === otherId)
  if (existing) return existing

  const thread: ChatThread = {
    id: `thread-${otherId}`,
    otherId,
    otherName,
    otherPhoto,
    lastMessage: '',
    lastMessageAt: new Date().toISOString(),
  }
  chatThreadStore.threads = [thread, ...chatThreadStore.threads]
  return thread
}

export async function listThreads(): Promise<ChatThread[]> {
  await delay(null, 300)
  return [...chatThreadStore.threads].sort((a, b) => b.lastMessageAt.localeCompare(a.lastMessageAt))
}

export async function listMessages(threadId: string): Promise<DirectMessage[]> {
  await delay(null, 200)
  return directMessageStore.messages.filter((message) => message.threadId === threadId)
}

function touchThread(threadId: string, lastMessage: string) {
  chatThreadStore.threads = chatThreadStore.threads.map((thread) =>
    thread.id === threadId ? { ...thread, lastMessage, lastMessageAt: new Date().toISOString() } : thread,
  )
}

export async function sendMessage(threadId: string, text: string): Promise<void> {
  await delay(undefined, 200)
  const profile = ownProfileStore.profile
  const message: DirectMessage = {
    id: `dm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    threadId,
    authorId: profile?.id ?? 'me',
    text,
    createdAt: new Date().toISOString(),
  }
  directMessageStore.messages = [...directMessageStore.messages, message]
  touchThread(threadId, text)
}

const AUTO_REPLIES = [
  "Hey! Thanks for your interest — how's your day going?",
  "Nice to hear from you! What are you up to this weekend?",
  "I saw your profile, we seem to have a lot in common!",
  'Haha, true. So what do you do for fun around here?',
]

/** Simulates the other member replying, since there's no second real account in this session. */
export function simulateReply(threadId: string, otherId: string) {
  const message: DirectMessage = {
    id: `dm-sim-${Date.now()}`,
    threadId,
    authorId: otherId,
    text: AUTO_REPLIES[Math.floor(Math.random() * AUTO_REPLIES.length)],
    createdAt: new Date().toISOString(),
  }
  directMessageStore.messages = [...directMessageStore.messages, message]
  touchThread(threadId, message.text)
}
