import { describe, expect, it } from 'vitest'
import { normalizeOrderStatusFilter, toOrderApiStatusFilter } from '../src/utils/orderFilters'

describe('订单状态标签筛选', () => {
  it('将退款与 Credit 处理合并到其他标签', () => {
    expect(normalizeOrderStatusFilter('refunded')).toBe('other')
    expect(normalizeOrderStatusFilter('external_dispute')).toBe('other')
    expect(toOrderApiStatusFilter('other')).toBe('refund_pending,refunded,external_dispute')
  })

  it('保留常用状态并忽略未知状态', () => {
    expect(normalizeOrderStatusFilter('paid')).toBe('paid')
    expect(toOrderApiStatusFilter('delivered')).toBe('delivered')
    expect(normalizeOrderStatusFilter('unknown')).toBe('')
  })
})
