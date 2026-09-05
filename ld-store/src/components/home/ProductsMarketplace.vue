<template>
  <section id="home-panel-products" class="section-content" role="tabpanel" aria-labelledby="home-tab-products" tabindex="0">
    <div class="filter-section">
      <CategoryFilter
        :categories="marketCategories"
        :current-category="currentCategory"
        @select="handleCategorySelect"
      />
    </div>

    <div class="sort-section">
      <div class="sort-options">
        <button
          v-for="tab in sortTabs"
          :key="tab.value"
          type="button"
          class="sort-btn"
          :class="{ active: currentSort === tab.value }"
          :aria-pressed="currentSort === tab.value"
          @click="handleSortChange(tab.value)"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="catalog-filters">
        <div class="price-filter">
          <label for="home-price-min" class="sr-only">最低折后价</label>
          <input
            id="home-price-min"
            v-model="priceMinInput"
            type="number"
            min="0"
            step="0.01"
            class="price-filter-input"
            placeholder="最低折后价"
            @keyup.enter="applyPriceFilter"
          />
          <span class="price-filter-separator">-</span>
          <label for="home-price-max" class="sr-only">最高折后价</label>
          <input
            id="home-price-max"
            v-model="priceMaxInput"
            type="number"
            min="0"
            step="0.01"
            class="price-filter-input"
            placeholder="最高折后价"
            @keyup.enter="applyPriceFilter"
          />
          <button type="button" class="price-filter-btn" @click="applyPriceFilter">筛选</button>
          <button
            v-if="hasDraftPriceFilter || hasActivePriceFilter"
            type="button"
            class="price-filter-btn secondary"
            @click="clearPriceFilter"
          >
            清空
          </button>
        </div>
        <label class="stock-filter">
          <input
            type="checkbox"
            class="stock-filter-input"
            :checked="inStockOnly"
            @change="handleToggleInStock"
          />
          <span class="checkbox" :class="{ checked: inStockOnly }" aria-hidden="true">
            <span v-if="inStockOnly" class="checkmark">✓</span>
          </span>
          <span class="filter-label">只看有货</span>
        </label>
      </div>
    </div>

    <div class="mobile-catalog-toolbar">
      <label for="home-mobile-sort" class="sr-only">商品排序</label>
      <span class="mobile-sort-control">
        <select
          id="home-mobile-sort"
          :value="currentSort"
          :disabled="loading"
          @change="handleMobileSortChange"
        >
          <option v-for="tab in sortTabs" :key="tab.value" :value="tab.value">
            {{ tab.mobileLabel }}
          </option>
        </select>
        <ChevronDown :size="17" aria-hidden="true" />
      </span>
      <button
        type="button"
        class="mobile-filter-trigger"
        aria-haspopup="dialog"
        aria-controls="home-catalog-filter-sheet"
        :aria-expanded="mobileFilterOpen"
        :aria-label="mobileFilterAriaLabel"
        :disabled="loading"
        @click="openMobileFilters"
      >
        <SlidersHorizontal :size="17" aria-hidden="true" />
        <span>筛选</span>
        <span v-if="activeFilterCount" class="mobile-filter-badge" aria-hidden="true">{{ activeFilterCount }}</span>
      </button>
    </div>

    <CatalogFilterSheet
      :open="mobileFilterOpen"
      :price-min="shopStore.currentPriceMin"
      :price-max="shopStore.currentPriceMax"
      :in-stock-only="inStockOnly"
      :loading="filterApplying"
      @close="closeMobileFilters"
      @apply="handleMobileFilterApply"
    />

    <div class="products-header">
      <span class="products-count">
        <template v-if="isProductListHiddenByMaintenance">{{ maintenanceTitle }}</template>
        <template v-else>{{ currentCategoryName }} 共 <strong>{{ total }}</strong> 件物品</template>
        <span v-if="inStockOnly" class="filter-tag">有库存</span>
        <span v-if="hasActivePriceFilter" class="filter-tag price-tag">{{ activePriceFilterLabel }}</span>
      </span>
    </div>

    <div v-if="initialLoading" class="products-loading">
      <Skeleton type="card" :count="6" :columns="gridColumns" />
    </div>

    <div v-else-if="marketProducts.length > 0" class="products-grid" :aria-busy="loading">
      <ProductCard
        v-for="product in marketProducts"
        :key="product.id"
        :product="product"
        :categories="categories"
        :image-loading="priorityImageIds.has(product.id) ? 'eager' : 'lazy'"
        :fetch-priority="priorityImageIds.has(product.id) ? 'high' : 'auto'"
      />
      <div v-if="hasMore" ref="sentinel" class="load-more">
        <div v-if="loading" class="loading-indicator">
          <span class="spinner"></span>
          <span>加载中...</span>
        </div>
        <span v-else class="load-hint">⬇️ 滚动加载更多</span>
      </div>
      <div v-else class="loaded-all">✨ 已加载全部</div>
    </div>

    <EmptyState
      v-else
      :icon="isProductListHiddenByMaintenance ? '🚧' : '🛒'"
      :text="isProductListHiddenByMaintenance ? maintenanceTitle : '暂无物品'"
      :hint="isProductListHiddenByMaintenance ? maintenanceCatalogHint : '快来发布第一个物品吧~'"
    >
      <template v-if="!isProductListHiddenByMaintenance" #action>
        <router-link to="/seller/products/new" class="btn btn-primary mt-4">➕ 发布物品</router-link>
      </template>
    </EmptyState>
  </section>
