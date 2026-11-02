export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'vigyan-theme'
const VALID_MODES: ThemeMode[] = ['light', 'dark', 'system']

export function getSavedTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)

    if (saved && VALID_MODES.includes(saved as ThemeMode)) {
      return saved as ThemeMode
    }
  } catch {
    // Storage may be unavailable; use the safe default.
  }

  return 'light'
}

export function saveTheme(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // Theme still works for the current page if storage is unavailable.
  }
}

export function isDarkTheme(mode: ThemeMode): boolean {
  if (mode === 'dark') return true
  if (mode === 'light') return false

  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyPreAuthTheme(mode: ThemeMode): void {
  const shell = document.querySelector('.app-shell')

  if (shell) {
    shell.classList.toggle('is-dark', isDarkTheme(mode))
  }
}
