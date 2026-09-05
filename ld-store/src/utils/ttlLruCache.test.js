import { describe, expect, it } from 'vitest'
import { createTtlLruCache } from './ttlLruCache'

describe('TTL-LRU cache', () => {
  it('promotes reads and evicts the least recently used entry', () => {
    let time = 0
    const cache = createTtlLruCache({ ttl: 300_000, max: 24, now: () => time })
    for (let index = 1; index <= 24; index++) cache.set(`filter-${index}`, index)

    expect(cache.get('filter-1')).toBe(1)
    time++
    cache.set('filter-25', 25)

    expect(cache.size).toBe(24)
    expect(cache.get('filter-2')).toBeUndefined()
    expect(cache.get('filter-1')).toBe(1)
    expect(cache.get('filter-25')).toBe(25)
  })

  it('removes expired entries immediately on read', () => {
    let time = 10
    const cache = createTtlLruCache({ ttl: 100, max: 2, now: () => time })
    cache.set('products', ['one'])
    time = 110

    expect(cache.get('products')).toBeUndefined()
    expect(cache.size).toBe(0)
  })

  it('supports delete and clear without exposing the backing map', () => {
    const cache = createTtlLruCache({ ttl: 100, max: 2 })
    cache.set('one', 1)
    cache.set('two', 2)
    expect(cache.delete('one')).toBe(true)
    expect(cache.size).toBe(1)
    cache.clear()
    expect(cache.size).toBe(0)
  })
})
