<template>
  <SellerDrawer
    :open="open"
    :title="displayCampaign?.name || '优惠券详情'"
    eyebrow="COUPON LEDGER"
    @close="$emit('close')"
  >
    <div v-if="detailLoading" class="drawer-state" aria-live="polite">
      <LoaderCircle class="spinning" :size="26" aria-hidden="true" />
      <span>正在加载活动详情…</span>
    </div>
    <div v-else-if="detailError" class="drawer-state error" role="alert">
      <CircleAlert :size="26" aria-hidden="true" />
      <strong>活动详情加载失败</strong>
      <span>{{ detailError }}</span>
      <button type="button" @click="loadDetail">重新加载</button>
    </div>
    <template v-else-if="displayCampaign">
      <section class="coupon-overview">
        <div class="coupon-track" aria-hidden="true"></div>
        <div class="coupon-overview-main">
          <div class="coupon-badges">
            <SellerStatusBadge v-bind="campaignStatus" />
            <span class="coupon-kind">{{ displayCampaign.scopeType === 'product' ? '商品券' : '店铺券' }}</span>
          </div>
          <strong class="coupon-rule">{{ formatCouponRule(displayCampaign) }}</strong>
          <p>{{ displayCampaign.productName || '店铺内平台商品' }} · {{ spendText }}</p>
          <p class="coupon-period">{{ formatCouponDate(displayCampaign.startsAt) }} 至 {{ formatCouponDate(displayCampaign.expiresAt) }}</p>
        </div>
      </section>

      <div class="overview-actions">
        <button type="button" :disabled="actionLoading" @click="copyClaimUrl">
          <Link2 :size="16" aria-hidden="true" />复制领取链接
        </button>
        <button
          v-if="claimingAction"
          type="button"
          class="claiming-action"
          :class="claimingAction"
          :disabled="actionLoading"
          @click="changeClaiming"
        >
          <Pause v-if="claimingAction === 'pause'" :size="16" aria-hidden="true" />
          <Play v-else :size="16" aria-hidden="true" />
          {{ actionLoading ? '处理中…' : (claimingAction === 'pause' ? '暂停领取' : '恢复领取') }}
        </button>
        <span v-else-if="displayCampaign.claimingControlReason" class="control-reason">{{ displayCampaign.claimingControlReason }}</span>
      </div>

      <dl class="coupon-metrics">
        <div><dt>已领取</dt><dd>{{ displayCampaign.claimedCount }} / {{ displayCampaign.totalQuantity }}</dd></div>
        <div><dt>未使用</dt><dd>{{ displayCampaign.counts?.available || 0 }}</dd></div>
        <div><dt>订单占用</dt><dd>{{ displayCampaign.counts?.reserved || 0 }}</dd></div>
        <div><dt>已使用</dt><dd>{{ displayCampaign.counts?.used || 0 }}</dd></div>
      </dl>

      <div class="discount-summary">
        <span>已支付订单累计让利</span>
        <strong>{{ Number(displayCampaign.totalDiscountAmount || 0).toFixed(2) }} LDC</strong>
      </div>

      <form v-if="quotaEditable" class="quota-editor" @submit.prevent="increaseQuota">
        <label for="coupon-quota-total">增加发行量</label>
        <div>
          <input id="coupon-quota-total" v-model="quotaDraft" type="number" :min="displayCampaign.totalQuantity + 1" max="100000" step="1" inputmode="numeric" />
          <button type="submit" :disabled="actionLoading">更新总量</button>
        </div>
        <small>填写新的发行总量；暂停领取期间也可以先补充数量。</small>
      </form>

      <LiquidTabs v-model="activeTab" class="detail-tabs" :tabs="detailTabs" mode="tabs" activation="automatic" size="sm" aria-label="优惠券详情内容" />

      <section v-show="activeTab === 'claims'" id="coupon-claims-panel" class="claim-ledger" role="tabpanel" aria-labelledby="coupon-claims-tab" tabindex="0">
        <h3 id="claim-ledger-title" class="seller-sr-only">领取明细</h3>
        <form class="claim-filter" role="search" @submit.prevent="applyClaimFilters">
          <label>
            <Search :size="16" aria-hidden="true" />
            <span class="seller-sr-only">搜索领取人或订单号</span>
            <input v-model.trim="claimFilter.search" type="search" placeholder="搜索用户名或订单号" />
          </label>
          <select v-model="claimFilter.status" aria-label="使用状态" @change="applyClaimFilters">
            <option value="all">全部状态</option>
            <option value="unused">未使用</option>
            <option value="reserved">订单占用</option>
            <option value="used">已使用</option>
            <option value="expired">过期未用</option>
          </select>
          <button type="submit">查询</button>
        </form>

        <div v-if="claimsLoading" class="claim-loading" aria-live="polite"><LoaderCircle class="spinning" :size="22" aria-hidden="true" />正在加载领取记录…</div>
        <div v-else-if="claimsError" class="claim-error" role="alert"><span>{{ claimsError }}</span><button type="button" @click="loadClaims">重试</button></div>
        <div v-else-if="claims.length" class="claim-results">
          <div class="claim-table-wrap">
            <table>
              <thead><tr><th scope="col">领取人 / 时间</th><th scope="col">状态</th><th scope="col">关联订单</th><th scope="col">使用时间</th></tr></thead>
              <tbody>
                <tr v-for="claim in claims" :key="claim.claimId">
                  <td><strong>@{{ claim.buyerUsername }}</strong><small>{{ formatCouponDate(claim.claimedAt) }}</small></td>
                  <td><SellerStatusBadge v-bind="claimStatus(claim.status)" /></td>
                  <td>
                    <router-link v-if="claim.orderNo" :to="orderTarget(claim.orderNo)">{{ claim.orderNo }}</router-link>
                    <span v-else>—</span>
                    <small v-if="claim.orderStatus">{{ orderStatusText(claim.orderStatus) }}</small>
                  </td>
                  <td>{{ claim.usedAt ? formatCouponDate(claim.usedAt) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="claim-card-list">
            <article v-for="claim in claims" :key="`mobile-${claim.claimId}`">
              <header><div><strong>@{{ claim.buyerUsername }}</strong><time>{{ formatCouponDate(claim.claimedAt) }} 领取</time></div><SellerStatusBadge v-bind="claimStatus(claim.status)" /></header>
              <dl>
                <div><dt>关联订单</dt><dd><router-link v-if="claim.orderNo" :to="orderTarget(claim.orderNo)">{{ claim.orderNo }}</router-link><span v-else>—</span><small v-if="claim.orderStatus">{{ orderStatusText(claim.orderStatus) }}</small></dd></div>
                <div><dt>使用时间</dt><dd>{{ claim.usedAt ? formatCouponDate(claim.usedAt) : '—' }}</dd></div>
              </dl>
            </article>
          </div>
        </div>
        <div v-else class="claim-empty">
          <TicketCheck :size="30" aria-hidden="true" />
          <strong>{{ claimFilter.search || claimFilter.status !== 'all' ? '没有符合条件的领取记录' : '还没有买家领取' }}</strong>
          <span>{{ claimFilter.search || claimFilter.status !== 'all' ? '可清除搜索或切换状态后再查看。' : '分享领取链接后，记录会按时间出现在这里。' }}</span>
        </div>
        <SellerPagination :page="claimPagination.page" :total-pages="claimPagination.totalPages" :total="claimPagination.total" @change="changeClaimPage" />
      </section>

      <section v-show="activeTab === 'events'" id="coupon-events-panel" class="event-ledger" role="tabpanel" aria-labelledby="coupon-events-tab" tabindex="0">
        <ol v-if="displayCampaign.events?.length">
          <li v-for="event in displayCampaign.events" :key="event.id">
            <span class="event-marker" aria-hidden="true"></span>
            <div><strong>{{ getCouponEventLabel(event.action) }}</strong><p>{{ event.actorName || event.actorType || '系统' }}<template v-if="event.orderNo"> · 订单 {{ event.orderNo }}</template></p></div>
            <time>{{ formatCouponDate(event.createdAt) }}</time>
          </li>
        </ol>
        <div v-else class="claim-empty"><History :size="30" aria-hidden="true" /><strong>暂无活动记录</strong></div>
      </section>
    </template>
  </SellerDrawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { CircleAlert, History, Link2, LoaderCircle, Pause, Play, Search, TicketCheck } from '@lucide/vue'
import { useDialog } from '@/composables/useDialog'
import { useToast } from '@/composables/useToast'
import {
  fetchSellerCouponClaimsRequest,
  formatCouponDate,
  formatCouponRule,
  getSellerCouponRequest,
  increaseCouponQuotaRequest,
  setCouponClaimingRequest
} from '@/services/shop/couponService'
import {
  buildSellerCouponClaimsQuery,
  getCouponCampaignStateMeta,
  getCouponClaimingAction,
  getCouponClaimStatusMeta,
  getCouponEventLabel
} from '@/utils/sellerCoupons'
import SellerDrawer from './SellerDrawer.vue'
import LiquidTabs from '@/components/common/LiquidTabs.vue'
import SellerPagination from './SellerPagination.vue'
import SellerStatusBadge from './SellerStatusBadge.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  campaign: { type: Object, default: null }
})
const emit = defineEmits(['close', 'changed'])
const dialog = useDialog()
const toast = useToast()
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const claims = ref([])
const claimsLoading = ref(false)
const claimsError = ref('')
const activeTab = ref('claims')
const detailTabs = [
  { value: 'claims', label: '领取明细', id: 'coupon-claims-tab', panelId: 'coupon-claims-panel' },
  { value: 'events', label: '活动记录', id: 'coupon-events-tab', panelId: 'coupon-events-panel' }
]
const actionLoading = ref(false)
const quotaDraft = ref('')
const claimFilter = reactive({ search: '', status: 'all' })
const claimPagination = reactive({ page: 1, pageSize: 20, total: 0, totalPages: 0 })
let detailSequence = 0
let claimsSequence = 0

