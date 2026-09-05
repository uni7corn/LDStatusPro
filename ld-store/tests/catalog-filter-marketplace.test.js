// @vitest-environment jsdom
/* global document, window */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let shopStore
let wrapper
const toast = {
  error: vi.fn(),
  warning: vi.fn()
}

vi.mock('../src/stores/catalog', () => ({
  useCatalogStore: () => shopStore
}))

vi.mock('../src/composables/useToast', () => ({
  useToast: () => toast
}))

import ProductsMarketplace from '../src/components/home/ProductsMarketplace.vue'

function successResult() {
  return {
    success: true,
    status: 200,
    data: {
      products: [],
      pagination: { total: 0, page: 1, pageSize: 20, totalPages: 0, hasMore: false }
    }
  }
}

function createStore() {
  const store = {
    categories: [],
    products: [],
    currentCategory: '',
    currentCategoryName: '全部',
    currentSort: 'default',
    inStockOnly: false,
    currentPriceMin: null,
    currentPriceMax: null,
    loading: false,
    hasMore: false,
    page: 1,
    total: 0,
    catalogCursor: '',
    rankingContext: null,
    fetchCategories: vi.fn().mockResolvedValue({ success: true, data: { categories: [] } }),
    fetchProducts: vi.fn(async options => {
      store.currentCategory = options.categoryId
      store.currentSort = options.sort
      store.currentPriceMin = options.priceMin
      store.currentPriceMax = options.priceMax
      return successResult()
    }),
    loadMore: vi.fn(),
    consumeError: vi.fn(() => ''),
    setInStockOnly: vi.fn(value => {
      store.inStockOnly = Boolean(value)
      return store.inStockOnly
    }),
    restoreFromCache: vi.fn(snapshot => {
      store.products = [...snapshot.products]
      store.currentCategory = snapshot.categoryId
      store.currentSort = snapshot.sort
      store.inStockOnly = snapshot.inStockOnly
      store.currentPriceMin = snapshot.priceMin
      store.currentPriceMax = snapshot.priceMax
      store.total = snapshot.total
      store.hasMore = snapshot.hasMore
      store.page = snapshot.page
      store.catalogCursor = snapshot.cursor
      store.rankingContext = snapshot.rankingContext
    })
  }
  return store
}

beforeEach(async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375, writable: true })
  shopStore = createStore()
  toast.error.mockClear()
  toast.warning.mockClear()
  wrapper = mount(ProductsMarketplace, {
    attachTo: document.body,
    global: {
      stubs: {
        CategoryFilter: true,
        EmptyState: true,
        ProductCard: true,
        Skeleton: true
      }
    }
  })
  await flushPromises()
  shopStore.fetchProducts.mockClear()
  shopStore.setInStockOnly.mockClear()
  shopStore.restoreFromCache.mockClear()
})

afterEach(() => {
  wrapper.unmount()
  document.body.style.overflow = ''
  vi.restoreAllMocks()
})

async function openFilterSheet() {
  await wrapper.get('.mobile-filter-trigger').trigger('click')
  await flushPromises()
  return document.querySelector('[role="dialog"]')
}

describe('ProductsMarketplace mobile filters', () => {
  it('applies a native mobile sort selection with one catalog request', async () => {
    await wrapper.get('#home-mobile-sort').setValue('sales')
    await flushPromises()

    expect(shopStore.fetchProducts).toHaveBeenCalledTimes(1)
    expect(shopStore.fetchProducts).toHaveBeenCalledWith(expect.objectContaining({ sort: 'sales' }))
  })

  it('normalizes and applies price plus stock in one catalog request', async () => {
    const dialog = await openFilterSheet()
    const min = dialog.querySelector('#catalog-price-min')
    const max = dialog.querySelector('#catalog-price-max')
    const stock = dialog.querySelector('.catalog-stock-option input')

    min.value = '20'
    min.dispatchEvent(new window.Event('input', { bubbles: true }))
    max.value = '8'
    max.dispatchEvent(new window.Event('input', { bubbles: true }))
    stock.click()
    dialog.querySelector('.catalog-filter-apply').click()
    await flushPromises()

    expect(shopStore.setInStockOnly).toHaveBeenCalledTimes(1)
    expect(shopStore.setInStockOnly).toHaveBeenCalledWith(true)
    expect(shopStore.fetchProducts).toHaveBeenCalledTimes(1)
    expect(shopStore.fetchProducts).toHaveBeenCalledWith(expect.objectContaining({
      forceRefresh: true,
      sort: 'default',
      priceMin: 8,
      priceMax: 20
    }))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('keeps the sheet open and restores active filters when loading fails', async () => {
    shopStore.fetchProducts.mockImplementationOnce(async options => {
      shopStore.currentPriceMin = options.priceMin
      shopStore.currentPriceMax = options.priceMax
      return { success: false, status: 503, error: '物品列表暂时不可用' }
    })
    const dialog = await openFilterSheet()
    const min = dialog.querySelector('#catalog-price-min')
    min.value = '-5'
    min.dispatchEvent(new window.Event('input', { bubbles: true }))
    dialog.querySelector('.catalog-stock-option input').click()
    dialog.querySelector('.catalog-filter-apply').click()
    await flushPromises()

    expect(shopStore.fetchProducts).toHaveBeenCalledTimes(1)
    expect(shopStore.fetchProducts).toHaveBeenCalledWith(expect.objectContaining({ priceMin: 0, priceMax: null }))
    expect(shopStore.restoreFromCache).toHaveBeenCalledTimes(1)
    expect(shopStore.inStockOnly).toBe(false)
    expect(shopStore.currentPriceMin).toBeNull()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(toast.error).toHaveBeenCalledWith('物品列表暂时不可用')
  })

  it('closes and releases the sheet when the viewport becomes desktop-sized', async () => {
    await openFilterSheet()
    expect(document.body.style.overflow).toBe('hidden')

    window.innerWidth = 1024
    window.dispatchEvent(new window.Event('resize'))
    await flushPromises()

    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.body.style.overflow).toBe('')
  })
})
