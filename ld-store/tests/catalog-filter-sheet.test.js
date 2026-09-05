// @vitest-environment jsdom
/* global document */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CatalogFilterSheet from '../src/components/home/CatalogFilterSheet.vue'

let wrapper
let trigger

beforeEach(() => {
  trigger = document.createElement('button')
  trigger.textContent = '打开筛选'
  document.body.append(trigger)
  trigger.focus()
  wrapper = mount(CatalogFilterSheet, {
    attachTo: document.body,
    props: {
      open: false,
      priceMin: 5,
      priceMax: 20,
      inStockOnly: true
    }
  })
})

afterEach(() => {
  wrapper.unmount()
  trigger.remove()
  document.body.style.overflow = ''
})

async function openSheet() {
  await wrapper.setProps({ open: true })
  await flushPromises()
  return document.querySelector('[role="dialog"]')
}

describe('CatalogFilterSheet', () => {
  it('copies active filters, locks scrolling, traps focus, and restores the trigger', async () => {
    const dialog = await openSheet()
    const close = dialog.querySelector('.catalog-filter-close')
    const apply = dialog.querySelector('.catalog-filter-apply')

    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')).textContent).toBe('筛选物品')
    expect(dialog.querySelector('#catalog-price-min').value).toBe('5')
    expect(dialog.querySelector('#catalog-price-max').value).toBe('20')
    expect(dialog.querySelector('.catalog-stock-option input').checked).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')
    expect(document.activeElement).toBe(close)

    close.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(apply)
    apply.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(close)
    close.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.setProps({ open: false })
    await flushPromises()
    expect(document.body.style.overflow).toBe('')
    expect(document.activeElement).toBe(trigger)
  })

  it('keeps edits as drafts, resets locally, and emits one combined apply payload', async () => {
    const dialog = await openSheet()
    const min = dialog.querySelector('#catalog-price-min')
    const max = dialog.querySelector('#catalog-price-max')
    const stock = dialog.querySelector('.catalog-stock-option input')

    min.value = '-3'
    min.dispatchEvent(new document.defaultView.Event('input', { bubbles: true }))
    max.value = '12.345'
    max.dispatchEvent(new document.defaultView.Event('input', { bubbles: true }))
    stock.click()
    expect(wrapper.emitted('apply')).toBeUndefined()

    dialog.querySelector('.catalog-filter-apply').click()
    expect(wrapper.emitted('apply')).toEqual([[{ priceMin: -3, priceMax: 12.345, inStockOnly: false }]])

    dialog.querySelector('.catalog-filter-reset').click()
    await wrapper.vm.$nextTick()
    expect(min.value).toBe('')
    expect(max.value).toBe('')
    expect(stock.checked).toBe(false)
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })

  it('discards unsubmitted edits when it closes and reopens', async () => {
    let dialog = await openSheet()
    const min = dialog.querySelector('#catalog-price-min')
    min.value = '99'
    min.dispatchEvent(new document.defaultView.Event('input', { bubbles: true }))
    dialog.querySelector('.catalog-filter-close').click()
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.setProps({ open: false })
    await flushPromises()
    trigger.focus()
    dialog = await openSheet()
    expect(dialog.querySelector('#catalog-price-min').value).toBe('5')
  })

  it('disables dismissal and form actions while applying', async () => {
    const dialog = await openSheet()
    await wrapper.setProps({ loading: true })
    await flushPromises()

    expect(dialog.getAttribute('aria-busy')).toBe('true')
    expect(dialog.querySelector('.catalog-filter-close').disabled).toBe(true)
    expect(dialog.querySelector('.catalog-filter-apply').disabled).toBe(true)
    dialog.dispatchEvent(new document.defaultView.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    document.querySelector('.catalog-filter-layer').click()
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
