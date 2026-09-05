<template>
  <div class="detail-media" :class="{ 'detail-media--landscape': landscape }">
    <button class="media-wrapper" type="button" :style="coverStyle" :aria-label="product.imageUrl ? '查看物品大图' : '物品图片占位'" @click="emit('open')">
      <img v-if="product.imageUrl" :src="String(product.imageUrl)" :alt="String(product.name || '')" class="media-image" @load="emit('load', $event)" @error="emit('error', $event)" />
      <component :is="categoryIcon" v-else class="media-placeholder" :size="80" :stroke-width="1.5" aria-hidden="true" />
      <span v-if="hasDiscount" class="discount-tag">-{{ discountPercent }}%</span>
      <span v-if="product.imageUrl" class="media-zoom-hint" aria-hidden="true"><Search :size="14" />点击查看大图</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { Component, CSSProperties } from 'vue'
import { Search } from '@lucide/vue'
import type { DetailProduct } from '@/composables/product-detail/useProductDetail'

defineProps<{ product: DetailProduct; categoryIcon: Component; coverStyle: CSSProperties; hasDiscount: boolean; discountPercent: number; landscape: boolean }>()
const emit = defineEmits<{ open: []; load: [event: Event]; error: [event: Event] }>()
</script>

<style scoped>
.detail-media { display: flex; align-items: center; justify-content: center; }
.detail-media--landscape { align-self: start; justify-content: flex-start; align-items: flex-start; }
.media-wrapper { position: relative; display: flex; width: 100%; max-width: 400px; min-height: 200px; max-height: 500px; align-items: center; justify-content: center; padding: 0; overflow: hidden; background: var(--bg-secondary); border: 0; border-radius: 16px; cursor: pointer; transition: transform 0.3s, box-shadow 0.3s; }
.detail-media--landscape .media-wrapper { max-width: 100%; }
.media-wrapper:hover { transform: scale(1.02); box-shadow: 0 8px 24px var(--palette-rgba-0-0-0-0p1); }
.media-wrapper:has(.media-placeholder) { aspect-ratio: 1 / 1; }
.media-image { width: 100%; height: auto; max-height: 500px; object-fit: contain; background: var(--bg-secondary); }
.media-placeholder { color: var(--text-tertiary); opacity: 0.6; }
.discount-tag { position: absolute; top: 12px; right: 12px; padding: 8px 12px; color: var(--palette-hex-ffffff); background: linear-gradient(135deg, var(--palette-hex-ad9090), var(--palette-hex-937474)); border-radius: 10px; font-size: 13px; font-weight: 700; }
.media-zoom-hint { position: absolute; right: 0; bottom: 0; left: 0; display: flex; align-items: center; justify-content: center; gap: 5px; padding: 10px; color: var(--palette-hex-ffffff); background: linear-gradient(transparent, var(--palette-rgba-0-0-0-0p5)); opacity: 0; font-size: 12px; transition: opacity 0.3s; }
.media-wrapper:hover .media-zoom-hint, .media-wrapper:focus-visible .media-zoom-hint { opacity: 1; }
@media (max-width: 640px) {
  .media-wrapper { max-width: 100%; max-height: 350px; }
  .media-image { max-height: 350px; }
}
</style>
