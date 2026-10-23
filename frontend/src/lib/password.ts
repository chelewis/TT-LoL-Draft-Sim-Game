/** Letters and digits that can't be confused when read aloud or copied by hand (no 0/O, 1/l/I). */
export const PASSWORD_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'

/** A random password for an admin to hand to a user, from the browser's secure random source. */
export function generatePassword(length = 16, random: (bytes: Uint32Array) => Uint32Array = (b) => crypto.getRandomValues(b)): string {
  const values = random(new Uint32Array(length))
  return Array.from(values, (v) => PASSWORD_ALPHABET[v % PASSWORD_ALPHABET.length]).join('')
}
