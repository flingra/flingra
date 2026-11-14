import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ChevronRight,
  Eye,
  Flag,
  LifeBuoy,
  PhoneCall,
  ShieldAlert,
  ShieldOff,
  Siren,
  UserX,
} from 'lucide-react'
import { Card } from '@/components/ui/card'

const QUICK_LINKS = [
  { to: '/safety/emergency-contacts', icon: Siren, label: 'Emergency contacts', description: 'Add trusted contacts, alert them instantly' },
  { to: '/blocked', icon: ShieldOff, label: 'Blocked accounts', description: 'See and manage who you have blocked' },
  { to: '/help', icon: LifeBuoy, label: 'Help & support', description: 'Contact the Flingra team' },
]

const BEFORE_YOU_MEET = [
  {
    icon: ShieldAlert,
    title: 'Get to know them first',
    body: 'Video or voice chat before meeting. A reluctance to call or show their face, especially after a verified profile, is worth noticing on its own.',
  },
  {
    icon: Eye,
    title: 'Meet in public, first time',
    body: "Choose a busy, public place for at least your first meetup. Don't give out your home address until you trust someone.",
  },
  {
    icon: PhoneCall,
    title: 'Tell someone your plan',
    body: 'Share who you\'re meeting, where, and when with a friend or your emergency contacts. Arrange your own transport both ways.',
  },
]

const DURING_YOUR_MEETUP = [
  'Keep your phone charged and on you. Share your live location with a trusted contact if you can.',
  "Stay sober enough to make good decisions. It's harder to notice red flags, or leave, if you're impaired.",
  'Trust your instincts. If something feels off, you can leave at any time — you never owe anyone an explanation.',
  'Keep your own transport and money on you. Never rely on the other person to get you home.',
]

const RED_FLAGS = [
  'Asks for money, gifts, or your financial details early on.',
  'Avoids video or voice calls, or every excuse not to meet in public.',
  "Pressures you to move off Flingra quickly, or to meet alone somewhere private right away.",
  'Stories that don\'t add up, or photos that look inconsistent with how they talk or write.',
  'Gets angry, guilt-trips you, or pushes back hard when you set a boundary.',
]

export function SafetyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold text-ink-900">Safety guidance</h1>
      <p className="mt-2 text-ink-500">
        Flingra can't guarantee the outcome of any meetup. These practices, and the tools below, lower your risk
        when meeting someone you've connected with online.
      </p>

      <div className="mt-6 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
        {QUICK_LINKS.map(({ to, icon: Icon, label, description }, index) => (
          <Link
            key={to}
            to={to}
            className={`flex items-center gap-3 px-5 py-4 transition-colors hover:bg-ink-50 ${
              index < QUICK_LINKS.length - 1 ? 'border-b border-ink-100' : ''
            }`}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-ink-800">{label}</span>
              <span className="block truncate text-xs text-ink-500">{description}</span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-ink-300" aria-hidden="true" />
          </Link>
        ))}
      </div>

      <h2 className="mt-10 text-xl font-bold text-ink-900">Before you meet</h2>
      <div className="mt-4 flex flex-col gap-4">
        {BEFORE_YOU_MEET.map(({ icon: Icon, title, body }) => (
          <Card key={title} className="flex items-start gap-4">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="text-lg font-bold text-ink-900">{title}</h3>
              <p className="mt-1.5 text-ink-700">{body}</p>
            </div>
          </Card>
        ))}
      </div>

      <h2 className="mt-10 text-xl font-bold text-ink-900">During your meetup</h2>
      <Card className="mt-4">
        <ul className="flex flex-col gap-3">
          {DURING_YOUR_MEETUP.map((item) => (
            <li key={item} className="flex gap-3 text-ink-700">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary-500" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </Card>

      <h2 className="mt-10 text-xl font-bold text-ink-900">Red flags to watch for</h2>
      <Card className="mt-4 border-warning/30 bg-warning/5">
        <ul className="flex flex-col gap-3">
          {RED_FLAGS.map((item) => (
            <li key={item} className="flex gap-3 text-ink-700">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </Card>

      <h2 className="mt-10 text-xl font-bold text-ink-900">Block and report</h2>
      <div className="mt-4 flex flex-col gap-4">
        <Card className="flex items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <UserX className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-bold text-ink-900">Block anyone, anytime</h3>
            <p className="mt-1.5 text-ink-700">
              Blocking stops a member from contacting or discovering you immediately, and files a report with our
              safety team for review. Manage blocked accounts from{' '}
              <Link to="/blocked" className="font-semibold text-primary-600 hover:underline">
                Blocked accounts
              </Link>
              .
            </p>
          </div>
        </Card>
        <Card className="flex items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <Flag className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-bold text-ink-900">Report concerning behaviour</h3>
            <p className="mt-1.5 text-ink-700">
              Use the Report action on any profile. Our team reviews every report and investigates before taking
              action, which can include banning the account. We never share who reported someone with the reported
              member.
            </p>
          </div>
        </Card>
      </div>

      <h2 className="mt-10 text-xl font-bold text-ink-900">If something goes wrong</h2>
      <Card className="mt-4 border-danger/20 bg-danger/5">
        <div className="flex items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-danger text-white">
            <Siren className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-bold text-ink-900">You're not alone</h3>
            <p className="mt-1.5 text-ink-700">
              If you're in immediate danger, call <span className="font-semibold">112</span>, Nigeria's national
              emergency number, or your local emergency services first. Afterwards, use{' '}
              <Link to="/safety/emergency-contacts" className="font-semibold text-primary-600 hover:underline">
                Emergency contacts
              </Link>{' '}
              to alert people you trust, and{' '}
              <Link to="/help" className="font-semibold text-primary-600 hover:underline">
                contact our safety team
              </Link>{' '}
              so we can investigate.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
