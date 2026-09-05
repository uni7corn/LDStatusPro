<template>
          <div class="board-panel">
            <div class="board-toolbar">
              <div>
                <p class="panel-eyebrow">容量与占用</p>
                <h2 class="panel-title">名额看板</h2>
                <p class="panel-subtitle">查看各甄选池与优选池的实时余量、占用情况及预计释放时间。</p>
              </div>
              <div class="board-actions">
                <label class="board-filter-select"><span class="sr-only">查看分类名额</span><select v-model="quotaBoardCategoryId" :disabled="quotaBoardLoading || (!quotaBoardLoaded && !quotaBoardCategories.length)"><option v-for="option in quotaBoardCategoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
                <button class="ghost-btn" :disabled="quotaBoardLoading" @click="loadQuotaBoard">
                  <RefreshCw :size="16" aria-hidden="true" />
                  {{ quotaBoardLoading ? '刷新中...' : '刷新看板' }}
                </button>
                <button type="button" class="ghost-btn" @click="$emit('purchase')">选择物品开通<ArrowRight :size="16" aria-hidden="true" /></button>
              </div>
            </div>

            <p v-if="boardError" class="board-error" role="alert">{{ boardError }}<button type="button" class="ghost-btn" :disabled="quotaBoardLoading" @click="loadQuotaBoard">重新加载</button></p>
            <div v-if="showQuotaBoardLoading" class="board-loading">
              <div class="board-summary-grid">
                <article v-for="index in 4" :key="`board-summary-loading-${index}`" class="board-summary-card board-summary-card--loading">
                  <div class="loading-shimmer board-skeleton board-skeleton-kicker"></div>
                  <div class="loading-shimmer board-skeleton board-skeleton-value"></div>
                  <div class="loading-shimmer board-skeleton board-skeleton-copy"></div>
                  <div class="board-summary-meta">
                    <span class="loading-shimmer board-skeleton board-skeleton-meta"></span>
                    <span class="loading-shimmer board-skeleton board-skeleton-meta board-skeleton-meta--wide"></span>
                  </div>
                </article>
              </div>

              <div class="category-quota-grid">
                <article v-for="index in 6" :key="`category-loading-${index}`" class="category-quota-card category-quota-card--loading">
                  <div class="category-quota-head">
                    <div class="loading-shimmer board-skeleton board-skeleton-title"></div>
                    <div class="loading-shimmer board-skeleton board-skeleton-pill"></div>
                  </div>
                  <div class="loading-shimmer board-skeleton board-skeleton-copy"></div>
                  <div class="loading-shimmer board-skeleton board-skeleton-copy board-skeleton-copy--short"></div>
                </article>
              </div>

              <div class="board-records">
                <article v-for="index in 3" :key="`record-loading-${index}`" class="active-service-card active-service-card--loading">
                  <div class="active-service-head">
                    <div class="active-service-main">
                      <div class="active-service-badges">
                        <span class="loading-shimmer board-skeleton board-skeleton-badge"></span>
                        <span class="loading-shimmer board-skeleton board-skeleton-badge board-skeleton-badge--wide"></span>
                      </div>
                      <div class="loading-shimmer board-skeleton board-skeleton-heading"></div>
                    </div>
                    <div class="active-service-remaining">
                      <span class="loading-shimmer board-skeleton board-skeleton-mini"></span>
                      <strong class="loading-shimmer board-skeleton board-skeleton-number"></strong>
                    </div>
                  </div>
                  <div class="active-service-grid">
                    <div v-for="cellIndex in 4" :key="cellIndex">
                      <span class="loading-shimmer board-skeleton board-skeleton-mini"></span>
                      <strong class="loading-shimmer board-skeleton board-skeleton-field"></strong>
                    </div>
                  </div>
                </article>
              </div>
            </div>

            <template v-else-if="quotaBoardLoaded">
              <div class="board-summary-grid">
                <article
                  v-for="pool in quotaBoardGlobalPools"
                  :key="pool.key"
                  class="board-summary-card"
                  :class="pool.usesSharedGlobalPool ? 'board-summary-card--global' : 'board-summary-card--special'"
                >
                  <span class="board-summary-kicker">{{ pool.usesSharedGlobalPool ? '共享甄选池' : '独立甄选池' }}</span>
                  <strong class="board-summary-value">{{ pool.remaining }} / {{ pool.limit }}</strong>
                  <p class="board-summary-copy">{{ formatGlobalPoolSummary(pool) }}</p>
                  <div class="board-summary-meta">
                    <span>占用中 {{ pool.used }} 个</span>
                    <span v-if="pool.pendingUsed > 0">待支付占位 {{ pool.pendingUsed }} 个</span>
                    <span>{{ formatQuotaReleaseHint(pool.nextReleaseAt, pool.hasPermanentTop, pool.used, 'global', pool.name) }}</span>
                  </div>
                </article>

                <article class="board-summary-card board-summary-card--focus">
                  <span class="board-summary-kicker">{{ selectedQuotaCategory ? '当前分类优选池' : '优选池说明' }}</span>
                  <strong class="board-summary-value">
                    {{ selectedQuotaCategory ? `${selectedQuotaCategory.categoryRemaining} / ${selectedQuotaCategory.categoryLimit}` : `${quotaBoardCategories.length} 个` }}
                  </strong>
                  <p class="board-summary-copy">
                    {{ selectedQuotaCategory
                      ? `${selectedQuotaCategory.categoryName} 当前优选池剩余名额；本分类的士多甄选走「${selectedQuotaCategory.globalPoolName}」，当前可见 ${selectedQuotaCategory.visibleTotal} 个置顶项（含管理员无偿置顶）。`
                      : '请选择下方分类卡片或右上角筛选器，查看某个分类的优选池与甄选池占用情况。' }}
                  </p>
                  <div class="board-summary-meta">
                    <template v-if="selectedQuotaCategory">
                      <span>优选占用 {{ selectedQuotaCategory.categoryUsed }} 个</span>
                      <span v-if="selectedQuotaCategory.categoryPendingUsed > 0">优选待支付 {{ selectedQuotaCategory.categoryPendingUsed }} 个</span>
                      <span>甄选池 {{ selectedQuotaCategory.globalRemaining }} / {{ selectedQuotaCategory.globalLimit }}</span>
                      <span>{{ formatQuotaReleaseHint(selectedQuotaCategory.nextCategoryReleaseAt, selectedQuotaCategory.hasPermanentCategoryTop, selectedQuotaCategory.categoryUsed, 'category') }}</span>
                    </template>
                    <template v-else>
                      <span>分类总数 {{ quotaBoardCategories.length }} 个</span>
                      <span>共享甄选池 {{ sharedGlobalQuota.remaining }} / {{ sharedGlobalQuota.limit }}</span>
                      <span>更新时间 {{ quotaBoard.generatedAt || '-' }}</span>
                    </template>
                  </div>
                </article>
              </div>

              <div class="category-quota-grid">
                <button
                  type="button"
                  class="category-quota-card category-quota-card--all"
                  :class="{ active: quotaBoardCategoryId === 'all' }"
                  @click="quotaBoardCategoryId = 'all'"
                >
                  <div class="category-quota-head">
                    <span class="category-quota-title">
                      <span class="category-quota-icon" aria-hidden="true"></span>
                      全部分类
                    </span>
                    <span class="category-quota-pill">{{ quotaBoard.activeRecords?.length || 0 }} 条</span>
                  </div>
                  <p class="category-quota-copy">查看全部分类当前已生效的置顶服务。共享甄选池与独立甄选池的真实剩余名额请以上方总览卡片为准；切到非开通分类而被暂停的付费服务不会显示在这里。</p>
                  <div class="category-quota-meta">
                    <span>分类总数 {{ quotaBoardCategories.length }} 个</span>
                    <span>共享甄选占用 {{ sharedGlobalQuota.used }} 个</span>
                  </div>
                </button>

                <button
                  v-for="category in quotaBoardCategories"
                  :key="category.categoryId"
                  type="button"
                  class="category-quota-card"
                  :class="{ active: String(quotaBoardCategoryId) === String(category.categoryId) }"
                  @click="quotaBoardCategoryId = String(category.categoryId)"
                >
                  <div class="category-quota-head">
                    <span class="category-quota-title">
                      <span class="category-quota-icon" aria-hidden="true"></span>
                      {{ category.categoryName }}
                    </span>
                    <span class="category-quota-pill">优选 {{ category.categoryRemaining }} / {{ category.categoryLimit }}</span>
                  </div>
                  <div class="category-quota-stats">
                    <div class="category-quota-stat">
                      <span class="category-quota-stat-label">优选池</span>
                      <strong class="category-quota-stat-value">{{ category.categoryRemaining }} / {{ category.categoryLimit }}</strong>
                      <p class="category-quota-stat-copy">{{ category.categoryName }} 分类独立优选池</p>
                    </div>
                    <div class="category-quota-stat">
                      <span class="category-quota-stat-label">甄选池</span>
                      <strong class="category-quota-stat-value">{{ category.globalRemaining }} / {{ category.globalLimit }}</strong>
                      <p class="category-quota-stat-copy">{{ category.globalPoolName }}</p>
                    </div>
                  </div>
                  <p class="category-quota-copy">{{ formatCategoryQuotaCopy(category) }}</p>
                  <div class="category-quota-meta">
                    <span>优选占用 {{ category.categoryUsed }} 个</span>
                    <span v-if="category.categoryPendingUsed > 0">优选待支付 {{ category.categoryPendingUsed }} 个</span>
                    <span>甄选展示 {{ category.globalVisibleCount }} 个</span>
                    <span v-if="category.globalPendingUsed > 0">甄选待支付 {{ category.globalPendingUsed }} 个</span>
                    <span>当前可见 {{ category.visibleTotal }} 个置顶项</span>
                    <span>{{ formatQuotaReleaseHint(category.nextCategoryReleaseAt, category.hasPermanentCategoryTop, category.categoryUsed, 'category') }}</span>
                    <span>{{ formatQuotaReleaseHint(category.nextGlobalReleaseAt, category.hasPermanentGlobalTop, category.globalUsed, 'global', category.globalPoolName) }}</span>
                  </div>
                </button>
              </div>

              <div class="board-list-panel">
                <div class="board-list-head">
                  <div>
                    <h3 class="board-list-title">生效服务</h3>
                    <p class="panel-subtitle">
                      {{ selectedQuotaCategory
                        ? `当前展示 ${selectedQuotaCategory.categoryName} 分类下已生效的士多甄选、士多优选与管理员无偿置顶。待支付占位已计入上方名额，不在此列表中展示。`
                        : '当前展示全部分类下已生效的士多甄选、士多优选与管理员无偿置顶。待支付占位已计入上方名额，不在此列表中展示；切到非开通分类而暂停的付费服务也不会出现在这里。' }}
                    </p>
                  </div>
                  <span class="board-generated-at">更新时间：{{ quotaBoard.generatedAt || '-' }}</span>
                </div>

                <div v-if="filteredQuotaRecords.length > 0" class="board-records">
                  <article v-for="record in filteredQuotaRecords" :key="record.id" class="active-service-card">
                    <div class="active-service-head">
                      <div class="active-service-main">
                        <div class="active-service-badges">
                          <span :class="['active-service-type', `type-${record.packageType || 'category'}`]">
                            {{ record.packageType === 'global' ? '士多甄选' : '士多优选' }}
                          </span>
                          <span v-if="!record.isPaidService" class="active-service-source">
                            管理员非有偿
                          </span>
                          <span v-else-if="record.packageType === 'global' && !record.usesSharedGlobalPool" class="active-service-source active-service-source--exempt">
                            {{ record.globalPoolName }}
                          </span>
                          <span class="active-service-category">
                            {{ record.categoryName || '未分类' }}
                          </span>
                        </div>
                        <h3 class="active-service-title">{{ record.productName }}</h3>
                      </div>
                      <div class="active-service-remaining">
                        <span>剩余时长</span>
                        <strong>{{ record.remainingDurationText || '永久置顶' }}</strong>
                      </div>
                    </div>

                    <div class="active-service-grid">
                      <div>
                        <span>服务天数</span>
                        <strong>{{ record.durationDays ? `${record.durationDays} 天` : '永久置顶' }}</strong>
                      </div>
                      <div>
                        <span>生效时间</span>
                        <strong>{{ record.effectiveAt || '-' }}</strong>
                      </div>
                      <div>
                        <span>到期时间</span>
                        <strong>{{ record.expiredAt || '永久置顶' }}</strong>
                      </div>
                      <div>
                        <span>服务类型</span>
                        <strong>{{ record.packageName }}</strong>
                      </div>
                    </div>
                  </article>
                </div>

                <div v-else class="empty-state">
                  当前筛选下暂无生效中的置顶服务
                </div>
              </div>
            </template>
          </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, RefreshCw } from '@lucide/vue'
