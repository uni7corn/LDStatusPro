import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getDiscoveryRequestHeaders, getDiscoverySessionId } from '../src/utils/discovery'
import {
  clearDiscoveryTokenForProduct,
  getDiscoveryTokenForProduct,
  rememberDiscoveryToken,
} from '../src/services/shop/discoveryService'

function createMemoryStorage() {
  const values = new Map()
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null },
    setItem(key, value) { values.set(key, String(value)) },
    removeItem(key) { values.delete(key) },
  }
}

describe('商城发现会话与归因', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      sessionStorage: createMemoryStorage(),
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    })
    vi.stubGlobal('navigator', { globalPrivacyControl: false, doNotTrack: '0' })
    vi.stubGlobal('crypto', { randomUUID: () => '9ec0bb58-d9eb-4e53-9dc7-a9c4c0a54a26' })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('同一标签页复用匿名 UUID，并且只给商城请求添加发现头', () => {
    expect(getDiscoverySessionId()).toBe('9ec0bb58-d9eb-4e53-9dc7-a9c4c0a54a26')
    expect(getDiscoverySessionId()).toBe('9ec0bb58-d9eb-4e53-9dc7-a9c4c0a54a26')
    expect(getDiscoveryRequestHeaders('/api/shop/products')).toEqual({
      'X-Discovery-Session': '9ec0bb58-d9eb-4e53-9dc7-a9c4c0a54a26',
    })
    expect(getDiscoveryRequestHeaders('/api/auth/me')).toEqual({})
  })

  it('GPC/DNT 开启时不创建会话，只发送退出标记', () => {
    vi.stubGlobal('navigator', { globalPrivacyControl: true, doNotTrack: '1' })
    expect(getDiscoverySessionId()).toBe('')
    expect(getDiscoveryRequestHeaders('/api/shop/products')).toEqual({ 'X-Discovery-Privacy': 'opt-out' })
  })

  it('点击商品后按商品保存签名令牌，并可在下单成功后清理', () => {
    expect(rememberDiscoveryToken({ id: 42, discoveryToken: 'd1.payload.signature' })).toBe('d1.payload.signature')
    expect(getDiscoveryTokenForProduct(42)).toBe('d1.payload.signature')
    clearDiscoveryTokenForProduct(42)
    expect(getDiscoveryTokenForProduct(42)).toBe('')
  })
})
