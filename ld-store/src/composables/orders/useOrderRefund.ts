import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch, type Ref } from 'vue'
import type { Refund } from '@/contracts/commerce'
import { useDialog } from '@/composables/useDialog'
import { useToast } from '@/composables/useToast'
import { useNotificationSummaryStore } from '@/stores/notificationSummary'
import {
  approveRefundRequest,
  proactiveRefundRequest,
  contactRefundBuyerRequest,
  createRefundRequest,
  fetchOrderRefundRequest,
  rejectRefundRequest
} from '@/services/shop/refundService'
import {
  REFUND_REASON_OPTIONS,
  buildLinuxDoMessageUrl,
  buildRefundStages,
  formatRefundDate,
  getRefundErrorMessage,
  getRefundReasonLabel,
  getRefundStatusMeta,
  validateRefundForm
} from '@/utils/refund'

type RefundRecord = Refund & Record<string, unknown>

interface RefundOrder extends Record<string, unknown> {
  orderNo?: string
  paidAmount?: number | string
  amount?: number | string
  sellerUsername?: string
  buyerUsername?: string
  seller?: { username?: string }
  buyer?: { username?: string }
}

interface RefundState {
  serverNow?: string
  responsePolicyEnabled?: boolean
  fulfillment?: { canProactivelyRefund?: boolean }
  eligibility?: { canApply?: boolean; message?: string }
  refund?: RefundRecord | null
  disputeGuideUrl?: string
}

interface RefundFormState {
  reasonCode: string
  reasonDetail: string
  buyerContactedSeller: boolean
}

interface UseOrderRefundOptions {
  order: Ref<RefundOrder>
  role: Ref<string>
  onUpdated?: () => void
}