</template>

<script setup>
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { ChevronDown, SlidersHorizontal } from '@lucide/vue'
import { useCatalogStore } from '@/stores/catalog'
import { useToast } from '@/composables/useToast'
import ProductCard from '@/components/product/ProductCard.vue'
import CategoryFilter from '@/components/product/CategoryFilter.vue'
import CatalogFilterSheet from '@/components/home/CatalogFilterSheet.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import Skeleton from '@/components/common/Skeleton.vue'
import { MAINTENANCE_STATE, isMaintenanceFeatureEnabled, isRestrictedMaintenanceMode } from '@/config/maintenance'
import { createTtlLruCache } from '@/utils/ttlLruCache'
import { normalizePriceFilterInput, normalizePriceFilterRange } from '@/utils/catalogFilters'

defineOptions({ name: 'ProductsMarketplace' })

const shopStore = useCatalogStore()
const toast = useToast()
const sentinel = ref(null)
const initialLoading = ref(true)
const hasInitialized = ref(false)
const priceMinInput = ref('')
const priceMaxInput = ref('')
const mobileFilterOpen = ref(false)
const filterApplying = ref(false)
const gridColumns = ref(2)
const CATEGORY_CACHE_TTL = 5 * 60 * 1000
const categoryCache = createTtlLruCache({ ttl: CATEGORY_CACHE_TTL, max: 24 })
let lastLoadedAt = 0
let observer = null
let latestCatalogActionId = 0
let activeRequest = null

const sortTabs = [
  { value: 'default', label: '默认', mobileLabel: '默认排序' },
  { value: 'newest', label: '最新', mobileLabel: '最新上架' },
  { value: 'price_asc', label: '价格↑', mobileLabel: '价格最低' },
  { value: 'price_desc', label: '价格↓', mobileLabel: '价格最高' },
  { value: 'sales', label: '销量', mobileLabel: '销量优先' }
]

const isProductListHiddenByMaintenance = computed(() => (
  isRestrictedMaintenanceMode() && !isMaintenanceFeatureEnabled('productListRead')
))
const maintenanceTitle = computed(() => MAINTENANCE_STATE.title || 'LD士多受限维护中')
const maintenanceCatalogHint = computed(() => (
  MAINTENANCE_STATE.message || '因 LinuxDo 暂时下线 Credit 积分服务，物品列表已临时隐藏。'
))

function consumeStoreError(fallback = '') {
  return shopStore.consumeError('products') || fallback
}

function toSafeArray(value) {
  return Array.isArray(value) ? value : []
}

function syncPriceFilterInputs(priceMin, priceMax) {
  priceMinInput.value = priceMin === null || priceMin === undefined || priceMin === '' ? '' : String(priceMin)
  priceMaxInput.value = priceMax === null || priceMax === undefined || priceMax === '' ? '' : String(priceMax)
}

function buildCatalogFilters(overrides = {}) {
  const hasOwn = (key) => Object.prototype.hasOwnProperty.call(overrides, key)
  const range = normalizePriceFilterRange(
    hasOwn('priceMin') ? overrides.priceMin : shopStore.currentPriceMin,
    hasOwn('priceMax') ? overrides.priceMax : shopStore.currentPriceMax
  )
  return {
    inStockOnly: hasOwn('inStockOnly') ? !!overrides.inStockOnly : !!shopStore.inStockOnly,
    priceMin: range.priceMin,
    priceMax: range.priceMax
  }
}

