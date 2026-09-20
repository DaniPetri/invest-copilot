import { useEffect, useState } from 'react'

export interface Loaded<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/** Runs `load` whenever `key` changes and ignores results that arrive after a newer request started. */
export function useLoad<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, loading: key !== null, error: null })

  useEffect(() => {
    if (key === null) return
    let alive = true
    setState((s) => ({ data: s.data, loading: true, error: null }))
    load()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e: Error) => alive && setState({ data: null, loading: false, error: e.message }))
    return () => {
      alive = false
    }
    // `load` is a fresh closure each render; `key` identifies the request
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return state
}
