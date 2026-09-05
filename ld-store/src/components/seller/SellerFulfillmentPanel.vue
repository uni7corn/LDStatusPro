<template>
  <aside v-if="placement === 'summary' && state?.enabled && (state.validCount > 0 || state.activeRestriction)" class="fulfillment-summary" :class="{ restricted: state.activeRestriction }" aria-label="履约待办提醒">
    <ShieldAlert :size="20" aria-hidden="true" />
    <div>
      <p v-if="state.activeRestriction"><strong>新增交易受限至 {{ formatDate(state.activeRestriction.endsAt) }}（北京时间）</strong><span>已有订单仍可交付及处理售后；到期不会自动上架物品。</span></p>
      <p v-else><strong>最近 {{ state.windowDays }} 天有效超时记录 {{ state.validCount }}/{{ state.threshold }} 笔</strong><span v-if="state.validCount === state.threshold - 1">再有 1 笔有效超时退款将触发交易限制。</span></p>
      <div class="fulfillment-links"><router-link to="/seller/orders?status=paid">处理待发货订单</router-link><a href="#seller-fulfillment-records" @click="openRecords">查看履约记录</a></div>
    </div>
  </aside>
  <section v-else-if="placement === 'details'" id="seller-fulfillment-records" class="fulfillment-details" aria-label="发货规则与履约记录">
    <details ref="records">
      <summary>发货规则与履约记录</summary>
      <div class="fulfillment-content">
        <p v-if="loading" role="status">正在读取履约记录…</p>
        <p v-else-if="error" role="alert">{{ error }} <button type="button" @click="$emit('refresh')">重新加载</button></p>
        <template v-else-if="state">
          <p v-if="!state.enabled">发货时限规则暂未启用。</p>
          <template v-else>
            <p>最近 {{ state.windowDays }} 天有效超时记录：<strong>{{ state.validCount }}/{{ state.threshold }} 笔</strong>。</p>
            <p v-if="state.activeRestriction">新增交易受限至 {{ formatDate(state.activeRestriction.endsAt) }}（北京时间）。已有订单仍可交付及处理售后；到期不会自动上架物品。</p>
            <button v-if="!state.accepted" type="button" :disabled="reminder.pending" @click="acceptRules">阅读并确认发货规则</button>
          </template>
          <div class="fulfillment-links"><router-link :to="state.ruleUrl">完整规则</router-link><router-link to="/seller/orders?status=paid">处理待发货订单</router-link><router-link :to="state.supportUrl">联系平台 / 申诉</router-link></div>
          <details v-if="state.history.length" class="fulfillment-history"><summary>查看超时记录（{{ state.history.length }}）</summary>
            <ul><li v-for="record in state.history" :key="record.id"><router-link :to="`/seller/orders/${encodeURIComponent(record.orderNo)}?source=product`">{{ record.orderNo }}</router-link>
              <span>{{ formatDate(record.occurredAt) }} · {{ record.revokedAt ? '已撤销' : record.exemptReason ? '旧处罚周期，不重复计次' : record.penaltyId ? '已用于本轮处罚' : '超时记录' }}</span>
              <span v-if="record.revokeReason">{{ record.revokeReason }}</span></li></ul>
          </details>
          <p v-else>暂无超时记录。</p>
        </template>
      </div>
    </details>
    <FulfillmentRuleDialog v-bind="reminder.dialogProps" @confirm="reminder.confirm" @cancel="reminder.cancel" @retry="reminder.retry" />
  </section>
</template>
<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ShieldAlert } from '@lucide/vue'
import type { SellerFulfillment } from '@/contracts/fulfillment'
import { useUserStore } from '@/stores/user'
import { useFulfillmentReminder } from '@/composables/useFulfillmentReminder'
import FulfillmentRuleDialog from './FulfillmentRuleDialog.vue'
defineProps<{ placement: 'summary' | 'details'; state: SellerFulfillment | null; error?: string; loading?: boolean }>()
const emit = defineEmits<{ refresh: [] }>()
const userStore = useUserStore()
const reminder = reactive(useFulfillmentReminder(() => `${userStore.currentUser?.site || 'linux.do'}:${userStore.currentUser?.id || ''}`))
const records = ref<HTMLDetailsElement | null>(null)
const formatDate = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
async function acceptRules() { if (await reminder.request({ force: true })) emit('refresh') }
function openRecords() {
  const details = document.querySelector<HTMLDetailsElement>('#seller-fulfillment-records > details')
  if (details) { details.open = true; details.querySelector('summary')?.focus() }
}
</script>
<style scoped>
.fulfillment-summary { display:flex; align-items:flex-start; gap:12px; margin:18px 0; padding:16px 20px; border:1px solid var(--seller-border); border-radius:12px; background:var(--seller-surface-soft); color:var(--seller-ink); }
.fulfillment-summary > svg { flex-shrink:0; margin-top:3px; color:var(--seller-warning); }
.fulfillment-summary.restricted > svg { color:var(--seller-danger); }
p { margin:0; font-size:14px; line-height:1.7; }
p > span { display:block; color:var(--seller-muted); }
.fulfillment-links { display:flex; flex-wrap:wrap; gap:4px 20px; }
a { display:inline-flex; align-items:center; min-height:44px; font-size:14px; color:var(--seller-jade-strong); text-decoration:underline; text-underline-offset:3px; }
.fulfillment-details { margin-top:24px; color:var(--seller-muted); border-top:1px solid var(--seller-border); scroll-margin-top:100px; }
summary { width:fit-content; min-height:44px; padding:12px 0; box-sizing:border-box; cursor:pointer; font-size:14px; line-height:1.5; }
.fulfillment-content { display:grid; gap:12px; padding:8px 0 16px; color:var(--seller-ink); }
button { justify-self:start; min-height:44px; padding:8px 14px; border:1px solid var(--seller-border); border-radius:10px; color:var(--seller-jade-strong); background:var(--seller-surface); font:inherit; cursor:pointer; }
button:disabled { opacity:.55; cursor:wait; }
a:focus-visible,summary:focus-visible,button:focus-visible { outline:3px solid var(--seller-jade-strong); outline-offset:3px; }
ul { list-style:none; padding:0; margin:0; }
li { display:grid; gap:4px; border-top:1px solid var(--seller-border); padding:10px 0; font-size:14px; line-height:1.6; overflow-wrap:anywhere; }
li span { color:var(--seller-muted); }
@media(max-width:640px) { .fulfillment-summary { padding:14px; } }
</style>
