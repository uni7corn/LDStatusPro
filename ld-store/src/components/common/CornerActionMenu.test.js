// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import CornerActionMenu from './CornerActionMenu.vue'
let wrapper
afterEach(() => { wrapper?.unmount(); vi.useRealTimers() })
it('keeps collapsed actions inert, restores focus on Escape, and routes announcements from the expanded menu', async () => {
  vi.useFakeTimers()
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/')
  await router.isReady()
  wrapper = mount(CornerActionMenu, { attachTo: document.body, global: { plugins: [router] } })
  await vi.advanceTimersByTimeAsync(450)
  expect(wrapper.findAll('.corner-action[inert]')).toHaveLength(4)
  const trigger = wrapper.get('[aria-label="快捷菜单"]')
  await trigger.trigger('click')
  expect(wrapper.findAll('.corner-action[inert]')).toHaveLength(0)
  const link = wrapper.get('[aria-label="公告中心"]')
  link.element.focus()
  await link.trigger('keydown', { key: 'Escape' })
  expect(trigger.attributes('aria-expanded')).toBe('false')
  expect(document.activeElement).toBe(trigger.element)
  await trigger.trigger('click')
  await link.trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/announcements')
  expect(trigger.attributes('aria-expanded')).toBe('false')
})