const getCacheKey = (categoryId, sortKey, filters = buildCatalogFilters()) => [
  categoryId || 'all',
  sortKey || 'default',
  filters.inStockOnly ? 'stock' : 'all-stock',
  filters.priceMin ?? 'min-any',
  filters.priceMax ?? 'max-any'
].join('_')

function isSameCatalogState(categoryId, sortKey, filters = buildCatalogFilters()) {
  return String(shopStore.currentCategory) === String(categoryId || '')
    && (shopStore.currentSort || 'default') === (sortKey || 'default')
    && !!shopStore.inStockOnly === !!filters.inStockOnly
    && shopStore.currentPriceMin === (filters.priceMin ?? null)
    && shopStore.currentPriceMax === (filters.priceMax ?? null)
}

function tryRestoreFromCache(categoryId, sortKey, filters = buildCatalogFilters()) {
  const key = getCacheKey(categoryId, sortKey, filters)
  const cached = categoryCache.get(key)
  if (cached && Array.isArray(cached.products)) {
    shopStore.restoreFromCache(cached)
    syncPriceFilterInputs(cached.priceMin, cached.priceMax)
    initialLoading.value = false
    return true
  }
  return false
}

function saveCache(categoryId, sortKey, filters = buildCatalogFilters()) {
  const products = toSafeArray(shopStore.products)
  categoryCache.set(getCacheKey(categoryId, sortKey, filters), {
    categoryId,
    products: [...products],
    total: Number.isFinite(Number(shopStore.total)) ? Number(shopStore.total) : products.length,
    hasMore: !!shopStore.hasMore,
    page: Number.isFinite(Number(shopStore.page)) ? Number(shopStore.page) : 1,
    cursor: shopStore.catalogCursor || '',
    rankingContext: shopStore.rankingContext || null,
    sort: sortKey || 'default',
    inStockOnly: !!filters.inStockOnly,
    priceMin: filters.priceMin ?? null,
    priceMax: filters.priceMax ?? null
  })
}

const categories = computed(() => toSafeArray(shopStore.categories))
const marketCategories = computed(() => categories.value.filter((category) => {
  const name = String(category?.name || '')
  return name && name !== '小店' && name !== '友情小店'
}))
const marketProducts = computed(() => toSafeArray(shopStore.products).filter((product) => product?.productType !== 'store'))
const priorityImageIds = computed(() => new Set(
  marketProducts.value.filter((product) => !!product?.imageUrl).slice(0, 4).map((product) => product.id)
))
const currentCategory = computed(() => shopStore.currentCategory)
const currentCategoryName = computed(() => shopStore.currentCategoryName)
const currentSort = computed(() => shopStore.currentSort)
const inStockOnly = computed(() => shopStore.inStockOnly)
const loading = computed(() => shopStore.loading)
const hasMore = computed(() => shopStore.hasMore)
const total = computed(() => shopStore.total)
const hasActivePriceFilter = computed(() => shopStore.currentPriceMin !== null || shopStore.currentPriceMax !== null)
const hasDraftPriceFilter = computed(() => (
  normalizePriceFilterInput(priceMinInput.value) !== null || normalizePriceFilterInput(priceMaxInput.value) !== null
))
const activeFilterCount = computed(() => Number(inStockOnly.value) + Number(hasActivePriceFilter.value))
const activePriceFilterLabel = computed(() => {
  const { priceMin, priceMax } = buildCatalogFilters()
  if (priceMin !== null && priceMax !== null) return `价格 ${priceMin} - ${priceMax} LDC`
  if (priceMin !== null) return `价格 ≥ ${priceMin} LDC`
  if (priceMax !== null) return `价格 ≤ ${priceMax} LDC`
  return ''
})
const mobileFilterAriaLabel = computed(() => {
  const activeLabels = []
  if (inStockOnly.value) activeLabels.push('只看有货')
  if (activePriceFilterLabel.value) activeLabels.push(activePriceFilterLabel.value)
  return activeLabels.length ? `筛选，已启用：${activeLabels.join('，')}` : '筛选物品'
})

watch(
  () => [shopStore.currentPriceMin, shopStore.currentPriceMax],
  ([priceMin, priceMax]) => syncPriceFilterInputs(priceMin, priceMax),
  { immediate: true }
)

