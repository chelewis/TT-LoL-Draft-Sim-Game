import { describe, expect, it } from 'vitest'
import { rankCrestUrl, rankEmblemUrl, ratingBand, tierColour } from './ranked'

describe('ratingBand', () => {
  it('bands a stat total per player', () => {
    expect(ratingBand(48).label).toBe('Elite')
    expect(ratingBand(40).label).toBe('Pro')
    expect(ratingBand(36.5).label).toBe('Strong')
    expect(ratingBand(32).label).toBe('Solid')
    expect(ratingBand(28).label).toBe('Average')
    expect(ratingBand(12).label).toBe('Developing')
  })
})

describe('ranked art', () => {
  it('builds lower-case tier URLs and falls back to unranked', () => {
    expect(rankEmblemUrl('GOLD')).toMatch(/ranked-emblem\/emblem-gold\.png$/)
    expect(rankCrestUrl('GRANDMASTER')).toMatch(/ranked-mini-crests\/grandmaster\.svg$/)
    expect(rankCrestUrl(null)).toMatch(/ranked-mini-crests\/unranked\.svg$/)
  })
  it('colours known tiers and mutes the rest', () => {
    expect(tierColour('gold')).toBe('#f2c14e')
    expect(tierColour(null)).toBe('var(--muted)')
  })
})
