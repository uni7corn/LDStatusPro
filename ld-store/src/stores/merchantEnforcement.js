import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchMerchantEnforcementRequest } from '@/services/shop/merchantService'

const ACTIVE_STATE = Object.freeze({
  status: 'active',
  sellingAllowed: true,
  version: 0,
  reasonCode: null,
  reason: null,
  changedByName: null,
  changedAt: null
})

export const useMerchantEnforcementStore = defineStore('merchantEnforcement', () => {
  const enforcement = ref({ ...ACTIVE_STATE })
  const history = ref([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  const refreshedAt = ref(0)
  let pendingRequest = null

  const sellingDisabled = computed(() => enforcement.value.status === 'disabled')

  async function refresh({ force = false } = {}) {
    if (!force && loaded.value && Date.now() - refreshedAt.value < 15_000) return true
    if (pendingRequest) return pendingRequest

    loading.value = true
    error.value = ''
    pendingRequest = (async () => {
      const result = await fetchMerchantEnforcementRequest()
      const payload = result?.success ? result.data : null
      if (result?.success === false || !payload?.enforcement) {
        error.value = result?.error || '卖家权限状态加载失败'
        return false
      }
      enforcement.value = { ...ACTIVE_STATE, ...payload.enforcement }
      history.value = Array.isArray(payload.history) ? payload.history : []
      loaded.value = true
      refreshedAt.value = Date.now()
      return true
    })()

    try {
      return await pendingRequest
    } finally {
      pendingRequest = null
      loading.value = false
    }
  }

  function reset() {
    enforcement.value = { ...ACTIVE_STATE }
    history.value = []
    loading.value = false
    loaded.value = false
    error.value = ''
    refreshedAt.value = 0
    pendingRequest = null
  }

  return { enforcement, history, loading, loaded, error, sellingDisabled, refresh, reset }
})
