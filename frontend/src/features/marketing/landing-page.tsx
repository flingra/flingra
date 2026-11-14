import { Link } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button'
import { MapBackground } from '@/components/ui/map-background'
import { cn, hashSeed } from '@/lib/utils'

function avatar(seed: string) {
  return `https://i.pravatar.cc/200?img=${hashSeed(seed, 70) + 1}`
}

const CLUSTER_AVATARS = [
  { seed: 'Tunde-hero', top: '2%', left: '10%', size: 'size-12 sm:size-14' },
  { seed: 'Amaka-hero', top: '6%', left: '62%', size: 'size-10 sm:size-12' },
  { seed: 'Chidi-hero', top: '42%', left: '0%', size: 'size-10 sm:size-12' },
  { seed: 'Zainab-hero', top: '66%', left: '20%', size: 'size-14 sm:size-16' },
  { seed: 'Emeka-hero', top: '50%', left: '66%', size: 'size-12 sm:size-14' },
]

function AvatarCluster() {
  return (
    <div
      className="relative mx-auto mb-4 size-36 animate-float overflow-hidden rounded-full shadow-float sm:mb-6 sm:size-52 md:size-56"
      aria-hidden="true"
    >
      <MapBackground className="absolute inset-0" />
      <span className="absolute inset-0 rounded-full border border-white/40" />
      <span className="absolute inset-[14%] rounded-full border border-white/30" />
      {CLUSTER_AVATARS.map((item) => (
        <img
          key={item.seed}
          src={avatar(item.seed)}
          alt=""
          className={cn('absolute rounded-full border-4 border-white/90 bg-primary-200 shadow-float', item.size)}
          style={{ top: item.top, left: item.left }}
        />
      ))}
    </div>
  )
}

export function LandingPage() {
  return (
    <section className="relative flex h-full flex-col items-center justify-center overflow-x-hidden overflow-y-auto bg-gradient-to-b from-primary-400 to-primary-600 px-4 py-6 text-center text-white sm:px-6">
      <span
        className="pointer-events-none absolute -left-16 -top-16 size-64 animate-pulse rounded-full bg-white/10 blur-3xl"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute -bottom-20 -right-16 size-72 animate-pulse rounded-full bg-ink-900/10 blur-3xl"
        style={{ animationDelay: '1s' }}
        aria-hidden="true"
      />

      <div className="relative mx-auto w-full max-w-sm">
        <AvatarCluster />
        <h1 className="text-2xl font-extrabold leading-tight tracking-tight sm:text-3xl md:text-4xl">
          Create, find and join your circle now!
        </h1>
        <p className="mx-auto mt-3 max-w-xs text-sm text-white/90 sm:mt-4 sm:text-base">
          Flingra helps adults in Nigeria discover people nearby, with privacy-conscious location and
          safety tools built in from the start.
        </p>
        <Link
          to="/signup"
          className={cn(buttonVariants({ variant: 'primary', size: 'lg' }), 'mt-6 w-full bg-ink-900 hover:bg-ink-800 sm:mt-8')}
        >
          Get started
        </Link>
        <Link to="/login" className="mt-3 inline-block text-sm font-semibold text-white/90 hover:text-white hover:underline sm:mt-4">
          Sign in
        </Link>
      </div>
    </section>
  )
}
