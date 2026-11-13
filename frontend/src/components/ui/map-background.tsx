import { cn } from '@/lib/utils'

const TREE_DOTS = [
  [48, 48], [62, 40], [40, 64], [66, 62], [54, 72], [30, 50],
  [330, 230], [346, 244], [318, 248], [340, 214], [354, 226], [326, 212],
]

/**
 * Decorative map texture — land, water, parks and an organic road network with
 * proper casing (dark outline + lighter fill, like a real map style), not a
 * repeating grid. No map provider, API key or geodata: Flingra only ever shows
 * coarse area/distance, never a precise, queryable map.
 */
export function MapBackground({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-[#eef1ea]', className)} aria-hidden="true">
      <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full">
        <rect width="400" height="300" fill="#eef1ea" />

        {/* Water */}
        <path d="M400,170 C360,150 320,175 310,220 C302,255 330,300 330,300 L400,300 Z" fill="#b9dce3" />

        {/* Parks */}
        <path d="M-10,10 C40,-10 90,10 80,55 C72,90 20,95 -10,70 Z" fill="#c9e3ba" />
        <path d="M290,180 C330,165 365,185 358,220 C352,250 310,260 290,235 C278,215 275,190 290,180 Z" fill="#c9e3ba" />
        {TREE_DOTS.map(([cx, cy]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={4} fill="#9fcb8c" opacity={0.75} />
        ))}

        {/* Local streets (irregular, not a repeating grid) */}
        <g stroke="#e4e7dd" strokeWidth={3.5} fill="none" strokeLinecap="round">
          <path d="M20,120 L160,110 L180,180 L90,260" />
          <path d="M60,0 L75,140 L55,300" />
          <path d="M140,20 L130,150 L220,165 L235,300" />
          <path d="M0,200 L140,210 L260,190" />
          <path d="M250,40 L245,160 L330,150" />
        </g>
        <g stroke="#ffffff" strokeWidth={1.6} fill="none" strokeLinecap="round">
          <path d="M20,120 L160,110 L180,180 L90,260" />
          <path d="M60,0 L75,140 L55,300" />
          <path d="M140,20 L130,150 L220,165 L235,300" />
          <path d="M0,200 L140,210 L260,190" />
          <path d="M250,40 L245,160 L330,150" />
        </g>

        {/* Secondary roads */}
        <path d="M-10,95 C90,70 180,100 260,60 C320,35 360,45 410,30" stroke="#d9dcd1" strokeWidth={7} fill="none" strokeLinecap="round" />
        <path d="M-10,95 C90,70 180,100 260,60 C320,35 360,45 410,30" stroke="#ffffff" strokeWidth={4} fill="none" strokeLinecap="round" />
        <path d="M100,-10 C120,80 80,160 130,230 C160,275 180,290 170,310" stroke="#d9dcd1" strokeWidth={7} fill="none" strokeLinecap="round" />
        <path d="M100,-10 C120,80 80,160 130,230 C160,275 180,290 170,310" stroke="#ffffff" strokeWidth={4} fill="none" strokeLinecap="round" />

        {/* Arterial road (highway-style casing + fill + dashed centre line) */}
        <path d="M-20,260 C70,230 150,250 210,190 C270,130 310,120 410,70" stroke="#d1a648" strokeWidth={13} fill="none" strokeLinecap="round" />
        <path d="M-20,260 C70,230 150,250 210,190 C270,130 310,120 410,70" stroke="#ffc24b" strokeWidth={10} fill="none" strokeLinecap="round" />
        <path
          d="M-20,260 C70,230 150,250 210,190 C270,130 310,120 410,70"
          stroke="#ffffff"
          strokeWidth={1.4}
          strokeDasharray="7 7"
          fill="none"
          strokeLinecap="round"
          opacity={0.85}
        />

        {/* City blocks */}
        <g fill="#f7f6f1" stroke="#e2e0d6" strokeWidth={1}>
          <rect x={185} y={35} width={26} height={18} rx={2} />
          <rect x={30} y={150} width={22} height={30} rx={2} />
          <rect x={175} y={210} width={30} height={20} rx={2} />
          <rect x={95} y={95} width={20} height={22} rx={2} />
          <rect x={260} y={95} width={24} height={18} rx={2} />
          <rect x={140} y={250} width={26} height={20} rx={2} />
        </g>

        {/* Soft vignette for depth */}
        <defs>
          <radialGradient id="map-vignette" cx="50%" cy="45%" r="75%">
            <stop offset="60%" stopColor="#000000" stopOpacity={0} />
            <stop offset="100%" stopColor="#1a1f16" stopOpacity={0.12} />
          </radialGradient>
        </defs>
        <rect width="400" height="300" fill="url(#map-vignette)" />
      </svg>
    </div>
  )
}
