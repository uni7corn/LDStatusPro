// @vitest-environment jsdom
/* global document, URL */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'
import { nextTick } from 'vue'
import { previewCampaign, previewResponse } from './fixtures/liquid-tabs-data.js'
import LiquidTabs from '../src/components/common/LiquidTabs.vue'
import CouponManage from '../src/views/CouponManage.vue'
import SellerRefunds from '../src/views/seller/SellerRefunds.vue'
import SellerDashboard from '../src/views/seller/SellerDashboard.vue'
import MerchantServices from '../src/views/MerchantServices.vue'
import Orders from '../src/views/Orders.vue'

const requests = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), request: vi.fn() }))
vi.mock('../src/utils/api', () => ({ api: requests }))

let wrappers = []
let pinia

async function page(component, path, props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { render: () => null } }] })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    attachTo: document.body,
    props,
    global: { plugins: [pinia, router], stubs: { SellerTrendChart: true } }
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

function buttonByText(wrapper, text) {
  const button = wrapper.findAll('button').find(item => item.isVisible() && item.text() === text)
  if (!button) throw new Error(`No visible button: ${text}`)
  return button
}

beforeEach(() => {
  pinia = createPinia()
  requests.get.mockReset().mockImplementation(async url => previewResponse(url))
  requests.post.mockReset().mockImplementation(() => { throw new Error('Writes disabled') })
  requests.request.mockReset().mockImplementation(() => { throw new Error('Writes disabled') })
  vi.stubGlobal('requestAnimationFrame', () => 1)
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
})

afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount())
  wrappers = []
  pinia._s.forEach(store => store.$dispose())
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
  expect(requests.post).not.toHaveBeenCalled()
  expect(requests.request).not.toHaveBeenCalled()
})

