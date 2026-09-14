import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { DEFAULT_THEME, PALETTES } from './theme.js'

const THEME_KEY = 'dashboard.theme.v1'
const ThemeContext = createContext(null)

/* ?theme=noir in the URL wins (handy for a kiosk launcher or a screenshot),
 * then whatever was last chosen in this browser, then the default. */
function initialTheme() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('theme')
    if (fromUrl && PALETTES[fromUrl]) return fromUrl
    const stored = localStorage.getItem(THEME_KEY)
    if (stored && PALETTES[stored]) return stored
  } catch {
    /* no storage (private window, thumbnail capture) - fall through */
  }
  return DEFAULT_THEME
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* cosmetic */
    }
  }, [theme])

  const toggle = useCallback(
    () => setTheme((current) => (current === 'noir' ? 'cream' : 'noir')),
    [],
  )

  const value = useMemo(
    () => ({ theme, setTheme, toggle, palette: PALETTES[theme] }),
    [theme, toggle],
  )
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used inside <ThemeProvider>')
  return context
}

export const usePalette = () => useTheme().palette
