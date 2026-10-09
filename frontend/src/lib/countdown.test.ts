import { describe, expect, it } from 'vitest'
import { nextTickDelay, tickInterval } from './countdown'

describe('tickInterval', () => {
  it('speeds up as time runs out', () => {
    expect(tickInterval(10000)).toBe(1000)
    expect(tickInterval(5001)).toBe(1000)
    expect(tickInterval(5000)).toBe(500)
    expect(tickInterval(3000)).toBe(250)
    expect(tickInterval(100)).toBe(250)
  })
})

describe('nextTickDelay', () => {
  it('waits for the 10 second mark', () => {
    expect(nextTickDelay(25000)).toBe(15000)
  })
  it('lands on the next beat', () => {
    expect(nextTickDelay(10000)).toBe(1000)
    expect(nextTickDelay(7300)).toBe(300)
    expect(nextTickDelay(4200)).toBe(200)
    expect(nextTickDelay(1100)).toBe(100)
  })
  it('ticks every beat from 10 seconds down to zero', () => {
    const beats: number[] = []
    for (let left = 10000; left > 0; left -= nextTickDelay(left)) beats.push(left)
    expect(beats.slice(0, 6)).toEqual([10000, 9000, 8000, 7000, 6000, 5000])
    expect(beats.slice(6, 10)).toEqual([4500, 4000, 3500, 3000])
    expect(beats[beats.length - 1]).toBe(250)
    expect(beats).toHaveLength(21)
  })
})
