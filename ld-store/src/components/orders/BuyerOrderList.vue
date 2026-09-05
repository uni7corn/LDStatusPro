<template>
  <div class="orders-list" :aria-busy="busy">
    <template v-for="order in orders" :key="String(order.orderNo || order.id || '')">
      <slot :order="order" />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { OrderListItem } from '@/composables/orders/useOrderListController'
defineProps<{ orders: OrderListItem[]; busy?: boolean }>()
</script>