const displayCampaign = computed(() => detail.value || props.campaign)
const campaignStatus = computed(() => getCouponCampaignStateMeta(displayCampaign.value?.state))
const claimingAction = computed(() => getCouponClaimingAction(displayCampaign.value))
const spendText = computed(() => Number(displayCampaign.value?.minSpend || 0) > 0
  ? `满 ${Number(displayCampaign.value.minSpend).toFixed(2)} LDC 可用`
  : '无门槛')
const quotaEditable = computed(() => displayCampaign.value
  && !['closed', 'expired', 'disabled'].includes(displayCampaign.value.state))

function claimStatus(status) {
  return getCouponClaimStatusMeta(status)
}

function orderTarget(orderNo) {
  return { path: `/seller/orders/${encodeURIComponent(orderNo)}`, query: { source: 'product' } }
}

function orderStatusText(status) {
  return ({ pending: '待支付', paid: '已支付', delivered: '已发货', completed: '已完成', cancelled: '已取消', expired: '已过期', refunded: '已退款' })[status] || status
}

async function loadDetail() {
  if (!props.open || !props.campaign?.id) return
  const sequence = ++detailSequence
  detailLoading.value = true
  detailError.value = ''
  const result = await getSellerCouponRequest(props.campaign.id)
  if (sequence !== detailSequence) return
  if (result.success) {
    detail.value = result.data
    quotaDraft.value = String(Number(result.data.totalQuantity || 0) + 1)
  } else {
    detail.value = null
    detailError.value = result.error || '优惠券详情加载失败'
  }
  detailLoading.value = false
}

