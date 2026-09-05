import { describe, expect, it } from 'vitest'
import { validateStylePolicy } from '../scripts/check-style-tokens.mjs'

describe('semantic style token policy', () => {
  it('keeps component styles free of raw colors and broad transitions', () => {
    const result = validateStylePolicy()

    expect(result.files).toBeGreaterThan(70)
    expect(result.violations).toEqual([])
  })
})
