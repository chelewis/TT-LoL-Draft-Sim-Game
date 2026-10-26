import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

/** The bits of Google Identity Services (https://accounts.google.com/gsi/client) this button uses. */
interface GoogleIdentity {
  accounts: {
    id: {
      initialize: (config: { client_id: string; callback: (res: { credential: string }) => void; ux_mode?: 'popup' }) => void
      renderButton: (parent: HTMLElement, options: Record<string, string | number>) => void
    }
  }
}
declare global {
  interface Window {
    google?: GoogleIdentity
  }
}

const GSI_SRC = 'https://accounts.google.com/gsi/client'
let gsiLoading: Promise<GoogleIdentity> | null = null

/** Load Google's sign-in script once, only when a client ID is configured. */
function loadGoogleIdentity(): Promise<GoogleIdentity> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google)
  gsiLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GSI_SRC
    script.async = true
    script.onload = () => (window.google ? resolve(window.google) : reject(new Error('Google sign-in failed to load.')))
    script.onerror = () => {
      gsiLoading = null
      reject(new Error('Google sign-in could not be loaded.'))
    }
    document.head.appendChild(script)
  })
  return gsiLoading
}

/**
 * Google's own "Sign in with Google" button. Renders nothing unless the server has a Google client ID
 * (LDM_GOOGLE_CLIENT_ID). Google hands us a signed ID token; the server verifies it before logging in.
 */
export default function GoogleSignIn({ onCredential }: { onCredential: (credential: string) => void }) {
  const providers = useQuery({
    queryKey: ['auth-providers'],
    queryFn: () => api<{ google_client_id: string | null }>('/auth/providers'),
    staleTime: Infinity,
  })
  const clientId = providers.data?.google_client_id
  const slot = useRef<HTMLDivElement>(null)
  const callback = useRef(onCredential)
  callback.current = onCredential
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!clientId) return
    let cancelled = false
    loadGoogleIdentity()
      .then((google) => {
        if (cancelled || !slot.current) return
        google.accounts.id.initialize({ client_id: clientId, callback: (res) => callback.current(res.credential), ux_mode: 'popup' })
        google.accounts.id.renderButton(slot.current, {
          theme: 'filled_black',
          size: 'large',
          shape: 'pill',
          text: 'continue_with',
          width: Math.min(360, slot.current.offsetWidth || 360),
        })
      })
      .catch((err: Error) => !cancelled && setLoadError(err.message))
    return () => {
      cancelled = true
    }
  }, [clientId])

  if (!clientId) return null
  return (
    <div className="google-signin">
      <div className="auth-divider">
        <span>or</span>
      </div>
      <div ref={slot} className="google-signin-button" />
      {loadError && <p className="small muted">{loadError}</p>}
    </div>
  )
}
