import { ref, type Ref } from 'vue'

export type OrderActionKind = 'cancel' | 'deliver' | 'payment' | 'refresh' | 'buyRefresh'
export type OrderActionKey = string | number

type ActionResult = { success: boolean; [key: string]: unknown }

export function useOrderActions() {
  const cancellingOrderId = ref<OrderActionKey | null>(null)
  const deliveringOrderId = ref<OrderActionKey | null>(null)
  const payingOrderId = ref<OrderActionKey | null>(null)
  const refreshingOrderId = ref<OrderActionKey | null>(null)
  const refreshingBuyOrderId = ref<OrderActionKey | null>(null)

  const actionRefs: Record<OrderActionKind, Ref<OrderActionKey | null>> = {
    cancel: cancellingOrderId,
    deliver: deliveringOrderId,
    payment: payingOrderId,
    refresh: refreshingOrderId,
    buyRefresh: refreshingBuyOrderId
  }

  function isBusy(kind: OrderActionKind, key: OrderActionKey): boolean {
    return actionRefs[kind].value === key
  }

  async function run<T extends ActionResult>(
    kind: OrderActionKind,
    key: OrderActionKey,
    action: () => Promise<T>
  ): Promise<T | null> {
    const state = actionRefs[kind]
    if (state.value !== null) return null
    state.value = key
    try {
      return await action()
    } finally {
      if (state.value === key) state.value = null
    }
  }

  function clear() {
    for (const state of Object.values(actionRefs)) state.value = null
  }

  return {
    cancellingOrderId,
    deliveringOrderId,
    payingOrderId,
    refreshingOrderId,
    refreshingBuyOrderId,
    isBusy,
    run,
    clear
  }
}
