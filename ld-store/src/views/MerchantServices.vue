<template>
  <div class="merchant-services-page">
    <div class="page-shell">
      <section class="hero-card">
        <div class="hero-copy">
          <p class="hero-eyebrow">Merchant Services</p>
          <h1 class="hero-title">商家服务</h1>
          <p class="hero-desc">
            士多服务支持自助购买全站置顶与分类置顶。支付成功后立即生效，到期自动释放位置，并同步发送系统提醒。
          </p>
        </div>
        <div class="hero-badge">
          <span class="hero-badge-label">当前开放</span>
          <strong>士多甄选 | 士多优选</strong>
          <span>金色传说！额外曝光！物超所值！</span>
        </div>
      </section>

      <section class="content-card">
        <LiquidTabs v-model="activeTab" :tabs="tabs" />

        <div v-if="activeTab === 'service'" class="panel-body">
          <div class="service-grid">
            <div class="config-panel">
              <div class="panel-title-row">
                <div>
                  <h2 class="panel-title">选择服务</h2>
                  <p class="panel-subtitle">先选商品，再选套餐与天数。每个子分类最多 4 个付费分类置顶名额，“全部”分类最多 4 个付费全站置顶名额；管理员手动设置的非有偿置顶不占用这些名额。全站置顶会同步展示在所属分类，但不占用分类置顶名额。</p>
                </div>
                <button class="ghost-btn" :disabled="optionsLoading" @click="loadOptions">
                  {{ optionsLoading ? '刷新中...' : '刷新额度' }}
                </button>
              </div>

              <div class="field-block">
                <label class="field-label">要置顶的物品</label>
                <AppSelect
                  v-model="selectedProductId"
                  full-width
                  :options="productOptions"
                  :disabled="showPackageLoading"
                  :placeholder="showPackageLoading ? '正在加载可置顶物品...' : '请选择自己已上架的物品'"
                  @change="handleProductChange"
                />
                <p class="field-hint">只展示你自己发布且当前处于已上架状态的物品。</p>
              </div>

              <div class="package-grid">
                <template v-if="showPackageLoading">
                  <article v-for="index in 2" :key="`loading-${index}`" class="package-card package-card--loading" aria-hidden="true">
                    <div class="package-head">
                      <div class="package-loading-copy">
                        <div class="loading-shimmer package-skeleton package-skeleton-title"></div>
                        <div class="loading-shimmer package-skeleton package-skeleton-desc"></div>
                      </div>
                      <div class="loading-shimmer package-skeleton package-skeleton-pill"></div>
                    </div>

                    <div class="duration-list">
                      <div v-for="optionIndex in 3" :key="optionIndex" class="duration-btn duration-btn--loading">
                        <span class="loading-shimmer package-skeleton package-skeleton-days"></span>
                        <span class="loading-shimmer package-skeleton package-skeleton-price"></span>
                      </div>
                    </div>
                  </article>
                </template>

                <template v-else-if="packages.length > 0">
                  <article
                    v-for="group in packages"
                    :key="group.type"
                    class="package-card"
                    :class="{ disabled: isPackageDisabled(group.type) }"
                  >
                    <div class="package-head">
                      <div>
                        <h3 class="package-title">{{ group.name }}</h3>
                        <p class="package-desc">{{ group.type === 'global' ? '【士多甄选】同步展示在所属分类和“全部”分类，且不占用分类置顶名额' : '【士多优选】仅在所属分类顶部展示，占用该分类置顶名额' }}</p>
                      </div>
                      <span class="quota-pill">剩余额度：{{ formatRemaining(group.type) }}</span>
                    </div>

                    <div class="duration-list">
                      <button
                        v-for="option in group.options"
                        :key="`${group.type}-${option.durationDays}`"
                        type="button"
                        class="duration-btn"
                        :class="{ active: selectedPackageType === group.type && selectedDurationDays === option.durationDays }"
                        :disabled="isPackageDisabled(group.type) || !option.isEnabled"
                        @click="selectPackage(group.type, option.durationDays)"
                      >
                        <span class="duration-days">{{ option.durationDays }} 天</span>
                        <span class="duration-price">{{ Number(option.price || 0).toFixed(2) }} LDC</span>
                      </button>
                    </div>
                  </article>
                </template>

                <div v-else class="package-empty-state">
                  <strong>当前暂无可用套餐</strong>
                  <p>可能是额度已满或服务暂未开放，可稍后点击“刷新额度”再试。</p>
                </div>
              </div>

              <button class="submit-btn" :disabled="showPackageLoading || !canSubmit || submitting" @click="submitOrder">
                {{ submitting ? '创建订单中...' : showPackageLoading ? '套餐加载中...' : '确认提交' }}
              </button>
            </div>

            <aside class="summary-panel">
              <h2 class="panel-title">服务说明</h2>
              <div class="summary-card summary-card--intro">
                <div class="summary-intro">
                  <span class="summary-kicker">服务权益</span>
                  <strong>置顶曝光之外，还有专属卡片效果和铭牌</strong>
                  <p>根据你的推广目标选择合适的套餐，页面会同步展示对应的尊享标识和视觉强化。</p>
                </div>
                <div class="summary-points">
                  <div class="summary-point">
                    <span class="summary-point-index">01</span>
                    <div class="summary-point-copy">
                      <strong>优先展示，获得更多曝光</strong>
                      <p>置顶服务生效后，物品会展示在对应的置顶位，更容易被买家看到、点击和咨询。</p>
                    </div>
                  </div>
                  <div class="summary-point">
                    <span class="summary-point-index">02</span>
                    <div class="summary-point-copy">
                      <strong>专属铭牌，提升辨识度</strong>
                      <p>付费全站置顶显示“士多甄选”，付费分类置顶显示“士多优选”，并附带额外的物品卡片效果；管理员非有偿置顶仅保留排序能力，不附带专属样式。</p>
                    </div>
                  </div>
                  <div class="summary-point">
                    <span class="summary-point-index">03</span>
                    <div class="summary-point-copy">
                      <strong>支付成功立即生效</strong>
                      <p>请根据预算和推广周期选择套餐与时长。订单支付成功后立即生效，到期自动失效，无需手动操作。</p>
                    </div>
                  </div>
                </div>
              </div>
              <div class="summary-card">
                <div class="summary-line">
                  <span>已选商品</span>
                  <strong>{{ selectedProduct?.name || '未选择' }}</strong>
                </div>
                <div class="summary-line">
                  <span>套餐</span>
                  <strong>{{ selectedConfig?.groupName || '未选择' }}</strong>
                </div>
                <div class="summary-line">
                  <span>天数</span>
                  <strong>{{ selectedConfig ? `${selectedConfig.durationDays} 天` : '未选择' }}</strong>
                </div>
                <div class="summary-line">
                  <span>价格</span>
                  <strong>{{ selectedConfig ? `${Number(selectedConfig.price || 0).toFixed(2)} LDC` : '-' }}</strong>
                </div>
              </div>

              <div class="notice-card">
                <h3>购买须知</h3>
                <ul>
                  <li>为保证服务质量，付费置顶套餐名额有限。</li>
                  <li>全站付费置顶最多同时 4 个，且同步出现在所属分类，但不占用该分类的 4 个付费分类置顶名额。</li>
                  <li>订单支付成功时间即为置顶服务生效时间。</li>
                  <li>同一物品同一时间只能有一条生效中或待支付的置顶服务。</li>
                  <li>置顶到期时会自动失效，并通过系统消息提醒你。</li>
                  <li>管理员手动设置的非有偿置顶不占用付费名额，会排在付费置顶之后、普通物品之前。</li>
                  <li style="color: #cf697b;">「分类置顶」支持包年服务，如有需要请联系管理员。</li>
                </ul>
              </div>

              <div v-if="selectedProduct?.currentTopOrder" class="current-top-card">
                <h3>当前状态</h3>
                <p>该物品已存在 {{ selectedProduct.currentTopOrder.packageName }} 订单。</p>
                <p>状态：{{ getOrderStatusText(selectedProduct.currentTopOrder.status) }}</p>
                <p>到期：{{ selectedProduct.currentTopOrder.expiredAt || '永久置顶' }}</p>
                <p v-if="!selectedProduct.currentTopOrder.isPaidService">说明：这是管理员手动设置的非有偿置顶，不占用付费名额。</p>
              </div>
            </aside>
          </div>
        </div>

        <div v-else-if="activeTab === 'board'" class="panel-body">
          <div class="board-panel">
            <div class="board-toolbar">
              <div>
                <h2 class="panel-title">名额看板</h2>
                <p class="panel-subtitle">查看付费全站置顶与付费分类置顶剩余名额，并按分类浏览当前生效中的服务，提前判断什么时候会空出新额度。</p>
              </div>
              <div class="board-actions">
                <div class="board-filter-select">
                  <AppSelect
                    v-model="quotaBoardCategoryId"
                    full-width
                    :options="quotaBoardCategoryOptions"
                    :disabled="quotaBoardLoading || (!quotaBoardLoaded && !quotaBoardCategories.length)"
                    placeholder="选择要查看的分类"
                  />
                </div>
                <button class="ghost-btn" :disabled="quotaBoardLoading" @click="loadQuotaBoard">
                  {{ quotaBoardLoading ? '刷新中...' : '刷新看板' }}
                </button>
              </div>
            </div>

            <div v-if="showQuotaBoardLoading" class="board-loading">
              <div class="board-summary-grid">
                <article v-for="index in 2" :key="`board-summary-loading-${index}`" class="board-summary-card board-summary-card--loading">
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

            <template v-else>
              <div class="board-summary-grid">
                <article class="board-summary-card board-summary-card--global">
                  <span class="board-summary-kicker">全站置顶</span>
                  <strong class="board-summary-value">{{ globalQuota.globalRemaining }} / {{ globalQuota.globalLimit }}</strong>
                  <p class="board-summary-copy">当前剩余付费全站置顶名额。全站置顶会同步展示在所属分类，但不会占用付费分类置顶名额。</p>
                  <div class="board-summary-meta">
                    <span>生效中 {{ globalQuota.globalUsed }} 个</span>
                    <span>{{ formatQuotaReleaseHint(globalQuota.nextGlobalReleaseAt, globalQuota.hasPermanentGlobalTop, globalQuota.globalUsed, 'global') }}</span>
                  </div>
                </article>

                <article class="board-summary-card board-summary-card--focus">
                  <span class="board-summary-kicker">{{ selectedQuotaCategory ? '当前分类' : '当前筛选' }}</span>
                  <strong class="board-summary-value">
                    {{ selectedQuotaCategory ? `${selectedQuotaCategory.categoryRemaining} / ${selectedQuotaCategory.categoryLimit}` : `${filteredQuotaRecords.length} 条` }}
                  </strong>
                  <p class="board-summary-copy">
                    {{ selectedQuotaCategory
                      ? `${selectedQuotaCategory.categoryName} 当前付费分类置顶剩余名额；本分类可见 ${selectedQuotaCategory.visibleTotal} 个置顶项（含管理员非有偿置顶与全站置顶）。`
                      : `当前正在展示全部分类的 ${filteredQuotaRecords.length} 条生效服务，可通过下方分类卡片或右上角筛选器查看具体分类。` }}
                  </p>
                  <div class="board-summary-meta">
                    <template v-if="selectedQuotaCategory">
                      <span>分类付费置顶生效 {{ selectedQuotaCategory.categoryUsed }} 个</span>
                      <span>可见全站 {{ selectedQuotaCategory.globalVisibleCount }} 个</span>
                      <span>{{ formatQuotaReleaseHint(selectedQuotaCategory.nextCategoryReleaseAt, selectedQuotaCategory.hasPermanentCategoryTop, selectedQuotaCategory.categoryUsed, 'category') }}</span>
                    </template>
                    <template v-else>
                      <span>分类总数 {{ quotaBoardCategories.length }} 个</span>
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
                      <span class="category-quota-icon">🗂️</span>
                      全部分类
                    </span>
                    <span class="category-quota-pill">{{ quotaBoard.activeRecords?.length || 0 }} 条</span>
                  </div>
                  <p class="category-quota-copy">查看全部分类下正在展示的置顶服务，快速判断付费名额与管理员非有偿置顶的总体分布。</p>
                  <div class="category-quota-meta">
                    <span>分类总数 {{ quotaBoardCategories.length }} 个</span>
                    <span>全站生效 {{ globalQuota.globalUsed }} 个</span>
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
                      <span class="category-quota-icon">{{ category.categoryIcon || '📦' }}</span>
                      {{ category.categoryName }}
                    </span>
                    <span class="category-quota-pill">{{ category.categoryRemaining }} / {{ category.categoryLimit }}</span>
                  </div>
                  <p class="category-quota-copy">分类付费置顶生效 {{ category.categoryUsed }} 个，可见全站置顶 {{ category.globalVisibleCount }} 个。</p>
                  <div class="category-quota-meta">
                    <span>当前可见 {{ category.visibleTotal }} 个置顶项</span>
                    <span>{{ formatQuotaReleaseHint(category.nextCategoryReleaseAt, category.hasPermanentCategoryTop, category.categoryUsed, 'category') }}</span>
                  </div>
                </button>
              </div>

              <div class="board-list-panel">
                <div class="board-list-head">
                  <div>
                    <h3 class="board-list-title">生效服务</h3>
                    <p class="panel-subtitle">
                      {{ selectedQuotaCategory
                        ? `当前展示 ${selectedQuotaCategory.categoryName} 分类下的全站置顶与分类置顶生效服务。`
                        : '当前展示全部分类下的全站置顶与分类置顶生效服务。' }}
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
                          <span class="active-service-category">
                            {{ record.categoryIcon || '📦' }} {{ record.categoryName || '未分类' }}
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
        </div>

        <div v-else-if="activeTab === 'orders'" class="panel-body">
          <div class="orders-toolbar">
            <AppSelect v-model="orderFilterStatus" :options="orderStatusOptions" placeholder="全部状态" @change="loadOrders(1)" />
            <button class="ghost-btn" :disabled="ordersLoading" @click="loadOrders(1)">
              {{ ordersLoading ? '刷新中...' : '刷新订单' }}
            </button>
          </div>

          <div class="orders-list">
            <article v-for="order in orders" :key="order.id" class="order-card">
              <div class="order-head">
                <div>
                  <h3>{{ order.productName }}</h3>
                  <p>{{ order.orderNo }}</p>
                </div>
                <span class="order-status" :class="order.status">{{ getOrderStatusText(order.status) }}</span>
              </div>

              <div class="order-meta-grid">
                <div>
                  <span>套餐</span>
                  <strong>{{ order.packageName }}</strong>
                </div>
                <div>
                  <span>时长</span>
                  <strong>{{ order.durationDays ? `${order.durationDays} 天` : '永久置顶' }}</strong>
                </div>
                <div>
                  <span>金额</span>
                  <strong>{{ Number(order.amount || 0).toFixed(2) }} LDC</strong>
                </div>
                <div>
                  <span>创建时间</span>
                  <strong>{{ order.createdAt || '-' }}</strong>
                </div>
                <div>
                  <span>生效时间</span>
                  <strong>{{ order.effectiveAt || '待支付成功' }}</strong>
                </div>
                <div>
                  <span>到期时间</span>
                  <strong>{{ order.expiredAt || '永久置顶' }}</strong>
                </div>
              </div>

              <div class="order-actions">
                <button v-if="order.status === 'pending'" class="action-btn primary" @click="repayOrder(order)">
                  继续支付
                </button>
                <button v-if="order.status === 'pending'" class="action-btn" @click="refreshOrder(order)">
                  刷新状态
                </button>
              </div>
            </article>

            <div v-if="!ordersLoading && !orders.length" class="empty-state">
              暂无置顶服务订单
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LiquidTabs from '@/components/common/LiquidTabs.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { api } from '@/utils/api'
import { useToast } from '@/composables/useToast'
import { useDialog } from '@/composables/useDialog'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const dialog = useDialog()

