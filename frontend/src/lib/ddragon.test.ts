import { describe, expect, it } from 'vitest'
import { ddragonId, minimapUrl, splashUrl, squareUrl } from './ddragon'

describe('ddragonId', () => {
  it('joins multi-word names', () => {
    expect(ddragonId('Lee Sin')).toBe('LeeSin')
    expect(ddragonId('Jarvan IV')).toBe('JarvanIV')
    expect(ddragonId('Dr.Mundo')).toBe('DrMundo')
    expect(ddragonId('K Sante')).toBe('KSante')
    expect(ddragonId('Rek Sai')).toBe('RekSai')
    expect(ddragonId('Aurelion Sol')).toBe('AurelionSol')
  })
  it('uses Riot ids for the irregular names', () => {
    expect(ddragonId('Cho Gath')).toBe('Chogath')
    expect(ddragonId('Kai Sa')).toBe('Kaisa')
    expect(ddragonId('Kha Zix')).toBe('Khazix')
    expect(ddragonId('Vel Koz')).toBe('Velkoz')
    expect(ddragonId('Bel Veth')).toBe('Belveth')
    expect(ddragonId('Wukong')).toBe('MonkeyKing')
    expect(ddragonId('Nunu & Willump')).toBe('Nunu')
    expect(ddragonId('Renata Glasc')).toBe('Renata')
    expect(ddragonId('Leblanc')).toBe('Leblanc')
  })
  it('builds CDN urls', () => {
    expect(squareUrl('Miss Fortune', '15.1.1')).toBe('https://ddragon.leagueoflegends.com/cdn/15.1.1/img/champion/MissFortune.png')
    expect(splashUrl('Ahri')).toBe('https://ddragon.leagueoflegends.com/cdn/img/champion/splash/Ahri_0.jpg')
    expect(minimapUrl('15.1.1')).toBe('https://ddragon.leagueoflegends.com/cdn/15.1.1/img/map/map11.png')
  })
})
