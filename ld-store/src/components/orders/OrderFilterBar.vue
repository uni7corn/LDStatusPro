<template><div class="orders-filters" role="group" :aria-label="ariaLabel"><slot /></div></template>
<script setup lang="ts">
withDefaults(defineProps<{ ariaLabel?: string }>(), { ariaLabel: '订单筛选' })
</script>
