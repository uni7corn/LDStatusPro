import { describe, expect, it } from 'vitest'
import { normalizePriceFilterInput, normalizePriceFilterRange } from '../src/utils/catalogFilters'

describe('catalog filter normalization', () => {
  it('treats empty or invalid values as unbounded', () => {
    expect(normalizePriceFilterInput('')).toBeNull()
    expect(normalizePriceFilterInput('  ')).toBeNull()
    expect(normalizePriceFilterInput('not-a-price')).toBeNull()
  })

  it('clamps negative values and keeps two decimal places', () => {
    expect(normalizePriceFilterInput('-5')).toBe(0)
    expect(normalizePriceFilterInput('12.345')).toBe(12.35)
  })

  it('supports one-sided ranges and swaps reversed bounds', () => {
    expect(normalizePriceFilterRange('8', '')).toEqual({ priceMin: 8, priceMax: null })
    expect(normalizePriceFilterRange('', '20')).toEqual({ priceMin: null, priceMax: 20 })
    expect(normalizePriceFilterRange('20', '8')).toEqual({ priceMin: 8, priceMax: 20 })
  })
})
