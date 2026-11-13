import { Component, type ReactNode } from 'react'
import { ErrorState } from '@/components/ui/state-message'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto max-w-lg px-4 py-20">
          <ErrorState
            title="This page hit a snag"
            description="Reload the page to try again. If this keeps happening, contact support from the Help page."
            action={{ label: 'Reload', onClick: () => window.location.reload() }}
          />
        </div>
      )
    }
    return this.props.children
  }
}