export function useOrderRefund(options: UseOrderRefundOptions) {
  const dialog = useDialog()
  const toast = useToast()
  const notificationSummaryStore = useNotificationSummaryStore()
  const loading = ref(true)
  const autoRefreshPaused = ref(false)
  let refreshTimer: ReturnType<typeof setInterval> | undefined
  const loadError = ref('')
  const refundState = ref<RefundState | null>(null)
  const formOpen = ref(false)
  const submitting = ref(false)
  const errors = ref<Record<string, string>>({})
  const errorSummary = ref<HTMLElement | null>(null)
  const sellerActionMode = ref('')
  const sellerMessage = ref('')
  const sellerActionError = ref('')
  const sellerSubmitting = ref(false)
  const form = reactive<RefundFormState>({ reasonCode: '', reasonDetail: '', buyerContactedSeller: false })
  let loadRequestId = 0
  let loadController: AbortController | null = null

  const orderNo = computed(() => String(options.order.value?.orderNo || ''))
  const isBuyer = computed(() => options.role.value === 'buyer')
  const refund = computed(() => refundState.value?.refund || null)
  const eligibility = computed(() => refundState.value?.eligibility || null)
  const canApplyRefund = computed(() => eligibility.value?.canApply === true)
  const refundAvailabilityMessage = computed(() => canApplyRefund.value
    ? '当前可直接申请全额退款；联系卖家是可选的协商方式，不影响申请资格。'
    : `暂不可提交：${eligibility.value?.message || '未能确认退款申请资格，请刷新后重试。'}`)
  const disputeGuideUrl = computed(() => refundState.value?.disputeGuideUrl || 'https://credit.linux.do/docs/how-to-use#争议处理')
  const statusMeta = computed(() => getRefundStatusMeta(refund.value?.status))
  const stages = computed(() => buildRefundStages(refund.value?.status, Boolean(refund.value), String(refund.value?.source || 'buyer'), String(refund.value?.executionTrigger || '')))
  const refundAmount = computed(() => Number(options.order.value?.paidAmount ?? options.order.value?.amount ?? 0))
  const counterpartyUsername = computed(() => isBuyer.value
    ? (options.order.value?.sellerUsername || options.order.value?.seller?.username)
    : (options.order.value?.buyerUsername || options.order.value?.buyer?.username))
  const counterpartyMessageUrl = computed(() => buildLinuxDoMessageUrl(
    counterpartyUsername.value,
    orderNo.value,
    isBuyer.value ? 'buyer' : 'seller'
  ))
  const canProactivelyRefund = computed(() => !isBuyer.value && !refund.value
    && refundState.value?.fulfillment?.canProactivelyRefund === true)
  const canSellerDecide = computed(() => !isBuyer.value && (refund.value?.allowedActions?.approve ?? ['requested', 'negotiating', 'failed'].includes(String(refund.value?.status || ''))))
  const canSellerReject = computed(() => !isBuyer.value && (refund.value?.allowedActions?.reject ?? ['requested', 'negotiating'].includes(String(refund.value?.status || ''))))
  const canSellerContact = computed(() => !isBuyer.value && (refund.value?.allowedActions?.contact ?? ['requested', 'negotiating'].includes(String(refund.value?.status || ''))))
  const showSellerActions = computed(() => canSellerDecide.value || canSellerReject.value || canSellerContact.value)
  const refundSourceLabel = computed(() => ({ system: '系统超时保障', seller: '卖家主动退款', buyer: '买家售后申请' }[String(refund.value?.source || 'buyer')] || '退款处理'))
  const contactActionLabel = computed(() => refund.value?.status === 'requested' ? '标记为协商中' : '补充协商记录')
  const buyerGuidance = computed(() => {
    const guidance: Record<string, { title: string; description: string; tone: string }> = {
      requested: { title: '申请已送达卖家', description: '请留意订单状态和 LINUX DO 私信，避免重复提交售后。', tone: 'warning' },
      negotiating: { title: '卖家正在与你协商', description: '及时补充问题细节和双方约定，并保留沟通记录。', tone: 'info' },
      processing: { title: '系统正在执行退款', description: '请等待 Credit 返回结果，期间无需重复操作。', tone: 'info' },
      refunded: { title: '退款已经完成', description: 'LDC 已按原订单退回，可在 Credit 中核对余额与记录。', tone: 'success' },
      failed: { title: '本次退款执行失败', description: '卖家可查看失败原因并重试；你可以私信卖家确认下一步。', tone: 'danger' },
      unknown: { title: '退款结果正在人工核对', description: '为避免重复退款，系统已停止自动重试，请等待卖家或平台确认。', tone: 'warning' },
      external_dispute: { title: '本站退款流程已结束', description: '请前往 Credit 核对争议状态、交易记录与积分余额；本站状态不代表积分已经退回。', tone: 'warning' }
    }
    return guidance[String(refund.value?.status || '')] || null
  })

  async function loadRefund(mode?: unknown) {
    const background = mode === true
    if (!orderNo.value) return null
    const currentRequestId = ++loadRequestId
    loadController?.abort('caller')
    loadController = new AbortController()
    if (!background) loading.value = true
    loadError.value = ''
    const result = await fetchOrderRefundRequest(orderNo.value, { signal: loadController.signal })
    if (currentRequestId !== loadRequestId || loadController.signal.aborted) return null
    if (result.success) refundState.value = result.data
    else loadError.value = getRefundErrorMessage(result, '加载退款状态失败，请稍后重试')
    loading.value = false
    return result
  }

  function toggleForm() {
    if (!canApplyRefund.value) return
    formOpen.value = !formOpen.value
    errors.value = {}
  }

  function closeForm() {
    formOpen.value = false
    errors.value = {}
  }

  function validateField(field: 'reasonCode' | 'reasonDetail') {
    const nextErrors = validateRefundForm(form) as Record<'reasonCode' | 'reasonDetail', string>
    errors.value = { ...errors.value, [field]: nextErrors[field] }
    if (!nextErrors[field]) delete errors.value[field]
  }

  async function submitRefund() {
    errors.value = { ...validateRefundForm(form) }
    if (Object.keys(errors.value).length) {
      await nextTick()
      errorSummary.value?.focus()
      return
    }
    const confirmed = await dialog.confirm(
      `将为订单 ${orderNo.value} 申请全额退回 ${refundAmount.value.toFixed(2)} LDC。提交后请等待卖家处理。`,
      { title: '确认提交退款申请', confirmText: '提交退款申请', cancelText: '返回检查' }
    )
    if (!confirmed) return

    submitting.value = true
    const result = await createRefundRequest(orderNo.value, form)
    submitting.value = false
    if (!result.success) {
      toast.error(getRefundErrorMessage(result, '提交退款申请失败，请稍后重试'))
      return
    }
    refundState.value = result.data
    formOpen.value = false
    if (refundState.value?.refund?.status === 'external_dispute') {
      toast.warning('检测到订单已转 Credit 处理，请前往 Credit 核对实际结果')
    } else {
      toast.success('退款申请已提交')
    }
    options.onUpdated?.()
  }

  function openSellerAction(mode: string) {
    sellerActionMode.value = sellerActionMode.value === mode ? '' : mode
    sellerMessage.value = mode === 'contact' ? String(refund.value?.sellerResponse || '') : ''
    sellerActionError.value = ''
  }

  function closeSellerAction() {
    sellerActionMode.value = ''
    sellerMessage.value = ''
    sellerActionError.value = ''
  }

  async function applySellerResult(result: Awaited<ReturnType<typeof approveRefundRequest>>, successMessage: string) {
    if (!result.success) {
      const message = getRefundErrorMessage(result, '处理退款申请失败，请稍后重试')
      sellerActionError.value = message
      toast.error(message)
      await loadRefund()
      return false
    }
    refundState.value = result.data
    closeSellerAction()
    if (refundState.value?.refund?.status === 'external_dispute') {
      toast.warning('检测到订单已转 Credit 处理，LD 士多未继续同意或拒绝退款')
    } else if (refundState.value?.refund?.status === 'unknown') {
      toast.warning('退款结果待核对，系统已停止自动重试')
    } else if (refundState.value?.refund?.status === 'failed') {
      toast.error('退款未完成，请按失败原因修复后重试')
    } else {
      toast.success(successMessage)
    }
    options.onUpdated?.()
    if (!isBuyer.value) void notificationSummaryStore.refresh({ force: true })
    return true
  }

  async function submitSellerAction() {
    if (!sellerActionMode.value || sellerSubmitting.value) return
    if (sellerActionMode.value === 'reject' && sellerMessage.value.trim().length < 5) {
      sellerActionError.value = '请至少填写 5 个字，向买家说明拒绝原因'
      return
    }
    if (sellerActionMode.value === 'reject') {
      const confirmed = await dialog.confirm(
        '拒绝后，买家将在订单页看到你的说明，并可前往 LINUX DO Credit 发起争议。',
        { title: '确认拒绝退款申请', confirmText: '确认拒绝', cancelText: '继续协商' }
      )
      if (!confirmed) return
    }

    const actionMode = sellerActionMode.value
    sellerSubmitting.value = true
    const result = actionMode === 'reject'
      ? await rejectRefundRequest(orderNo.value, sellerMessage.value)
      : await contactRefundBuyerRequest(orderNo.value, sellerMessage.value)
    sellerSubmitting.value = false
    await applySellerResult(result, actionMode === 'reject' ? '已拒绝退款申请' : '协商记录已更新')
  }

  async function approveRefund() {
    if (!canSellerDecide.value || sellerSubmitting.value) return
    const amount = Number(refund.value?.refundAmount || 0).toFixed(2)
    const retrying = refund.value?.status === 'failed'
    const confirmed = await dialog.confirm(
      `将通过 LINUX DO Credit 为订单 ${orderNo.value} 全额退回 ${amount} LDC。该操作成功后不可撤销，卡密、库存、优惠券和限购额度不会恢复。`,
      { title: retrying ? '确认重试退款' : '确认同意并退款', confirmText: retrying ? '确认重试' : '同意并退款', cancelText: '返回检查' }
    )
    if (!confirmed) return

    sellerSubmitting.value = true
    const result = await approveRefundRequest(orderNo.value)
    sellerSubmitting.value = false
    await applySellerResult(result, '退款已完成')
  }

  async function proactivelyRefund() {
    if (!canProactivelyRefund.value || sellerSubmitting.value) return
    const confirmed = await dialog.confirm(`将为订单 ${orderNo.value} 原路退回全部 ${refundAmount.value.toFixed(2)} LDC。成功后不可撤销，库存、优惠券和限购额度不会恢复；截止后发起且成功的退款仍按超时规则计次。`, { title: '无法履约，主动全额退款', confirmText: '确认全额退款', cancelText: '返回检查' })
    if (!confirmed) return
    sellerSubmitting.value = true
    const result = await proactiveRefundRequest(orderNo.value)
    sellerSubmitting.value = false
    await applySellerResult(result, '退款处理结果已更新')
  }

  function stop() {
    clearInterval(refreshTimer)
    loadRequestId += 1
    loadController?.abort('caller')
    loadController = null
  }

  watch(orderNo, (next, previous) => {
    if (next && next !== previous) void loadRefund()
  })
  onMounted(() => {
    void loadRefund()
    refreshTimer = setInterval(() => {
      if (!document.hidden && !autoRefreshPaused.value && !loading.value && !sellerSubmitting.value && !submitting.value && !formOpen.value && !sellerActionMode.value && ['requested', 'negotiating', 'processing'].includes(String(refund.value?.status || ''))) void loadRefund(true)
    }, 30000)
  })
  onUnmounted(stop)

  return {
    autoRefreshPaused, loading, loadError, refundState, refund, eligibility, formOpen, submitting, errors, errorSummary,
    sellerActionMode, sellerMessage, sellerActionError, sellerSubmitting, form, orderNo, isBuyer,
    canApplyRefund, refundAvailabilityMessage, disputeGuideUrl, statusMeta, stages, refundAmount,
    counterpartyMessageUrl, canSellerDecide, canSellerReject, canSellerContact, showSellerActions, contactActionLabel, refundSourceLabel,
    buyerGuidance, loadRefund, toggleForm, closeForm, validateField, submitRefund, openSellerAction,
    closeSellerAction, submitSellerAction, approveRefund, proactivelyRefund, canProactivelyRefund, REFUND_REASON_OPTIONS, formatRefundDate,
    getRefundReasonLabel
  }
}
