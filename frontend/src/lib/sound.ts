/** Short synthesized UI sounds (Web Audio), so champ select needs no audio files. */
export type SoundName = 'select' | 'lock' | 'ban' | 'swap' | 'turn' | 'tick' | 'tickUrgent' | 'buzzer' | 'chatSend' | 'chatReceive'

const SOUND_KEY = 'ldm_sound'

interface Note {
  freq: number
  /** seconds after the sound starts */
  at: number
  dur: number
  gain: number
  type: OscillatorType
}

const SOUNDS: Record<SoundName, Note[]> = {
  select: [{ freq: 880, at: 0, dur: 0.05, gain: 0.05, type: 'triangle' }],
  lock: [
    { freq: 523.25, at: 0, dur: 0.12, gain: 0.12, type: 'triangle' },
    { freq: 783.99, at: 0.09, dur: 0.24, gain: 0.12, type: 'triangle' },
  ],
  ban: [
    { freq: 220, at: 0, dur: 0.12, gain: 0.07, type: 'sawtooth' },
    { freq: 164.81, at: 0.09, dur: 0.26, gain: 0.07, type: 'sawtooth' },
  ],
  swap: [
    { freq: 587.33, at: 0, dur: 0.07, gain: 0.07, type: 'sine' },
    { freq: 440, at: 0.07, dur: 0.1, gain: 0.07, type: 'sine' },
  ],
  turn: [
    { freq: 659.25, at: 0, dur: 0.3, gain: 0.18, type: 'sine' },
    { freq: 783.99, at: 0.14, dur: 0.3, gain: 0.18, type: 'sine' },
    { freq: 1046.5, at: 0.28, dur: 0.45, gain: 0.18, type: 'sine' },
  ],
  tick: [{ freq: 1000, at: 0, dur: 0.04, gain: 0.08, type: 'square' }],
  tickUrgent: [{ freq: 1400, at: 0, dur: 0.04, gain: 0.1, type: 'square' }],
  // two detuned low saws beat against each other for a harsh "time's up" buzz
  buzzer: [
    { freq: 110, at: 0, dur: 0.6, gain: 0.14, type: 'sawtooth' },
    { freq: 117, at: 0, dur: 0.6, gain: 0.14, type: 'sawtooth' },
  ],
  chatSend: [{ freq: 740, at: 0, dur: 0.07, gain: 0.05, type: 'sine' }],
  chatReceive: [
    { freq: 932.33, at: 0, dur: 0.08, gain: 0.08, type: 'sine' },
    { freq: 1244.5, at: 0.07, dur: 0.14, gain: 0.08, type: 'sine' },
  ],
}

export function isSoundOn(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) !== '0'
  } catch {
    return true
  }
}

export function setSoundOn(on: boolean): void {
  try {
    localStorage.setItem(SOUND_KEY, on ? '1' : '0')
  } catch {
    /* preference just isn't remembered */
  }
}

let context: AudioContext | null | undefined

function audioContext(): AudioContext | null {
  if (context === undefined) {
    const Ctor = typeof window === 'undefined'
      ? undefined
      : window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    context = Ctor ? new Ctor() : null
  }
  return context
}

function schedule(ac: AudioContext, notes: Note[]) {
  const t0 = ac.currentTime + 0.01
  for (const n of notes) {
    const osc = ac.createOscillator()
    const gain = ac.createGain()
    const start = t0 + n.at
    osc.type = n.type
    osc.frequency.value = n.freq
    gain.gain.setValueAtTime(0.0001, start)
    gain.gain.exponentialRampToValueAtTime(n.gain, start + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + n.dur)
    osc.connect(gain).connect(ac.destination)
    osc.start(start)
    osc.stop(start + n.dur + 0.02)
  }
}

/** Plays a sound if sound is on and the browser allows it; never throws. */
export function playSound(name: SoundName): void {
  if (!isSoundOn()) return
  try {
    const ac = audioContext()
    if (!ac) return
    if (ac.state === 'running') {
      schedule(ac, SOUNDS[name])
      return
    }
    // Browsers keep audio suspended until the first click. Drop the sound unless it can start right away,
    // so a stale chime doesn't play whenever the page is finally clicked.
    const asked = performance.now()
    void ac.resume().then(() => {
      if (performance.now() - asked < 300) schedule(ac, SOUNDS[name])
    })
  } catch {
    /* audio is a nicety */
  }
}
