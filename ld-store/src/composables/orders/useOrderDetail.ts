import { ref, type Ref } from 'vue'
import type { Order } from '@/contracts/commerce'
import type { ApiResult } from '@/utils/api'

export type OrderDetailRecord = Order & Record<string, unknown>
export type OrderLogRecord = Record<string, unknown>

interface OrderDetailPayload {
  order: OrderDetailRecord
  logs?: OrderLogRecord[]
}

interface OrderDetailOptions {
  orderId: Ref<string>
  role: Ref<string>
  fetchDetail: (orderId: string, role: string, signal: AbortSignal) => Promise<ApiResult<OrderDetailPayload>>
  onError?: (message: string) => void
  refreshIntervalMs?: number
}

export function useOrderDetail(options: OrderDetailOptions) {
  const loading = ref(true)
  const order = ref<OrderDetailRecord | null>(null)
  const logs = ref<OrderLogRecord[]>([])
  let requestId = 0
  let controller: AbortController | null = null
  let refreshTimer: ReturnType<typeof setInterval> | null = null

  async function load(loadOptions: { silent?: boolean } = {}) {
    const silent = loadOptions.silent === true
    const currentRequestId = ++requestId
    controller?.abort('caller')
    controller = new AbortController()
    if (!silent) loading.value = true

    try {
      const result = await options.fetchDetail(options.orderId.value, options.role.value, controller.signal)
      if (currentRequestId !== requestId || controller.signal.aborted) return null
      if (!result.success) {
        if (!silent) options.onError?.(result.error || '加载订单详情失败')
        return result
      }
      order.value = result.data.order
      logs.value = Array.isArray(result.data.logs) ? result.data.logs : []
      return result
    } catch (cause) {
      if (currentRequestId !== requestId || controller.signal.aborted) return null
      if (!silent) options.onError?.(cause instanceof Error ? cause.message : '加载订单详情失败')
      return null
    } finally {
      if (!silent && currentRequestId === requestId) loading.value = false
    }
  }

  function stopAutoRefresh() {
    if (!refreshTimer) return
    clearInterval(refreshTimer)
    refreshTimer = null
  }

  function startAutoRefresh(enabled: () => boolean) {
    stopAutoRefresh()
    if (!enabled()) return
    refreshTimer = setInterval(() => {
      if (enabled()) void load({ silent: true })
      else stopAutoRefresh()
    }, options.refreshIntervalMs ?? 30_000)
  }

  function stop() {
    requestId += 1
    controller?.abort('caller')
    controller = null
    stopAutoRefresh()
    loading.value = false
  }

  return { loading, order, logs, load, startAutoRefresh, stopAutoRefresh, stop }
}
