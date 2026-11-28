import { NavLink } from 'react-router-dom'

export function MessagesTabs() {
  return (
    <nav aria-label="Messages sections" className="mb-5 inline-flex rounded-full bg-ink-100 p-1">
      <NavLink
        to="/messages"
        end
        className={({ isActive }) =>
          `rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            isActive ? 'bg-white text-ink-900 shadow-soft' : 'text-ink-500 hover:text-ink-900'
          }`
        }
      >
        Chats
      </NavLink>
      <NavLink
        to="/messages/calls"
        className={({ isActive }) =>
          `rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            isActive ? 'bg-white text-ink-900 shadow-soft' : 'text-ink-500 hover:text-ink-900'
          }`
        }
      >
        Calls
      </NavLink>
    </nav>
  )
}