async function loadClaims(page = claimPagination.page || 1) {
  if (!props.open || !props.campaign?.id) return
  const sequence = ++claimsSequence
  claimsLoading.value = true
  claimsError.value = ''
  const result = await fetchSellerCouponClaimsRequest(props.campaign.id, buildSellerCouponClaimsQuery({
    ...claimFilter,
    page,
    pageSize: claimPagination.pageSize
  }))
  if (sequence !== claimsSequence) return
  if (result.success) {
    claims.value = result.data?.items || []
    Object.assign(claimPagination, result.data?.pagination || { page, pageSize: 20, total: 0, totalPages: 0 })
  } else {
    claims.value = []
    claimsError.value = result.error || '领取记录加载失败'
  }
  claimsLoading.value = false
}

function applyClaimFilters() {
  claimPagination.page = 1
  void loadClaims(1)
}

function changeClaimPage(page) {
  claimPagination.page = page
  void loadClaims(page)
}

async function copyClaimUrl() {
  const campaign = displayCampaign.value
  if (!campaign) return
  const url = `${window.location.origin}${campaign.claimPath || `/coupon/${campaign.publicToken}`}`
  try {
    await navigator.clipboard.writeText(url)
    toast.success('领取链接已复制')
  } catch {
    toast.error('复制失败，请手动复制领取链接')
  }
}

async function changeClaiming() {
  const campaign = displayCampaign.value
  const action = claimingAction.value
  if (!campaign || !action || actionLoading.value) return
  if (action === 'pause') {
    const confirmed = await dialog.confirm('暂停后新买家暂时不能领取；已经领取且仍有效的优惠券可以继续使用。', {
      title: '暂停领取？',
      confirmText: '暂停领取'
    })
    if (!confirmed) return
  }
  actionLoading.value = true
  const result = await setCouponClaimingRequest(campaign.id, action === 'resume')
  if (result.success) {
    toast.success(action === 'resume' ? '已恢复领取' : '已暂停领取')
    emit('changed', result.data)
    await loadDetail()
  } else toast.error(result.error || '领取状态更新失败')
  actionLoading.value = false
}

