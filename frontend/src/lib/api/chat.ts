import { apiRequest, ensureCsrfHeaders, uploadFile } from './client'
import { type ChatAttachment, type ChatThread, type DirectMessage, type MeetupPayment } from './types'

export async function getOrCreateThread(otherId: string, _otherName: string, _otherPhoto: string): Promise<ChatThread> {
  return apiRequest<ChatThread>('/chat/threads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ otherId }),
  })
}

export async function listThreads(): Promise<ChatThread[]> {
  return apiRequest<ChatThread[]>('/chat/threads')
}

export async function listMessages(threadId: string): Promise<DirectMessage[]> {
  return apiRequest<DirectMessage[]>(`/chat/threads/${encodeURIComponent(threadId)}/messages`)
}

export async function uploadChatAttachment(file: File): Promise<ChatAttachment> {
  return uploadFile<ChatAttachment>('/chat/attachments', file)
}

export async function sendMessage(threadId: string, text: string, attachment?: ChatAttachment): Promise<void> {
  await apiRequest<DirectMessage>(`/chat/threads/${encodeURIComponent(threadId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ text: text || undefined, attachment }),
  })
}

/** Proposes a meetup payment right in the conversation, so the agreement has a visible paper trail. */
export async function proposePaymentInChat(
  threadId: string,
  _otherId: string,
  _otherName: string,
  amountNaira: number,
): Promise<MeetupPayment> {
  return apiRequest<MeetupPayment>(`/chat/threads/${encodeURIComponent(threadId)}/payment-proposals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ amountNaira }),
  })
}
