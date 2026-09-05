<template>
  <section class="service-order" :class="[`tone-${presentation.tone}`, { embedded, 'has-refund': order.paymentReversalStatus }]" aria-label="推广订单进度">
    <div class="order-content" :tabindex="embedded ? 0 : null" :role="embedded ? 'region' : null" :aria-label="embedded ? '订单信息，可滚动查看' : null">
    <header><span class="order-eyebrow">{{ embedded ? '当前状态' : '订单进度' }}</span><SellerStatusBadge :label="presentation.label" :tone="presentation.tone" /></header>
    <h2>{{ order.productName }}</h2>
    <p class="order-number">{{ order.orderNo }}</p>
    <p class="state-message" role="status" aria-atomic="true">{{ presentation.message }}</p>
    <p v-if="notice" class="order-notice" role="alert">{{ notice }}</p>
    <dl>
      <div><dt>实际金额</dt><dd><strong>{{ Number(order.amount || 0).toFixed(2) }}</strong> LDC</dd></div>
      <div><dt>服务方案</dt><dd>{{ order.packageName }} · {{ order.durationDays ? `${order.durationDays} 天` : '永久' }}</dd></div>
      <div><dt>绑定分类</dt><dd>{{ order.boundCategoryName || order.categoryName || '未分类' }}</dd></div>
      <div><dt>展示范围</dt><dd>{{ placement }}</dd></div>
      <div v-if="order.effectiveAt"><dt>生效时间</dt><dd>{{ order.effectiveAt }}</dd></div>
      <div v-if="order.effectiveAt || order.status === 'active'"><dt>到期时间</dt><dd>{{ order.expiredAt || '永久' }}</dd></div>
    </dl>
    <div v-if="order.status === 'pending'" class="payment-deadline">
      <div><span>支付剩余时间</span><strong role="timer" aria-live="off" aria-label="支付剩余时间">{{ countdown }}</strong></div>
      <p>请在北京时间 {{ deadline }} 前完成支付</p>
    </div>
    <p v-if="feedback || error" class="action-feedback" role="status" aria-atomic="true">{{ error || feedback }}</p>
    </div>
    <footer class="order-footer">
    <div class="order-actions" :class="{ 'has-payment': canPay }">
      <a v-if="fallbackUrl && canPay && !action && !error" class="primary" :href="fallbackUrl" target="_blank" rel="noopener noreferrer">{{ paymentLabel }}<ArrowUpRight :size="16" aria-hidden="true" /></a>
      <button v-else-if="canPay" class="primary" type="button" :disabled="!!action || !!error" @click="$emit('pay', order)">{{ paymentLabel }}<ArrowUpRight :size="16" aria-hidden="true" /></button>
      <button v-if="order.status === 'pending' && !order.paymentReversalStatus" type="button" :disabled="!!action" @click="$emit('refresh', order)"><RefreshCw :size="16" aria-hidden="true" />{{ action === 'refresh' ? '正在检查…' : '检查支付结果' }}</button>
      <button v-else-if="order.paymentReversalStatus && order.paymentReversalStatus !== 'refunded'" type="button" :disabled="!!action" @click="$emit('refresh', order)"><RefreshCw :size="16" aria-hidden="true" />{{ action === 'refresh' ? '正在检查…' : '检查退款进度' }}</button>
      <button v-if="canCancel" class="cancel" type="button" :disabled="!!action" @click="$emit('cancel', order)">{{ action === 'cancel' ? '取消中…' : '取消订单' }}</button>
    </div>
    <p v-if="canPay" class="order-footnote">关闭支付窗口不会取消订单。如已付款，请先检查支付结果。</p>
    <router-link v-if="order.status === 'active' && !order.isSuspendedForCategory" class="product-link" :to="`/product/${order.productId}`">查看物品<ArrowUpRight :size="15" aria-hidden="true" /></router-link>
    <router-link v-else-if="order.isSuspendedForCategory || order.status === 'suspended'" class="product-link" to="/seller/products">前往物品管理<ArrowUpRight :size="15" aria-hidden="true" /></router-link>
    <button v-if="['expired','cancelled'].includes(order.status) && !order.paymentReversalStatus" class="restart" type="button" @click="$emit('restart', order)">选择更多推广方案</button>
    </footer>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { ArrowUpRight, RefreshCw } from '@lucide/vue'
