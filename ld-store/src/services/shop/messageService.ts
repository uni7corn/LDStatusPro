import { api } from '@/utils/api'
import {
  CommerceActionResponseSchema,
  NotificationSummaryResponseSchema,
  SystemMessagesResponseSchema
} from '@/contracts/commerce'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'

interface SystemMessageListOptions {
  page?: number
  pageSize?: number
  readStatus?: string
  search?: string
  signal?: AbortSignal
}

export async function fetchNotificationSummaryRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.get('/api/shop/messages/unread-summary'),
    NotificationSummaryResponseSchema,
    '/api/shop/messages/unread-summary',
    'NotificationSummaryResponse'
  ), '消息状态暂时不可用，请稍后重试')
}

export function openNotificationStreamRequest(signal?: AbortSignal) {
  return api.openEventStream('/api/shop/notifications/stream', { signal })
}

export async function fetchSystemMessagesRequest(options: SystemMessageListOptions = {}) {
  const params = new URLSearchParams({
    page: String(options.page || 1),
    pageSize: String(options.pageSize || 20)
  })
  if (options.readStatus) params.set('readStatus', options.readStatus)
  if (options.search?.trim()) params.set('search', options.search.trim())
  return withServiceFailure(async () => validateServiceResult(
    await api.get(`/api/shop/messages/system?${params.toString()}`, { signal: options.signal }),
    SystemMessagesResponseSchema,
    '/api/shop/messages/system',
    'SystemMessagesResponse'
  ), '加载系统消息失败，请稍后重试')
}

export async function markSystemMessageReadRequest(messageId: string | number) {
  return withServiceFailure(async () => validateServiceResult(
    await api.post(`/api/shop/messages/system/${messageId}/read`),
    CommerceActionResponseSchema,
    '/api/shop/messages/system/:id/read',
    'CommerceActionResponse'
  ), '标记已读失败，请稍后重试')
}

export async function markAllSystemMessagesReadRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.post('/api/shop/messages/system/read-all'),
    CommerceActionResponseSchema,
    '/api/shop/messages/system/read-all',
    'CommerceActionResponse'
  ), '全部标记已读失败，请稍后重试')
}
