// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ManualDeliveryEditor from '../src/components/orders/ManualDeliveryEditor.vue'
import { useOrderActions } from '../src/composables/orders/useOrderActions'
import { useOrderDetail } from '../src/composables/orders/useOrderDetail'
import { useOrderListController } from '../src/composables/orders/useOrderListController'

afterEach(() => {
  vi.useRealTimers()
})

function orderPage(orderNo, page = 1, totalPages = 1) {
  return {
    success: true,
    status: 200,
    data: {
      orders: [{ orderNo, status: 'pending' }],
      pagination: { page, pageSize: 20, total: totalPages, totalPages }
    }
  }
}

describe('order list controller', () => {
  it('aborts stale filters and prevents late responses from replacing current orders', async () => {
    const pending = []
    const queries = []
    const controller = useOrderListController({
      buildQuery: (page, signal) => ({ page, signal }),
      fetchPage: query => {
        queries.push(query)
        return new Promise(resolve => pending.push(resolve))
      }
    })

    const staleLoad = controller.load()
    const currentLoad = controller.load()
    expect(queries[0].signal.aborted).toBe(true)
    pending[1](orderPage('CURRENT'))
    await currentLoad
    pending[0](orderPage('STALE'))
    await staleLoad

    expect(controller.orders.value.map(order => order.orderNo)).toEqual(['CURRENT'])
    expect(controller.loading.value).toBe(false)
  })

  it('appends pages and stops at the authoritative total page', async () => {
    const fetchPage = vi.fn(async query => orderPage(`ORDER-${query.page}`, query.page, 2))
    const controller = useOrderListController({
      buildQuery: (page, signal) => ({ page, signal }),
      fetchPage
    })
    await controller.load()
    expect(controller.hasMore.value).toBe(true)
    await controller.loadMore()
    expect(controller.orders.value.map(order => order.orderNo)).toEqual(['ORDER-1', 'ORDER-2'])
    expect(controller.hasMore.value).toBe(false)
  })
})

describe('order actions and detail lifecycle', () => {
  it('keeps one busy owner per action and always releases it', async () => {
    const actions = useOrderActions()
    let finish
    const first = actions.run('cancel', 'A', () => new Promise(resolve => { finish = resolve }))
    expect(actions.cancellingOrderId.value).toBe('A')
    await expect(actions.run('cancel', 'B', async () => ({ success: true }))).resolves.toBeNull()
    finish({ success: true })
    await first
    expect(actions.cancellingOrderId.value).toBeNull()

    await expect(actions.run('deliver', 'A', async () => { throw new Error('failed') })).rejects.toThrow('failed')
    expect(actions.deliveringOrderId.value).toBeNull()
  })

  it('cancels stale detail loads and stops visible-order polling', async () => {
    vi.useFakeTimers()
    const pending = []
    const signals = []
    const fetchDetail = vi.fn((orderId, role, signal) => {
      signals.push(signal)
      return new Promise(resolve => pending.push(resolve))
    })
    const detail = useOrderDetail({ orderId: ref('A'), role: ref('buyer'), fetchDetail, refreshIntervalMs: 1_000 })
    const staleLoad = detail.load()
    const currentLoad = detail.load()
    expect(signals[0].aborted).toBe(true)
    pending[1]({ success: true, status: 200, data: { order: { orderNo: 'CURRENT', status: 'paid' }, logs: [] } })
    await currentLoad
    pending[0]({ success: true, status: 200, data: { order: { orderNo: 'STALE', status: 'paid' }, logs: [] } })
    await staleLoad
    expect(detail.order.value.orderNo).toBe('CURRENT')

    detail.startAutoRefresh(() => true)
    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetchDetail).toHaveBeenCalledTimes(3)
    detail.stop()
    await vi.advanceTimersByTimeAsync(2_000)
    expect(fetchDetail).toHaveBeenCalledTimes(3)
  })
})

describe('manual delivery editor', () => {
  it('keeps labelled seller input and emits trimmed-gated submission controls', async () => {
    const wrapper = mount(ManualDeliveryEditor, {
      props: {
        modelValue: '',
        inputId: 'delivery-42',
        placeholder: '填写交付内容',
        hint: '请确认内容',
        variant: 'seller'
      }
    })
    expect(wrapper.get('label').attributes('for')).toBe('delivery-42')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('已完成交付')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['已完成交付'])
  })
})
