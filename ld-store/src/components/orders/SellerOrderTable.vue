<template>
  <SellerDataTable v-bind="$attrs" :caption="caption" :columns="columns" :rows="rows" :loading="loading" :row-key="rowKey" :expanded-row-key="expandedRowKey">
    <template v-for="(_, slotName) in $slots" #[slotName]="slotProps">
      <slot :name="slotName" v-bind="slotProps || {}" />
    </template>
  </SellerDataTable>
</template>

<script setup lang="ts">
import SellerDataTable from '@/components/seller/SellerDataTable.vue'
import type { OrderListItem } from '@/composables/orders/useOrderListController'

defineOptions({ inheritAttrs: false })
defineProps<{
  columns: Array<Record<string, unknown>>
  rows: OrderListItem[]
  loading: boolean
  caption: string
  rowKey: (_order: OrderListItem) => string | number
  expandedRowKey?: string | number
}>()
</script>
