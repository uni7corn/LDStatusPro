import { api, type JsonValue } from '@/utils/api'
import { OrderRefundResponseSchema, SellerRefundListResponseSchema } from '@/contracts/commerce'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'

interface RefundPayload extends Record<string, JsonValue> {
  reasonCode: string
  reasonDetail: string
  buyerContactedSeller: boolean
}

interface SellerRefundListOptions {
  page?: number
  pageSize?: number
  status?: string
  search?: string
  signal?: AbortSignal
}

function orderPath(orderNo: string): string {
  return `/api/shop/orders/${encodeURIComponent(String(orderNo || ''))}/refund`
}

function validatedRefundRequest(result: Awaited<ReturnType<typeof api.get>>, endpoint: string) {
  return validateServiceResult(result, OrderRefundResponseSchema, endpoint, 'OrderRefundResponse')
}

export async function fetchOrderRefundRequest(orderNo: string, options: { signal?: AbortSignal } = {}) {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.get(orderPath(orderNo), { signal: options.signal }),
    '/api/shop/orders/:orderNo/refund'
  ), '加载退款状态失败，请稍后重试')
}

export async function createRefundRequest(orderNo: string, payload: RefundPayload) {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.post(orderPath(orderNo), payload),
    '/api/shop/orders/:orderNo/refund'
  ), '提交退款申请失败，请稍后重试')
}

export async function contactRefundBuyerRequest(orderNo: string, message = '') {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.post(`${orderPath(orderNo)}/contact`, { message }),
    '/api/shop/orders/:orderNo/refund/contact'
  ), '更新协商状态失败，请稍后重试')
}

export async function rejectRefundRequest(orderNo: string, message: string) {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.post(`${orderPath(orderNo)}/reject`, { message }),
    '/api/shop/orders/:orderNo/refund/reject'
  ), '拒绝退款申请失败，请稍后重试')
}

export async function approveRefundRequest(orderNo: string, message = '') {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.post(`${orderPath(orderNo)}/approve`, { message }),
    '/api/shop/orders/:orderNo/refund/approve'
  ), '执行退款失败，请稍后重试')
}

export async function fetchSellerRefundsRequest(options: SellerRefundListOptions = {}) {
  const params = new URLSearchParams({
    page: String(options.page || 1),
    pageSize: String(options.pageSize || 20)
  })
  if (options.status) params.set('status', String(options.status))
  if (options.search) params.set('search', String(options.search).trim())
  return withServiceFailure(async () => validateServiceResult(
    await api.get(`/api/shop/refunds?${params.toString()}`, { signal: options.signal }),
    SellerRefundListResponseSchema,
    '/api/shop/refunds',
    'SellerRefundListResponse'
  ), '加载退款售后列表失败，请稍后重试')
}

export async function proactiveRefundRequest(orderNo: string) {
  return withServiceFailure(async () => validatedRefundRequest(
    await api.post(`${orderPath(orderNo)}/proactive`, { confirm: true }),
    '/api/shop/orders/:orderNo/refund/proactive'
  ), '执行主动退款失败，请查看退款状态')
}