import { fetchTopServiceBoardRequest } from '@/services/shop/topServiceService'
const quotaBoardLoading = ref(false)
defineEmits(['purchase'])
const quotaBoardLoaded = ref(false)
const boardError = ref('')
const quotaBoardCategoryId = ref('all')
const quotaBoard = ref({ generatedAt: '', globalQuota: null, globalPools: [], categories: [], activeRecords: [] })
function formatQuotaValue(remaining = 0, limit = 0) {
  return `${Number(remaining || 0)} / ${Number(limit || 0)}`
}

function getGlobalPoolLabel(poolName = '') {
  return poolName || '甄选池'
}

function normalizeGlobalPool(pool = {}) {
  return {
    ...pool,
    key: pool?.key || 'shared_all',
    name: pool?.name || pool?.globalPoolName || '甄选池',
    categoryName: pool?.categoryName || '',
    limit: Number(pool?.limit ?? pool?.globalLimit ?? 0),
    used: Number(pool?.used ?? pool?.globalUsed ?? 0),
    pendingUsed: Number(pool?.pendingUsed ?? 0),
    remaining: Number(pool?.remaining ?? pool?.globalRemaining ?? 0),
    nextReleaseAt: pool?.nextReleaseAt || pool?.nextGlobalReleaseAt || '',
    hasPermanentTop: Boolean(pool?.hasPermanentTop ?? pool?.hasPermanentGlobalTop),
    usesSharedGlobalPool: pool?.usesSharedGlobalPool !== false
  }
}

