import { Link } from 'react-router-dom'
import { HelpCircle, Mail, MessageCircleQuestion, ShieldCheck, Siren, Wallet } from 'lucide-react'
import { Card } from '@/components/ui/card'

const QUICK_LINKS = [
  { to: '/safety', icon: ShieldCheck, label: 'Safety guidance' },
  { to: '/safety/emergency-contacts', icon: Siren, label: 'Emergency contacts' },
  { to: '/wallet', icon: Wallet, label: 'Wallet & payments' },
]

const FAQ_GROUPS = [
  {
    title: 'Account & profile',
    icon: HelpCircle,
    items: [
      {
        q: 'How do I delete my account?',
        a: "Go to Settings › Privacy and choose Delete account. You'll see exactly what happens to your data before confirming.",
      },
      {
        q: 'Can other members see my exact location?',
        a: 'No. Flingra only ever shows an approximate area or distance, never exact coordinates.',
      },
      {
        q: 'Who can see my phone number?',
        a: "No one. Your phone number is never shown to other members — all communication happens inside the app.",
      },
    ],
  },
  {
    title: 'Safety & moderation',
    icon: ShieldCheck,
    items: [
      {
        q: 'What happens after I report someone?',
        a: "Our moderation team reviews every report and investigates before taking action, which can include a ban. We never disclose the outcome or your identity to the reported member.",
      },
      {
        q: "What's the difference between blocking and reporting?",
        a: 'Blocking immediately stops someone from contacting or discovering you. It also files a report with our safety team for review — you don\'t need to do both separately.',
      },
    ],
  },
  {
    title: 'Payments & wallet',
    icon: Wallet,
    items: [
      {
        q: 'How do I withdraw money I\'ve earned from gifts?',
        a: 'Redeem received gifts from Wallet › Redeem gifts to add their value to your balance, then request a withdrawal from Wallet › Payout. You\'ll need a bank account on file first.',
      },
      {
        q: 'Is funding my wallet a real payment?',
        a: 'Not in this preview build — funding is a demo top-up. Live payments are handled separately once the backend is connected.',
      },
    ],
  },
]

export function HelpPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold text-ink-900">Help &amp; support</h1>
      <p className="mt-2 text-ink-500">Answers to common questions, and how to reach us if you need more help.</p>

      <div className="mt-6 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
        {QUICK_LINKS.map(({ to, icon: Icon, label }, index) => (
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
            <span className="flex-1 font-medium text-ink-800">{label}</span>
          </Link>
        ))}
      </div>

      <Card className="mt-6 flex items-center gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
          <Mail className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-lg font-bold text-ink-900">Contact support</h2>
          <p className="mt-1 text-sm text-ink-500">
            Email{' '}
            <a href="mailto:support@flingra.example" className="font-semibold text-primary-600 hover:underline">
              support@flingra.example
            </a>{' '}
            for account issues, moderation appeals, or anything else. We typically reply within 24 hours.
          </p>
        </div>
      </Card>

      {FAQ_GROUPS.map(({ title, icon: Icon, items }) => (
        <section key={title} className="mt-10">
          <h2 className="flex items-center gap-2 text-xl font-bold text-ink-900">
            <Icon className="size-5 text-primary-500" aria-hidden="true" /> {title}
          </h2>
          <div className="mt-4 flex flex-col gap-3">
            {items.map(({ q, a }) => (
              <Card key={q} className="flex items-start gap-4">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-ink-50 text-ink-400">
                  <MessageCircleQuestion className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-semibold text-ink-900">{q}</p>
                  <p className="mt-1 text-sm text-ink-600">{a}</p>
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
