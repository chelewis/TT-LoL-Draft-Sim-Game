import { useState } from 'react'
import type { Champion, Lane } from '../api/types'
import { useDDragonVersion } from '../hooks/useData'
import { loadingUrl, splashUrl, squareUrl } from '../lib/ddragon'

function initials(name: string): string {
  return name
    .split(/[^A-Za-z]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')
}

/** Square champion portrait; falls back to initials when Data Dragon has no image for the name. */
export function ChampionIcon({ champion, size = 48, className = '' }: { champion: Pick<Champion, 'name'> | undefined; size?: number; className?: string }) {
  const version = useDDragonVersion()
  const [failed, setFailed] = useState(false)
  const style = { width: size, height: size }
  if (!champion || !version || failed) {
    return (
      <span className={`champ-icon champ-icon-fallback ${className}`} style={{ ...style, fontSize: size * 0.34 }} aria-hidden="true">
        {champion ? initials(champion.name) : ''}
      </span>
    )
  }
  return (
    <img
      className={`champ-icon ${className}`}
      style={style}
      src={squareUrl(champion.name, version)}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

/** CSS background for a pick slot: the champion's splash (wide) or loading-screen (tall) art. */
export function championArt(champion: Champion | undefined, kind: 'splash' | 'loading' = 'splash'): string | undefined {
  if (!champion) return undefined
  return `url("${kind === 'splash' ? splashUrl(champion.name) : loadingUrl(champion.name)}")`
}

/** Position icons in the style of the League client (map-quadrant shapes). */
export function LaneIcon({ lane, size = 18, className = '' }: { lane: Lane; size?: number; className?: string }) {
  const dim = { opacity: 0.35 }
  let body
  switch (lane) {
    case 'TOP':
      body = (
        <>
          <path d="M3 3h14l-4 4H7v6l-4 4z" />
          <path d="M10 10h4v4h-4z" />
          <path style={dim} d="M21 7v14H7l4-4h6v-6z" />
        </>
      )
      break
    case 'BOT':
      body = (
        <>
          <path d="M21 21H7l4-4h6v-6l4-4z" />
          <path d="M10 10h4v4h-4z" />
          <path style={dim} d="M3 17V3h14l-4 4H7v6z" />
        </>
      )
      break
    case 'MID':
      body = (
        <>
          <path d="M17 3h4v4L7 21H3v-4z" />
          <path style={dim} d="M3 3h10l-4 4H7v2l-4 4z" />
          <path style={dim} d="M21 11v10H11l4-4h2v-2z" />
        </>
      )
      break
    case 'JUNGLE':
      body = (
        <>
          <path d="M5 2c3.2 2.8 5.6 6.4 6 10.4.2 2.4-.3 5-1.6 7.6-1.2-3.4-3-5.8-5.4-7.6 1.6-.2 2.6.4 3.4 1.2C7.6 9.8 6.8 5.8 5 2z" />
          <path d="M19 2c-2.2 3-3.8 6.4-4.2 10-.2 2 0 4 .6 6 1.2-1.8 2.8-3.4 4.6-4.4-1.2-.2-2.2 0-3 .6.2-4 .8-8 2-12.2z" />
          <path d="M12.2 15c.6 2.4.6 4.6-.2 7 1.4-1 2.4-2.4 2.8-4-.8-1.2-1.6-2.2-2.6-3z" />
        </>
      )
      break
    case 'SUPPORT':
      body = (
        <>
          <path d="M9 3h6l-1.2 3h-3.6z" />
          <path d="M2 7h6.2l1.8 2.6-2 2.8H6L4.8 10.2H2z" />
          <path d="M22 7h-6.2L14 9.6l2 2.8h2l1.2-2.2H22z" />
          <path d="M10.4 9h3.2l1.2 5.4L12 21l-2.8-6.6z" />
        </>
      )
      break
  }
  return (
    <svg className={`lane-icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="currentColor" role="img" aria-label={lane.toLowerCase()}>
      {body}
    </svg>
  )
}
