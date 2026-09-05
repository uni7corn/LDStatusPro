import { ref } from 'vue'
import { useCatalogStore } from '@/stores/catalog'

const EMPTY_STATS = {
  products: { total: 0, online: 0 },
  orders: { total: 0, today: 0, week: 0 },
  stores: 0
}

export function useHomeStats() {
  const catalogStore = useCatalogStore()
  const stats = ref(structuredClone(EMPTY_STATS))

  async function refreshStats() {
    const result = await catalogStore.fetchPublicStats()
    if (result.success) stats.value = result.data
    return {
      success: result.success,
      error: result.success ? '' : (result.error || '加载首页统计失败，请稍后重试')
    }
  }

  return { stats, refreshStats }
}
