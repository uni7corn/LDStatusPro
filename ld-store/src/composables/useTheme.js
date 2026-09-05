/**
 * 主题切换 composable
 * 支持：跟随系统、浅色模式、深色模式
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 主题模式
export const THEME_MODES = {
  SYSTEM: 'system',
  LIGHT: 'light',
  DARK: 'dark'
}

// 本地存储 key
const STORAGE_KEY = 'ld-store-theme'

// 全局状态
const themeMode = ref(THEME_MODES.SYSTEM)
const isDark = ref(false)

// 系统主题查询
let mediaQuery = null
let transitionTimer = null

/**
 * 获取系统主题偏好
 */
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/**
 * 应用主题到 DOM
 */
function applyTheme(dark, withTransition = true) {
  // 添加过渡类实现平滑切换
  if (withTransition) {
    if (transitionTimer) window.clearTimeout(transitionTimer)
    document.documentElement.classList.add('theme-transition')
  } else {
    if (transitionTimer) window.clearTimeout(transitionTimer)
    transitionTimer = null
    document.documentElement.classList.remove('theme-transition')
  }
  
  isDark.value = dark
  if (dark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
  
  // 过渡结束后移除过渡类
  if (withTransition) {
    transitionTimer = window.setTimeout(() => {
      document.documentElement.classList.remove('theme-transition')
      transitionTimer = null
    }, 300)
  }
}

/**
 * 更新主题
 * @param {boolean} withTransition - 是否使用过渡动画
 */
function updateTheme(withTransition = true) {
  const mode = themeMode.value
  if (mode === THEME_MODES.SYSTEM) {
    applyTheme(getSystemTheme() === 'dark', withTransition)
  } else {
    applyTheme(mode === THEME_MODES.DARK, withTransition)
  }
}

/**
 * 主题切换 hook
 */
export function useTheme() {
  // 初始化
  onMounted(() => {
    // 从本地存储读取偏好
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && Object.values(THEME_MODES).includes(saved)) {
      themeMode.value = saved
    }
    
    // 应用主题（初始化时不使用过渡动画，避免页面加载时闪烁）
    updateTheme(false)
    
    // 监听系统主题变化
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', handleSystemChange)
  })
  
  onUnmounted(() => {
    if (mediaQuery) {
      mediaQuery.removeEventListener('change', handleSystemChange)
    }
  })
  
  // 系统主题变化处理
  function handleSystemChange() {
    if (themeMode.value === THEME_MODES.SYSTEM) {
      updateTheme(false)
    }
  }
  
  // 设置主题模式
  function setTheme(mode) {
    if (!Object.values(THEME_MODES).includes(mode)) return
    themeMode.value = mode
    localStorage.setItem(STORAGE_KEY, mode)
    updateTheme()
  }
  
  // 切换主题（循环切换）
  function toggleTheme() {
    const modes = [THEME_MODES.SYSTEM, THEME_MODES.LIGHT, THEME_MODES.DARK]
    const currentIndex = modes.indexOf(themeMode.value)
    const nextIndex = (currentIndex + 1) % modes.length
    setTheme(modes[nextIndex])
  }
  
  // 主题模式文本
  const themeModeText = computed(() => {
    const texts = {
      [THEME_MODES.SYSTEM]: '跟随系统',
      [THEME_MODES.LIGHT]: '浅色模式',
      [THEME_MODES.DARK]: '深色模式'
    }
    return texts[themeMode.value]
  })
  
  // 主题图标
  const themeIcon = computed(() => {
    if (themeMode.value === THEME_MODES.SYSTEM) return '🌗'
    return isDark.value ? '🌙' : '☀️'
  })
  
  return {
    themeMode,
    isDark,
    themeModeText,
    themeIcon,
    setTheme,
    toggleTheme,
    THEME_MODES
  }
}

// 初始化主题（在应用启动时调用）
export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && Object.values(THEME_MODES).includes(saved)) {
    themeMode.value = saved
  }
  // 初始化时不使用过渡动画
  updateTheme(false)
  
  // 监听系统主题变化（系统切换时使用过渡动画）
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    if (themeMode.value === THEME_MODES.SYSTEM) {
      updateTheme(false)
    }
  })
}