const tabs = [
  { value: 'service', label: '置顶服务', icon: '🏅' },
  { value: 'board', label: '名额看板', icon: '📡' },
  { value: 'orders', label: '我的订单', icon: '📋' }
]

function normalizeMerchantTab(value = '') {
  return tabs.some((tab) => tab.value === value) ? value : 'service'
}

const activeTab = ref(normalizeMerchantTab(route.query.tab))
const optionsLoading = ref(false)
const submitting = ref(false)
const packages = ref([])
const products = ref([])
const orders = ref([])
const ordersLoading = ref(false)
const quotaBoardLoading = ref(false)
const quotaBoardLoaded = ref(false)
const quotaBoard = ref({
  generatedAt: '',
  globalQuota: null,
  categories: [],
  activeRecords: []
})
const selectedProductId = ref('')
const selectedPackageType = ref('')
const selectedDurationDays = ref(0)
const orderFilterStatus = ref('')
const quotaBoardCategoryId = ref('all')

const orderStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待支付' },
  { value: 'active', label: '生效中' },
  { value: 'expired', label: '已过期' },
  { value: 'cancelled', label: '已取消' }
]

function unwrap(result) {
  return result?.success ? result.data : null
}

const selectedProduct = computed(() => products.value.find(item => String(item.id) === String(selectedProductId.value)) || null)

