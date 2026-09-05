;(() => {
  let themeMode = 'system'

  try {
    themeMode = globalThis.localStorage.getItem('ld-store-theme') || themeMode
  } catch {
    // localStorage 不可用时回退到系统主题
  }

  const shouldUseDarkTheme = themeMode === 'dark'
    || (themeMode !== 'light' && globalThis.matchMedia('(prefers-color-scheme: dark)').matches)

  globalThis.document.documentElement.classList.toggle('dark', shouldUseDarkTheme)
})()
