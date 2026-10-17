import { describe, expect, it } from 'vitest'
import { DEFAULT_PLAYLIST, GAME_FIVE_PLAYLIST, pickTrack, playlistFor } from './music'

describe('playlistFor', () => {
  it('plays Silver Scrapes only in game 5 of a series', () => {
    expect(playlistFor(5)).toBe(GAME_FIVE_PLAYLIST)
    for (const n of [null, undefined, 1, 2, 3, 4]) expect(playlistFor(n)).toBe(DEFAULT_PLAYLIST)
  })
})

describe('pickTrack', () => {
  it('weights Silver Scrapes versions 60 / 30 / 10', () => {
    const at = (r: number) => pickTrack(GAME_FIVE_PLAYLIST, null, () => r).id
    expect(at(0)).toBe('8_BBfWES5ak')
    expect(at(0.59)).toBe('8_BBfWES5ak')
    expect(at(0.6)).toBe('JNM3G5nGf0g')
    expect(at(0.89)).toBe('JNM3G5nGf0g')
    expect(at(0.9)).toBe('21hQsnpdNpA')
    expect(at(0.999)).toBe('21hQsnpdNpA')
  })

  it('picks evenly from unweighted tracks', () => {
    const ids = DEFAULT_PLAYLIST.map((_, i) => pickTrack(DEFAULT_PLAYLIST, null, () => (i + 0.5) / DEFAULT_PLAYLIST.length).id)
    expect(ids).toEqual(DEFAULT_PLAYLIST.map((t) => t.id))
  })

  it('never repeats the track that just played when there is another', () => {
    for (let i = 0; i < 20; i++) {
      const avoid = DEFAULT_PLAYLIST[i % DEFAULT_PLAYLIST.length].id
      expect(pickTrack(DEFAULT_PLAYLIST, avoid, () => i / 20).id).not.toBe(avoid)
    }
    expect(pickTrack([{ id: 'only' }], 'only').id).toBe('only')
  })
})
