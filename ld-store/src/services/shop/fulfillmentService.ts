import { api } from '@/utils/api'
import { FulfillmentPolicySchema, SellerFulfillmentSchema } from '@/contracts/fulfillment'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'

export const fetchFulfillmentPolicy = () => withServiceFailure(async () => validateServiceResult(
  await api.get('/api/shop/fulfillment-policy'), FulfillmentPolicySchema, '/api/shop/fulfillment-policy', 'FulfillmentPolicy'
), '加载发货规则失败')
export const fetchSellerFulfillment = () => withServiceFailure(async () => validateServiceResult(
  await api.get('/api/shop/merchant/fulfillment'), SellerFulfillmentSchema, '/api/shop/merchant/fulfillment', 'SellerFulfillment'
), '加载履约记录失败')
export const acknowledgeFulfillment = (version: string) => withServiceFailure(async () => validateServiceResult(
  await api.post('/api/shop/merchant/fulfillment/acknowledge', { version, accepted: true }), SellerFulfillmentSchema,
  '/api/shop/merchant/fulfillment/acknowledge', 'SellerFulfillment'
), '确认发货规则失败')
