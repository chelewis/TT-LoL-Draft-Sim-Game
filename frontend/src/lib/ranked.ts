/** League ranked art (from CommunityDragon, loaded straight by the browser) and the colours used to show strength. */

const ASSETS = 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images'

/** The large ranked emblem for a tier (a 1280x720 image with the crest in the middle). */
export function rankEmblemUrl(tier: string): string {
  return `${ASSETS}/ranked-emblem/emblem-${tier.toLowerCase()}.png`
}

/** The small ranked crest for a tier, or the unranked crest. */
export function rankCrestUrl(tier: string | null | undefined): string {
  return `${ASSETS}/ranked-mini-crests/${(tier ?? 'unranked').toLowerCase()}.svg`
}

/** Text colour for each ranked tier, close to the tier's emblem. */
export const TIER_COLOUR: Record<string, string> = {
  IRON: '#a19d94',
  BRONZE: '#cd8b62',
  SILVER: '#b4c1cc',
  GOLD: '#f2c14e',
  PLATINUM: '#4fd1c5',
  EMERALD: '#3ecf8e',
  DIAMOND: '#7aa2ff',
  MASTER: '#c77dff',
  GRANDMASTER: '#ff5b6e',
  CHALLENGER: '#f7d774',
}

export function tierColour(tier: string | null | undefined): string {
  return (tier && TIER_COLOUR[tier.toUpperCase()]) || 'var(--muted)'
}

/** Highest stat total a player can have (5 stats of 10). */
export const MAX_STAT_TOTAL = 50

export interface RatingBand { label: string; colour: string }

/** Strength band for a stat total per player; the thresholds follow the Riot rank stat ceilings (28 / 32 / 36 / 40 / 48). */
const BANDS: [number, RatingBand][] = [
  [44, { label: 'Elite', colour: '#f7d774' }],
  [40, { label: 'Pro', colour: '#c77dff' }],
  [36, { label: 'Strong', colour: '#7aa2ff' }],
  [32, { label: 'Solid', colour: '#3ecf8e' }],
  [28, { label: 'Average', colour: '#4fd1c5' }],
  [0, { label: 'Developing', colour: '#ff8a5b' }],
]

/** Band for one player's stat total, or for a team's average stat total per player. */
export function ratingBand(perPlayer: number): RatingBand {
  return BANDS.find(([min]) => perPlayer >= min)![1]
}
