import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { Customer } from '../types/contracts'

interface PersonaState {
  customers: Customer[]
  /** The active persona; undefined until the customers have loaded. */
  current: Customer | undefined
  setPersona: (id: string) => void
  loading: boolean
  error: string | null
}

const STORAGE_KEY = 'invest-copilot.persona'
const DEFAULT_PERSONA = 'markus'

const PersonaContext = createContext<PersonaState | null>(null)

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_PERSONA
  } catch {
    return DEFAULT_PERSONA // storage can be unavailable (private mode, previews)
  }
}

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [id, setId] = useState<string>(readStored)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .getCustomers()
      .then((c) => alive && setCustomers(c))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  const value = useMemo<PersonaState>(
    () => ({
      customers,
      current: customers.find((c) => c.id === id) ?? customers[0],
      setPersona: (next) => {
        setId(next)
        try {
          localStorage.setItem(STORAGE_KEY, next)
        } catch {
          /* not persisted, still works for this session */
        }
      },
      loading,
      error,
    }),
    [customers, id, loading, error],
  )
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>
}

export function usePersona(): PersonaState {
  const ctx = useContext(PersonaContext)
  if (!ctx) throw new Error('usePersona must be used inside <PersonaProvider>')
  return ctx
}