function updateGridColumns() {
  const width = window.innerWidth
  gridColumns.value = width >= 1024 ? 4 : (width >= 768 ? 3 : 2)
}

function handleViewportResize() {
  updateGridColumns()
  if (window.innerWidth > 768) mobileFilterOpen.value = false
}

function setupInfiniteScroll() {
  observer?.disconnect()
  if (!sentinel.value || !hasMore.value || typeof IntersectionObserver !== 'function') return
  observer = new IntersectionObserver(async (entries) => {
    if (!entries[0].isIntersecting || loading.value || !hasMore.value) return
    activeRequest?.abort()
    activeRequest = new AbortController()
    const result = await shopStore.loadMore({ signal: activeRequest.signal })
    if (result?.success === false && !result.aborted) {
      toast.error(result.error || consumeStoreError('加载更多失败，请稍后重试'))
      return
    }
    saveCache(shopStore.currentCategory, shopStore.currentSort || 'default', buildCatalogFilters())
  }, { rootMargin: '100px' })
  observer.observe(sentinel.value)
}

async function loadCatalogState({
  categoryId = shopStore.currentCategory,
  sortKey = shopStore.currentSort || 'default',
  filters = buildCatalogFilters(),
  actionId = null,
  useCache = true,
  signal
} = {}) {
  if (useCache && tryRestoreFromCache(categoryId, sortKey, filters)) {
    await nextTick()
    if (actionId !== null && actionId !== latestCatalogActionId) return { success: false, cancelled: true, error: '' }
    setupInfiniteScroll()
    return { success: true, restored: true }
  }

  initialLoading.value = true
  const result = await shopStore.fetchProducts({
    categoryId,
    forceRefresh: true,
    sort: sortKey,
    priceMin: filters.priceMin,
    priceMax: filters.priceMax,
    signal
  })
  if (actionId !== null && actionId !== latestCatalogActionId) return { success: false, cancelled: true, error: '' }
  initialLoading.value = false
  if (!result?.success) return result
  if (isSameCatalogState(categoryId, sortKey, filters)) saveCache(categoryId, sortKey, filters)
  syncPriceFilterInputs(filters.priceMin, filters.priceMax)
  lastLoadedAt = Date.now()
  await nextTick()
  if (actionId !== null && actionId !== latestCatalogActionId) return { success: false, cancelled: true, error: '' }
  setupInfiniteScroll()
  return result
}

async function runCatalogAction(options) {
  const actionId = ++latestCatalogActionId
  activeRequest?.abort()
  activeRequest = new AbortController()
  const result = await loadCatalogState({ ...options, actionId, signal: activeRequest.signal })
  if (!result?.success && !result?.cancelled && !result?.aborted) {
    toast.error(result?.error || consumeStoreError('加载物品失败，请稍后重试'))
  }
  return result
}

function handleCategorySelect(categoryId) {
  return runCatalogAction({ categoryId, sortKey: shopStore.currentSort || 'default', filters: buildCatalogFilters() })
}

function handleSortChange(sortKey) {
  return runCatalogAction({ categoryId: shopStore.currentCategory, sortKey, filters: buildCatalogFilters() })
}

function handleMobileSortChange(event) {
  return handleSortChange(event.target.value)
}

function openMobileFilters() {
  if (!loading.value) mobileFilterOpen.value = true
}

function closeMobileFilters() {
  if (!filterApplying.value) mobileFilterOpen.value = false
}

function captureCatalogSnapshot() {
  return {
    categoryId: shopStore.currentCategory,
    products: [...toSafeArray(shopStore.products)],
    total: shopStore.total,
    hasMore: shopStore.hasMore,
    page: shopStore.page,
    cursor: shopStore.catalogCursor || '',
    rankingContext: shopStore.rankingContext || null,
    sort: shopStore.currentSort || 'default',
    inStockOnly: !!shopStore.inStockOnly,
    priceMin: shopStore.currentPriceMin,
    priceMax: shopStore.currentPriceMax
  }
}

