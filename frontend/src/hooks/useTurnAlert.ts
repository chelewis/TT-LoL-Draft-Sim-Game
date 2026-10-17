import { useEffect, useRef } from 'react'
import { clearTurnNotification, isPullBackOn, notifyTurn, type TurnAlertKey } from '../lib/alerts'
import { playSound } from '../lib/sound'

const NOTIFY_BODY = 'League Draft Manager · champion select'

/**
 * Alerts the player when `alertKey` becomes non-null: a chime, a desktop notification if they are away,
 * and a marker in the tab title until they come back or the turn ends. With "pull me back" on, the
 * notification also stays up, the title flashes and the chime repeats while they are away.
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
      notifyTurn(text.current, NOTIFY_BODY)
    }
    const base = document.title
    const isAway = () => document.hidden || !document.hasFocus()
    let wasAway = isAway()
    let flash = false
    const sync = () => {
      const away = isAway()
      // pull me back: they left during their turn, so raise the notification now
      if (away && !wasAway && isPullBackOn()) notifyTurn(text.current, NOTIFY_BODY)
      wasAway = away
      flash = false
      document.title = away ? `● ${text.current} · ${base}` : base
      if (!away) clearTurnNotification()
    }
    sync()
    const timers = [
      window.setInterval(() => {
        if (!isAway() || !isPullBackOn()) return
        flash = !flash
        document.title = flash ? '🟢 YOUR TURN' : `● ${text.current} · ${base}`
      }, 1000),
      window.setInterval(() => isAway() && isPullBackOn() && playSound('turn'), 5000),
    ]
    document.addEventListener('visibilitychange', sync)
    window.addEventListener('focus', sync)
    window.addEventListener('blur', sync)
    return () => {
      timers.forEach((t) => window.clearInterval(t))
      document.removeEventListener('visibilitychange', sync)
      window.removeEventListener('focus', sync)
      window.removeEventListener('blur', sync)
      document.title = base
      clearTurnNotification()
    }
  }, [alertKey])
}
