import { MapPin, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'

interface LocationAccessDialogProps {
  open: boolean
  locating: boolean
  message: string | null
  onClose: () => void
  onAllow: () => void
  onChooseManually: () => void
}

export function LocationAccessDialog({
  open,
  locating,
  message,
  onClose,
  onAllow,
  onChooseManually,
}: LocationAccessDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Find people near you"
      description="Use your current location to make nearby discovery more accurate."
    >
      <div className="flex flex-col items-center text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-primary-50 text-primary-600">
          <MapPin className="size-8" aria-hidden="true" />
        </span>
        <div className="mt-4 flex items-start gap-2 rounded-2xl bg-ink-50 p-3 text-left">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-primary-600" aria-hidden="true" />
          <p className="text-sm text-ink-600">
            Your exact coordinates stay private. We use them to estimate distance, and you can choose an area instead.
          </p>
        </div>
        <p className="mt-3 text-xs text-ink-400">
          Your browser may ask you to allow location access next.
        </p>
        {message && (
          <p className="mt-3 w-full rounded-xl bg-amber-50 px-3 py-2 text-left text-sm text-amber-800" role="status">
            {message}
          </p>
        )}
        <div className="mt-5 flex w-full flex-col-reverse gap-2 sm:flex-row">
          <Button type="button" variant="outline" className="flex-1" onClick={onChooseManually}>
            Choose an area
          </Button>
          <Button type="button" className="flex-1" loading={locating} onClick={onAllow}>
            {locating ? 'Finding your location…' : 'Allow location'}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
