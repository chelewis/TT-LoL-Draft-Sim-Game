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
// "pull me back": the notification stays up, the tab title flashes and the chime repeats until the player returns
const PULL_BACK_KEY = 'ldm_pullback'

function wanted(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function setWanted(key: string, on: boolean): void {
  try {
    localStorage.setItem(key, on ? '1' : '0')
  } catch {
    /* preference just isn't remembered */
  }
}

function stateOf(key: string): AlertsState {
  if (typeof Notification === 'undefined') return 'unsupported'
  if (Notification.permission === 'denied') return 'blocked'
  return wanted(key) && Notification.permission === 'granted' ? 'on' : 'off'
}

/** Asks the browser for permission if needed; must be called from a click. */
async function enable(key: string): Promise<AlertsState> {
  if (typeof Notification === 'undefined') return 'unsupported'
  try {
    const permission = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission
    if (permission === 'granted') setWanted(key, true)
  } catch {
    /* stays off */
  }
  return stateOf(key)
}

export const alertsState = () => stateOf(ALERTS_KEY)
export const enableAlerts = () => enable(ALERTS_KEY)
export function disableAlerts(): AlertsState {
  setWanted(ALERTS_KEY, false)
  if (pullBackState() !== 'on') clearTurnNotification()
  return alertsState()
}

export const pullBackState = () => stateOf(PULL_BACK_KEY)
export const isPullBackOn = () => pullBackState() === 'on'
export const enablePullBack = () => enable(PULL_BACK_KEY)
export function disablePullBack(): AlertsState {
  setWanted(PULL_BACK_KEY, false)
  if (alertsState() !== 'on') clearTurnNotification()
  return pullBackState()
}

let shown: Notification | null = null

/** Desktop notification, only when the player isn't looking at the tab. */
export function notifyTurn(title: string, body: string): void {
  const pullBack = isPullBackOn()
  if (alertsState() !== 'on' && !pullBack) return
  if (!document.hidden && document.hasFocus()) return
  try {
    // pull me back: stays on screen until clicked, and the click brings the player to this tab
    const n = new Notification(title, { body, tag: 'ldm-turn', requireInteraction: pullBack })
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
