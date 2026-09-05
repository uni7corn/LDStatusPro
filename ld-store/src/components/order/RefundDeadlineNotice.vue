<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
const props = defineProps<{ refund: { status: string; decisionDeadlineAt?: string | null; executionTrigger?: string | null }; serverNow?: string; compact?: boolean }>()
const clock = ref(Date.now())
const offset = computed(() => props.serverNow ? new Date(props.serverNow).getTime() - receivedAt.value : 0)
const receivedAt = ref(Date.now())
watch(() => props.serverNow, () => { receivedAt.value = Date.now(); clock.value = Date.now() })
const waiting = computed(() => ['requested', 'negotiating'].includes(props.refund.status))
const deadline = computed(() => props.refund.decisionDeadlineAt ? new Date(props.refund.decisionDeadlineAt).getTime() : 0)
const remaining = computed(() => deadline.value - clock.value - offset.value)
const dateText = computed(() => deadline.value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(deadline.value) : '')
const remainingText = computed(() => {
  if (remaining.value <= 0) return '已到期，等待系统处理'
  const minutes = Math.ceil(remaining.value / 60000)
  return `剩余 ${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟`
})
const triggerText = computed(() => ({ response_timeout: '卖家未在期限内作出决定，系统已自动同意退款', admin_approved: '管理员已同意退款', admin_override: '管理员已改判退款', shipment_timeout: '系统已按未发货保障发起退款' }[props.refund.executionTrigger || ''] || ''))
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { if (!document.hidden) clock.value = Date.now() }, 30000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <div v-if="waiting && deadline" class="refund-deadline" :class="{ 'is-urgent': remaining <= 10800000, 'is-compact': compact }">
    <strong>{{ compact ? '处理截止' : '请在处理期限内作出决定' }}</strong>
    <p>{{ dateText }}（北京时间）</p><span>{{ remainingText }}</span>
    <p v-if="!compact" class="refund-deadline-rule">卖家须同意退款或说明理由拒绝，逾期系统自动同意并发起全额退款。协商、发货均不延长时限；原有更早的未发货保障期限继续有效。</p>
  </div>
  <p v-else-if="triggerText && !compact" class="refund-execution-note">{{ triggerText }}。{{ refund.status === 'refunded' ? 'Credit 已确认退款成功。' : '请以最终退款结果和 Credit 积分记录为准。' }}</p>
</template>
<style scoped>
.refund-deadline { padding:16px; border:1px solid var(--border-medium); border-radius:12px; background:var(--bg-secondary); color:var(--text-primary); }
.refund-deadline strong { font-size:14px; }.refund-deadline p { margin:6px 0; font-size:14px; line-height:1.6; }.refund-deadline span { font-size:13px; color:var(--text-secondary); }.refund-deadline .refund-deadline-rule { color:var(--text-secondary); font-size:13px; }
.refund-deadline.is-urgent { border-color:var(--color-warning); }.refund-deadline.is-urgent>strong { color:var(--text-primary); }
.refund-deadline.is-compact { padding:0; border:0; background:transparent; }.refund-deadline.is-compact p,.refund-deadline.is-compact span { font-size:12px; }.refund-execution-note { color:var(--text-secondary); font-size:14px; line-height:1.6; margin:12px 0; }
</style>
