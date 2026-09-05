// @vitest-environment jsdom
import { expect, it, vi } from 'vitest'
import { initializeMxaAnalytics } from './mxa'

it('loads the analytics SDK without inline handlers and initializes it after load', async () => {
  const init = vi.fn()
  const result = initializeMxaAnalytics(document, window)
  const script = document.getElementById('MXA_COLLECT')

  expect(script).not.toBeNull()
  expect(script.src).toBe('https://mxana.tacool.com/sdk.js')
  expect(script.async).toBe(true)
  expect(script.getAttribute('onload')).toBeNull()

  window.MXA = { init }
  script.dispatchEvent(new window.Event('load'))

  await expect(result).resolves.toBe(window.MXA)
  expect(init).toHaveBeenCalledWith({ id: 'c2-9FYYP0Vm' })
})
