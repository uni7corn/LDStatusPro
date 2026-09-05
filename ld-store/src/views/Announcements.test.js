// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import { reactive } from 'vue'
import Announcements from './Announcements.vue'

const mocks = vi.hoisted(() => ({ center: vi.fn(), detail: vi.fn(), acknowledge: vi.fn(), track: vi.fn(), account: null }))
vi.mock('@/services/announcementService', () => ({ fetchAnnouncementCenter: mocks.center, fetchAnnouncementDetail: mocks.detail, acknowledgeAnnouncement: mocks.acknowledge }))
vi.mock('@/stores/user', () => ({ useUserStore: () => mocks.account }))
vi.mock('@/utils/announcementPreferences', () => ({ announcementIdentity: account => account.identity }))
vi.mock('@/utils/announcementTelemetry', () => ({ announcementImpression: {}, trackAnnouncement: mocks.track }))
const entry = { id: 11, title: '发货规则', summary: '了解发货时限', content: '请及时发货。', contentType: 'text', status: 'active', contentVersion: 2, createdAt: '2026-09-05T00:00:00Z', requiresAcknowledgement: true, actionUrl: '/docs/shipping-deadline', actionLabel: '查看规则' }
let wrapper
beforeEach(() => {
  vi.resetAllMocks()
  mocks.account = reactive({ identity: 'user-a', isLoggedIn: true })
  mocks.center.mockResolvedValue({ success: true, data: { items: [entry], pagination: { total: 42, totalPages: 3 } } })
  mocks.detail.mockResolvedValue({ success: true, data: { item: entry } })
  mocks.acknowledge.mockResolvedValue({ success: true })
})
afterEach(() => { wrapper?.unmount() })
async function open(path) {
  const router = createRouter({ history: createMemoryHistory(), routes: [ { path: '/announcements/:id?', component: Announcements }, { path: '/:pathMatch(.*)*', component: { template: '<div />' } } ] })
  await router.push(path)
  await router.isReady()
  wrapper = mount(Announcements, { global: { plugins: [router] } })
  await flushPromises()
  return router
}
it('keeps search, status and page when opening a detail and returning to results', async () => {
  const router = await open('/announcements?q=发货&status=expired&page=2')
  expect(mocks.center).toHaveBeenLastCalledWith({ page: 2, search: '发货', status: 'expired' }, expect.any(AbortSignal))
  await wrapper.get('.announcement-list-item').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.params.id).toBe('11')
  expect(wrapper.get('.announcement-document-header h1').text()).toBe('发货规则')
  await wrapper.get('.announcement-navigation a').trigger('click')
  await flushPromises()
  expect(wrapper.get('input').element.value).toBe('发货')
  expect(router.currentRoute.value.query).toEqual({ q: '发货', status: 'expired', page: '2' })
  await wrapper.get('.announcement-reset').trigger('click')
  await flushPromises()
  expect(mocks.center).toHaveBeenLastCalledWith({ page: 1, search: '', status: '' }, expect.any(AbortSignal))
})
it('submits search, resets pagination on status changes, and advances pages with the applied search', async () => {
  const router = await open('/announcements')
  await wrapper.get('input').setValue('规则')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(router.currentRoute.value.query.q).toBe('规则')
  await wrapper.findAll('.announcement-pagination button')[1].trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.page).toBe('2')
  await wrapper.findAll('.announcement-filters button')[2].trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({ q: '规则', status: 'expired' })
})
it('offers retry on failure and filter reset on empty results', async () => {
  mocks.center.mockResolvedValueOnce({ success: false, error: '网络暂时不可用' })
  await open('/announcements?q=无结果')
  expect(wrapper.get('[role="alert"]').text()).toContain('网络暂时不可用')
  mocks.center.mockResolvedValueOnce({ success: true, data: { items: [], pagination: { total: 0, totalPages: 0 } } })
  await wrapper.get('[role="alert"] button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('没有找到相关公告')
  await wrapper.get('.announcement-state button').trigger('click')
  await flushPromises()
  expect(wrapper.findAll('.announcement-list-item')).toHaveLength(1)
})
it('records confirmation against the displayed version and records the action click separately', async () => {
  await open('/announcements/11')
  await wrapper.get('.announcement-acknowledgement button').trigger('click')
  await flushPromises()
  expect(mocks.acknowledge).toHaveBeenCalledWith(11, 2)
  expect(wrapper.get('.announcement-acknowledgement button').attributes('disabled')).toBeDefined()
  expect(wrapper.get('[role="status"]').text()).toContain('已记录本版本')
  wrapper.get('.announcement-document-actions a').element.addEventListener('click', event => event.preventDefault())
  await wrapper.get('.announcement-document-actions a').trigger('click')
  expect(mocks.track).toHaveBeenCalledWith(entry, 'action', 'detail')
})
it('does not apply a pending confirmation to another account', async () => {
  let resolve
  mocks.acknowledge.mockReturnValue(new Promise(done => { resolve = done }))
  await open('/announcements/11')
  await wrapper.get('.announcement-acknowledgement button').trigger('click')
  mocks.account.identity = 'user-b'
  await flushPromises()
  resolve({ success: true })
  await flushPromises()
  expect(wrapper.get('.announcement-acknowledgement button').text()).toBe('我已阅读并知悉')
})
