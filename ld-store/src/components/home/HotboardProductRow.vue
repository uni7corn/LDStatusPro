<template>
  <router-link :to="`/product/${item.id}`" class="hotboard-product-item">
    <span class="rank-badge" :class="`rank-${item.rank}`">{{ item.rank }}</span>
    <img v-if="item.imageUrl" :src="item.imageUrl" :alt="item.name" class="product-image" loading="lazy" />
    <div v-else class="product-image placeholder" aria-hidden="true">📦</div>
    <div class="product-info">
      <span class="product-name">{{ item.name }}</span>
      <span class="product-meta">{{ item.categoryIcon }} {{ item.categoryName }}<template v-if="item.sellerUsername"> · {{ item.sellerUsername }}</template></span>
    </div>
    <div class="product-right">
      <span class="product-count">{{ metric === 'views' ? item.viewCount : item.soldQuantity }}<small>{{ metric === 'views' ? '次' : '已售' }}</small></span>
      <span class="product-price">{{ formatPrice(item.discount ? item.price * item.discount : item.price ?? 0) }}<small>LDC</small></span>
    </div>
  </router-link>
</template>

<script setup>
import { formatPrice } from '@/utils/format'

defineProps({
  item: { type: Object, required: true },
  metric: { type: String, required: true }
})
</script>

<style scoped>
.hotboard-product-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border: 1px solid var(--glass-border-light); border-radius: 12px; background: var(--glass-bg-heavy); color: inherit; text-decoration: none; transition: transform .2s ease, background-color .2s ease, border-color .2s ease; }.hotboard-product-item:hover { transform: translateX(4px); background: var(--glass-bg-medium); }.hotboard-product-item:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
.rank-badge { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 8px; background: var(--bg-tertiary); color: var(--text-tertiary); font-size: 13px; font-weight: 700; flex-shrink: 0; }.rank-1 { background: linear-gradient(135deg, var(--palette-hex-ffd700), var(--palette-hex-ffb800)); color: var(--palette-hex-5a4000); }.rank-2 { background: linear-gradient(135deg, var(--palette-hex-d1d5db), var(--palette-hex-b0b5bc)); color: var(--palette-hex-3a3a3a); }.rank-3 { background: linear-gradient(135deg, var(--palette-hex-e8a860), var(--palette-hex-cd7f32)); color: var(--palette-hex-ffffff); }
.product-image { width: 48px; height: 48px; border-radius: 10px; object-fit: cover; flex-shrink: 0; border: 1px solid var(--border-light); }.placeholder { display: grid; place-items: center; background: var(--bg-tertiary); font-size: 20px; }.product-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }.product-name, .product-meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.product-name { font-size: 14px; font-weight: 600; }.product-meta { font-size: 12px; color: var(--text-tertiary); }.product-right { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; }.product-count { color: var(--color-primary); font-size: 14px; font-weight: 700; }.product-price { color: var(--text-tertiary); font-size: 12px; font-weight: 600; }.product-right small { margin-left: 1px; font-size: 9px; font-weight: 500; }
@media (max-width: 640px) { .hotboard-product-item:hover { transform: none; } }
@media (prefers-reduced-motion: reduce) { .hotboard-product-item { transition: none; }.hotboard-product-item:hover { transform: none; } }
</style>
