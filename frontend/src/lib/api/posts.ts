import { delay } from './client'
import { postStore } from './mock-db'
import { ApiError, type Post } from './types'

export interface CreatePostInput {
  photos: string[]
  video?: string
  caption?: string
}

export async function createPost(input: CreatePostInput): Promise<Post> {
  await delay(null, 700)
  const hasEnoughPhotos = input.photos.length >= 3
  const hasVideo = Boolean(input.video)
  if (!hasEnoughPhotos && !hasVideo) {
    throw new ApiError('POST_MEDIA_REQUIRED', 'Add at least 3 photos or 1 video to post.')
  }

  const post: Post = {
    id: `post-${Date.now()}`,
    authorId: 'me',
    photos: input.photos,
    video: input.video,
    caption: input.caption,
    createdAt: new Date().toISOString(),
  }
  postStore.posts = [post, ...postStore.posts]
  return post
}

export async function listMyPosts(): Promise<Post[]> {
  await delay(null, 400)
  return postStore.posts
}

export async function deletePost(id: string): Promise<void> {
  await delay(undefined, 400)
  postStore.posts = postStore.posts.filter((post) => post.id !== id)
}
