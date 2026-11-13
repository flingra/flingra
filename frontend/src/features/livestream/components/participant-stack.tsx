interface Participant {
  id: string
  name: string
  photo: string
}

/** Guest tiles stack from the top-right corner downward; tapping one brings it into focus. */
export function ParticipantStack({
  participants,
  focusedId,
  onFocus,
}: {
  participants: Participant[]
  focusedId: string
  onFocus: (id: string) => void
}) {
  const others = participants.filter((participant) => participant.id !== focusedId)
  if (others.length === 0) return null

  return (
    <div className="absolute right-3 top-20 z-10 flex flex-col gap-2">
      {others.map((participant) => (
        <button
          key={participant.id}
          type="button"
          onClick={() => onFocus(participant.id)}
          aria-label={`Switch to ${participant.name}'s stream`}
          className="relative size-16 cursor-pointer overflow-hidden rounded-xl border-2 border-white/70 shadow-float transition-transform hover:scale-105"
        >
          <img src={participant.photo} alt="" className="size-full object-cover" />
          <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-1 py-0.5 text-[10px] font-medium text-white">
            {participant.name}
          </span>
        </button>
      ))}
    </div>
  )
}