const showQuotaBoardLoading = computed(() => quotaBoardLoading.value && !quotaBoardLoaded.value)
const quotaBoardCategories = computed(() => Array.isArray(quotaBoard.value.categories) ? quotaBoard.value.categories : [])
const quotaBoardGlobalPools = computed(() => {
  if (Array.isArray(quotaBoard.value.globalPools) && quotaBoard.value.globalPools.length > 0) {
    return quotaBoard.value.globalPools.map((item) => normalizeGlobalPool(item))
  }
  return quotaBoard.value.globalQuota ? [normalizeGlobalPool(quotaBoard.value.globalQuota)] : []
})
const sharedGlobalQuota = computed(() => (
  quotaBoardGlobalPools.value.find((item) => item.usesSharedGlobalPool)
  || normalizeGlobalPool(quotaBoard.value.globalQuota || {
    key: 'shared_all',
    name: '全部分类共享甄选池',
    limit: 0,
    used: 0,
    pendingUsed: 0,
    remaining: 0,
    nextReleaseAt: '',
    hasPermanentTop: false
  })
))
const quotaBoardCategoryOptions = computed(() => [
  {
    value: 'all',
    label: '全部分类',
    description: `查看全部分类的 ${Array.isArray(quotaBoard.value.activeRecords) ? quotaBoard.value.activeRecords.length : 0} 条生效服务`,
    icon: ''
  },
  ...quotaBoardCategories.value.map((item) => ({
    value: String(item.categoryId),
    label: item.categoryName || '未分类',
    description: `优选 ${formatQuotaValue(item.categoryRemaining, item.categoryLimit)} · ${getGlobalPoolLabel(item.globalPoolName)} ${formatQuotaValue(item.globalRemaining, item.globalLimit)}`,
    icon: ''
  }))
])
const selectedQuotaCategory = computed(() => (
  quotaBoardCategories.value.find((item) => String(item.categoryId) === String(quotaBoardCategoryId.value)) || null
))
const filteredQuotaRecords = computed(() => {
  const records = Array.isArray(quotaBoard.value.activeRecords) ? quotaBoard.value.activeRecords : []
  if (String(quotaBoardCategoryId.value) === 'all') return records
  return records.filter((item) => String(item.categoryId) === String(quotaBoardCategoryId.value))
})