import SellerStatusBadge from '@/components/seller/SellerStatusBadge.vue'
import { canPayTopServiceOrder, canCancelTopServiceOrder, getTopServiceOrderPresentation, topServicePlacement, formatTopServicePaymentCountdown, getTopServicePaymentDeadlineMs } from '@/utils/topServiceOrder'
const props = defineProps({ order: { type: Object, required: true }, embedded: Boolean, now: { type: Number, default: () => Date.now() }, action: { type: String, default: '' }, notice: { type: String, default: '' }, feedback: { type: String, default: '' }, error: { type: String, default: '' }, fallbackUrl: { type: String, default: '' } })
defineEmits(['pay', 'refresh', 'cancel', 'restart'])
const presentation = computed(() => getTopServiceOrderPresentation(props.order, props.now))
const canPay = computed(() => canPayTopServiceOrder(props.order, props.now))
const paymentLabel = computed(() => props.action === 'pay' ? '正在打开…' : props.notice ? '核对信息并继续支付' : '继续支付')
const canCancel = computed(() => canCancelTopServiceOrder(props.order, props.now))
const countdown = computed(() => formatTopServicePaymentCountdown(props.order, props.now))
const placement = computed(() => topServicePlacement(props.order.packageType, props.order.boundCategoryName || props.order.categoryName, props.order.boundUsesSharedGlobalPool === true))
const deadline = computed(() => {
  const ms = getTopServicePaymentDeadlineMs(props.order)
  return ms ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(ms) : '所示截止时间'
})
</script>
<style scoped>
.service-order { padding:24px; border:1px solid var(--seller-border); border-top:3px solid var(--seller-jade); border-radius:14px; background:var(--seller-surface-strong); }
header { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.order-eyebrow { color:var(--seller-muted); font-size:12px; }
h2 { margin:20px 0 8px; color:var(--seller-ink); font-size:19px; line-height:1.55; overflow-wrap:anywhere; }
.order-number { margin:0; font-size:12px; color:var(--seller-muted); overflow-wrap:anywhere; font-variant-numeric:tabular-nums; }
.state-message { margin:18px 0; padding:12px 14px; border-radius:8px; background:var(--seller-jade-soft); color:var(--seller-ink); font-size:13px; line-height:1.8; }
.tone-warning .state-message { border-left:3px solid var(--service-gold); background:var(--service-gold-soft); color:var(--service-gold-ink); }
.has-refund .state-message { border-color:var(--service-rose); background:var(--service-rose-soft); color:var(--service-rose-ink); }
.order-notice,.action-feedback { padding:12px; border:1px solid var(--seller-border-strong); border-radius:8px; color:var(--seller-ink); font-size:13px; line-height:1.8; }
dl { display:grid; gap:13px; margin:18px 0; }
dl>div { display:grid; grid-template-columns:70px minmax(0,1fr); gap:12px; align-items:baseline; }
dt { color:var(--seller-muted); font-size:12px; }
dd { margin:0; text-align:right; color:var(--seller-ink); font-size:13px; line-height:1.65; overflow-wrap:anywhere; font-variant-numeric:tabular-nums; }
dd strong { font-size:22px; font-weight:650; }
.payment-deadline { margin:22px 0 18px; padding-top:16px; border-top:1px solid var(--seller-border); }
.payment-deadline>div { display:flex; justify-content:space-between; align-items:center; gap:12px; color:var(--seller-muted); font-size:13px; }
.payment-deadline strong { color:var(--seller-ink); font-size:26px; font-variant-numeric:tabular-nums; }
.payment-deadline p,.order-footnote { color:var(--seller-muted); font-size:12px; line-height:1.7; margin:8px 0 0; }
.order-actions { display:grid; gap:9px; }
button,a.primary { display:flex; align-items:center; justify-content:center; gap:7px; min-height:44px; padding:10px 12px; border:1px solid var(--seller-border); border-radius:9px; font-size:13px; font-weight:600; background:var(--seller-surface); color:var(--seller-ink); }
button:disabled { opacity:.55; cursor:not-allowed; }
.order-actions .primary { background:var(--seller-navy); color:var(--palette-hex-ffffff); border-color:var(--seller-navy); text-decoration:none; }
button.cancel { border-color:var(--seller-danger); color:var(--seller-danger); background:color-mix(in srgb,var(--seller-danger) 8%,var(--seller-surface-strong)); font-weight:650; }
button.cancel:hover:not(:disabled) { background:color-mix(in srgb,var(--seller-danger) 14%,var(--seller-surface-strong)); }
.product-link { display:flex; justify-content:center; align-items:center; gap:5px; min-height:44px; margin-top:12px; color:var(--seller-jade-strong); font-size:13px; }
.restart { width:100%; margin-top:12px; }
@media(max-width:767px) { .service-order { padding:20px; } }
.service-order.embedded { display:flex; flex-direction:column; min-height:0; padding:0; border:0; border-radius:0; background:transparent; }
.embedded .order-content { min-height:0; overflow-y:auto; overscroll-behavior:contain; }
.embedded h2 { margin:12px 0 6px; font-size:18px; }
.embedded .state-message { margin:12px 0; padding:10px 12px; line-height:1.7; }
.embedded dl { gap:8px; margin:14px 0; }
.embedded .payment-deadline { margin:14px 0 0; padding-top:12px; }
.embedded .payment-deadline strong { font-size:24px; }
.embedded .order-footer { flex:0 0 auto; margin-top:16px; padding-top:14px; border-top:1px solid var(--seller-border); }
.embedded .has-payment { grid-template-columns:repeat(2,minmax(0,1fr)); }
.embedded .has-payment .primary { grid-column:1 / -1; }
.embedded .product-link,.embedded .restart { margin-top:0; }
@media(max-height:520px) and (min-width:641px) { .embedded .order-footer { margin-top:10px; padding-top:10px; } .embedded .has-payment { grid-template-columns:minmax(0,1.15fr) repeat(2,minmax(0,1fr)); } .embedded .has-payment .primary { grid-column:auto; } }
</style>
