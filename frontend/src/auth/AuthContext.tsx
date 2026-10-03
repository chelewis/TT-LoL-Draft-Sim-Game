import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore } from '../api/client'
import type { User } from '../api/types'

interface AuthValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

interface TokenResponse {
  access_token: string
  user: User
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokenStore.get() !== null)

  useEffect(() => {
    if (!tokenStore.get()) return
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const accept = useCallback((res: TokenResponse) => {
    tokenStore.set(res.access_token)
    setUser(res.user)
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      login: async (username, password) => accept(await api<TokenResponse>('/auth/login', { body: { username, password } })),
      register: async (username, email, password) =>
        accept(await api<TokenResponse>('/auth/register', { body: { username, email, password } })),
      logout: () => {
        api('/auth/logout', { method: 'POST' }).catch(() => undefined)
        tokenStore.clear()
        setUser(null)
      },
    }),
    [user, loading, accept],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
