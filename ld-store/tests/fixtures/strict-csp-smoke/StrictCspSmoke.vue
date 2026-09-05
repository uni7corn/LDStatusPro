<template>
  <main class="smoke-shell">
    <header class="smoke-header">
      <div>
        <p>LD士多 · 本地隔离验证</p>
        <h1>严格 CSP 组件冒烟</h1>
      </div>
      <ThemeToggle show-text />
    </header>

    <section class="smoke-section">
      <h2>LiquidTabs 与动态指示器</h2>
      <LiquidTabs
        v-model="activeTab"
        :tabs="tabs"
        mode="tabs"
        activation="automatic"
        layout="equal"
        aria-label="严格 CSP 选项卡"
      />
      <div :id="`smoke-panel-${activeTab}`" role="tabpanel" :aria-labelledby="`smoke-tab-${activeTab}`" tabindex="0">
        当前面板：{{ activeTab }}
      </div>
    </section>

    <section class="smoke-section smoke-actions">
      <h2>Toast、进度与浮层定位</h2>
      <button type="button" class="smoke-button" @click="showSmokeToast">显示 CSP Toast</button>
      <div class="smoke-progress" aria-label="演示进度 72%">
        <span :style="{ transform: 'scaleX(0.72)' }"></span>
      </div>
      <SellerReasonDisclosure text="这个浮层使用对象式动态属性计算视口位置。" label="CSP 定位说明" />
    </section>

    <section class="smoke-section">
      <h2>卡片 tilt 与详情封面</h2>
      <div class="smoke-media-grid">
        <ProductCard :product="product" :categories="categories" />
        <ProductMedia
          :product="detailProduct"
          :category-icon="PackageOpen"
          :cover-style="coverStyle"
          :has-discount="true"
          :discount-percent="20"
          :landscape="false"
        />
      </div>
    </section>

    <section class="smoke-section seller-shell">
      <h2>延迟图表与 Tooltip</h2>
      <SellerTrendChart :trend="trend" view="revenue" />
    </section>

    <Toast />
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import type { CSSProperties } from 'vue'
import { PackageOpen } from '@lucide/vue'
import LiquidTabs from '@/components/common/LiquidTabs.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import Toast from '@/components/common/Toast.vue'
import ProductCard from '@/components/product/ProductCard.vue'
import ProductMedia from '@/components/product-detail/ProductMedia.vue'
import SellerReasonDisclosure from '@/components/seller/SellerReasonDisclosure.vue'
import SellerTrendChart from '@/components/seller/SellerTrendChart.vue'
import { useUiStore } from '@/stores/ui'
import type { DetailProduct } from '@/composables/product-detail/useProductDetail'

const uiStore = useUiStore()
const activeTab = ref('products')
const tabs = [
  { value: 'products', label: '物品', id: 'smoke-tab-products', panelId: 'smoke-panel-products' },
  { value: 'stores', label: '小店', id: 'smoke-tab-stores', panelId: 'smoke-panel-stores' },
  { value: 'requests', label: '求购', id: 'smoke-tab-requests', panelId: 'smoke-panel-requests' }
]

const categories = [{ id: 1, name: '软件' }]
const product = {
  id: 9001,
  name: '严格 CSP 演示物品',
  categoryId: 1,
  categoryName: '软件',
  productType: 'normal',
  status: 'on_sale',
  price: 80,
  discount: 0.8,
  stock: 12,
  availableStock: 12,
  sellerUsername: 'local-smoke',
  viewCount: 128,
  soldCount: 24,
  updatedAt: '2026-09-01T08:00:00.000Z'
}
const detailProduct = { ...product, imageUrl: '' } as DetailProduct
const coverStyle: CSSProperties = { background: 'var(--surface-subtle)' }
const trend = Array.from({ length: 12 }, (_, index) => ({
  date: `2026-08-${String(index + 20).padStart(2, '0')}`,
  productRevenue: 20 + index * 8,
  serviceRevenue: 8 + index * 3,
  productOrders: 2 + index,
  serviceOrders: 1 + Math.floor(index / 2),
  productViews: 50 + index * 12
}))

function showSmokeToast() {
  uiStore.showToast('严格 CSP 下 Toast 与进度条正常', 'success', 10_000)
}

onBeforeUnmount(() => uiStore.clearToasts())
</script>
