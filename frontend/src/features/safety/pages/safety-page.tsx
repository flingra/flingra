import { ShieldAlert, UserX, Flag } from 'lucide-react'
import { Card } from '@/components/ui/card'

const SECTIONS = [
  {
    icon: ShieldAlert,
    title: 'Before you meet',
    body: "Video or voice chat first, meet in a public place, tell a friend where you're going, and arrange your own transport to and from the meetup.",
  },
  {
    icon: UserX,
    title: 'Block anyone, anytime',
    body: 'Blocking stops a member from contacting or discovering you. You can manage blocked accounts from Settings › Privacy › Blocked accounts.',
  },
  {
    icon: Flag,
    title: 'Report concerning behaviour',
    body: "Use the Report action on any profile. Our team reviews every report; we don't share who reported an account with the reported member.",
  },
]

export function SafetyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold text-ink-900">Safety guidance</h1>
      <p className="mt-2 text-ink-500">
        Flingra can't guarantee the outcome of any meetup. These practices lower your risk when meeting
        someone you've connected with online.
      </p>

      <div className="mt-8 flex flex-col gap-4">
        {SECTIONS.map(({ icon: Icon, title, body }) => (
          <Card key={title} className="flex items-start gap-4">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-lg font-bold text-ink-900">{title}</h2>
              <p className="mt-1.5 text-ink-700">{body}</p>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
