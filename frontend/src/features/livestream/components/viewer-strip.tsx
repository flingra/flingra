interface Viewer {
  id: string
  name: string
  photo: string
}

/** Tiny bottom-left strip of who's watching, à la every real livestream app. */
export function ViewerStrip({ viewers, count }: { viewers: Viewer[]; count: number }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex -space-x-2">
        {viewers.slice(0, 5).map((viewer) => (
          <img key={viewer.id} src={viewer.photo} alt={viewer.name} title={viewer.name} className="size-6 rounded-full border border-white object-cover" />
        ))}
      </div>
      <span className="text-[11px] font-medium text-white/90">{count} watching</span>
    </div>
  )
}
