// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCatalogStore } from './catalog'
import { useOrderStore } from './order'

const mocks = vi.hoisted(() => ({
  fetchProducts: vi.fn(),
  fetchCategories: vi.fn(),
  fetchPublicStats: vi.fn(),
  fetchUserDashboard: vi.fn(),
  fetchOrders: vi.fn(),
  fetchBuyOrders: vi.fn()
}))

vi.mock('@/services/shop/catalogService', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/services/shop/catalogService')>(),
  fetchProductsRequest: mocks.fetchProducts,
  fetchCategoriesRequest: mocks.fetchCategories,
  fetchPublicStatsRequest: mocks.fetchPublicStats,
  fetchUserDashboardRequest: mocks.fetchUserDashboard,
  normalizeFavoritesOptions: (options: unknown) => options
}))

vi.mock('@/services/shop/orderService', () => ({
  fetchOrdersByRoleRequest: mocks.fetchOrders,
  fetchMyBuyOrdersRequest: mocks.fetchBuyOrders,
  fetchOrderDetailRequest: vi.fn(),
  createOrderRequest: vi.fn(),
  cancelOrderRequest: vi.fn(),
  deliverOrderRequest: vi.fn(),
  getBuyOrderDetailRequest: vi.fn(),
  getBuyOrderPaymentUrlRequest: vi.fn(),
  getPaymentUrlRequest: vi.fn(),
  refreshBuyOrderStatusRequest: vi.fn(),
  refreshOrderStatusRequest: vi.fn()
}))

vi.mock('@/services/shop/inventoryService', () => ({
  fetchMyProductsRequest: vi.fn(),
  createProductRequest: vi.fn(),
  getProductSubmissionStatusRequest: vi.fn(),
  updateProductRequest: vi.fn(),
  offlineProductRequest: vi.fn(),
  deleteProductRequest: vi.fn(),
  fetchMyProductDetailRequest: vi.fn(),
  fetchCdkListRequest: vi.fn(),
  addCdkRequest: vi.fn(),
  deleteCdkRequest: vi.fn(),
  clearCdkRequest: vi.fn()
}))

vi.mock('@/services/shop/merchantService', () => ({
  fetchMerchantConfigRequest: vi.fn(),
  updateMerchantConfigRequest: vi.fn()
}))

vi.mock('@/services/shop/discoveryService', () => ({
  getDiscoveryTokenForProduct: vi.fn(() => ''),
  clearDiscoveryTokenForProduct: vi.fn()
}))

function success<T>(data: T) {
  return { success: true as const, status: 200, data }
}

function failure(error: string) {
  return { success: false as const, status: 503, error, aborted: false, kind: 'http' as const }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function productPage(id: number, page: number) {
  return success({
    products: [{ id, name: `物品 ${id}` }],
    pagination: { total: 2, page, pageSize: 20, totalPages: 1 },
    rankingContext: { surface: 'home', version: 'v1', fallback: false }
  })
}

describe('storefront domain stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('prevents an older catalog response from overwriting the latest page', async () => {
    const older = deferred<ReturnType<typeof productPage>>()
    mocks.fetchProducts
      .mockReturnValueOnce(older.promise)
      .mockResolvedValueOnce(productPage(2, 2))
    const store = useCatalogStore()

    const first = store.fetchProducts({ page: 1 })
    const second = await store.fetchProducts({ page: 2 })
    older.resolve(productPage(1, 1))
    const stale = await first

    expect(second.success).toBe(true)
    expect(stale).toMatchObject({ success: false, aborted: true, kind: 'abort' })
    expect(store.products.map(product => product.id)).toEqual([2])
    expect(store.page).toBe(2)
  })

  it('keeps buyer and seller request lifecycle state independent', async () => {
    const buyer = deferred<ReturnType<typeof success>>()
    mocks.fetchOrders.mockImplementation((role: string) => role === 'buyer'
      ? buyer.promise
      : Promise.resolve(success({
          orders: [{ orderNo: 'SELLER-1', status: 'paid' }],
          pagination: { total: 1, page: 1, pageSize: 20, totalPages: 1 }
        })))
    const store = useOrderStore()

    const buyerTask = store.fetchBuyerOrders()
    expect(store.buyerOrdersLoading).toBe(true)
    await store.fetchSellerOrders()
    expect(store.buyerOrdersLoading).toBe(true)
    expect(store.sellerOrdersLoading).toBe(false)
    expect(store.sellerOrders[0]?.orderNo).toBe('SELLER-1')

    buyer.resolve(success({
      orders: [{ orderNo: 'BUYER-1', status: 'pending' }],
      pagination: { total: 1, page: 1, pageSize: 20, totalPages: 1 }
    }))
    await buyerTask
    expect(store.buyerOrdersLoading).toBe(false)
    expect(store.buyerOrders[0]?.orderNo).toBe('BUYER-1')
  })

  it('returns an explicit failure instead of masking a list error as an empty array', async () => {
    mocks.fetchOrders.mockResolvedValue(failure('订单服务维护中'))
    const store = useOrderStore()
    const result = await store.fetchBuyerOrders()

    expect(result).toMatchObject({ success: false, status: 503, kind: 'http' })
    expect(store.buyerOrdersError).toBe('订单服务维护中')
    expect(Array.isArray(result)).toBe(false)
  })

  it('exposes catalog state directly without a compatibility facade', async () => {
    mocks.fetchProducts.mockResolvedValue(productPage(9, 1))
    const catalog = useCatalogStore()

    const result = await catalog.fetchProducts({ page: 1 })
    expect(result.success).toBe(true)
    expect(catalog.products[0]?.id).toBe(9)
  })
})
