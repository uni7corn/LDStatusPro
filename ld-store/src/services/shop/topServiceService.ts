import { api } from '@/utils/api'
import {
  TopServiceBoardResponseSchema,
  TopServiceMutationResponseSchema,
  TopServiceOptionsResponseSchema,
  TopServiceOrdersResponseSchema
} from '@/contracts/commerce'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'

interface TopServiceOrderListOptions {
  status?: string
  search?: string
  page?: number
  pageSize?: number
  signal?: AbortSignal
}

interface TopServiceOrderPayload extends Record<string, string | number> {
  productId: number
  packageType: string
  durationDays: number
}

export async function fetchTopServiceOptionsRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.get('/api/shop/top-service/options'),
    TopServiceOptionsResponseSchema,
    '/api/shop/top-service/options',
    'TopServiceOptionsResponse'
  ), '无法加载服务信息，请重试')
}

export async function fetchTopServiceBoardRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.get('/api/shop/top-service/board'),
    TopServiceBoardResponseSchema,
    '/api/shop/top-service/board',
    'TopServiceBoardResponse'
  ), '名额看板未能更新，请重试')
}

export async function fetchTopServiceOrdersRequest(options: TopServiceOrderListOptions = {}) {
  const page = options.page || 1
  const pageSize = options.pageSize || 20
  const params = new URLSearchParams()
  if (options.status) params.set('status', options.status)
  if (options.search?.trim()) params.set('search', options.search.trim())
  params.set('page', String(page))
  params.set('pageSize', String(pageSize))
  return withServiceFailure(async () => {
    const result = validateServiceResult(
      await api.get(`/api/shop/top-service/orders?${params.toString()}`, { signal: options.signal }),
      TopServiceOrdersResponseSchema,
      '/api/shop/top-service/orders',
      'TopServiceOrdersResponse'
    )
    if (!result.success) return result
    const pagination = result.data.pagination || {}
    return {
      ...result,
      data: {
        ...result.data,
        pagination: {
          total: pagination.total ?? result.data.orders.length,
          page: pagination.page ?? page,
          pageSize: pagination.pageSize ?? pageSize,
          totalPages: pagination.totalPages ?? 0
        }
      }
    }
  }, '无法读取购买记录，请重试')
}

export async function createTopServiceOrderRequest(payload: TopServiceOrderPayload) {
  return withServiceFailure(async () => validateServiceResult(
    await api.post('/api/shop/top-service/orders', payload),
    TopServiceMutationResponseSchema,
    '/api/shop/top-service/orders',
    'TopServiceMutationResponse'
  ), '创建服务订单失败，请重试')
}

export async function refreshTopServiceOrderRequest(orderNo: string) {
  return withServiceFailure(async () => validateServiceResult(
    await api.post(`/api/shop/top-service/orders/${encodeURIComponent(orderNo)}/refresh`),
    TopServiceMutationResponseSchema,
    '/api/shop/top-service/orders/:orderNo/refresh',
    'TopServiceMutationResponse'
  ), '暂时无法核验支付结果，请稍后重试')
}

export async function getTopServicePaymentUrlRequest(orderNo: string) {
  return withServiceFailure(async () => validateServiceResult(
    await api.get(`/api/shop/top-service/orders/${encodeURIComponent(orderNo)}/payment-url`),
    TopServiceMutationResponseSchema,
    '/api/shop/top-service/orders/:orderNo/payment-url',
    'TopServiceMutationResponse'
  ), '支付链接不可用，请核验订单状态')
}

export async function cancelTopServiceOrderRequest(orderNo: string) {
  return withServiceFailure(async () => validateServiceResult(
    await api.post(`/api/shop/top-service/orders/${encodeURIComponent(orderNo)}/cancel`),
    TopServiceMutationResponseSchema,
    '/api/shop/top-service/orders/:orderNo/cancel',
    'TopServiceMutationResponse'
  ), '未能取消，请核对最新订单状态')
}
