/** Champion art from Riot's Data Dragon CDN. The browser loads images straight from Riot; nothing is proxied. */

const CDN = 'https://ddragon.leagueoflegends.com'
/** Used until (or if) the live version list can't be fetched. */
export const FALLBACK_VERSION = '15.24.1'

/** Our champion names that don't reduce cleanly to Riot's Data Dragon id. */
const DDRAGON_ID_OVERRIDES: Record<string, string> = {
  chogath: 'Chogath',
  kaisa: 'Kaisa',
  khazix: 'Khazix',
  velkoz: 'Velkoz',
  belveth: 'Belveth',
  leblanc: 'Leblanc',
  wukong: 'MonkeyKing',
  nunuwillump: 'Nunu',
  renataglasc: 'Renata',
  fiddlesticks: 'Fiddlesticks',
}

/** "Lee Sin" -> "LeeSin", "Dr.Mundo" -> "DrMundo", "Kai Sa" -> "Kaisa", "Wukong" -> "MonkeyKing". */
export function ddragonId(name: string): string {
  const key = name.toLowerCase().replace(/[^a-z0-9]/g, '')
  if (DDRAGON_ID_OVERRIDES[key]) return DDRAGON_ID_OVERRIDES[key]
  return name
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join('')
}

/** Square portrait (120x120), versioned. */
export function squareUrl(name: string, version: string): string {
  return `${CDN}/cdn/${version}/img/champion/${ddragonId(name)}.png`
}

/** Full splash art of the base skin (unversioned). */
export function splashUrl(name: string): string {
  return `${CDN}/cdn/img/champion/splash/${ddragonId(name)}_0.jpg`
}

/** Tall loading-screen art of the base skin (unversioned). */
export function loadingUrl(name: string): string {
  return `${CDN}/cdn/img/champion/loading/${ddragonId(name)}_0.jpg`
}

export async function fetchLatestVersion(): Promise<string> {
  try {
    const res = await fetch(`${CDN}/api/versions.json`)
    if (!res.ok) return FALLBACK_VERSION
    const versions = (await res.json()) as string[]
    return versions[0] ?? FALLBACK_VERSION
  } catch {
    return FALLBACK_VERSION
  }
}
