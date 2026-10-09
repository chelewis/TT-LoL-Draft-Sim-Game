import { describe, expect, it } from 'vitest'
import { turnAlertKey } from './alerts'

describe('turnAlertKey', () => {
  it('alerts while it is my pick or ban', () => {
    expect(turnAlertKey({ solo: false, myTurn: true, canFinalize: false })).toBe('draft')
  })
  it('is quiet on the opponent turn', () => {
    expect(turnAlertKey({ solo: false, myTurn: false, canFinalize: false })).toBeNull()
  })
  it('alerts when my lineup still needs locking in', () => {
    expect(turnAlertKey({ solo: false, myTurn: false, canFinalize: true })).toBe('finalize')
  })
  it('never alerts in single player', () => {
    expect(turnAlertKey({ solo: true, myTurn: true, canFinalize: false })).toBeNull()
    expect(turnAlertKey({ solo: true, myTurn: false, canFinalize: true })).toBeNull()
  })
})
