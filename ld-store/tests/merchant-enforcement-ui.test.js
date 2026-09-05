import { readFileSync } from 'node:fs'
import { URL } from 'node:url'
import { describe, expect, it } from 'vitest'

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}

describe('卖家禁用状态 UI', () => {
  it('在卖家后台持续展示原因，同时保留订单处理和购买说明', () => {
    const layout = readSource('../src/layouts/SellerLayout.vue')
    expect(layout).toContain('卖家功能已被平台禁用')
    expect(layout).toContain('购买其他商家的物品不受影响')
    expect(layout).toContain('处理已付款订单')
    expect(layout).toContain('aria-live="assertive"')
  })

  it('发布与编辑路由要求有效卖家权限', () => {
    const router = readSource('../src/router/index.js')
    expect(router).toMatch(/name:\s*'SellerPublish'[\s\S]*requiresSelling:\s*true/)
    expect(router).toMatch(/name:\s*'SellerEdit'[\s\S]*requiresSelling:\s*true/)
    expect(router).toContain("query: { sellingDisabled: '1' }")
  })

  it('状态存储轮询专用权限接口且不复用收款配置状态', () => {
    const store = readSource('../src/stores/merchantEnforcement.js')
    const service = readSource('../src/services/shop/merchantService.ts')
    expect(store).toContain('fetchMerchantEnforcementRequest()')
    expect(service).toContain("api.get('/api/shop/merchant/enforcement')")
    expect(store).toContain("enforcement.value.status === 'disabled'")
    expect(store).not.toContain('@/utils/api')
  })
})
