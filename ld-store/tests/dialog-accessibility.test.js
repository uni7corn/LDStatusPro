// @vitest-environment jsdom
/* global document */
import { afterEach, beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import Dialog from '../src/components/common/Dialog.vue'
import { useUiStore } from '../src/stores/ui'

let wrapper, store, trigger
beforeEach(() => {
  const pinia = createPinia(); setActivePinia(pinia); store = useUiStore()
  trigger = document.createElement('button'); document.body.append(trigger); trigger.focus()
  wrapper = mount(Dialog, { attachTo: document.body, global: { plugins: [pinia] } })
})
afterEach(() => { wrapper.unmount(); trigger.remove() })

it('names the dialog, focuses the safe action, traps Tab, and restores focus on Escape', async () => {
  const result = store.confirm('取消后释放名额', { title: '取消待支付订单', cancelText: '保留订单', confirmText: '确认取消', danger: true })
  await flushPromises()
  const dialog = document.querySelector('[role="dialog"]')
  const cancel = dialog.querySelector('.dialog-btn-cancel')
  const confirm = dialog.querySelector('.dialog-btn-confirm')
  expect(dialog.getAttribute('aria-modal')).toBe('true')
  expect(document.getElementById(dialog.getAttribute('aria-labelledby')).textContent).toBe('取消待支付订单')
  expect(document.activeElement).toBe(cancel)
  await wrapper.getComponent(Dialog).vm.$nextTick()
  cancel.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }))
  expect(document.activeElement).toBe(confirm)
  confirm.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
  expect(document.activeElement).toBe(cancel)
  cancel.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
  expect(await result).toBe(false); await flushPromises()
  expect(document.activeElement).toBe(trigger)
})

it('renders dynamic dialog content as plain text and preserves line breaks', async () => {
  const hostileName = '<img src=x onerror="window.__dialogXss = true"><script>window.__dialogXss = true</script>'
  const result = store.confirm(`确定取消「${hostileName}」吗？\n取消后无法恢复。`, { title: '取消订单' })
  await flushPromises()

  const body = document.querySelector('.dialog-body')
  expect(body.textContent).toBe(`确定取消「${hostileName}」吗？\n取消后无法恢复。`)
  expect(body.querySelector('img')).toBeNull()
  expect(body.querySelector('script')).toBeNull()
  expect(body.getAttribute('onerror')).toBeNull()

  document.querySelector('.dialog-btn-cancel').click()
  expect(await result).toBe(false)
})
