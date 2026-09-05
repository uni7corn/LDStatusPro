<template><aside v-if="enabled" class="fulfillment-policy-notice"><strong>普通物品 · 72 小时发货保障</strong><p>支付后 72 小时内发货，超时系统自动发起实付全额退款；实际到账以退款结果为准。</p><router-link to="/docs/shipping-deadline">查看规则与历史订单安排</router-link></aside></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchFulfillmentPolicy } from '@/services/shop/fulfillmentService'
const enabled = ref(false)
onMounted(async () => { const result = await fetchFulfillmentPolicy(); if (result.success) enabled.value = result.data.enabled })
</script>
<style scoped>
.fulfillment-policy-notice { margin: 1rem 0; padding: 1rem; border: 1px solid var(--border-default-semantic); border-radius: var(--radius-md, 12px); background: var(--surface-subtle); font-size: .875rem; line-height: 1.7; }
p { color: var(--text-secondary-semantic); margin: .4rem 0; } a { color: var(--text-link); text-decoration: underline; }
</style>
