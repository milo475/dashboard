/* Chart colors.
 *
 * The 8 series slots below were generated for the #0a0e14 surface and verified
 * with the dataviz palette validator (dark mode):
 *   lightness band PASS - chroma floor PASS - contrast >=3:1 PASS
 *   worst adjacent CVD dE 12.4 (deutan), tritan 20.4, normal vision dE 20.5
 * Do not hand-edit a slot without re-running that validator.
 *
 * The neon #00ffcc / #a78bfa brand accents are deliberately NOT series colors -
 * they are too light for the band and are reserved for chrome (borders, glow,
 * the clock, focus rings).
 */
export const SERIES = [
  '#00ac7f', // teal
  '#974aa3', // purple
  '#00a6af', // cyan
  '#c54f3b', // terracotta
  '#0081c6', // blue
  '#c07000', // amber
  '#7478e1', // periwinkle
  '#ce577f', // rose
]

export const OTHER_COLOR = '#6b7688' // neutral: "Other" is a remainder, not an identity
export const SURFACE = '#0a0e14'
export const ACCENT = '#00ffcc'
export const ACCENT_SOFT = '#a78bfa'
export const UP = '#3fd68b'
export const DOWN = '#ff6b7a'

const STORAGE_KEY = 'dashboard.appColors.v1'

function loadAssignments() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

let assignments = loadAssignments()

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(assignments))
  } catch {
    /* a lost color assignment is cosmetic - never break the render over it */
  }
}

/* Color follows the app, not its current rank: once an app owns a slot it keeps
 * it, so yesterday's "VS Code is teal" still holds after the ranking shifts. */
export function colorForApp(app) {
  if (app === 'Other') return OTHER_COLOR
  if (assignments[app] != null) return SERIES[assignments[app] % SERIES.length]

  const taken = new Set(Object.values(assignments))
  let slot = SERIES.findIndex((_, i) => !taken.has(i))
  if (slot === -1) slot = Object.keys(assignments).length % SERIES.length
  assignments = { ...assignments, [app]: slot }
  persist()
  return SERIES[slot]
}