describe('migrated seller pages', () => {
  it('preserves coupon draft input across automatic keyboard tabs and keeps panel links valid', async () => {
    const { wrapper } = await page(CouponManage, '/seller/coupons')
    expect(wrapper.findComponent(LiquidTabs).props('activation')).toBe('automatic')
    wrapper.get('#coupon-list-tab').element.focus()
    await wrapper.get('#coupon-list-tab').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('#coupon-create-panel').isVisible()).toBe(true)
    const name = wrapper.get('input[maxlength="60"]')
    await name.setValue('仍然保留的草稿')
    await wrapper.get('#coupon-create-tab').trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.get('#coupon-create-panel').isVisible()).toBe(false)
    expect(wrapper.get('#coupon-create-panel').exists()).toBe(true)
    await wrapper.get('#coupon-list-tab').trigger('keydown', { key: 'End' })
    expect(name.element.value).toBe('仍然保留的草稿')
    expect(wrapper.get('#coupon-create-panel').attributes('aria-labelledby')).toBe('coupon-create-tab')
  })

  it('reopens the coupon drawer with working tabs and valid panel links', async () => {
    const { wrapper } = await page(CouponManage, '/seller/coupons')
    await wrapper.get('.campaign-identity').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').isVisible()).toBe(true)
    wrapper.get('#coupon-claims-tab').element.focus()
    await wrapper.get('#coupon-claims-tab').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('#coupon-events-panel').isVisible()).toBe(true)
    expect(wrapper.get('#coupon-claims-panel').isVisible()).toBe(false)
    await wrapper.get('button[aria-label="关闭详情"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('.campaign-identity').trigger('click')
    await flushPromises()
    expect(wrapper.get('#coupon-events-tab').attributes('aria-selected')).toBe('true')
    await wrapper.get('#coupon-events-tab').trigger('keydown', { key: 'Home' })
    expect(wrapper.get('#coupon-claims-panel').isVisible()).toBe(true)
    expect(requests.get).toHaveBeenCalledWith(`/api/shop/merchant/coupons/${previewCampaign.id}`)
  })

  it('keeps refund counts, search, page reset, and browser back/forward in sync', async () => {
    const { wrapper, router } = await page(SellerRefunds, '/seller/refunds?status=requested&page=3&search=sample')
    const tabs = wrapper.findComponent(LiquidTabs)
    expect(tabs.attributes('role')).toBe('group')
    expect(tabs.findAll('.tab-badge').map(badge => badge.text())).toContain('0')
    await buttonByText(tabs, '执行异常0').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ status: 'exception', search: 'sample' })
    expect(requests.get.mock.calls.at(-1)[0]).toContain('status=exception')
    router.back()
    await flushPromises()
    expect(tabs.props('modelValue')).toBe('requested')
    expect(router.currentRoute.value.query.page).toBe('3')
    router.forward()
    await flushPromises()
    expect(tabs.props('modelValue')).toBe('exception')
  })

  it('loads service panels only on activation and preserves query normalization', async () => {
    const { wrapper, router } = await page(MerchantServices, '/seller/services?tab=service&from=preview')
    expect(requests.get.mock.calls.map(([url]) => url)).toEqual(['/api/shop/top-service/options'])
    const tabs = wrapper.findComponent(LiquidTabs)
    expect(tabs.props('layout')).toBe('equal')
    expect(tabs.findAll('.tab-description')).toHaveLength(3)
    wrapper.get('#merchant-tab-service').element.focus()
    await wrapper.get('#merchant-tab-service').trigger('keydown', { key: 'ArrowRight' })
    expect(router.currentRoute.value.query.tab).toBe('service')
    expect(requests.get).toHaveBeenCalledTimes(1)
    await wrapper.get('#merchant-tab-board').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'board', from: 'preview' })
    expect(requests.get.mock.calls.at(-1)[0]).toBe('/api/shop/top-service/board')
    expect(wrapper.get('#merchant-panel-board').isVisible()).toBe(true)
    await wrapper.get('#merchant-tab-orders').trigger('click')
    await flushPromises()
    expect(requests.get.mock.calls.at(-1)[0]).toContain('/api/shop/top-service/orders?')
    await router.push({ query: { tab: 'not-a-tab' } })
    await flushPromises()
    expect(wrapper.get('#merchant-tab-service').attributes('aria-selected')).toBe('true')
  })

  it('retains dashboard range loading disablement and local chart metric switching', async () => {
    const { wrapper } = await page(SellerDashboard, '/seller/dashboard')
    let finish
    requests.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const range = wrapper.findAllComponents(LiquidTabs)[0]
    await buttonByText(range, '近 7 天').trigger('click')
    expect(range.findAll('button:disabled')).toHaveLength(3)
    await buttonByText(range, '近 90 天').trigger('click')
    expect(requests.get.mock.calls.at(-1)[0]).toBe('/api/shop/merchant/dashboard?range=7d')
    finish(previewResponse('/api/shop/merchant/dashboard'))
    await flushPromises()
    expect(range.findAll('button:disabled')).toHaveLength(0)
    const count = requests.get.mock.calls.length
    await buttonByText(wrapper.findAllComponents(LiquidTabs)[1], '浏览').trigger('click')
    expect(wrapper.findAllComponents(LiquidTabs)[1].props('modelValue')).toBe('views')
    expect(requests.get).toHaveBeenCalledTimes(count)
  })

  it('keeps order tab selection and focus independent from list loading feedback', async () => {
    const { wrapper } = await page(Orders, '/seller/orders?source=product&page=3', { sellerMode: true })
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    let finish
    requests.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const [sources, statuses] = wrapper.findAllComponents(LiquidTabs)
    const ledger = wrapper.get('.seller-order-ledger')
    const paid = buttonByText(statuses, '待发货')
    paid.element.focus()
    await paid.trigger('click')

    for (const tabs of [sources, statuses]) {
      expect(tabs.classes()).not.toContain('is-switching')
      expect(tabs.attributes('aria-busy')).toBeUndefined()
    }
    expect(document.activeElement).toBe(paid.element)
    expect(sources.props('modelValue')).toBe('seller')
    expect(buttonByText(sources, '商品订单').attributes('aria-pressed')).toBe('true')
    expect(statuses.props('modelValue')).toBe('paid')
    expect(ledger.attributes('aria-busy')).toBe('true')
    expect(ledger.classes()).toContain('is-filter-pending')
    expect(ledger.attributes('inert')).toBe('')

    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()
    // The debounce ended, but the list is still waiting for its response.
    expect(ledger.classes()).not.toContain('is-filter-pending')
    expect(ledger.attributes('aria-busy')).toBe('true')
    expect(document.activeElement).toBe(paid.element)
    finish(previewResponse('/api/shop/orders'))
    await flushPromises()
    expect(ledger.attributes('aria-busy')).toBe('false')
    expect(ledger.attributes('inert')).toBeUndefined()
  })

  it('does not highlight the status shell when returning to product orders', async () => {
    const { wrapper, router } = await page(Orders, '/seller/orders?source=service', { sellerMode: true })
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const sources = wrapper.findComponent(LiquidTabs)
    const product = buttonByText(sources, '商品订单')
    product.element.focus()
    await product.trigger('click')
    const statuses = wrapper.findAllComponents(LiquidTabs)[1]
    expect(sources.classes()).not.toContain('is-switching')
    expect(statuses.classes()).not.toContain('is-switching')
    expect(statuses.attributes('aria-busy')).toBeUndefined()
    expect(statuses.element.contains(document.activeElement)).toBe(false)
    expect(buttonByText(statuses, '全部').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.seller-order-ledger').attributes('aria-busy')).toBe('true')
    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()
    expect(router.currentRoute.value.query.source).toBe('product')
    expect(wrapper.get('.seller-order-ledger').attributes('aria-busy')).toBe('false')
  })

  it('retains debounced order switching, page reset, and the other-status API mapping', async () => {
    const { wrapper, router } = await page(Orders, '/seller/orders?source=product&page=4', { sellerMode: true })
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const statuses = wrapper.findAllComponents(LiquidTabs)[1]
    await buttonByText(statuses, '待发货').trigger('click')
    await buttonByText(statuses, '其他').trigger('click')
    expect(router.currentRoute.value.query.page).toBe('4')
    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()
    expect(router.currentRoute.value.query.status).toBe('other')
    expect(router.currentRoute.value.query.page).toBeUndefined()
    const orderCalls = requests.get.mock.calls.map(([url]) => url).filter(url => url.startsWith('/api/shop/orders?'))
    expect(new URL(orderCalls.at(-1), 'http://test.invalid').searchParams.get('status')).toBe('refund_pending,refunded,external_dispute')
    await buttonByText(wrapper.findAllComponents(LiquidTabs)[0], '求购服务').trigger('click')
    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()
    expect(router.currentRoute.value.query.source).toBe('service')
    expect(wrapper.findAllComponents(LiquidTabs)).toHaveLength(1)
    await router.push('/seller/orders?source=product&status=delivered&page=2')
    await nextTick()
    await flushPromises()
    expect(wrapper.findAllComponents(LiquidTabs)[1].props('modelValue')).toBe('delivered')
  })
})
