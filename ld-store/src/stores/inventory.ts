import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { Product } from '@/contracts/catalog'
import type { ProductCreatePayload, ProductUpdatePayload } from '@/contracts/commerce'
import {
  addCdkRequest,
  clearCdkRequest,
  createProductRequest,
  deleteCdkRequest,
  deleteProductRequest,
  fetchCdkListRequest,
  fetchMyProductDetailRequest,
  fetchMyProductsRequest,
  getProductSubmissionStatusRequest,
  offlineProductRequest,
  updateProductRequest
} from '@/services/shop/inventoryService'
import { fetchMerchantConfigRequest, updateMerchantConfigRequest } from '@/services/shop/merchantService'
import { serviceFailure } from '@/services/serviceContract'
import { useCatalogStore } from '@/stores/catalog'
import { useProductStore } from '@/stores/product'

interface RequestOptions {
  timeout?: number
  signal?: AbortSignal
}

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
type ProductPayload = ProductCreatePayload | ProductUpdatePayload | Record<string, JsonValue>

export const useInventoryStore = defineStore('inventory', () => {
  const products = ref<Product[]>([])
  const loading = ref(false)
  const error = ref('')
  const merchantConfig = ref<Record<string, unknown> | null>(null)
  const merchantConfigLoading = ref(false)
  const merchantConfigError = ref('')
  let productsRequestId = 0

  function invalidateProductCaches(id?: string | number) {
    useCatalogStore().invalidateCache()
    if (id !== undefined) useProductStore().invalidateProduct(id)
    else useProductStore().clearDetailCache()
  }

  async function fetchProducts(options: { signal?: AbortSignal } = {}) {
    const requestId = ++productsRequestId
    loading.value = true
    try {
      const result = await fetchMyProductsRequest({ signal: options.signal })
      if (requestId === productsRequestId) {
        if (result.success) {
          products.value = result.data.products
          error.value = ''
        } else {
          error.value = result.error || '加载卖家物品失败，请稍后重试'
        }
      }
      return result
    } catch (caught) {
      const failure = serviceFailure(caught, '加载卖家物品失败，请稍后重试')
      if (requestId === productsRequestId) error.value = failure.error
      return failure
    } finally {
      if (requestId === productsRequestId) loading.value = false
    }
  }

  async function createProduct(data: ProductPayload, options: RequestOptions = {}) {
    const result = await createProductRequest(data, options)
    if (result.success) {
      invalidateProductCaches()
      await fetchProducts()
    }
    return result
  }

  async function updateProduct(id: string | number, data: ProductPayload, options: RequestOptions = {}) {
    const result = await updateProductRequest(id, data, options)
    if (result.success) {
      invalidateProductCaches(id)
      await fetchProducts()
    }
    return result
  }

  async function offlineProduct(id: string | number) {
    const result = await offlineProductRequest(id)
    if (result.success) {
      invalidateProductCaches(id)
      await fetchProducts()
    }
    return result
  }

  async function deleteProduct(id: string | number) {
    const result = await deleteProductRequest(id)
    if (result.success) {
      invalidateProductCaches(id)
      products.value = products.value.filter(product => String(product.id) !== String(id))
    }
    return result
  }

  async function addCdk(productId: string | number, codes: string[]) {
    const result = await addCdkRequest(productId, codes)
    if (result.success) invalidateProductCaches(productId)
    return result
  }

  async function clearCdk(productId: string | number) {
    const result = await clearCdkRequest(productId)
    if (result.success) invalidateProductCaches(productId)
    return result
  }

  async function fetchMerchantConfig() {
    merchantConfigLoading.value = true
    try {
      const result = await fetchMerchantConfigRequest()
      if (result.success) {
        merchantConfig.value = result.data
        merchantConfigError.value = ''
      } else {
        merchantConfigError.value = result.error || '加载商户配置失败，请稍后重试'
      }
      return result
    } finally {
      merchantConfigLoading.value = false
    }
  }

  async function updateMerchantConfig(config: Record<string, JsonValue>) {
    const result = await updateMerchantConfigRequest(config)
    if (result.success) await fetchMerchantConfig()
    return result
  }

  return {
    products,
    loading,
    error,
    merchantConfig,
    merchantConfigLoading,
    merchantConfigError,
    fetchProducts,
    createProduct,
    getProductSubmissionStatus: getProductSubmissionStatusRequest,
    updateProduct,
    offlineProduct,
    deleteProduct,
    fetchProductDetail: fetchMyProductDetailRequest,
    fetchCdkList: fetchCdkListRequest,
    addCdk,
    deleteCdk: deleteCdkRequest,
    clearCdk,
    fetchMerchantConfig,
    updateMerchantConfig
  }
})
