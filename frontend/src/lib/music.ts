/** Lobby music: which YouTube videos can play and how the next one is chosen. Edit the lists here. */

export interface Track {
  /** YouTube video id (the `v=` part of a watch link, or the path of a youtu.be link) */
  id: string
  /** relative chance of being picked; tracks without one are equally likely */
  weight?: number
}

/** Plays in every game, one picked at random each time. */
export const DEFAULT_PLAYLIST: Track[] = [
  { id: 'WkTwA7LMd3E' },
  { id: '8tNNL9S8LDk' },
  { id: 'eABTBM-uLak' },
  { id: 'N1S2z4fAAqo' },
  { id: 'zdRHubvsdK8' },
]

/** Game 5 of a series plays Silver Scrapes instead: one of three versions, weighted 60 / 30 / 10. */
export const GAME_FIVE_PLAYLIST: Track[] = [
  { id: '8_BBfWES5ak', weight: 60 },
  { id: 'JNM3G5nGf0g', weight: 30 },
  { id: '21hQsnpdNpA', weight: 10 },
]

/** The playlist for a game: Silver Scrapes for game 5 of a series, the default playlist otherwise. */
export function playlistFor(seriesGameNumber: number | null | undefined): Track[] {
  return seriesGameNumber === 5 ? GAME_FIVE_PLAYLIST : DEFAULT_PLAYLIST
}

/**
 * Pick a track by weight. `avoid` (usually the one that just played) is skipped when anything else is
 * left, so "next" never repeats the same video. `random` returns a number in [0, 1).
 */
export function pickTrack(tracks: Track[], avoid: string | null = null, random: () => number = Math.random): Track {
  const pool = tracks.length > 1 && avoid ? tracks.filter((t) => t.id !== avoid) : tracks
  const total = pool.reduce((sum, t) => sum + (t.weight ?? 1), 0)
  let roll = random() * total
  for (const track of pool) {
    roll -= track.weight ?? 1
    if (roll < 0) return track
  }
  return pool[pool.length - 1]
}

const MUSIC_KEY = 'ldm_music'

/** Whether music starts by itself; remembered per browser, on unless the viewer turned it off. */
export function isMusicOn(): boolean {
  try {
    return localStorage.getItem(MUSIC_KEY) !== '0'
  } catch {
    return true
  }
}

export function setMusicOn(on: boolean): void {
  try {
    localStorage.setItem(MUSIC_KEY, on ? '1' : '0')
  } catch {
    /* preference just isn't remembered */
  }
}