function formatQuotaReleaseHint(nextReleaseAt = '', hasPermanent = false, used = 0, scope = 'category', poolName = '') {
  if (used <= 0) {
    return scope === 'global'
      ? `${poolName || '甄选池'} 当前名额充足`
      : '当前分类优选池名额充足'
  }
  if (nextReleaseAt) {
    return `最早释放：${nextReleaseAt}`
  }
  if (hasPermanent) {
    return '含永久生效服务'
  }
  return '当前暂无预计释放时间'
}

function formatCategoryQuotaCopy(category = {}) {
  const globalPoolText = `${getGlobalPoolLabel(category.globalPoolName)} ${formatQuotaValue(category.globalRemaining, category.globalLimit)}`
  if (category.usesSharedGlobalPool) {
    return `优选池剩余 ${formatQuotaValue(category.categoryRemaining, category.categoryLimit)}；甄选走共享池，当前池余量 ${globalPoolText}。`
  }
  return `优选池剩余 ${formatQuotaValue(category.categoryRemaining, category.categoryLimit)}；甄选走独立池，当前池余量 ${globalPoolText}，不占用“全部”共享池。`
}

function formatGlobalPoolSummary(pool = {}) {
  if (pool.usesSharedGlobalPool) {
    return `所有会进入“全部”分类的商品共用这 ${Number(pool.limit || 0)} 个士多甄选名额。`
  }
  return `${pool.categoryName || '当前分类'} 专属士多甄选池，不占用“全部分类共享甄选池”。`
}

