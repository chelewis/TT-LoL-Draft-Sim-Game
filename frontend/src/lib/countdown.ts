/** Timing of the champ select countdown ticks: they start at 10 seconds left and speed up towards zero. */
export const TICK_FROM_MS = 10000
/** From here the ticks also rise in pitch. */
export const TICK_URGENT_MS = 3000

/** Gap between ticks with `leftMs` on the clock: every second, then twice a second, then four times. */
export function tickInterval(leftMs: number): number {
  return leftMs > 5000 ? 1000 : leftMs > TICK_URGENT_MS ? 500 : 250
}

/** Milliseconds until the next tick, so ticks land on the clock's own beats (10.0, 9.0 … 5.0, 4.5 … 3.0, 2.75 …). */
export function nextTickDelay(leftMs: number): number {
  if (leftMs > TICK_FROM_MS) return leftMs - TICK_FROM_MS
  const step = tickInterval(leftMs)
  return leftMs - (Math.ceil(leftMs / step) - 1) * step
}
