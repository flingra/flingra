import { AppProviders } from './app/providers'
import { AppRouter } from './app/router'
import { Preloader } from './components/preloader'

export default function App() {
  return (
    <AppProviders>
      <AppRouter />
      <Preloader />
    </AppProviders>
  )
}