async function loadQuotaBoard() {
  if (quotaBoardLoading.value) return
  quotaBoardLoading.value = true
  try {
    const response = await fetchTopServiceBoardRequest()
    if (!response?.success) throw new Error('名额看板未能更新，请重试。')
    const result = response.data
    boardError.value = ''
    quotaBoard.value = {
      generatedAt: result?.generatedAt || '',
      globalQuota: result?.globalQuota || null,
      globalPools: Array.isArray(result?.globalPools) ? result.globalPools : [],
      categories: Array.isArray(result?.categories) ? result.categories : [],
      activeRecords: Array.isArray(result?.activeRecords) ? result.activeRecords : []
    }
    quotaBoardLoaded.value = true
    if (
      String(quotaBoardCategoryId.value) !== 'all'
      && !quotaBoard.value.categories.some((item) => String(item.categoryId) === String(quotaBoardCategoryId.value))
    ) {
      quotaBoardCategoryId.value = 'all'
    }
  } catch (error) {
    boardError.value = error.message || '名额看板未能更新，请重试。'
  } finally {
    quotaBoardLoading.value = false
  }
}


onMounted(loadQuotaBoard)
defineExpose({ refresh: loadQuotaBoard })
</script>
<style scoped>
.board-panel {
  --services-title:var(--seller-ink); --services-title-strong:var(--seller-ink);
  --services-copy:var(--seller-muted); --services-copy-strong:var(--seller-muted);
  --services-accent:var(--seller-jade-strong); --services-accent-deep:var(--seller-jade-strong);
  --services-card-bg:var(--seller-surface); --services-card-border:var(--seller-border);
  --services-card-shadow:none; --services-highlight-bg:var(--seller-jade-soft);
  --services-highlight-shadow:none; --services-muted-bg:var(--seller-surface-soft);
  --services-muted-border:var(--seller-border); --services-hover-border:var(--seller-jade);
  --services-hover-shadow:none; --services-accent-soft:var(--seller-jade-soft);
  --services-accent-border:var(--seller-border); --services-category-chip-bg:var(--seller-jade-soft);
  --services-category-chip-text:var(--seller-jade-strong); --services-category-type-bg:var(--seller-jade-soft);
  --services-category-type-text:var(--seller-jade-strong); --services-accent-soft-strong:var(--seller-jade-soft);
  --services-muted-chip-bg:var(--seller-surface-soft); --services-muted-chip-text:var(--seller-muted);
}
.board-panel {
  display: grid;
  gap: 18px;
}