const productOptions = computed(() => products.value.map((item) => ({
  value: String(item.id),
  label: item.name,
  description: item.currentTopOrder
    ? `当前存在${item.currentTopOrder.isPaidService ? '' : '管理员非有偿'} ${item.currentTopOrder.packageName} 订单`
    : `${item.categoryName || '未分类'} · 分类置顶余量 ${item.quota?.categoryRemaining ?? '-'} · 全站置顶余量 ${item.quota?.globalRemaining ?? '-'}`,
  icon: item.categoryIcon || '📦',
  disabled: false
})))
const showPackageLoading = computed(() => optionsLoading.value && packages.value.length === 0)
const showQuotaBoardLoading = computed(() => quotaBoardLoading.value && !quotaBoardLoaded.value)
const quotaBoardCategories = computed(() => Array.isArray(quotaBoard.value.categories) ? quotaBoard.value.categories : [])
const globalQuota = computed(() => quotaBoard.value.globalQuota || {
  globalLimit: 4,
  globalUsed: 0,
  globalRemaining: 4,
  nextGlobalReleaseAt: '',
  hasPermanentGlobalTop: false
})
const quotaBoardCategoryOptions = computed(() => [
  {
    value: 'all',
    label: '全部分类',
    description: `查看全部分类的 ${Array.isArray(quotaBoard.value.activeRecords) ? quotaBoard.value.activeRecords.length : 0} 条生效服务`,
    icon: '🗂️'
  },
  ...quotaBoardCategories.value.map((item) => ({
    value: String(item.categoryId),
    label: item.categoryName || '未分类',
    description: `分类剩余 ${item.categoryRemaining}/${item.categoryLimit} · 可见全站 ${item.globalVisibleCount}`,
    icon: item.categoryIcon || '📦'
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

const selectedConfig = computed(() => {
  const group = packages.value.find(item => item.type === selectedPackageType.value)
  const option = group?.options?.find(item => Number(item.durationDays) === Number(selectedDurationDays.value))
  if (!group || !option) return null
  return {
    groupName: group.name,
    packageType: group.type,
    durationDays: option.durationDays,
    price: option.price
  }
})

const canSubmit = computed(() => {
  if (!selectedProduct.value || !selectedConfig.value) return false
  if (selectedProduct.value.currentTopOrder) return false
  const remaining = selectedConfig.value.packageType === 'global'
    ? selectedProduct.value.quota?.globalRemaining
    : selectedProduct.value.quota?.categoryRemaining
  return Number(remaining || 0) > 0
})

watch(
  () => route.query.tab,
  (value) => {
    activeTab.value = normalizeMerchantTab(value)
  }
)

watch(activeTab, async (value) => {
  router.replace({
    query: {
      ...route.query,
      tab: normalizeMerchantTab(value)
    }
  })
  if (value === 'orders') {
    await loadOrders(1)
  }
  if (value === 'board') {
    await loadQuotaBoard()
  }
})

function handleProductChange() {
  selectedPackageType.value = ''
  selectedDurationDays.value = 0
}

function formatRemaining(type) {
  if (!selectedProduct.value) return '请选择物品'
  const remaining = type === 'global'
    ? selectedProduct.value.quota?.globalRemaining
    : selectedProduct.value.quota?.categoryRemaining
  return String(Number(remaining || 0))
}

function isPackageDisabled(type) {
  if (!selectedProduct.value) return true
  const remaining = type === 'global'
    ? selectedProduct.value.quota?.globalRemaining
    : selectedProduct.value.quota?.categoryRemaining
  return Number(remaining || 0) <= 0
}

function selectPackage(type, durationDays) {
  if (isPackageDisabled(type)) return
  selectedPackageType.value = type
  selectedDurationDays.value = Number(durationDays || 0)
}

function getOrderStatusText(status = '') {
  return {
    pending: '待支付',
    active: '生效中',
    expired: '已过期',
    cancelled: '已取消'
  }[status] || status
}

function formatQuotaReleaseHint(nextReleaseAt = '', hasPermanent = false, used = 0, scope = 'category') {
  if (used <= 0) {
    return scope === 'global' ? '当前全站名额充足' : '当前分类名额充足'
  }
  if (nextReleaseAt) {
    return `最早释放：${nextReleaseAt}`
  }
  if (hasPermanent) {
    return '含永久生效服务'
  }
  return '当前暂无预计释放时间'
}

async function loadOptions() {
  optionsLoading.value = true
  try {
    const result = unwrap(await api.get('/api/shop/top-service/options'))
    packages.value = Array.isArray(result?.packages) ? result.packages : []
    products.value = Array.isArray(result?.products) ? result.products : []
    if (selectedProductId.value && !products.value.some(item => String(item.id) === String(selectedProductId.value))) {
      selectedProductId.value = ''
      selectedPackageType.value = ''
      selectedDurationDays.value = 0
    }
  } catch (error) {
    console.error('Load merchant services options failed:', error)
    toast.error('加载置顶服务信息失败')
  } finally {
    optionsLoading.value = false
  }
}

async function loadOrders(page = 1) {
  ordersLoading.value = true
  try {
    const result = unwrap(await api.get(`/api/shop/top-service/orders?status=${encodeURIComponent(orderFilterStatus.value)}&page=${page}&pageSize=20`))
    orders.value = Array.isArray(result?.orders) ? result.orders : []
  } catch (error) {
    console.error('Load merchant service orders failed:', error)
    toast.error('加载置顶订单失败')
  } finally {
    ordersLoading.value = false
  }
}

async function loadQuotaBoard() {
  quotaBoardLoading.value = true
  try {
    const result = unwrap(await api.get('/api/shop/top-service/board'))
    quotaBoard.value = {
      generatedAt: result?.generatedAt || '',
      globalQuota: result?.globalQuota || null,
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
    console.error('Load top service quota board failed:', error)
    toast.error('加载名额看板失败')
  } finally {
    quotaBoardLoading.value = false
  }
}

async function submitOrder() {
  if (!canSubmit.value || !selectedProduct.value || !selectedConfig.value) return

  const confirmed = await dialog.confirm(
    [
      '<div style="line-height:1.8;text-align:left">',
      `<div><strong>套餐：</strong>${selectedConfig.value.groupName}</div>`,
      `<div><strong>天数：</strong>${selectedConfig.value.durationDays} 天</div>`,
      `<div><strong>物品：</strong>${selectedProduct.value.name}</div>`,
      '<div><strong>生效时间：</strong>订单支付成功时间</div>',
      `<div><strong>金额：</strong>${Number(selectedConfig.value.price || 0).toFixed(2)} LDC</div>`,
      '</div>'
    ].join(''),
    {
      title: '确认服务信息',
      confirmText: '立即支付',
      cancelText: '返回修改'
    }
  )
  if (!confirmed) return

  submitting.value = true
  try {
    const result = unwrap(await api.post('/api/shop/top-service/orders', {
      productId: Number(selectedProduct.value.id),
      packageType: selectedConfig.value.packageType,
      durationDays: Number(selectedConfig.value.durationDays)
    }))
    if (!result?.paymentUrl) {
      toast.error('支付链接生成失败')
      return
    }
    await loadOptions()
    await loadOrders(1)
    window.location.href = result.paymentUrl
  } catch (error) {
    console.error('Create top service order failed:', error)
    toast.error(error?.message || '创建置顶订单失败')
  } finally {
    submitting.value = false
  }
}

async function repayOrder(order) {
  try {
    const result = unwrap(await api.get(`/api/shop/top-service/orders/${encodeURIComponent(order.orderNo)}/payment-url`))
    if (!result?.paymentUrl) {
      toast.error('支付链接不存在')
      return
    }
    window.location.href = result.paymentUrl
  } catch (error) {
    console.error('Repay top order failed:', error)
    toast.error(error?.message || '获取支付链接失败')
  }
}

async function refreshOrder(order) {
  try {
    const result = unwrap(await api.post(`/api/shop/top-service/orders/${encodeURIComponent(order.orderNo)}/refresh`))
    toast.success(result?.message || '订单状态已刷新')
    await loadOptions()
    await loadOrders(1)
  } catch (error) {
    console.error('Refresh top order failed:', error)
    toast.error(error?.message || '刷新订单状态失败')
  }
}

onMounted(async () => {
  const tasks = [loadOptions()]
  if (activeTab.value === 'orders') {
    tasks.push(loadOrders(1))
  }
  if (activeTab.value === 'board') {
    tasks.push(loadQuotaBoard())
  }
  await Promise.all(tasks)
})
</script>

<style scoped>
.merchant-services-page {
  min-height: 100vh;
  padding: 24px 0 72px;
}

.page-shell {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  display: grid;
  gap: 20px;
}

.hero-card,
.content-card {
  border: 1px solid var(--glass-border-light);
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(255, 220, 145, 0.35), transparent 42%),
    linear-gradient(155deg, rgba(255, 255, 255, 0.92), rgba(251, 244, 231, 0.96));
  box-shadow: 0 24px 60px var(--glass-shadow);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.hero-card {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 18px;
  padding: 28px;
}

.hero-eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #9d7b2f;
}

.hero-title {
  margin: 0;
  font-size: clamp(32px, 5vw, 48px);
  line-height: 1.02;
  color: #34240f;
}

.hero-desc {
  margin: 14px 0 0;
  max-width: 640px;
  font-size: 15px;
  line-height: 1.8;
  color: #5d4c2d;
}

.hero-badge {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 22px;
  border-radius: 24px;
  color: #fff7e3;
  background:
    radial-gradient(circle at top, rgba(255, 248, 210, 0.28), transparent 45%),
    linear-gradient(145deg, #b88624, #6f4a14);
}

.hero-badge-label {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.82;
}

.hero-badge strong {
  font-size: 28px;
}

.content-card {
  padding: 22px;
}

.panel-body {
  margin-top: 18px;
}

.service-grid {
  display: grid;
  grid-template-columns: 1.6fr 0.95fr;
  gap: 18px;
  align-items: start;
}

.config-panel,
.summary-panel {
  display: grid;
  gap: 18px;
}

.panel-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-title {
  margin: 0;
  font-size: 22px;
  color: #30210d;
}

.panel-subtitle,
.field-hint {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.field-block {
  display: grid;
  gap: 8px;
}

.field-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.package-grid {
  display: grid;
  gap: 14px;
}

.package-card,
.summary-card,
.notice-card,
.current-top-card,
.order-card,
.board-summary-card,
.category-quota-card,
.active-service-card {
  border: 1px solid var(--glass-border-light);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 14px 36px var(--glass-shadow-light);
}

.package-card {
  padding: 18px;
}

.package-card.disabled {
  opacity: 0.72;
}

.package-card--loading {
  pointer-events: none;
}

.package-loading-copy {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 10px;
}

.package-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.package-title {
  margin: 0;
  font-size: 18px;
  color: #2f2515;
}

.package-desc {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.loading-shimmer {
  background: linear-gradient(90deg, var(--skeleton-base) 25%, var(--bg-tertiary) 50%, var(--skeleton-base) 75%);
  background-size: 200% 100%;
  animation: merchant-services-shimmer 1.5s infinite;
}

.package-skeleton {
  border-radius: 999px;
}

.package-skeleton-title {
  width: 140px;
  height: 18px;
  border-radius: 10px;
}

.package-skeleton-desc {
  width: min(100%, 260px);
  height: 12px;
  border-radius: 8px;
}

.package-skeleton-pill {
  flex-shrink: 0;
  width: 98px;
  height: 30px;
}

.quota-pill {
  flex-shrink: 0;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(203, 153, 33, 0.12);
  color: #9b6c13;
  font-size: 12px;
  font-weight: 700;
}

.duration-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.duration-btn {
  width: 100%;
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  background: rgba(255, 252, 246, 0.9);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  color: var(--text-primary);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.duration-btn--loading {
  cursor: default;
}

.package-skeleton-days {
  width: 54px;
  height: 14px;
}

.package-skeleton-price {
  width: 84px;
  height: 14px;
}

.duration-btn:hover:not(:disabled),
.duration-btn.active {
  transform: translateY(-1px);
  border-color: #c18a19;
  box-shadow: 0 14px 30px rgba(193, 138, 25, 0.16);
}

.duration-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.package-empty-state {
  padding: 20px 18px;
  border: 1px dashed rgba(191, 139, 31, 0.28);
  border-radius: 18px;
  background: rgba(255, 250, 239, 0.72);
  text-align: center;
}

.package-empty-state strong {
  display: block;
  font-size: 14px;
  color: #6f4a14;
}

.package-empty-state p {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.duration-days {
  font-size: 15px;
  font-weight: 700;
}

.duration-price {
  font-size: 13px;
  color: #8b6316;
}

.submit-btn,
.ghost-btn,
.action-btn {
  border-radius: 999px;
  font-weight: 700;
}

.submit-btn {
  border: none;
  padding: 16px 22px;
  color: #fff;
  background: linear-gradient(135deg, #c78d1e, #8a5a15);
  box-shadow: 0 18px 34px rgba(151, 98, 18, 0.24);
}

.submit-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.ghost-btn,
.action-btn {
  border: 1px solid var(--glass-border);
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-primary);
  padding: 11px 16px;
}

.action-btn.primary {
  border-color: transparent;
  background: linear-gradient(135deg, #c78d1e, #8a5a15);
  color: #fff;
}

.summary-card,
.notice-card,
.current-top-card {
  padding: 18px;
}

.summary-card--intro {
  position: relative;
  overflow: hidden;
  border-color: rgba(203, 154, 41, 0.24);
  background:
    radial-gradient(circle at top right, rgba(255, 223, 150, 0.4), transparent 36%),
    linear-gradient(160deg, rgba(255, 251, 242, 0.98), rgba(248, 239, 216, 0.94));
  box-shadow:
    0 18px 42px rgba(145, 105, 24, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.summary-card--intro::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.24), transparent 58%);
  pointer-events: none;
}

.summary-card--intro > * {
  position: relative;
  z-index: 1;
}

.summary-intro {
  display: grid;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(188, 141, 42, 0.18);
}

.summary-kicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(191, 139, 31, 0.12);
  color: #9c6a12;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.summary-intro strong {
  font-size: 18px;
  line-height: 1.5;
  color: #35240f;
}

.summary-intro p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #6d5731;
}

.summary-points {
  display: grid;
  gap: 2px;
  margin-top: 14px;
}

.summary-point {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
  padding: 12px 0;
}

.summary-point + .summary-point {
  border-top: 1px dashed rgba(188, 141, 42, 0.2);
}

.summary-point-index {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: linear-gradient(145deg, #cb9623, #8f5d14);
  color: #fff8e6;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.05em;
  box-shadow: 0 10px 18px rgba(153, 101, 20, 0.22);
}

.summary-point-copy strong {
  display: block;
  font-size: 14px;
  line-height: 1.5;
  color: #2f2414;
}

.summary-point-copy p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: #6d5731;
}

.summary-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid var(--glass-border-light);
}

.summary-line:last-child {
  border-bottom: none;
}

.summary-line span,
.notice-card li,
.current-top-card p {
  font-size: 13px;
  color: var(--text-secondary);
}

.summary-line strong,
.notice-card h3,
.current-top-card h3 {
  color: var(--text-primary);
}

.notice-card ul {
  margin: 12px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
}

.current-top-card p {
  margin: 10px 0 0;
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
  min-width: 280px;
}

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
  border-color: rgba(191, 139, 31, 0.24);
  background:
    radial-gradient(circle at top right, rgba(255, 225, 154, 0.42), transparent 36%),
    linear-gradient(150deg, rgba(255, 252, 244, 0.98), rgba(247, 236, 208, 0.94));
}

.board-summary-card--focus {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.48), transparent 36%),
    linear-gradient(150deg, rgba(255, 255, 255, 0.94), rgba(247, 242, 231, 0.92));
}

.board-summary-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #9b6c13;
}

.board-summary-value {
  font-size: clamp(28px, 4vw, 38px);
  line-height: 1;
  color: #2f2414;
}

.board-summary-copy {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: #6d5731;
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
  background: rgba(191, 139, 31, 0.1);
  font-size: 12px;
  color: #7d5a1f;
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
  border-color: rgba(191, 139, 31, 0.12);
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.42), transparent 42%),
    linear-gradient(155deg, rgba(255, 255, 255, 0.96), rgba(247, 242, 231, 0.92));
  cursor: pointer;
  appearance: none;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.category-quota-card:hover,
.category-quota-card.active {
  transform: translateY(-1px);
  border-color: rgba(193, 138, 25, 0.4);
  box-shadow: 0 18px 34px rgba(193, 138, 25, 0.16);
}

.category-quota-card--all {
  background:
    radial-gradient(circle at top right, rgba(255, 235, 184, 0.38), transparent 42%),
    linear-gradient(155deg, rgba(255, 252, 245, 0.96), rgba(244, 236, 219, 0.92));
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
  color: #2f2414;
}

.category-quota-icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: rgba(191, 139, 31, 0.12);
  flex-shrink: 0;
}

.category-quota-pill {
  flex-shrink: 0;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(191, 139, 31, 0.14);
  font-size: 12px;
  font-weight: 800;
  color: #9b6c13;
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
  color: #30210d;
}

.board-generated-at {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(191, 139, 31, 0.1);
  font-size: 12px;
  color: #7d5a1f;
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
  background: rgba(191, 139, 31, 0.16);
  color: #8f5d14;
}

.active-service-type.type-category {
  background: rgba(89, 119, 64, 0.12);
  color: #52643a;
}

.active-service-source {
  background: rgba(113, 113, 122, 0.12);
  color: #5f6470;
}

.active-service-category {
  background: rgba(98, 113, 81, 0.1);
  color: #5c6650;
}

.active-service-title {
  margin: 0;
  font-size: 18px;
  line-height: 1.5;
  color: #2f2414;
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
  color: #8f5d14;
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

.orders-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.orders-list {
  margin-top: 18px;
  display: grid;
  gap: 14px;
}

.order-card {
  padding: 18px;
}

.order-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.order-head h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.order-head p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.order-status {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.order-status.pending {
  background: rgba(216, 158, 31, 0.12);
  color: #9d6d0e;
}

.order-status.active {
  background: rgba(49, 158, 97, 0.12);
  color: #1f7b4b;
}

.order-status.expired,
.order-status.cancelled {
  background: rgba(107, 114, 128, 0.12);
  color: #596172;
}

.order-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.order-meta-grid span {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
}

.order-meta-grid strong {
  display: block;
  margin-top: 6px;
  font-size: 14px;
  color: var(--text-primary);
}

.order-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.empty-state {
  padding: 48px 12px;
  text-align: center;
  font-size: 14px;
  color: var(--text-secondary);
}

@keyframes merchant-services-shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

@media (max-width: 960px) {
  .hero-card,
  .service-grid {
    grid-template-columns: 1fr;
  }

  .board-toolbar,
  .board-list-head {
    flex-direction: column;
  }

  .board-actions {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .board-filter-select {
    min-width: 0;
    width: 100%;
  }

  .board-summary-grid,
  .active-service-grid {
    grid-template-columns: 1fr 1fr;
  }

  .orders-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .order-meta-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .merchant-services-page {
    padding-top: 16px;
  }

  .page-shell {
    width: min(100% - 20px, 1120px);
  }

  .hero-card,
  .content-card {
    border-radius: 24px;
    padding: 18px;
  }

  .package-head,
  .order-head,
  .panel-title-row {
    flex-direction: column;
  }

  .board-summary-grid,
  .active-service-grid {
    grid-template-columns: 1fr;
  }

  .active-service-head {
    flex-direction: column;
  }

  .active-service-remaining {
    min-width: 0;
    text-align: left;
  }

  .order-meta-grid {
    grid-template-columns: 1fr;
  }

  .order-actions {
    flex-direction: column;
  }

  .summary-point {
    grid-template-columns: 30px minmax(0, 1fr);
    gap: 10px;
  }

  .summary-point-index {
    width: 30px;
    height: 30px;
    border-radius: 10px;
  }
}
</style>
