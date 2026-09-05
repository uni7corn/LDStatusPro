<template>
  <div v-if="deadline" class="fulfillment-deadline" :class="{ 'is-urgent': remaining <= 12 * 3600, 'is-compact': compact }">
    <strong>{{ order.status === 'refund_pending' ? '订单已进入退款处理' : remaining > 0 ? `距发货截止约 ${remainingLabel}` : '已到发货截止时间' }}</strong>
    <span>截止 {{ dateLabel }}（北京时间）</span>
    <template v-if="!compact">
      <p>{{ order.status === 'refund_pending' ? '请查看下方退款进度；失败或结果待核对不代表积分已退回，期间请勿继续交付。' : '到期仍未发货，系统自动发起实付全额退款，到账以最终处理结果为准。' }}</p>
      <p v-if="source === 'legacy'">本单为历史过渡订单，通知双方后另给 72 小时，不计入新处罚。</p>
      <router-link to="/docs/shipping-deadline">查看发货与退款规则</router-link>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { FulfillmentInfo } from '@/contracts/fulfillment'
const props = defineProps<{ order: Record<string, unknown>; compact?: boolean }>()
const info = computed(() => props.order.fulfillment as FulfillmentInfo | undefined)
const deadline = computed(() => info.value?.deadlineAt || String(props.order.fulfillmentDeadlineAt || ''))
const source = computed(() => info.value?.source || props.order.fulfillmentPolicySource)
const now = ref(Date.now())
let offset = 0
watch(() => info.value?.serverNow, (value) => { offset = value ? Date.parse(value) - Date.now() : 0; now.value = Date.now() + offset }, { immediate: true })
const remaining = computed(() => Math.max(0, Math.ceil((Date.parse(deadline.value) - now.value) / 1000)))
const remainingLabel = computed(() => remaining.value >= 3600 ? `${Math.ceil(remaining.value / 3600)} 小时` : `${Math.max(1, Math.ceil(remaining.value / 60))} 分钟`)
const dateLabel = computed(() => new Date(deadline.value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }))
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { if (!document.hidden) now.value = Date.now() + offset }, 15000) })
onUnmounted(() => clearInterval(timer))
</script>
<style scoped>
.fulfillment-deadline { display: grid; gap: .4rem; padding: 1rem; border: 1px solid var(--border-default-semantic); border-radius: var(--radius-md, 12px); background: var(--surface-subtle); color: var(--text-primary-semantic); font-size: .875rem; }
.fulfillment-deadline span, .fulfillment-deadline p { color: var(--text-secondary-semantic); margin: 0; line-height: 1.6; }
.fulfillment-deadline a { color: var(--text-link); text-decoration: underline; }
.is-urgent strong { color: var(--status-warning); }
.is-compact { padding: .5rem 0; border: 0; background: none; font-size: .75rem; }
</style>
