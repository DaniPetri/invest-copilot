import { Navigate, Route, Routes } from 'react-router'
import { AppLayout } from './components/AppLayout'
import { ChatScreen } from './screens/ChatScreen'
import { DepotScreen } from './screens/DepotScreen'
import { EvalsScreen } from './screens/EvalsScreen'
import { HomeScreen } from './screens/HomeScreen'
import { ProductScreen } from './screens/ProductScreen'
import { SimulatorScreen } from './screens/SimulatorScreen'
import { PersonaProvider } from './state/persona'
import { SessionProvider } from './state/session'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomeScreen />} />
        <Route path="chat" element={<ChatScreen />} />
        <Route path="depot" element={<DepotScreen />} />
        <Route path="produkt/:id" element={<ProductScreen />} />
        <Route path="simulator" element={<SimulatorScreen />} />
        <Route path="evals" element={<EvalsScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

/** Everything except the router, so tests can bring their own (MemoryRouter). */
export default function App({ speed }: { speed?: number }) {
  return (
    <PersonaProvider>
      <SessionProvider speed={speed}>
        <AppRoutes />
      </SessionProvider>
    </PersonaProvider>
  )
}