.board-toolbar,
.board-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.board-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.board-filter-select {
  min-width: 200px;
}
.board-filter-select select { width:100%; min-height:44px; padding:10px 12px; border:1px solid var(--seller-border); border-radius:9px; color:var(--seller-ink); background:var(--seller-surface); font-size:13px; }

.board-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.board-summary-card,
.active-service-card {
  padding: 20px;
}

.board-summary-card {
  display: grid;
  gap: 10px;
}

.board-summary-card--global {
  border-color: var(--services-accent-border);
  background: var(--services-highlight-bg);
}

.board-summary-card--special {
  background: linear-gradient(180deg, var(--palette-rgba-249-237-214-0p72) 0%, var(--services-card-bg) 100%);
  border-color: var(--palette-rgba-198-146-68-0p22);
}

.board-summary-card--focus {
  background: var(--services-panel-bg);
}

.board-summary-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--services-accent);
}

.board-summary-value {
  font-size: clamp(28px, 4vw, 38px);
  line-height: 1;
  color: var(--services-title);
}

.board-summary-copy {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--services-copy);
}

.board-summary-meta,
.category-quota-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.board-summary-meta span,
.category-quota-meta span {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--services-accent-soft);
  font-size: 12px;
  color: var(--services-accent);
}

.category-quota-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.category-quota-card {
  width: 100%;
  padding: 18px;
  text-align: left;
  border-color: var(--services-accent-border-soft);
  background: var(--services-panel-bg);
  cursor: pointer;
  appearance: none;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.category-quota-card:hover,
.category-quota-card.active {
  transform: translateY(-1px);
  border-color: var(--services-hover-border);
  box-shadow: var(--services-hover-shadow);
}

.category-quota-card--all {
  background: var(--services-highlight-bg);
}

.category-quota-card--loading,
.active-service-card--loading,
.board-summary-card--loading {
  pointer-events: none;
}

.category-quota-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.category-quota-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--services-title);
}

.category-quota-icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--services-accent-soft);
  flex-shrink: 0;
}

.category-quota-pill {
  flex-shrink: 0;
  padding: 7px 10px;
  border-radius: 999px;
  background: var(--services-accent-soft-strong);
  font-size: 12px;
  font-weight: 800;
  color: var(--services-accent);
}

.category-quota-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.category-quota-stat {
  min-width: 0;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid var(--services-accent-border-soft);
  background: var(--services-card-bg-strong);
  display: grid;
  gap: 6px;
}

.category-quota-stat-label {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--services-accent);
}

.category-quota-stat-value {
  font-size: 18px;
  line-height: 1.1;
  color: var(--services-title);
}

