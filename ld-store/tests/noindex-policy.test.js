import { describe, expect, it } from 'vitest'
import { EXPECTED_NOINDEX_POLICY, validateNoindexPolicy } from '../scripts/validate-noindex-policy.mjs'
import { NOINDEX_POLICY } from '../public/_worker.js'

describe('storefront noindex policy', () => {
  it('keeps source, Worker, crawler access and the ADR aligned', () => {
    expect(NOINDEX_POLICY).toBe(EXPECTED_NOINDEX_POLICY)
    expect(validateNoindexPolicy().violations).toEqual([])
  })
})
