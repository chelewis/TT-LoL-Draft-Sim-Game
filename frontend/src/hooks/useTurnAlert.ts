import { useEffect, useRef } from 'react'
import { clearTurnNotification, notifyTurn, type TurnAlertKey } from '../lib/alerts'
import { playSound } from '../lib/sound'

/**
 * Alerts the player when `alertKey` becomes non-null: a chime, a desktop notification if they are away,
 * and a marker in the tab title until they come back or the turn ends.
 */
export function useTurnAlert(alertKey: TurnAlertKey, message: string): void {
  const text = useRef(message)
  text.current = message
  // survives StrictMode's double effect run, so the chime plays once
  const alerted = useRef<TurnAlertKey>(null)

  useEffect(() => {
    if (!alertKey) {
      alerted.current = null
      return
    }
    if (alerted.current !== alertKey) {
      alerted.current = alertKey
      playSound('turn')
      notifyTurn(text.current, 'League Draft Manager · champion select')
    }
    const base = document.title
    const sync = () => {
      const away = document.hidden || !document.hasFocus()
      document.title = away ? `● ${text.current} · ${base}` : base
      if (!away) clearTurnNotification()
    }
    sync()
    document.addEventListener('visibilitychange', sync)
    window.addEventListener('focus', sync)
    window.addEventListener('blur', sync)
    return () => {
      document.removeEventListener('visibilitychange', sync)
      window.removeEventListener('focus', sync)
      window.removeEventListener('blur', sync)
      document.title = base
      clearTurnNotification()
    }
  }, [alertKey])
}
