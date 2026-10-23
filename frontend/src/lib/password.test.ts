import { describe, expect, it } from 'vitest'
import { PASSWORD_ALPHABET, generatePassword } from './password'

describe('generatePassword', () => {
  it('makes a password of the requested length from the unambiguous alphabet', () => {
    const p = generatePassword(16)
    expect(p).toHaveLength(16)
    expect([...p].every((c) => PASSWORD_ALPHABET.includes(c))).toBe(true)
    expect(generatePassword(24)).toHaveLength(24)
  })

  it('leaves out characters that are easy to misread', () => {
    for (const c of '0O1lI') expect(PASSWORD_ALPHABET).not.toContain(c)
  })

  it('maps random values onto the alphabet', () => {
    const fixed = (b: Uint32Array) => b.map((_, i) => i)
    expect(generatePassword(3, fixed)).toBe(PASSWORD_ALPHABET.slice(0, 3))
  })

  it('differs between calls', () => {
    expect(generatePassword()).not.toBe(generatePassword())
  })
})
