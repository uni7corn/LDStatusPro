import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { URL } from 'node:url'
import { parse, compileTemplate } from '@vue/compiler-sfc'
import { beginCatalogRotation, catalogRotationKey, rememberCatalogSlate } from '../src/utils/catalogRotation'
import { fetchProductsRequest } from '../src/services/shop/catalogService'
import { useCatalogStore } from '../src/stores/catalog'
import { api } from '../src/utils/api'

vi.mock('../src/utils/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
const first = '7bf4e11a-1615-4c93-91d8-e17d72f5f0a1'
const second = '7bf4e11a-1615-4c93-91d8-e17d72f5f0a2'
function memoryStorage() {
  const map = new Map()
  return { getItem: key => map.get(key) || null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }
}
function catalogResponse({ products = [], slateId = first } = {}) {
  return {
    success: true,
    status: 200,
    data: {
      products: products.map(product => ({ name: `Product ${product.id}`, ...product })),
      pagination: { total: products.length, page: 1, pageSize: 20, totalPages: products.length ? 1 : 0, hasMore: false },
      rankingContext: {
        slateId,
        requestId: 'request-1',
        surface: 'home',
        version: 'catalog-v2',
        releaseMode: 'active',
        fallback: false
      }
    }
  }
}
describe('V2.2 recommendation rotation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', { sessionStorage: memoryStorage(), localStorage: memoryStorage() })
    vi.stubGlobal('localStorage', globalThis.window.localStorage)
    vi.stubGlobal('navigator', { globalPrivacyControl: false, doNotTrack: '0' })
    vi.stubGlobal('crypto', { randomUUID: vi.fn().mockReturnValueOnce(first).mockReturnValue(second) })
    setActivePinia(createPinia())
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

  it('new first-page requests rotate; only the same filter remembers the previous slate', () => {
    expect(beginCatalogRotation().rotationId).toBe(first)
    rememberCatalogSlate({}, first)
    expect(beginCatalogRotation()).toEqual({ rotationId: second, previousSlateId: first })
    expect(beginCatalogRotation({ categoryId: 4 }).previousSlateId).toBe('')
    expect(catalogRotationKey({ priceMin: 5 })).not.toBe(catalogRotationKey({ priceMin: 8 }))
    vi.useFakeTimers()
    vi.advanceTimersByTime(31 * 60 * 1000)
    expect(beginCatalogRotation().previousSlateId).toBe('')
  })
  it('privacy opt-out does not retain slate identifiers', () => {
    vi.stubGlobal('navigator', { globalPrivacyControl: true })
    rememberCatalogSlate({}, first)
    expect(beginCatalogRotation().previousSlateId).toBe('')
  })
  it('only default recommendation first pages send rotation parameters', async () => {
    api.get.mockResolvedValue(catalogResponse())
    await fetchProductsRequest()
    expect(api.get.mock.lastCall[0]).toContain(`rotationId=${first}`)
    await fetchProductsRequest()
    expect(api.get.mock.lastCall[0]).toContain(`previousSlateId=${first}`)
    for (const options of [{ search: 'apple' }, { sort: 'newest' }, { sort: 'price_asc' }, { page: 2, cursor: 'cursor' }]) {
      await fetchProductsRequest(options)
      expect(api.get.mock.lastCall[0]).not.toMatch(/rotationId|previousSlateId/)
    }
  })
  it('keeps valid catalog data when optional ranking metadata is malformed', async () => {
    const warning = vi.spyOn(globalThis.console, 'warn').mockImplementation(() => {})
    const response = catalogResponse({ products: [{ id: 9 }] })
    response.data.rankingContext = { slateId: 'malformed-ranking-context' }
    api.get.mockResolvedValue(response)

    const result = await fetchProductsRequest({ sort: 'newest' })
    expect(result).toMatchObject({ success: true, data: { products: [{ id: 9, name: 'Product 9' }] } })
    expect(result.data).not.toHaveProperty('rankingContext')
    expect(warning).toHaveBeenCalledWith('[api-contract] Invalid response', expect.objectContaining({ schema: 'RankingContext' }))
    warning.mockRestore()
  })
  it('page reload rotates automatically while retaining the prior slate for overlap control', async () => {
    const response = catalogResponse({ products: [{ id: 1 }] })
    api.get.mockResolvedValue(response)
    await useCatalogStore().fetchProducts({ forceRefresh: true })
    const initial = new URL(api.get.mock.lastCall[0], 'http://localhost')
    expect(initial.searchParams.get('rotationId')).toBe(first)
    expect(initial.searchParams.has('previousSlateId')).toBe(false)

    // A full page reload recreates Pinia but retains this tab's sessionStorage.
    setActivePinia(createPinia())
    await useCatalogStore().fetchProducts({ forceRefresh: true })
    const reloaded = new URL(api.get.mock.lastCall[0], 'http://localhost')
    expect(reloaded.searchParams.get('rotationId')).toBe(second)
    expect(reloaded.searchParams.get('previousSlateId')).toBe(first)
  })
  it('home has no manual catalog rotation control or stale rotation state', () => {
    const source = readFileSync(new URL('../src/components/home/ProductsMarketplace.vue', import.meta.url), 'utf8')
    const { descriptor, errors } = parse(source)
    expect(errors).toEqual([])
    expect(compileTemplate({ source: descriptor.template.content, filename: 'Home.vue', id: 'home' }).errors).toEqual([])
    expect(source).not.toMatch(/catalog-rotate-btn|rotatingCatalog|rotateCatalog/)
    expect(descriptor.template.content).toContain('class="products-grid" :aria-busy="loading"')
  })
  it('failed rotation retains the visible list, page, context, and cursor', async () => {
    const store = useCatalogStore()
    store.restoreFromCache({ products: [{ id: 1 }], page: 3, total: 80, hasMore: true,
      cursor: 'old-cursor', rankingContext: { slateId: first } })
    let finish
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const request = store.fetchProducts({ forceRefresh: true, preserveProducts: true })
    expect(store.products.map(item => item.id)).toEqual([1])
    finish({ success: false, error: 'network unavailable' })
    expect((await request).success).toBe(false)
    expect(store.products.map(item => item.id)).toEqual([1])
    expect(store.page).toBe(3)
    expect(store.catalogCursor).toBe('old-cursor')
    expect(store.rankingContext.slateId).toBe(first)
    expect(store.loading).toBe(false)
  })
  it('newer filter request wins over a late failed rotation', async () => {
    const store = useCatalogStore()
    store.restoreFromCache({ products: [{ id: 1 }] })
    let finish
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const old = store.fetchProducts({ forceRefresh: true, preserveProducts: true })
    api.get.mockResolvedValueOnce(catalogResponse({ products: [{ id: 2 }] }))
    await store.fetchProducts({ categoryId: 2 })
    finish({ success: false, error: 'late failure' })
    expect((await old).aborted).toBe(true)
    expect(store.products.map(item => item.id)).toEqual([2])
  })
})
