import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { InferOutput } from 'valibot'
import type { FulfillmentPolicySchema, SellerFulfillment } from '@/contracts/fulfillment'
import { acknowledgeFulfillment, fetchFulfillmentPolicy, fetchSellerFulfillment } from '@/services/shop/fulfillmentService'

type Policy = InferOutput<typeof FulfillmentPolicySchema>

/** A confirmation belongs to one mounted publishing flow, account and policy version. */
export function useFulfillmentReminder(getOwner: () => string) {
  const open = ref(false)
  const loading = ref(false)
  const busy = ref(false)
  const error = ref('')
  const state = ref<SellerFulfillment | null>(null)
  const policy = ref<Policy | null>(null)
  const confirmedVersion = ref('')
  const pending = ref(false)
  const confirmationCount = ref(0)
  let generation = 0
  let completion: Promise<boolean> | null = null
  let resolveCompletion: ((accepted: boolean) => void) | null = null
  let forceReminder = false

  function finish(accepted: boolean) {
    generation++
    open.value = false
    loading.value = false
    busy.value = false
    pending.value = false
    const resolve = resolveCompletion
    resolveCompletion = null
    completion = null
    resolve?.(accepted)
  }

  function reset() {
    finish(false)
    confirmedVersion.value = ''
    state.value = null
    policy.value = null
    error.value = ''
  }

  async function load() {
    const current = ++generation
    loading.value = true
    error.value = ''
    const [rules, seller] = await Promise.all([fetchFulfillmentPolicy(), fetchSellerFulfillment()])
    if (current !== generation) return
    loading.value = false
    if (!rules.success) {
      error.value = rules.error
      open.value = true
      return
    }
    policy.value = rules.data
    if (!rules.data.enabled) {
      confirmedVersion.value = ''
      finish(true)
      return
    }
    if (!seller.success) {
      error.value = seller.error
      open.value = true
      return
    }
    state.value = seller.data
    if (seller.data.policyVersion !== rules.data.version || !seller.data.enabled) {
      error.value = '发货规则已更新，请重新加载后确认。'
      open.value = true
      return
    }
    if (!forceReminder && confirmedVersion.value === rules.data.version && seller.data.accepted && !seller.data.activeRestriction) {
      finish(true)
      return
    }
    open.value = true
  }

  function request(options: { refresh?: boolean; force?: boolean } = {}): Promise<boolean> {
    if (completion) return completion
    if (confirmedVersion.value && !options.refresh && !options.force) return Promise.resolve(true)
    forceReminder = !!options.force
    pending.value = true
    open.value = !confirmedVersion.value || forceReminder
    completion = new Promise(resolve => { resolveCompletion = resolve })
    const result = completion
    void load()
    return result
  }

  async function confirm() {
    if (loading.value || busy.value || error.value || !state.value || !policy.value || state.value.activeRestriction) return
    if (!state.value.accepted) {
      const current = generation
      busy.value = true
      const result = await acknowledgeFulfillment(policy.value.version)
      if (current !== generation) return
      busy.value = false
      if (!result.success) {
        if (result.errorCode === 'POLICY_VERSION_MISMATCH') {
          confirmedVersion.value = ''
          await load()
        } else error.value = result.error
        return
      }
      state.value = result.data
      if (!result.data.accepted || result.data.policyVersion !== policy.value.version) {
        await load()
        return
      }
      if (result.data.activeRestriction) return
    }
    confirmedVersion.value = policy.value.version
    confirmationCount.value++
    finish(true)
  }

  watch(getOwner, reset, { flush: 'sync' })
  onBeforeUnmount(reset)
  return {
    pending,
    confirmationCount,
    request,
    confirm,
    cancel: () => finish(false),
    retry: () => { if (!loading.value && !busy.value) void load() },
    reset,
    dialogProps: computed(() => ({ open: open.value, loading: loading.value, busy: busy.value, error: error.value, state: state.value, policy: policy.value }))
  }
}