.category-quota-stat-copy {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.category-quota-copy {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.board-list-panel {
  display: grid;
  gap: 16px;
}

.board-list-title {
  margin: 0;
  font-size: 20px;
  color: var(--services-title);
}

.board-generated-at {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--services-accent-soft);
  font-size: 12px;
  color: var(--services-accent);
}

.board-records {
  display: grid;
  gap: 14px;
}

.active-service-card {
  display: grid;
  gap: 16px;
}

.active-service-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.active-service-main {
  min-width: 0;
}

.active-service-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.active-service-type,
.active-service-source,
.active-service-category {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.active-service-type.type-global {
  background: var(--services-accent-soft-strong);
  color: var(--services-accent-deep);
}

.active-service-type.type-category {
  background: var(--services-category-type-bg);
  color: var(--services-category-type-text);
}

.active-service-source {
  background: var(--services-muted-chip-bg);
  color: var(--services-muted-chip-text);
}

.active-service-category {
  background: var(--services-category-chip-bg);
  color: var(--services-category-chip-text);
}

.active-service-title {
  margin: 0;
  font-size: 18px;
  line-height: 1.5;
  color: var(--services-title);
}

.active-service-remaining {
  min-width: 120px;
  display: grid;
  gap: 6px;
  text-align: right;
}

.active-service-remaining span,
.active-service-grid span {
  font-size: 12px;
  color: var(--text-secondary);
}

.active-service-remaining strong {
  font-size: 18px;
  color: var(--services-accent-deep);
}

.active-service-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.active-service-grid strong {
  display: block;
  margin-top: 6px;
  font-size: 14px;
  color: var(--text-primary);
}

.board-loading {
  display: grid;
  gap: 18px;
}

.board-skeleton {
  display: block;
  border-radius: 999px;
}

.board-skeleton-kicker {
  width: 84px;
  height: 12px;
}

.board-skeleton-value {
  width: 140px;
  height: 34px;
  border-radius: 12px;
}

.board-skeleton-copy {
  width: 100%;
  height: 12px;
  border-radius: 8px;
}

.board-skeleton-copy--short {
  width: 70%;
}

.board-skeleton-meta {
  width: 90px;
  height: 26px;
}

.board-skeleton-meta--wide {
  width: 140px;
}

.board-skeleton-title {
  width: 110px;
  height: 16px;
  border-radius: 10px;
}

.board-skeleton-pill {
  width: 58px;
  height: 28px;
}

.board-skeleton-badge {
  width: 76px;
  height: 26px;
}

.board-skeleton-badge--wide {
  width: 120px;
}

.board-skeleton-heading {
  width: 220px;
  height: 18px;
  border-radius: 10px;
}

.board-skeleton-mini {
  width: 72px;
  height: 12px;
  border-radius: 8px;
}

.board-skeleton-number {
  width: 84px;
  height: 18px;
  justify-self: end;
  border-radius: 10px;
}

.board-skeleton-field {
  width: 100%;
  height: 16px;
  margin-top: 8px;
  border-radius: 8px;
}
.panel-eyebrow { margin:0 0 6px; font-size:12px; color:var(--seller-jade-strong); }
.panel-title { margin:0; color:var(--seller-ink); font-size:22px; }
.panel-subtitle { color:var(--seller-muted); font-size:13px; line-height:1.8; margin:8px 0 0; }
.ghost-btn { display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:44px; padding:10px 14px; border:1px solid var(--seller-border); border-radius:9px; color:var(--seller-ink); background:var(--seller-surface); font-size:13px; }
.board-error { display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--seller-ink); padding:16px; border:1px solid var(--seller-border); border-radius:10px; font-size:14px; }
.board-summary-card,.category-quota-card,.active-service-card { border:1px solid var(--seller-border); background:var(--seller-surface); box-shadow:none; border-radius:12px; }
.board-summary-card--global { border-left:3px solid var(--seller-jade); }
.board-summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
.category-quota-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
.category-quota-card.active { background:var(--seller-jade-soft); }
.category-quota-icon { width:7px; height:7px; background:var(--seller-jade); border-radius:50%; }
.loading-shimmer { background:var(--seller-surface-soft); }
.empty-state { padding:36px 16px; text-align:center; color:var(--seller-muted); font-size:14px; }
@media(max-width:1100px) { .board-toolbar { flex-direction:column; align-items:stretch; } .category-quota-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:767px) { .board-summary-grid,.category-quota-grid { grid-template-columns:1fr; } .board-actions,.board-list-head,.active-service-head { align-items:stretch; flex-direction:column; } .board-filter-select { min-width:0; } .active-service-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .active-service-remaining { align-items:flex-start; } .board-summary-card,.active-service-card { padding:16px; } }
@media(prefers-reduced-motion:reduce) { * { transition:none!important; animation:none!important; } }
</style>
