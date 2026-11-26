import { apiRequest, ensureCsrfHeaders } from './client'
import { type Post } from './types'

export interface CreatePostInput {
  photos: string[]
  video?: string
  caption?: string
}

export async function createPost(input: CreatePostInput): Promise<Post> {
  return apiRequest<Post>('/posts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await ensureCsrfHeaders()) },
    body: JSON.stringify({ photos: input.photos, video: input.video ?? null, caption: input.caption }),
  })
}

export async function listMyPosts(): Promise<Post[]> {
  return apiRequest<Post[]>('/posts/me')
}

export async function deletePost(id: string): Promise<void> {
  await apiRequest<void>(`/posts/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: await ensureCsrfHeaders(),
  })
}
