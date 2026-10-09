import { useEffect } from 'react'
import { TICK_FROM_MS, TICK_URGENT_MS, nextTickDelay } from '../lib/countdown'
import { playSound } from '../lib/sound'

/** While `active`, ticks through the last 10 seconds before `expiresAt`, faster and higher as it runs out. */
export function useCountdownTick(expiresAt: string | null, active: boolean): void {
  useEffect(() => {
    if (!active || !expiresAt) return
    const end = Date.parse(expiresAt)
    let timer: number | undefined
    const run = () => {
      const left = end - Date.now()
      if (left <= 0) return
      if (left <= TICK_FROM_MS) playSound(left <= TICK_URGENT_MS ? 'tickUrgent' : 'tick')
      // the floor keeps a timer that fires a hair early from ticking the same beat twice
      timer = window.setTimeout(run, Math.max(50, nextTickDelay(left)))
    }
    timer = window.setTimeout(run, Math.max(0, end - Date.now() - TICK_FROM_MS))
    return () => window.clearTimeout(timer)
  }, [expiresAt, active])
}
