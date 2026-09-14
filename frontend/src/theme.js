/* Two palettes, one per theme.
 *
 * noir - the original neon-on-#0a0e14 board. Its 8 series slots were generated
 * for that surface and verified with the dataviz palette validator (dark):
 *   lightness band PASS - chroma floor PASS - contrast >=3:1 PASS
 *   worst adjacent CVD dE 12.4 (deutan), tritan 20.4, normal vision dE 20.5
 * cream - the warm off-white planner look. Same 8 hues, darkened so every slot
 * clears 3:1 against #fbf9f4.
 * Do not hand-edit a slot without re-running that validator.
 *
 * The brand accents (neon teal / near-black ink) are deliberately NOT series
 * colors - they are reserved for chrome: borders, glow, the clock, focus rings.
 */
export const PALETTES = {
  noir: {
    surface: '#0a0e14',
    grid: '#1b2430',
    axisText: '#7d8b9e',
    cursor: 'rgba(0, 255, 204, 0.05)',
    accent: '#00ffcc',
    accentSoft: '#a78bfa',
    up: '#3fd68b',
    down: '#ff6b7a',
    warn: '#ffb45c', // temperature "warm" band - text-legible on #0a0e14
    blue: '#0081c6',
    neutral: '#6b7688', // "Other" is a remainder, not an identity
    series: [
      '#00ac7f', // teal
      '#974aa3', // purple
      '#00a6af', // cyan
      '#c54f3b', // terracotta
      '#0081c6', // blue
      '#c07000', // amber
      '#7478e1', // periwinkle
      '#ce577f', // rose
    ],
  },
  cream: {
    surface: '#fbf9f4',
    grid: '#e6dfd2',
    axisText: '#8c8274',
    cursor: 'rgba(31, 28, 25, 0.04)',
    accent: '#1f1c19',
    accentSoft: '#8a7b68',
    up: '#3b8a5c',
    down: '#c0503e',
    warn: '#b3832a',
    blue: '#2b62a8',
    neutral: '#8a8378',
    series: [
      '#2f7d5e', // teal
      '#7a4f9e', // purple
      '#1f6f8b', // cyan
      '#b3492f', // terracotta
      '#2b62a8', // blue
      '#a86a00', // amber
      '#5c5fc7', // periwinkle
      '#b1456f', // rose
    ],
  },
}

export const THEMES = Object.keys(PALETTES)
export const DEFAULT_THEME = 'cream'

/* Productivity categories reuse validated slots rather than inventing colors:
 * teal (slot 0) / neutral grey / terracotta (slot 3). Those three are the
 * widest-separated trio in the set under normal and CVD vision alike. */
export function categoryColors(palette) {
  return {
    productive: palette.series[0],
    neutral: palette.neutral,
    leisure: palette.series[3],
  }
}

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
 * it, so yesterday's "VS Code is teal" still holds after the ranking shifts.
 * The slot index is what persists; the theme decides which hue fills it. */
export function colorForApp(app, palette) {
  const series = palette.series
  if (app === 'Other') return palette.neutral
  if (assignments[app] != null) return series[assignments[app] % series.length]

  const taken = new Set(Object.values(assignments))
  let slot = series.findIndex((_, i) => !taken.has(i))
  if (slot === -1) slot = Object.keys(assignments).length % series.length
  assignments = { ...assignments, [app]: slot }
  persist()
  return series[slot]
}
