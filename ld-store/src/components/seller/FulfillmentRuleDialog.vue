<template>
  <span ref="anchor" hidden></span>
  <Teleport :to="portalTarget || 'body'">
    <Transition name="fulfillment-dialog">
      <div v-if="open" class="fulfillment-dialog-layer" @click.self="$emit('cancel')">
        <section ref="panel" class="fulfillment-dialog-panel" role="dialog" aria-modal="true" aria-labelledby="fulfillment-rule-title" aria-describedby="fulfillment-rule-description" tabindex="-1" @keydown="handleKeydown">
          <header class="rule-heading">
            <div><span class="rule-eyebrow"><PackageCheck :size="16" aria-hidden="true" />普通物品 · 手动交付</span><h2 id="fulfillment-rule-title">发布普通物品前，请确认交付安排</h2></div>
            <button type="button" class="rule-close" aria-label="关闭发货规则提醒" @click="$emit('cancel')"><X :size="20" aria-hidden="true" /></button>
          </header>
          <div class="rule-body" :aria-busy="loading || busy">
            <p v-if="loading" id="fulfillment-rule-description" role="status">正在读取发货规则…</p>
            <template v-else-if="policy && state">
              <p id="fulfillment-rule-description" class="rule-intro">普通物品需要您手动交付，请确认能够在买家支付后 <strong>{{ policy.deliveryHours }} 小时内</strong>完成。</p>
              <ul class="rule-timeline">
                <li><strong>{{ policy.offlineHours }} 小时</strong><span>未发货，自动下架对应物品。</span></li>
                <li><strong>{{ policy.deliveryHours }} 小时</strong><span>未发货，自动发起实付全额退款。<small>实际到账以退款结果为准。</small></span></li>
                <li><strong>{{ policy.strikeThreshold }} 笔超时</strong><span>最近 {{ policy.strikeWindowDays }} 天累计 {{ policy.strikeThreshold }} 笔有效超时退款，限制新增交易 {{ policy.restrictionHours / 24 }} 天。</span></li>
              </ul>
              <p class="rule-help">无法按时交付时，请在截止前主动处理退款。<a :href="policy.ruleUrl" target="_blank" rel="noopener noreferrer">完整规则<ArrowUpRight :size="14" aria-hidden="true" /></a></p>
              <p v-if="state.activeRestriction" class="rule-error" role="alert">当前新增交易受限，截止至 {{ formatDate(state.activeRestriction.endsAt) }}（北京时间）。已有订单仍可交付及处理售后。<a :href="state.supportUrl" target="_blank" rel="noopener noreferrer">联系平台 / 申诉</a></p>
              <label v-else-if="!state.accepted" class="rule-accept"><input v-model="checked" type="checkbox" :disabled="busy || !!error" /><span>我已阅读并接受发货时限、自动全额退款及卖家限制规则</span></label>
            </template>
            <p v-else id="fulfillment-rule-description">确认交付安排后，即可继续填写普通物品。</p>
            <div v-if="error" class="rule-error" role="alert"><p>{{ error }}</p><button type="button" :disabled="loading || busy" @click="$emit('retry')">重新加载</button></div>
          </div>
          <footer class="rule-footer">
            <button type="button" class="rule-secondary" @click="$emit('cancel')">暂不选择</button>
            <button type="button" class="rule-primary" :disabled="loading || busy || !!error || !state || !!state.activeRestriction || (!state.accepted && !checked)" @click="$emit('confirm')">{{ busy ? '正在确认…' : state?.accepted ? '我已了解，继续填写' : '同意规则，继续填写' }}</button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { InferOutput } from 'valibot'
