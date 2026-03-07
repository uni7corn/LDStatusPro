<template>
  <div class="category-page">
    <div class="page-container">
      <!-- 分类标题 -->
      <div class="page-header">
        <h1 class="page-title">
          {{ categoryIcon }} {{ categoryName }}
        </h1>
        <p class="page-subtitle">共 {{ total }} 个物品</p>
      </div>
      
      <!-- 筛选排序 -->
      <div class="filter-bar">
        <LiquidTabs
          v-model="currentSort"
          :tabs="sortTabs"
          @update:model-value="changeSort"
        />
      </div>
      
      <!-- 加载中 -->
      <div v-if="loading" class="loading-state">
        <Skeleton type="product" :count="4" />
      </div>
      
      <!-- 空状态 -->
      <EmptyState
        v-else-if="products.length === 0"
        icon="📦"
        title="暂无物品"
        :description="`该分类下暂无物品`"
      >
        <router-link to="/" class="back-btn">
          浏览全部物品
        </router-link>
      </EmptyState>
      
      <!-- 物品列表 -->
      <div v-else class="products-grid">
        <ProductCard
          v-for="product in products"
          :key="product.id"
          :product="product"
          @click="viewProduct(product)"
        />
      </div>
      
      <!-- 加载更多 -->
      <div v-if="hasMore && !loading" class="load-more">
        <button class="load-more-btn" @click="loadMore" :disabled="loadingMore">
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onActivated, onDeactivated, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useShopStore } from '@/stores/shop'
import { useToast } from '@/composables/useToast'
import ProductCard from '@/components/product/ProductCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import Skeleton from '@/components/common/Skeleton.vue'
import LiquidTabs from '@/components/common/LiquidTabs.vue'

// 组件名称（用于 keep-alive 缓存）
defineOptions({ name: 'Category' })

const route = useRoute()
const router = useRouter()
const shopStore = useShopStore()
const toast = useToast()

const loading = ref(true)
const loadingMore = ref(false)
const products = ref([])
const page = ref(1)
const total = ref(0)
const hasMore = ref(false)
const currentSort = ref('default')
const pageSize = 20

// 滚动位置保存
let savedScrollPosition = 0
let lastCategory = ''

// 分类配置
const categoryConfig = {
  'AI': { name: 'AI', icon: '🤖' },
  '存储': { name: '存储', icon: '💾' },
  '小鸡': { name: '小鸡', icon: '🐔' },
  '咨询': { name: '咨询', icon: '💬' },
  '卡券': { name: '卡券', icon: '🎫' }
}

// 排序选项
const sortOptions = [
  { value: 'default', label: '默认' },
  { value: 'newest', label: '最新' },
  { value: 'price_asc', label: '价格↑' },
  { value: 'price_desc', label: '价格↓' },
  { value: 'sales', label: '销量' }
]

// 转换为 LiquidTabs 格式
const sortTabs = sortOptions.map(opt => ({
  value: opt.value,
  label: opt.label
}))

// 当前分类
const category = computed(() => route.params.name || '')
const categoryName = computed(() => categoryConfig[category.value]?.name || category.value)
const categoryIcon = computed(() => categoryConfig[category.value]?.icon || '📦')

// 加载物品
async function loadProducts(append = false) {
  try {
    if (!append) {
      loading.value = true
      page.value = 1
    } else {
      loadingMore.value = true
    }
    
    const result = await shopStore.fetchProducts({
      category: category.value,
      page: page.value,
      pageSize,
      sort: currentSort.value
    })

    if (!result?.success) {
      toast.error(result?.error || shopStore.consumeLastError?.() || '加载分类物品失败，请稍后重试')
      if (!append) {
        products.value = []
        total.value = 0
        hasMore.value = false
      }
      return
    }
    
    if (append) {
      products.value.push(...(result.products || result))
    } else {
      products.value = result.products || result
      total.value = result.total || products.value.length
    }
    
    hasMore.value = typeof result.hasMore === 'boolean'
      ? result.hasMore
      : (result.products || result).length === pageSize
  } catch (error) {
    console.error('Load category products error:', error)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

// 加载更多
function loadMore() {
  page.value++
  loadProducts(true)
}

// 切换排序
function changeSort(sort) {
  currentSort.value = sort
  loadProducts()
}

// 查看物品
function viewProduct(product) {
  router.push(`/product/${product.id}`)
}

// 监听分类变化
watch(() => route.params.name, (newCategory) => {
  if (newCategory) {
    // 如果分类变化了，重新加载
    if (newCategory !== lastCategory) {
      lastCategory = newCategory
      loadProducts()
    }
  }
}, { immediate: true })

// keep-alive 激活时恢复滚动位置
onActivated(() => {
  // 如果分类没变，恢复滚动位置
  if (route.params.name === lastCategory && savedScrollPosition > 0) {
    nextTick(() => {
      window.scrollTo(0, savedScrollPosition)
    })
  }
})

// keep-alive 停用时保存滚动位置
onDeactivated(() => {
  savedScrollPosition = window.scrollY
})
</script>

<style scoped>
.category-page {
  min-height: 100vh;
  padding-bottom: 80px;
  background: var(--bg-primary);
}

.page-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 16px;
}

/* 页面头部 */
.page-header {
  text-align: center;
  padding: 24px 0;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 筛选栏 */
.filter-bar {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--bg-card);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
}

/* LiquidTabs 已替代原有样式 */

/* 加载状态 */
.loading-state {
  padding-top: 20px;
}

/* 返回按钮 */
.back-btn {
  display: inline-block;
  padding: 12px 24px;
  background: var(--color-primary);
  color: white;
  border-radius: 12px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.back-btn:hover {
  background: var(--color-primary-hover);
}

/* 物品网格 */
.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

@media (max-width: 640px) {
  .products-grid {
    grid-template-columns: 1fr;
  }
}

/* 加载更多 */
.load-more {
  padding: 30px;
  text-align: center;
}

.load-more-btn {
  padding: 12px 40px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 24px;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.load-more-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--border-default);
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
