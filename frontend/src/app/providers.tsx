import { type ReactNode, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, useLocation } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/toast'
import { AppErrorBoundary } from './error-boundary'
import { SessionRevocationListener } from '@/components/session-revocation-listener'

function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()

  return <AppErrorBoundary key={pathname}>{children}</AppErrorBoundary>
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
        },
      }),
  )

  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <SessionRevocationListener />
            <RouteErrorBoundary>{children}</RouteErrorBoundary>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  )
}
