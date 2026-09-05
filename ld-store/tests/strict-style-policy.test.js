import { describe, expect, it } from 'vitest'
import { validateStrictCspPolicy } from '../scripts/check-strict-csp.mjs'

describe('strict storefront style policy', () => {
  it('keeps source templates and CSP compatible with style-src-attr none', () => {
    const result = validateStrictCspPolicy()

    expect(result.sourceFiles).toBeGreaterThan(170)
    expect(result.violations).toEqual([])
  })
})