async function handleMobileFilterApply(draft) {
  if (filterApplying.value) return
  const filters = buildCatalogFilters(draft)
  const stockChanged = filters.inStockOnly !== !!shopStore.inStockOnly
  const priceChanged = filters.priceMin !== shopStore.currentPriceMin || filters.priceMax !== shopStore.currentPriceMax
  syncPriceFilterInputs(filters.priceMin, filters.priceMax)

  if (!stockChanged && !priceChanged) {
    mobileFilterOpen.value = false
    return
  }

  const previousSnapshot = captureCatalogSnapshot()
  if (stockChanged) {
    categoryCache.clear()
    shopStore.setInStockOnly(filters.inStockOnly)
  }

  filterApplying.value = true
  try {
    const result = await runCatalogAction({
      categoryId: shopStore.currentCategory,
      sortKey: shopStore.currentSort || 'default',
      filters,
      useCache: !stockChanged
    })
    if (result?.success) {
      mobileFilterOpen.value = false
      return
    }
    if (!result?.cancelled && !result?.aborted) {
      shopStore.restoreFromCache(previousSnapshot)
      syncPriceFilterInputs(previousSnapshot.priceMin, previousSnapshot.priceMax)
      await nextTick()
      setupInfiniteScroll()
    }
  } finally {
    filterApplying.value = false
  }
}

async function handleToggleInStock() {
  categoryCache.clear()
  shopStore.setInStockOnly(!shopStore.inStockOnly)
  await runCatalogAction({
    categoryId: shopStore.currentCategory,
    sortKey: shopStore.currentSort || 'default',
    filters: buildCatalogFilters(),
    useCache: false
  })
}

function applyPriceFilter() {
  const filters = buildCatalogFilters(normalizePriceFilterRange(priceMinInput.value, priceMaxInput.value))
  syncPriceFilterInputs(filters.priceMin, filters.priceMax)
  return runCatalogAction({ categoryId: shopStore.currentCategory, sortKey: shopStore.currentSort || 'default', filters })
}

function clearPriceFilter() {
  if (!hasDraftPriceFilter.value && !hasActivePriceFilter.value) return
  priceMinInput.value = ''
  priceMaxInput.value = ''
  return runCatalogAction({
    categoryId: shopStore.currentCategory,
    sortKey: shopStore.currentSort || 'default',
    filters: buildCatalogFilters({ priceMin: null, priceMax: null })
  })
}

async function initialize() {
  if (hasInitialized.value) return
  const categoriesResult = await shopStore.fetchCategories()
  if (!categoriesResult.success) toast.warning(categoriesResult.error || '加载分类失败，请稍后重试')
  activeRequest?.abort()
  activeRequest = new AbortController()
  const result = await loadCatalogState({
    categoryId: '',
    sortKey: shopStore.currentSort || 'default',
    filters: buildCatalogFilters(),
    useCache: false,
    signal: activeRequest.signal
  })
  if (!result?.success) toast.error(result?.error || consumeStoreError('加载物品失败，请稍后重试'))
  initialLoading.value = false
  hasInitialized.value = true
}

onMounted(() => {
  handleViewportResize()
  window.addEventListener('resize', handleViewportResize)
  initialize()
})

onActivated(async () => {
  window.addEventListener('resize', handleViewportResize)
  if (!hasInitialized.value || initialLoading.value) return
  if (Date.now() - lastLoadedAt >= CATEGORY_CACHE_TTL) {
    activeRequest?.abort()
    activeRequest = new AbortController()
    await loadCatalogState({ useCache: true, signal: activeRequest.signal })
  } else {
    await nextTick()
    setupInfiniteScroll()
  }
})

onDeactivated(() => {
  latestCatalogActionId++
  activeRequest?.abort()
  observer?.disconnect()
  window.removeEventListener('resize', handleViewportResize)
  mobileFilterOpen.value = false
})

onUnmounted(() => {
  activeRequest?.abort()
  observer?.disconnect()
  window.removeEventListener('resize', handleViewportResize)
})

watch(hasMore, (value) => {
  if (value) nextTick(setupInfiniteScroll)
})
</script>

