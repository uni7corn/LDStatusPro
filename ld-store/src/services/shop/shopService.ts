import { api, type JsonValue } from '@/utils/api'
import {
  MyShopResponseSchema,
  ShopDetailResponseSchema,
  ShopMutationResponseSchema
} from '@/contracts/commerce'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'

export async function fetchShopDetailRequest(shopId: string | number) {
  return withServiceFailure(async () => validateServiceResult(
    await api.get(`/api/shops/${shopId}`),
    ShopDetailResponseSchema,
    '/api/shops/:id',
    'ShopDetailResponse'
  ), '加载小店详情失败，请稍后重试')
}

export async function fetchMyShopRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.get('/api/shops/my'),
    MyShopResponseSchema,
    '/api/shops/my',
    'MyShopResponse'
  ), '加载小店信息失败，请稍后重试')
}

export async function createShopRequest(payload: Record<string, JsonValue>) {
  return withServiceFailure(async () => validateServiceResult(
    await api.post('/api/shops', payload),
    ShopMutationResponseSchema,
    '/api/shops',
    'ShopMutationResponse'
  ), '提交小店申请失败，请稍后重试')
}

export async function updateShopRequest(payload: Record<string, JsonValue>) {
  return withServiceFailure(async () => validateServiceResult(
    await api.put('/api/shops/my', payload),
    ShopMutationResponseSchema,
    '/api/shops/my',
    'ShopMutationResponse'
  ), '更新小店失败，请稍后重试')
}

export async function offlineShopRequest() {
  return withServiceFailure(async () => validateServiceResult(
    await api.post('/api/shops/my/offline'),
    ShopMutationResponseSchema,
    '/api/shops/my/offline',
    'ShopMutationResponse'
  ), '下架小店失败，请稍后重试')
}
