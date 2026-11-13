import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Radio } from 'lucide-react'
import { Drawer } from '@/components/ui/drawer'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { getOwnProfile } from '@/lib/api/profiles'
import { startStream } from '@/lib/api/livestream'
import { ApiError } from '@/lib/api/types'

export function GoLiveDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [title, setTitle] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: profile } = useQuery({ queryKey: ['own-profile'], queryFn: getOwnProfile, enabled: open, retry: false })
  const restricted = profile && profile.identity !== 'woman'

  async function handleGoLive() {
    setError(null)
    setStarting(true)
    try {
      const stream = await startStream(title)
      onClose()
      setTitle('')
      navigate(`/live/${stream.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start your stream. Try again.')
      showToast({ title: 'Could not go live', variant: 'error' })
    } finally {
      setStarting(false)
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Go live">
      {restricted ? (
        <p className="rounded-2xl bg-ink-100 p-4 text-sm text-ink-700">
          Livestreaming is available for female accounts only. You can still watch, chat, send gifts and request calls on
          other members' streams.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 rounded-2xl bg-primary-50 p-4 text-primary-700">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-100">
              <Radio className="size-5" aria-hidden="true" />
            </span>
            <p className="text-sm">People near you will see your profile picture glow and can tap in to watch.</p>
          </div>

          <Field id="stream-title" label="What's your stream about?" optional>
            <Input
              id="stream-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="e.g. Getting ready for the weekend"
              maxLength={80}
            />
          </Field>

          {error && (
            <p role="alert" className="rounded-xl bg-danger/10 px-4 py-3 text-sm font-medium text-danger">
              {error}
            </p>
          )}

          <Button onClick={handleGoLive} loading={starting} className="bg-danger hover:bg-danger/90">
            <Radio className="size-4" aria-hidden="true" /> Go live
          </Button>
        </div>
      )}
    </Drawer>
  )
}
