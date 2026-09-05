<template>
  <section class="purchase-summary" aria-labelledby="promotion-summary-title">
    <header><span class="summary-eyebrow">本次推广</span><h2 id="promotion-summary-title">核对后，前往支付</h2></header>
    <dl>
      <div><dt>推广物品</dt><dd>{{ product?.name || '尚未选择' }}</dd></div>
      <div><dt>绑定分类</dt><dd>{{ product?.categoryName || '—' }}</dd></div>
      <div><dt>服务方案</dt><dd>{{ service?.name || config?.groupName || '尚未选择' }}</dd></div>
      <div><dt>展示范围</dt><dd>{{ service || config ? placement : '选择服务后显示' }}</dd></div>
      <div><dt>推广时长</dt><dd>{{ config ? `${config.durationDays} 天` : '尚未选择' }}</dd></div>
    </dl>
    <div class="summary-total"><span>应付积分</span><strong>{{ amount }} <small>LDC</small></strong></div>
    <ul id="promotion-payment-rules" class="payment-rules">
      <li>支付确认后开始计时，不自动续费。</li>
      <li>下单后保留名额 <strong>5 分钟</strong>，未付款可取消。</li>
      <li>更换分类会暂停展示，<strong>有效期不顺延</strong>；已生效服务不能自行取消。</li>
    </ul>
    <div class="purchase-action-bar">
      <div class="mobile-price"><span>应付积分</span><strong>{{ amount }} <small>LDC</small></strong></div>
      <button type="button" :disabled="!!reason" aria-describedby="promotion-payment-rules promotion-submit-reason" @click="$emit('submit')">{{ submitting ? '正在创建订单…' : '确认并支付' }}<ArrowUpRight v-if="!submitting" :size="17" aria-hidden="true" /></button>
      <p id="promotion-submit-reason" :class="{ ready: !reason }">{{ reason || '5 分钟内支付 · 改分类不顺延 · 不自动续费' }}</p>
    </div>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { ArrowUpRight } from '@lucide/vue'
import { topServicePlacement } from '@/utils/topServiceOrder'
const props = defineProps({ product: { type: Object, default: null }, service: { type: Object, default: null }, config: { type: Object, default: null }, reason: { type: String, default: '' }, submitting: Boolean })
defineEmits(['submit'])
const amount = computed(() => props.config ? Number(props.config.price || 0).toFixed(2) : '—')
const placement = computed(() => topServicePlacement(props.service?.type || props.config?.packageType, props.product?.categoryName, props.product?.quota?.usesSharedGlobalPool))
</script>
<style scoped>
.purchase-summary { padding:24px; border:1px solid var(--seller-border); border-radius:14px; background:var(--seller-surface-strong); }
.summary-eyebrow { color:var(--seller-jade-strong); font-size:12px; font-weight:650; }
h2 { margin:8px 0 22px; color:var(--seller-ink); font-family:"Noto Serif SC","Songti SC",serif; font-size:22px; font-weight:600; }
dl { display:grid; gap:16px; margin:0; }
dl>div { display:grid; grid-template-columns:72px minmax(0,1fr); align-items:baseline; gap:12px; }
dt { font-size:13px; color:var(--seller-muted); }
dd { margin:0; font-size:14px; line-height:1.65; color:var(--seller-ink); text-align:right; overflow-wrap:anywhere; }
.summary-total { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-top:24px; padding-top:20px; border-top:1px solid var(--seller-border); }
.summary-total>span { color:var(--seller-muted); font-size:14px; }
.summary-total strong { color:var(--seller-ink); font-size:30px; font-weight:650; font-variant-numeric:tabular-nums; }
strong small { font-size:12px; font-weight:500; }
.payment-rules { margin:20px 0; padding:16px 16px 16px 30px; background:var(--seller-surface-muted); border-radius:9px; color:var(--seller-muted); font-size:12px; line-height:1.8; }
.payment-rules li+li { margin-top:6px; }
.payment-rules strong { color:var(--seller-ink); font-weight:600; }
button { display:flex; align-items:center; justify-content:center; gap:6px; width:100%; min-height:48px; padding:12px; border:0; border-radius:9px; background:var(--seller-navy); color:var(--palette-hex-ffffff); font-size:13px; font-weight:600; }
button:disabled { background:var(--seller-surface-soft); color:var(--seller-muted); cursor:not-allowed; }
.purchase-action-bar p { margin:10px 0 0; color:var(--seller-muted); text-align:center; font-size:12px; line-height:1.6; }
.mobile-price { display:none; }
@media(max-width:767px) {
  .purchase-summary { padding:20px; }
  .purchase-action-bar { position:fixed; bottom:0; left:0; right:0; z-index:50; display:grid; grid-template-columns:1fr; gap:8px; padding:12px 16px calc(12px + env(safe-area-inset-bottom,0px)); border-top:1px solid var(--seller-border); background:var(--seller-surface-strong); box-shadow:0 -4px 18px var(--palette-rgba-0-0-0-p06); }
  .mobile-price { display:flex; justify-content:space-between; align-items:baseline; color:var(--seller-muted); font-size:12px; }
  .mobile-price strong { font-size:20px; color:var(--seller-ink); font-variant-numeric:tabular-nums; }
  .purchase-action-bar button { font-size:14px; }
  .purchase-action-bar p { margin:0; }
}
</style>
