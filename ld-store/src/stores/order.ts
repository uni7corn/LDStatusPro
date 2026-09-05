import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { BuyOrder, Order } from '@/contracts/commerce'
import { clearDiscoveryTokenForProduct, getDiscoveryTokenForProduct } from '@/services/shop/discoveryService'
import {
  cancelOrderRequest,
  createOrderRequest,
  deliverOrderRequest,
  fetchMyBuyOrdersRequest,
  fetchOrderDetailRequest,
  fetchOrdersByRoleRequest,
  getBuyOrderDetailRequest,
  getBuyOrderPaymentUrlRequest,
  getPaymentUrlRequest,
  refreshBuyOrderStatusRequest,
  refreshOrderStatusRequest
} from '@/services/shop/orderService'
import { serviceFailure } from '@/services/serviceContract'
import { useNotificationSummaryStore } from '@/stores/notificationSummary'

interface OrderListOptions {
  role?: string
  status?: string
  search?: string
  timeRange?: string
  categoryId?: string | number
  dealOnly?: boolean | string
  page?: number
  pageSize?: number
  signal?: AbortSignal
}

export const useOrderStore = defineStore('order', () => {
  const buyerOrders = ref<Order[]>([])
  const sellerOrders = ref<Order[]>([])
  const buyRequestOrders = ref<BuyOrder[]>([])
  const buyerOrdersLoading = ref(false)
  const sellerOrdersLoading = ref(false)
  const buyRequestOrdersLoading = ref(false)
  const buyerOrdersError = ref('')
  const sellerOrdersError = ref('')
  const buyRequestOrdersError = ref('')
  let buyerRequestId = 0
  let sellerRequestId = 0
  let buyRequestId = 0

  async function fetchBuyerOrders(options: OrderListOptions = {}) {
    const requestId = ++buyerRequestId
    buyerOrdersLoading.value = true
    try {
      const result = await fetchOrdersByRoleRequest('buyer', options)
      if (requestId === buyerRequestId) {
        if (result.success) {
          buyerOrders.value = result.data.orders
          buyerOrdersError.value = ''
        } else {
          buyerOrdersError.value = result.error || '加载买家订单失败，请稍后重试'
        }
      }
      return result
    } catch (error) {
      const failure = serviceFailure(error, '加载买家订单失败，请稍后重试')
      if (requestId === buyerRequestId) buyerOrdersError.value = failure.error
      return failure
    } finally {
      if (requestId === buyerRequestId) buyerOrdersLoading.value = false
    }
  }

  async function fetchSellerOrders(options: OrderListOptions = {}) {
    const requestId = ++sellerRequestId
    sellerOrdersLoading.value = true
    try {
      const result = await fetchOrdersByRoleRequest('seller', options)
      if (requestId === sellerRequestId) {
        if (result.success) {
          sellerOrders.value = result.data.orders
          sellerOrdersError.value = ''
        } else {
          sellerOrdersError.value = result.error || '加载卖家订单失败，请稍后重试'
        }
      }
      return result
    } catch (error) {
      const failure = serviceFailure(error, '加载卖家订单失败，请稍后重试')
      if (requestId === sellerRequestId) sellerOrdersError.value = failure.error
      return failure
    } finally {
      if (requestId === sellerRequestId) sellerOrdersLoading.value = false
    }
  }

  function fetchOrders(options: OrderListOptions = {}) {
    return options.role === 'seller' ? fetchSellerOrders(options) : fetchBuyerOrders(options)
  }

  async function fetchBuyRequestOrders(options: OrderListOptions = {}) {
    const requestId = ++buyRequestId
    buyRequestOrdersLoading.value = true
    try {
      const result = await fetchMyBuyOrdersRequest(options)
      if (requestId === buyRequestId) {
        if (result.success) {
          buyRequestOrders.value = result.data.orders
          buyRequestOrdersError.value = ''
        } else {
          buyRequestOrdersError.value = result.error || '加载求购订单失败，请稍后重试'
        }
      }
      return result
    } catch (error) {
      const failure = serviceFailure(error, '加载求购订单失败，请稍后重试')
      if (requestId === buyRequestId) buyRequestOrdersError.value = failure.error
      return failure
    } finally {
      if (requestId === buyRequestId) buyRequestOrdersLoading.value = false
    }
  }

  async function createOrder(productId: string | number, quantity = 1, couponClaimId: string | number | null = null) {
    const discoveryToken = getDiscoveryTokenForProduct(productId)
    const result = await createOrderRequest(productId, quantity, couponClaimId, discoveryToken)
    if (result.success) clearDiscoveryTokenForProduct(productId)
    return result
  }

  async function cancelOrder(orderNo: string) {
    const result = await cancelOrderRequest(orderNo)
    if (result.success) await fetchBuyerOrders()
    return result
  }

  async function deliverOrder(orderNo: string, content: string) {
    const result = await deliverOrderRequest(orderNo, content)
    if (result.success) {
      const notificationSummaryStore = useNotificationSummaryStore()
      await Promise.all([
        fetchSellerOrders(),
        notificationSummaryStore.refresh({ force: true })
      ])
    }
    return result
  }

  return {
    buyerOrders,
    sellerOrders,
    buyRequestOrders,
    buyerOrdersLoading,
    sellerOrdersLoading,
    buyRequestOrdersLoading,
    buyerOrdersError,
    sellerOrdersError,
    buyRequestOrdersError,
    fetchBuyerOrders,
    fetchSellerOrders,
    fetchOrders,
    fetchOrderDetail: fetchOrderDetailRequest,
    createOrder,
    cancelOrder,
    refreshOrderStatus: refreshOrderStatusRequest,
    getPaymentUrl: getPaymentUrlRequest,
    deliverOrder,
    fetchBuyRequestOrders,
    getBuyOrderDetail: getBuyOrderDetailRequest,
    getBuyOrderPaymentUrl: getBuyOrderPaymentUrlRequest,
    refreshBuyOrderStatus: refreshBuyOrderStatusRequest
  }
})