async function increaseQuota() {
  const campaign = displayCampaign.value
  const total = Number(quotaDraft.value)
  if (!campaign || !Number.isInteger(total) || total <= campaign.totalQuantity) {
    toast.warning('新的发行总量必须大于当前总量')
    return
  }
  actionLoading.value = true
  const result = await increaseCouponQuotaRequest(campaign.id, total)
  if (result.success) {
    toast.success('发行量已增加')
    emit('changed', result.data)
    await loadDetail()
  } else toast.error(result.error || '发行量更新失败')
  actionLoading.value = false
}

watch(() => [props.open, props.campaign?.id], async ([open, id], previous = []) => {
  if (!open || !id) {
    detailSequence += 1
    claimsSequence += 1
    return
  }
  if (id !== previous[1]) {
    detail.value = null
    claims.value = []
    claimFilter.search = ''
    claimFilter.status = 'all'
    Object.assign(claimPagination, { page: 1, pageSize: 20, total: 0, totalPages: 0 })
    activeTab.value = 'claims'
  }
  await Promise.all([loadDetail(), loadClaims(1)])
}, { immediate: true })
</script>

<style scoped>
.drawer-state { min-height: 360px; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--seller-muted); text-align: center; }
.drawer-state.error { color: var(--seller-danger); }.drawer-state button, .claim-error button { min-height: 42px; padding: 0 14px; border: 1px solid var(--seller-border); border-radius: 9px; background: var(--seller-surface-strong); color: var(--seller-ink); }
.spinning { animation: spin .8s linear infinite; }
.coupon-overview { position: relative; overflow: hidden; display: grid; grid-template-columns: 12px minmax(0, 1fr); border: 1px solid var(--seller-border); border-radius: 14px; background: var(--seller-surface-strong); }
.coupon-track { border-right: 1px dashed var(--seller-border-strong); background: color-mix(in srgb, var(--seller-jade) 15%, var(--seller-surface)); }
.coupon-overview-main { min-width: 0; padding: 20px; }
.coupon-badges { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.coupon-kind { min-height: 30px; display: inline-flex; align-items: center; padding: 5px 11px; border-radius: 8px; color: var(--seller-ink); background: var(--seller-surface-soft); font-size: 12px; font-weight: 700; }
.coupon-rule { display: block; margin-top: 17px; color: var(--seller-ink); font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", STSong, serif; font-size: 24px; }
.coupon-overview p { margin: 7px 0 0; color: var(--seller-muted); font-size: 13px; line-height: 1.55; }
.coupon-overview .coupon-period { font-variant-numeric: tabular-nums; }
.overview-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.overview-actions button { min-height: 44px; display: inline-flex; align-items: center; gap: 7px; padding: 0 14px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-ink); background: var(--seller-surface-strong); font-weight: 700; }
.overview-actions .claiming-action.pause { color: var(--seller-warning); border-color: color-mix(in srgb, var(--seller-warning) 38%, var(--seller-border)); }
.overview-actions .claiming-action.resume { color: var(--seller-surface-strong); border-color: var(--seller-jade-strong); background: var(--seller-jade-strong); }
.overview-actions button:disabled { cursor: wait; opacity: .55; }
.control-reason { color: var(--seller-muted); font-size: 12px; line-height: 1.5; }
.coupon-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 18px 0 0; }
.coupon-metrics div { min-width: 0; padding: 13px; border: 1px solid var(--seller-border); border-radius: 11px; background: var(--seller-surface-muted); }
.coupon-metrics dt { color: var(--seller-muted); font-size: 11px; }.coupon-metrics dd { overflow-wrap: anywhere; margin: 5px 0 0; color: var(--seller-ink); font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }
.discount-summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 9px; padding: 14px; border-radius: 11px; background: var(--seller-jade-soft); }
.discount-summary span { color: var(--seller-muted); font-size: 13px; }.discount-summary strong { color: var(--seller-jade-strong); font-size: 16px; font-variant-numeric: tabular-nums; }
.quota-editor { display: grid; gap: 7px; margin-top: 16px; padding: 15px; border: 1px solid var(--seller-border); border-radius: 12px; }
.quota-editor label { color: var(--seller-ink); font-size: 13px; font-weight: 750; }.quota-editor > div { display: flex; gap: 8px; }.quota-editor input { min-width: 0; min-height: 44px; flex: 1; padding: 0 12px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-ink); background: var(--seller-surface-strong); }.quota-editor button { min-height: 44px; padding: 0 14px; border-radius: 9px; color: var(--palette-hex-ffffff); background: var(--seller-navy); font-weight: 700; }.quota-editor small { color: var(--seller-muted); font-size: 11px; }
.detail-tabs { margin-top: 24px; }
.claim-filter { display: grid; grid-template-columns: minmax(0, 1fr) 130px auto; gap: 8px; margin: 16px 0 12px; }
.claim-filter label { min-width: 0; display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 11px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-muted); background: var(--seller-surface-strong); }
.claim-filter input { min-width: 0; width: 100%; border: 0; outline: 0; color: var(--seller-ink); background: transparent; }
.claim-filter select { min-height: 44px; padding: 0 10px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-ink); background: var(--seller-surface-strong); }
.claim-filter > button { min-height: 44px; padding: 0 14px; border-radius: 9px; color: var(--palette-hex-ffffff); background: var(--seller-navy); font-weight: 700; }
.claim-loading, .claim-error { min-height: 190px; display: flex; align-items: center; justify-content: center; gap: 9px; color: var(--seller-muted); }
.claim-error { flex-direction: column; color: var(--seller-danger); }
.claim-table-wrap { overflow-x: auto; border: 1px solid var(--seller-border); border-radius: 11px; }
.claim-card-list { display: none; }
table { width: 100%; min-width: 620px; border-collapse: collapse; }
th { padding: 11px 12px; border-bottom: 1px solid var(--seller-border); color: var(--seller-muted); background: var(--seller-surface-soft); text-align: left; font-size: 11px; letter-spacing: .04em; }
td { padding: 13px 12px; border-bottom: 1px solid color-mix(in srgb, var(--seller-border) 72%, transparent); color: var(--seller-ink); font-size: 12px; vertical-align: middle; }
tbody tr:last-child td { border-bottom: 0; } td strong, td small { display: block; } td small { margin-top: 4px; color: var(--seller-muted); } td a { color: var(--seller-jade-strong); font-weight: 750; }
.claim-empty { min-height: 210px; display: grid; place-items: center; align-content: center; gap: 8px; color: var(--seller-muted); text-align: center; }.claim-empty strong { color: var(--seller-ink); }.claim-empty span { max-width: 360px; font-size: 13px; line-height: 1.55; }
.event-ledger { padding-top: 14px; }.event-ledger ol { margin: 0; padding: 0; list-style: none; }.event-ledger li { position: relative; display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 10px; padding: 12px 0; }.event-ledger li:not(:last-child)::after { content: ''; position: absolute; top: 29px; bottom: -5px; left: 7px; border-left: 1px dashed var(--seller-border-strong); }.event-marker { z-index: 1; width: 9px; height: 9px; margin: 5px 0 0 3px; border: 2px solid var(--seller-surface); border-radius: 50%; background: var(--seller-jade-strong); box-shadow: 0 0 0 1px var(--seller-jade); }.event-ledger strong { color: var(--seller-ink); font-size: 13px; }.event-ledger p { margin: 4px 0 0; color: var(--seller-muted); font-size: 12px; }.event-ledger time { color: var(--seller-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.seller-sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 640px) {
  .coupon-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .claim-filter { grid-template-columns: 1fr; }
  .claim-filter > button { width: 100%; }
  .quota-editor > div { flex-direction: column; }
  .event-ledger li { grid-template-columns: 16px minmax(0, 1fr); }.event-ledger time { grid-column: 2; }
  .claim-filter input, .claim-filter select, .quota-editor input { font-size: 16px; }
  .claim-table-wrap { display: none; }
  .claim-card-list { display: grid; gap: 10px; }
  .claim-card-list article { min-width: 0; padding: 14px; border: 1px solid var(--seller-border); border-radius: 11px; background: var(--seller-surface-strong); }
  .claim-card-list header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .claim-card-list header strong, .claim-card-list header time { display: block; }
  .claim-card-list header strong { overflow-wrap: anywhere; color: var(--seller-ink); font-size: 13px; }
  .claim-card-list header time { margin-top: 4px; color: var(--seller-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .claim-card-list dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; margin: 12px 0 0; }
  .claim-card-list dl > div { min-width: 0; padding: 10px; border-radius: 9px; background: var(--seller-surface-muted); }
  .claim-card-list dt { color: var(--seller-muted); font-size: 10px; }
  .claim-card-list dd { overflow-wrap: anywhere; margin: 5px 0 0; color: var(--seller-ink); font-size: 11px; font-variant-numeric: tabular-nums; }
  .claim-card-list dd a { color: var(--seller-jade-strong); font-weight: 750; }
  .claim-card-list dd small { display: block; margin-top: 4px; color: var(--seller-muted); }
}
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } }
</style>
