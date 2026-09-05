import { api } from '@/utils/api'
import { MerchantDashboardResponseSchema } from '@/contracts/commerce'
import { validateServiceResult } from '@/services/serviceContract'

const VALID_RANGES = new Set(['7d', '30d', '90d'])

export async function fetchMerchantDashboard(range = '30d') {
  const normalized = VALID_RANGES.has(range) ? range : '30d'
  return validateServiceResult(
    await api.get(`/api/shop/merchant/dashboard?range=${normalized}`, { timeout: 20_000 }),
    MerchantDashboardResponseSchema,
    '/api/shop/merchant/dashboard',
    'MerchantDashboardResponse'
  )
}