import { ArrowUpRight, PackageCheck, X } from '@lucide/vue'
import type { FulfillmentPolicySchema, SellerFulfillment } from '@/contracts/fulfillment'
const props = defineProps<{ open: boolean; loading: boolean; busy: boolean; error: string; state: SellerFulfillment | null; policy: InferOutput<typeof FulfillmentPolicySchema> | null }>()
const emit = defineEmits<{ cancel: []; confirm: []; retry: [] }>()
const checked = ref(false)
const anchor = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const portalTarget = shallowRef<Element | null>(null)
let origin: HTMLElement | null = null
let previousOverflow = ''
let locked = false
const formatDate = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
onMounted(() => { portalTarget.value = anchor.value?.closest('.seller-shell') || document.body })
watch([() => props.open, () => props.policy?.version], () => { checked.value = false })
function release() {
  if (!locked) return
  locked = false
  document.body.style.overflow = previousOverflow
  const target = origin
  origin = null
  void nextTick(() => { if (!props.open && target?.isConnected) target.focus({ preventScroll: true }) })
}
watch([() => props.open, portalTarget], async ([open, target]) => {
  if (!open) { release(); return }
  if (!target || locked) return
  origin = document.activeElement as HTMLElement | null
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  locked = true
  await nextTick()
  if (props.open) panel.value?.focus({ preventScroll: true })
}, { immediate: true, flush: 'post' })
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('cancel'); return }
  if (event.key !== 'Tab' || !panel.value) return
  const controls = [...panel.value.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled)')]
  const first = controls[0], last = controls.at(-1)
  if (!first || !last) { event.preventDefault(); panel.value.focus(); return }
  if (!controls.includes(document.activeElement as HTMLElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
  else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onBeforeUnmount(release)
</script>

<style scoped>
.fulfillment-dialog-layer { position:fixed; inset:0; z-index:1400; display:grid; place-items:center; padding:24px; background:var(--overlay-bg); backdrop-filter:blur(4px); }
.fulfillment-dialog-panel { width:min(560px,100%); max-height:calc(100dvh - 48px); display:flex; flex-direction:column; min-height:0; border:1px solid var(--seller-border, var(--border-paper-default)); border-radius:18px; background:var(--seller-surface-strong, var(--surface-paper-strong)); color:var(--seller-ink, var(--text-paper-primary)); box-shadow:var(--elevation-paper-md); outline:none; }
.rule-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:24px 24px 16px; }
.rule-heading h2 { margin:10px 0 0; font-family:"Noto Serif SC","Songti SC",serif; font-size:22px; line-height:1.5; font-weight:600; text-wrap:balance; }
.rule-eyebrow { display:flex; align-items:center; gap:8px; color:var(--action-paper-accent-strong); font-size:13px; }
.rule-close { display:grid; place-items:center; width:44px; height:44px; flex-shrink:0; padding:0; border-radius:50%; }
.rule-body { min-height:0; overflow-y:auto; padding:0 24px 20px; font-size:14px; line-height:1.75; overflow-wrap:anywhere; }
.rule-intro { margin:0 0 20px; color:var(--text-paper-secondary); }
.rule-intro strong { color:var(--text-paper-primary); }
.rule-timeline { list-style:none; margin:0; padding:0; border-top:1px solid var(--border-paper-default); }
.rule-timeline li { display:grid; grid-template-columns:92px minmax(0,1fr); gap:12px; padding:14px 0; border-bottom:1px solid var(--border-paper-default); }
.rule-timeline li > strong { color:var(--action-paper-accent-strong); font-variant-numeric:tabular-nums; }
.rule-timeline small { display:block; color:var(--text-paper-secondary); font-size:13px; }
.rule-help { margin:16px 0; color:var(--text-paper-secondary); }
a { display:inline-flex; align-items:center; gap:2px; min-height:44px; color:var(--action-paper-accent-strong); text-decoration:underline; text-underline-offset:3px; }
.rule-help a { margin-left:6px; }
.rule-accept { display:flex; align-items:flex-start; gap:10px; padding:12px; border-radius:10px; background:var(--surface-paper-soft); cursor:pointer; }
.rule-accept input { width:18px; height:18px; flex-shrink:0; margin-top:4px; accent-color:var(--action-paper-accent-strong); }
.rule-error { color:var(--status-paper-danger); margin:12px 0 0; }
.rule-error p { margin:0 0 8px; }
.rule-footer { display:flex; justify-content:flex-end; flex-shrink:0; gap:12px; padding:16px 24px; border-top:1px solid var(--border-paper-default); }
button { min-height:44px; padding:10px 16px; border:1px solid var(--border-paper-default); border-radius:10px; background:var(--surface-paper-card); color:var(--text-paper-primary); font:inherit; font-size:14px; cursor:pointer; }
button:hover { background:var(--surface-paper-soft); }
.rule-primary { background:var(--action-paper-primary); border-color:var(--action-paper-primary); color:var(--palette-hex-ffffff); }
.rule-primary:hover { background:var(--action-paper-primary-hover); }
button:disabled { opacity:.55; cursor:not-allowed; }
button:focus-visible,a:focus-visible,input:focus-visible { outline:3px solid var(--action-paper-accent-strong); outline-offset:3px; }
.fulfillment-dialog-enter-active,.fulfillment-dialog-leave-active { transition:opacity .18s ease; }
.fulfillment-dialog-enter-active .fulfillment-dialog-panel,.fulfillment-dialog-leave-active .fulfillment-dialog-panel { transition:transform .18s ease; }
.fulfillment-dialog-enter-from,.fulfillment-dialog-leave-to { opacity:0; }
.fulfillment-dialog-enter-from .fulfillment-dialog-panel,.fulfillment-dialog-leave-to .fulfillment-dialog-panel { transform:translateY(10px); }
@media(max-width:640px) { .fulfillment-dialog-layer { padding:12px; padding-top:max(12px,env(safe-area-inset-top,0px)); padding-bottom:max(12px,env(safe-area-inset-bottom,0px)); align-items:end; } .fulfillment-dialog-panel { max-height:calc(100dvh - max(12px,env(safe-area-inset-top,0px)) - max(12px,env(safe-area-inset-bottom,0px))); border-radius:16px; } .rule-heading { padding:18px 16px 12px; } .rule-heading h2 { font-size:20px; } .rule-body { padding:0 16px 16px; } .rule-footer { padding:12px 16px; gap:8px; } .rule-footer button { flex:1; padding:10px 8px; } .rule-timeline li { grid-template-columns:80px minmax(0,1fr); gap:8px; } }
@media(prefers-reduced-motion:reduce) { .fulfillment-dialog-enter-active,.fulfillment-dialog-leave-active,.fulfillment-dialog-enter-active .fulfillment-dialog-panel,.fulfillment-dialog-leave-active .fulfillment-dialog-panel { transition:none; } }
</style>
