<template>
  <nav v-if="totalPages > 1" class="seller-pagination" aria-label="分页导航">
    <p>共 <strong>{{ total }}</strong> 条，第 {{ page }} / {{ totalPages }} 页</p>
    <div class="seller-pagination-controls">
      <button type="button" :disabled="page <= 1" aria-label="上一页" @click="go(page - 1)">
        <ChevronLeft :size="16" aria-hidden="true" />
      </button>
      <template v-for="item in visiblePages" :key="item.key">
        <span v-if="item.ellipsis" aria-hidden="true">…</span>
        <button
          v-else
          type="button"
          :class="{ active: item.page === page }"
          :aria-current="item.page === page ? 'page' : undefined"
          :aria-label="`第 ${item.page} 页`"
          @click="go(item.page)"
        >{{ item.page }}</button>
      </template>
      <button type="button" :disabled="page >= totalPages" aria-label="下一页" @click="go(page + 1)">
        <ChevronRight :size="16" aria-hidden="true" />
      </button>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from '@lucide/vue'

const props = defineProps({
  page: { type: Number, default: 1 },
  totalPages: { type: Number, default: 1 },
  total: { type: Number, default: 0 }
})
const emit = defineEmits(['change'])

const visiblePages = computed(() => {
  const total = Math.max(1, props.totalPages)
  const current = Math.min(Math.max(1, props.page), total)
  const pages = new Set([1, total, current - 1, current, current + 1])
  const values = [...pages].filter(value => value >= 1 && value <= total).sort((a, b) => a - b)
  const result = []
  values.forEach((value, index) => {
    if (index && value - values[index - 1] > 1) result.push({ key: `gap-${value}`, ellipsis: true })
    result.push({ key: `page-${value}`, page: value })
  })
  return result
})

function go(nextPage) {
  const normalized = Math.min(Math.max(1, Number(nextPage) || 1), Math.max(1, props.totalPages))
  if (normalized !== props.page) emit('change', normalized)
}
</script>

<style scoped>
.seller-pagination { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px 18px; border-top: 1px solid var(--seller-border); color: var(--seller-muted); font-size: 13px; }
.seller-pagination p { margin: 0; }
.seller-pagination p strong { color: var(--seller-ink); font-variant-numeric: tabular-nums; }
.seller-pagination-controls { display: flex; align-items: center; gap: 6px; }
.seller-pagination-controls button { min-width: 36px; height: 36px; display: grid; place-items: center; padding: 0 9px; border: 1px solid transparent; border-radius: 9px; color: var(--seller-muted); background: transparent; font-variant-numeric: tabular-nums; }
.seller-pagination-controls button:hover:not(:disabled) { color: var(--seller-ink); border-color: var(--seller-border); background: var(--seller-surface); }
.seller-pagination-controls button.active { color: var(--palette-hex-ffffff); background: var(--seller-navy); }
.seller-pagination-controls button:disabled { opacity: .35; cursor: not-allowed; }
@media (max-width: 640px) {
  .seller-pagination { align-items: flex-start; flex-direction: column; }
  .seller-pagination-controls { width: 100%; justify-content: space-between; }
}
</style>
