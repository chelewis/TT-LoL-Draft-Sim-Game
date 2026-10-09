/** "It's your turn" alerts for champ select: when to raise one, and the desktop notification itself. */
export type TurnAlertKey = 'draft' | 'finalize' | null

/**
 * What the player is being waited on for, or null. The key stays the same across back-to-back actions
 * (a double pick), so an alert fires only when the turn comes to the player, not on every action.
 * Single player never alerts: every turn is yours.
 */
export function turnAlertKey({ solo, myTurn, canFinalize }: { solo: boolean; myTurn: boolean; canFinalize: boolean }): TurnAlertKey {
  if (solo) return null
  if (myTurn) return 'draft'
  if (canFinalize) return 'finalize'
  return null
}

export type AlertsState = 'unsupported' | 'off' | 'on' | 'blocked'

const ALERTS_KEY = 'ldm_alerts'

function wanted(): boolean {
  try {
    return localStorage.getItem(ALERTS_KEY) === '1'
  } catch {
    return false
  }
}

function setWanted(on: boolean): void {
  try {
    localStorage.setItem(ALERTS_KEY, on ? '1' : '0')
  } catch {
    /* preference just isn't remembered */
  }
}

export function alertsState(): AlertsState {
  if (typeof Notification === 'undefined') return 'unsupported'
  if (Notification.permission === 'denied') return 'blocked'
  return wanted() && Notification.permission === 'granted' ? 'on' : 'off'
}

/** Asks the browser for permission if needed; must be called from a click. */
export async function enableAlerts(): Promise<AlertsState> {
  if (typeof Notification === 'undefined') return 'unsupported'
  try {
    const permission = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission
    if (permission === 'granted') setWanted(true)
  } catch {
    /* stays off */
  }
  return alertsState()
}

export function disableAlerts(): AlertsState {
  setWanted(false)
  clearTurnNotification()
  return alertsState()
}

let shown: Notification | null = null

/** Desktop notification, only when the player isn't looking at the tab. */
export function notifyTurn(title: string, body: string): void {
  if (alertsState() !== 'on') return
  if (!document.hidden && document.hasFocus()) return
  try {
    const n = new Notification(title, { body, tag: 'ldm-turn' })
    n.onclick = () => {
      window.focus()
      n.close()
    }
    shown = n
  } catch {
    /* some browsers only allow notifications from a service worker */
  }
}

export function clearTurnNotification(): void {
  shown?.close()
  shown = null
}
