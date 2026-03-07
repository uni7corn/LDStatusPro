<template>
  <div class="merchant-services-page">
    <div class="page-shell">
      <section class="hero-card">
        <div class="hero-copy">
          <p class="hero-eyebrow">Merchant Services</p>
          <h1 class="hero-title">商家服务</h1>
          <p class="hero-desc">
            士多甄选服务支持自助购买全站置顶与分类置顶。支付成功后立即生效，到期自动释放位置，并同步发送系统提醒。
          </p>
        </div>
        <div class="hero-badge">
          <span class="hero-badge-label">当前开放</span>
          <strong>士多甄选</strong>
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
                  <p class="panel-subtitle">先选商品，再选套餐与天数。每个子分类最多 4 个置顶，“全部”分类最多 4 个全站置顶。</p>
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
                  placeholder="请选择自己已上架的物品"
                  @change="handleProductChange"
                />
                <p class="field-hint">只展示你自己发布且当前处于已上架状态的物品。</p>
              </div>

              <div class="package-grid">
                <article
                  v-for="group in packages"
                  :key="group.type"
                  class="package-card"
                  :class="{ disabled: isPackageDisabled(group.type) }"
                >
                  <div class="package-head">
                    <div>
                      <h3 class="package-title">{{ group.name }}</h3>
                      <p class="package-desc">{{ group.type === 'global' ? '所属分类置顶，并同步进入“全部”分类置顶位' : '仅在所属分类顶部展示' }}</p>
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
              </div>

              <button class="submit-btn" :disabled="!canSubmit || submitting" @click="submitOrder">
                {{ submitting ? '创建订单中...' : '确认提交' }}
              </button>
            </div>

            <aside class="summary-panel">
              <h2 class="panel-title">服务说明</h2>
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
                  <li>为保证服务质量，每种套餐置顶额度有限</li>
                  <li>订单支付成功时间即为置顶服务生效时间。</li>
                  <li>同一物品同一时间只能有一条生效中或待支付的置顶服务。</li>
                  <li>置顶到期时会自动失效，并通过系统消息提醒你。</li>
                  <li style="color: #cf697b;">「分类置顶」支持包年服务，如有需要请联系管理员。</li>
                </ul>
              </div>

              <div v-if="selectedProduct?.currentTopOrder" class="current-top-card">
                <h3>当前状态</h3>
                <p>该物品已存在 {{ selectedProduct.currentTopOrder.packageName }} 订单。</p>
                <p>状态：{{ getOrderStatusText(selectedProduct.currentTopOrder.status) }}</p>
                <p>到期：{{ selectedProduct.currentTopOrder.expiredAt || '永久置顶' }}</p>
              </div>
            </aside>
          </div>
        </div>

        <div v-else class="panel-body">
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
  { value: 'orders', label: '我的订单', icon: '📋' }
]

const activeTab = ref(route.query.tab === 'orders' ? 'orders' : 'service')
const optionsLoading = ref(false)
const submitting = ref(false)
const packages = ref([])
const products = ref([])
const orders = ref([])
const ordersLoading = ref(false)
const selectedProductId = ref('')
const selectedPackageType = ref('')
const selectedDurationDays = ref(0)
const orderFilterStatus = ref('')

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
    ? `当前存在 ${item.currentTopOrder.packageName} 订单`
    : `${item.categoryName || '未分类'} · 分类余量 ${item.quota?.categoryRemaining ?? '-'} · 全站余量 ${item.quota?.globalRemaining ?? '-'}`,
  icon: item.categoryIcon || '📦',
  disabled: false
})))

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
    activeTab.value = value === 'orders' ? 'orders' : 'service'
  }
)

watch(activeTab, (value) => {
  router.replace({
    query: {
      ...route.query,
      tab: value === 'orders' ? 'orders' : 'service'
    }
  })
  if (value === 'orders') {
    loadOrders(1)
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
  await loadOptions()
  if (activeTab.value === 'orders') {
    await loadOrders(1)
  }
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
.order-card {
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

@media (max-width: 960px) {
  .hero-card,
  .service-grid {
    grid-template-columns: 1fr;
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

  .order-meta-grid {
    grid-template-columns: 1fr;
  }

  .order-actions {
    flex-direction: column;
  }
}
</style>
