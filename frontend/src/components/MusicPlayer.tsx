import { useEffect, useRef, useState } from 'react'
import { isMusicOn, pickTrack, playlistFor, setMusicOn } from '../lib/music'

/** The parts of the YouTube IFrame Player API this player uses. */
interface YTPlayer {
  playVideo(): void
  pauseVideo(): void
  loadVideoById(id: string): void
  cueVideoById(id: string): void
  setVolume(volume: number): void
  destroy(): void
}

interface YTNamespace {
  Player: new (el: HTMLElement, options: {
    videoId: string
    width?: number | string
    height?: number | string
    playerVars?: Record<string, number | string>
    events?: {
      onReady?: () => void
      onStateChange?: (e: { data: number }) => void
      onError?: () => void
    }
  }) => YTPlayer
}

declare global {
  interface Window {
    YT?: YTNamespace
    onYouTubeIframeAPIReady?: () => void
  }
}

const PLAYING = 1
const ENDED = 0
const VOLUME_KEY = 'ldm_music_volume'

let apiPromise: Promise<YTNamespace> | null = null

/** Load the YouTube IFrame API once per page. */
function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (!apiPromise) {
    apiPromise = new Promise((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => {
        previous?.()
        if (window.YT) resolve(window.YT)
      }
      const script = document.createElement('script')
      script.src = 'https://www.youtube.com/iframe_api'
      script.async = true
      script.onerror = () => {
        apiPromise = null
        reject(new Error('YouTube could not be reached.'))
      }
      document.head.appendChild(script)
    })
  }
  return apiPromise
}

function savedVolume(): number {
  try {
    const v = Number(localStorage.getItem(VOLUME_KEY))
    return Number.isFinite(v) && v > 0 && v <= 100 ? v : 40
  } catch {
    return 40
  }
}

/**
 * Lobby music for one viewer: a random track from the default playlist, or Silver Scrapes in game 5 of
 * a series. Plays on through lobby, champ select and results; each player controls their own.
 */
export default function MusicPlayer({ seriesGameNumber }: { seriesGameNumber?: number | null }) {
  const tracks = playlistFor(seriesGameNumber)
  const host = useRef<HTMLDivElement>(null)
  const player = useRef<YTPlayer | null>(null)
  const current = useRef<string>('')
  const [playing, setPlaying] = useState(false)
  const [failed, setFailed] = useState(false)
  const [showVideo, setShowVideo] = useState(false)
  const [volume, setVolume] = useState(savedVolume)

  useEffect(() => {
    let cancelled = false
    const first = pickTrack(tracks).id
    current.current = first
    const autoplay = isMusicOn()
    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !host.current) return
        player.current = new YT.Player(host.current, {
          videoId: first,
          width: '100%',
          height: '100%',
          playerVars: { autoplay: autoplay ? 1 : 0, playsinline: 1, rel: 0, modestbranding: 1 },
          events: {
            onReady: () => player.current?.setVolume(volume),
            onStateChange: (e) => {
              if (e.data === PLAYING) setPlaying(true)
              else setPlaying(false)
              // the next track follows on by itself, never the same one twice in a row
              if (e.data === ENDED) next(true)
            },
            // an unavailable or embed-blocked video: move on to another one
            onError: () => next(true),
          },
        })
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      player.current?.destroy()
      player.current = null
    }
    // the playlist only changes when the game does, and GamePage remounts per game
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function next(play: boolean) {
    const id = pickTrack(tracks, current.current).id
    current.current = id
    if (play) player.current?.loadVideoById(id)
    else player.current?.cueVideoById(id)
  }

  function toggle() {
    if (!player.current) return
    if (playing) {
      player.current.pauseVideo()
      setMusicOn(false)
    } else {
      player.current.playVideo()
      setMusicOn(true)
    }
  }

  function changeVolume(v: number) {
    setVolume(v)
    player.current?.setVolume(v)
    try {
      localStorage.setItem(VOLUME_KEY, String(v))
    } catch {
      /* not remembered */
    }
  }

  if (failed) return null

  return (
    <div className={`music-player card ${showVideo ? 'music-player-open' : ''}`}>
      <div className="music-video" aria-hidden={!showVideo}>
        <div ref={host} />
      </div>
      <div className="row wrap music-controls">
        <span className="music-title" title="Lobby music">
          ♪ {seriesGameNumber === 5 ? 'Game 5 · Silver Scrapes' : 'Lobby music'}
        </span>
        <button type="button" className="ghost small" onClick={toggle} aria-label={playing ? 'Pause music' : 'Play music'}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type="button" className="ghost small" onClick={() => next(true)} aria-label="Next track">Next</button>
        <label className="music-volume">
          <span className="visually-hidden">Volume</span>
          <input type="range" min={0} max={100} value={volume} onChange={(e) => changeVolume(Number(e.target.value))} aria-label="Music volume" />
        </label>
        <button type="button" className="ghost small" onClick={() => setShowVideo(!showVideo)} aria-expanded={showVideo}>
          {showVideo ? 'Hide video' : 'Show video'}
        </button>
      </div>
    </div>
  )
}
