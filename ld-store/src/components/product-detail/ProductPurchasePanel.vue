<template>
  <template v-if="isStore"><button type="button" class="buy-btn store" @click="emit('openStore')"><Store :size="18" aria-hidden="true" /><span>立即前往</span></button></template>
  <template v-else-if="isPlatformOrder">
    <div v-if="isOutOfStock" class="buy-action-row">
      <button class="buy-btn disabled" disabled><PackageX :size="18" aria-hidden="true" /><span>已售罄</span></button>
      <button v-if="isCdk" class="buy-btn restock" :class="{ subscribed: restockSubscribed }" :disabled="restockBusy || restockSubscribed" @click="emit('subscribeRestock')">
        <component :is="restockSubscribed ? BellCheck : Bell" :size="18" aria-hidden="true" /><span>{{ restockButtonText }}</span>
      </button>
    </div>
    <button v-else-if="isCdk && isTestMode && !isSeller" class="buy-btn disabled test-only" disabled><FlaskConical :size="18" aria-hidden="true" /><span>测试物品</span></button>
    <button v-else-if="maintenanceBlocked" class="buy-btn disabled" disabled>维护中暂不可下单</button>
    <button v-else-if="ownProductBlocked" class="buy-btn disabled" disabled>不能兑换自己的物品</button>
    <button v-else-if="purchaseLimitReached" class="buy-btn disabled" disabled><CircleOff :size="18" aria-hidden="true" /><span>已达限购</span></button>
    <button v-else-if="!canPurchase" class="buy-btn disabled" disabled><CircleOff :size="18" aria-hidden="true" /><span>暂停销售</span></button>
    <button v-else-if="isLoggedIn && !trustAllowed" class="buy-btn disabled" disabled>需达到 TL{{ purchaseTrustLevel }}</button>
    <button v-else class="buy-btn" :class="{ test: isTestMode && isSeller }" :disabled="purchasing" @click="emit('buy')">{{ purchasing ? '正在进入确认页…' : '立即兑换' }}</button>
    <p v-if="canEnterCheckout" class="purchase-next-step-hint">数量与优惠券将在下一步确认</p>
  </template>
  <button v-else-if="isLegacyLink" class="buy-btn disabled" disabled>外链已停用</button>
  <button v-else class="buy-btn" @click="emit('openStore')"><Store :size="18" aria-hidden="true" /><span>立即前往</span></button>
</template>

<script setup lang="ts">
import { Bell, BellCheck, CircleOff, FlaskConical, PackageX, Store } from '@lucide/vue'
defineProps<{
  isStore: boolean; isPlatformOrder: boolean; isLegacyLink: boolean; isCdk: boolean; isOutOfStock: boolean;
  isTestMode: boolean; isSeller: boolean; maintenanceBlocked: boolean; ownProductBlocked: boolean;
  purchaseLimitReached: boolean; canPurchase: boolean; isLoggedIn: boolean; trustAllowed: boolean;
  purchaseTrustLevel: number; purchasing: boolean; canEnterCheckout: boolean; restockSubscribed: boolean;
  restockBusy: boolean; restockButtonText: string
}>()
const emit = defineEmits<{ buy: []; openStore: []; subscribeRestock: [] }>()
</script>

<style scoped>
.buy-action-row { display: flex; align-items: stretch; gap: 10px; }
.buy-action-row .buy-btn { flex: 1; width: auto; min-width: 0; }
.purchase-next-step-hint { margin: 9px 0 0; color: var(--text-tertiary); font-size: 12px; line-height: 1.45; text-align: center; }
.buy-btn { display: flex; width: 100%; align-items: center; justify-content: center; gap: 8px; padding: 16px 24px; color: var(--palette-hex-ffffff); background: linear-gradient(135deg, var(--palette-hex-cfa76f), var(--palette-hex-bd8d57)); border: 0; border-radius: 14px; cursor: pointer; text-decoration: none; font-size: 16px; font-weight: 600; transition: opacity 0.2s, transform 0.2s, box-shadow 0.2s; }
.buy-btn:hover { opacity: 0.92; transform: translateY(-1px); box-shadow: 0 4px 12px var(--palette-rgba-207-167-111-0p3); }
.buy-btn.store, .buy-btn.test, .buy-btn.disabled.test-only { background: linear-gradient(135deg, var(--palette-hex-06b6d4), var(--palette-hex-0891b2)); }
.buy-btn.store:hover, .buy-btn.test:hover { box-shadow: 0 4px 12px var(--palette-rgba-6-182-212-0p3); }
.buy-btn.restock { color: var(--publish-btn-color); background: var(--publish-btn-bg); border: 1px solid transparent; box-shadow: var(--publish-btn-shadow); }
.buy-btn.restock:hover { opacity: 1; background: var(--publish-btn-hover-bg); box-shadow: var(--publish-btn-hover-shadow); }
.buy-btn.restock.subscribed { color: var(--text-secondary); background: var(--bg-secondary); border-color: var(--border-medium); box-shadow: none; }
.buy-btn.restock:disabled { transform: none; }
.buy-btn.restock.subscribed:disabled { cursor: default; opacity: 1; }
.buy-btn.disabled { cursor: not-allowed; background: var(--palette-hex-999999); box-shadow: none; opacity: 0.5; transform: none; }
.buy-btn.disabled.test-only { opacity: 0.6; }
:global(.action-bottom) .purchase-next-step-hint { margin-top: 8px; }
</style>