<style scoped>
.section-content { min-height: 360px; animation: fade-in .3s ease; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.filter-section, .sort-section, .mobile-catalog-toolbar { margin-bottom: 12px; }
.sort-section, .catalog-filters, .sort-options, .price-filter, .stock-filter, .products-header, .loading-indicator { display: flex; align-items: center; }
.sort-section { justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.mobile-catalog-toolbar { display: none; }
.sort-options { gap: 4px; flex-wrap: wrap; }
.catalog-filters { justify-content: flex-end; gap: 12px; flex: 1 1 360px; flex-wrap: wrap; }
.sort-btn { min-height: 32px; padding: 4px 10px; font-size: 12px; color: var(--text-tertiary); background: transparent; border: 0; border-radius: 12px; cursor: pointer; white-space: nowrap; transition: color .2s ease, background-color .2s ease; }
.sort-btn:hover { color: var(--text-secondary); background: var(--bg-tertiary); }
.sort-btn.active { color: var(--color-primary); background: var(--color-primary-bg); font-weight: 500; }
.price-filter { gap: 8px; flex-wrap: wrap; }
.price-filter-input { width: 112px; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); font-size: 12px; }
.price-filter-input:focus { outline: 0; border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--palette-rgba-34-197-94-p12); }
.price-filter-separator, .products-count { font-size: 13px; color: var(--text-tertiary); }
.price-filter-btn { min-height: 34px; padding: 8px 12px; border: 0; border-radius: 10px; background: var(--color-primary); color: var(--palette-hex-ffffff); font-size: 12px; font-weight: 600; cursor: pointer; }
.price-filter-btn.secondary { background: var(--bg-tertiary); color: var(--text-secondary); }
.stock-filter { position: relative; gap: 6px; cursor: pointer; user-select: none; flex-shrink: 0; }
.stock-filter-input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.checkbox { width: 16px; height: 16px; border: 1.5px solid var(--border-color); border-radius: 4px; display: grid; place-items: center; background: var(--bg-primary); }
.checkbox.checked { background: var(--color-primary); border-color: var(--color-primary); }
.checkmark { color: var(--palette-hex-ffffff); font-size: 10px; font-weight: 700; }
.filter-label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.sort-btn:focus-visible, .price-filter-btn:focus-visible, .stock-filter-input:focus-visible + .checkbox { outline: 2px solid var(--color-primary); outline-offset: 3px; }
.products-header { justify-content: space-between; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.products-count strong { color: var(--text-primary); }
.filter-tag { display: inline-block; margin-left: 8px; padding: 2px 8px; font-size: 11px; color: var(--color-success); background: var(--color-success-bg); border-radius: 10px; }
.filter-tag.price-tag { color: var(--color-primary); background: var(--color-primary-bg); }
.products-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.load-more, .loaded-all { grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; min-height: 64px; padding: 20px; color: var(--text-tertiary); font-size: 13px; }
.loading-indicator { gap: 8px; }
.spinner { width: 16px; height: 16px; border: 2px solid var(--border-medium); border-top-color: var(--color-primary); border-radius: 50%; animation: spin .8s linear infinite; }
.products-loading { min-height: 360px; padding: 20px 0; }
@media (min-width: 768px) { .products-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (min-width: 1024px) { .products-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 768px) {
  .sort-section { display: none; }
  .mobile-catalog-toolbar { width: 100%; min-width: 0; display: flex; align-items: center; gap: 8px; }
  .mobile-sort-control { position: relative; min-width: 0; flex: 1 1 auto; display: flex; align-items: center; }
  .mobile-sort-control select { width: 100%; min-width: 0; min-height: 44px; appearance: none; padding: 0 38px 0 13px; overflow: hidden; border: 1px solid var(--border-color); border-radius: 13px; background: var(--bg-card); color: var(--text-primary); font-size: 14px; font-weight: 600; text-overflow: ellipsis; cursor: pointer; touch-action: manipulation; }
  .mobile-sort-control svg { position: absolute; right: 13px; color: var(--text-tertiary); pointer-events: none; }
  .mobile-filter-trigger { min-height: 44px; flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 13px; border: 1px solid var(--border-color); border-radius: 13px; background: var(--bg-secondary); color: var(--text-secondary); font-size: 14px; font-weight: 700; white-space: nowrap; cursor: pointer; touch-action: manipulation; transition: background-color var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard), color var(--motion-duration-fast) var(--motion-ease-standard); }
  .mobile-filter-trigger[aria-expanded="true"], .mobile-filter-trigger:active { border-color: var(--border-interactive); background: var(--action-secondary); color: var(--action-secondary-text); }
  .mobile-filter-badge { min-width: 20px; height: 20px; display: inline-grid; place-items: center; padding: 0 5px; border-radius: 999px; background: var(--action-primary); color: var(--action-primary-text); font-size: 11px; line-height: 1; font-variant-numeric: tabular-nums; }
  .mobile-sort-control select:disabled, .mobile-filter-trigger:disabled { cursor: not-allowed; opacity: .5; }
  .mobile-sort-control select:focus-visible, .mobile-filter-trigger:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 3px; }
  .filter-tag { display: none; }
}
@keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .section-content, .spinner { animation: none; } }
</style>
