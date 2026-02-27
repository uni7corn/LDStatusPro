import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { storage } from '@/utils/storage'
import { isTokenExpired } from '@/utils/auth'
import { resolveAvatarUrl, buildFallbackAvatar } from '@/utils/avatar'

export const useUserStore = defineStore('user', () => {
  // 状态
  const token = ref(null)
  const user = ref(null)
  const loading = ref(false)

  // 计算属性
  const isLoggedIn = computed(() => {
    if (!token.value || !user.value) return false
    return !isTokenExpired(token.value)
  })
  const username = computed(() => user.value?.username || '')
  const avatarSeed = computed(() =>
    user.value?.name || user.value?.username || user.value?.id || 'user'
  )
  const avatar = computed(() =>
    resolveAvatarUrl(user.value?.avatar || user.value?.avatar_url || '', 128)
      || buildFallbackAvatar(avatarSeed.value, 128)
  )
  const trustLevel = computed(() => user.value?.trust_level || user.value?.trustLevel || null)

  // 恢复会话
  async function restoreSession() {
    const savedToken = storage.get('token')
    const savedUser = storage.get('user')

    if (!savedToken || !savedUser) {
      if (savedToken || savedUser) {
        logout()
      }
      return false
    }

    if (isTokenExpired(savedToken)) {
      logout()
      return false
    }

    token.value = savedToken
    user.value = savedUser
    return true
  }

  // 登录
  async function login(authToken, userData) {
    if (!authToken || !userData || isTokenExpired(authToken)) {
      logout()
      return false
    }

    token.value = authToken
    user.value = userData
    storage.set('token', authToken)
    storage.set('user', userData)
    return true
  }

  // 登出
  function logout() {
    token.value = null
    user.value = null
    storage.remove('token')
    storage.remove('user')
  }

  // 更新用户信息
  function updateUser(data) {
    user.value = { ...user.value, ...data }
    storage.set('user', user.value)
  }

  function ensureValidSession() {
    if (!token.value || !user.value) return false
    if (isTokenExpired(token.value)) {
      logout()
      return false
    }
    return true
  }

  return {
    // 状态
    token,
    user,
    loading,
    // 计算属性
    isLoggedIn,
    username,
    avatar,
    trustLevel,
    // 方法
    restoreSession,
    login,
    logout,
    updateUser,
    ensureValidSession
  }
})
