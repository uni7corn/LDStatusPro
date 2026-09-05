<template>
  <div class="my-shop-page">
    <div class="page-container">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <p>正在读取小店资料…</p>
      </div>

      <div v-else-if="loadError" class="shop-error-state" role="alert">
        <Store :size="24" aria-hidden="true" />
        <h2>小店资料加载失败</h2>
        <p>{{ loadError }}</p>
        <button type="button" class="btn btn-primary" @click="loadMyShop">重新加载</button>
      </div>

      <div v-else-if="myShop" class="my-shop-section">
        <div class="status-banner" :class="statusClass">
          <div class="status-content">
            <SellerStatusBadge :label="statusText" :tone="statusTone" />
            <div v-if="myShop.status === 'rejected' && shopRejectReason" class="reject-reason" role="note">
              <CircleAlert :size="17" aria-hidden="true" />
              <div>
                <strong>审核未通过原因</strong>
                <span>{{ shopRejectReason }}</span>
              </div>
            </div>
          </div>
          <button
            v-if="myShop.status === 'rejected' || myShop.status === 'offline'"
            type="button"
            class="banner-action"
            @click="showEditForm = true"
          >编辑并重新提交</button>
        </div>

        <div class="shop-management-grid">
          <section class="shop-preview-panel" aria-labelledby="shop-preview-title">
            <div class="panel-heading">
              <div><p class="panel-eyebrow">商城展示</p><h2 id="shop-preview-title">小店预览</h2></div>
              <span class="view-count"><Eye :size="15" aria-hidden="true" /> {{ myShop.viewCount || 0 }} 次浏览</span>
            </div>

            <div class="shop-card">
          <div class="shop-image-wrapper" v-if="myShop.imageUrl">
            <img :src="myShop.imageUrl" :alt="myShop.name" class="shop-image" />
          </div>
              <div class="shop-image-placeholder" v-else><Store :size="34" aria-hidden="true" /></div>

          <div class="shop-info">
            <h3 class="shop-name">{{ myShop.name }}</h3>

            <div class="shop-owner">
              <AvatarImage
                :candidates="ownerAvatarCandidates"
                :seed="ownerAvatarSeed"
                :size="48"
                :alt="myShop.ownerUsername"
                class="owner-avatar"
              />
              <span class="owner-name">{{ myShop.ownerUsername }}</span>
            </div>

            <p v-if="myShop.description" class="shop-description">{{ myShop.description }}</p>

            <a
              v-if="myShop.shopUrl"
              :href="myShop.shopUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="shop-url"
            >
              {{ myShop.shopUrl }}
            </a>

            <div class="shop-tags" v-if="parsedTags.length > 0">
              <span
                v-for="tag in parsedTags"
                :key="tag"
                class="shop-tag"
                :class="getTagClass(tag)"
              >
                {{ tag }}
              </span>
            </div>

          </div>
            </div>
          </section>

          <section class="shop-editor-panel" aria-labelledby="shop-editor-title">
            <div class="panel-heading">
              <div>
                <p class="panel-eyebrow">{{ showEditForm ? '资料维护' : '经营资料' }}</p>
                <h2 id="shop-editor-title">{{ showEditForm ? '编辑小店信息' : '当前配置' }}</h2>
              </div>
            </div>

            <div class="edit-section" v-if="showEditForm">
              <ShopForm
                :initial-data="myShop"
                :submitting="submitting"
                @submit="handleUpdate"
                @cancel="showEditForm = false"
              />
            </div>

            <template v-else>
              <dl class="shop-facts">
                <div><dt>审核状态</dt><dd>{{ statusText }}</dd></div>
                <div><dt>展示标签</dt><dd>{{ parsedTags.length ? parsedTags.join('、') : '暂无标签' }}</dd></div>
                <div><dt>访问地址</dt><dd class="truncate-value">{{ myShop.shopUrl || '尚未填写' }}</dd></div>
                <div><dt>累计浏览</dt><dd>{{ myShop.viewCount || 0 }}</dd></div>
              </dl>
              <p class="panel-note">修改资料后将按照现有规则重新进入审核；审核期间请保持访问地址可用。</p>
            </template>

            <div class="action-buttons" v-if="!showEditForm">
              <button class="btn btn-secondary" @click="showEditForm = true">{{ myShop.status === 'offline' ? '编辑并重新提交' : '编辑信息' }}</button>
              <a v-if="myShop.status === 'active'" :href="myShop.shopUrl" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
                访问小店 <ArrowUpRight :size="16" aria-hidden="true" />
              </a>
            </div>

            <div v-if="myShop.status === 'active'" class="danger-zone">
              <div><h3>下架小店</h3><p>下架后不再显示于小店集市，资料会继续保留。</p></div>
              <button type="button" class="btn btn-danger" @click="handleOffline" :disabled="submitting">{{ submitting ? '下架中…' : '下架小店' }}</button>
            </div>
          </section>
        </div>
      </div>

      <div v-else class="shop-application-grid">
        <section class="application-form-panel" aria-labelledby="application-title">
          <div class="panel-heading"><div><p class="panel-eyebrow">免费入驻</p><h2 id="application-title">填写小店资料</h2></div></div>
          <ShopForm :submitting="submitting" @submit="handleSubmit" />
        </section>
        <aside class="intro-card">
          <Store :size="24" aria-hidden="true" />
          <h2>入驻说明</h2>
          <p>小店集市面向社区用户提供友情链接展示，提交后由管理员审核。</p>
          <ol class="intro-list">
            <li><span>01</span>免费提交小店资料</li>
            <li><span>02</span>使用分类标签说明业务</li>
            <li><span>03</span>展示店主社区身份</li>
            <li><span>04</span>查看累计浏览数据</li>
          </ol>
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  createShopRequest,
  fetchMyShopRequest,
  offlineShopRequest,
  updateShopRequest
} from '@/services/shop/shopService'
import AvatarImage from '@/components/common/AvatarImage.vue'
import ShopForm from '@/components/shop/ShopForm.vue'
import SellerStatusBadge from '@/components/seller/SellerStatusBadge.vue'
import { ArrowUpRight, CircleAlert, Eye, Store } from '@lucide/vue'
import { buildAvatarCandidates } from '@/utils/avatar'
import { useToast } from '@/composables/useToast'
import { useDialog } from '@/composables/useDialog'

const toast = useToast()
const dialog = useDialog()

const loading = ref(true)
const submitting = ref(false)
const myShop = ref(null)
const showEditForm = ref(false)
const loadError = ref('')
const shopRejectReason = computed(() => String(myShop.value?.rejectReason || '').trim())

// 解析标签
const parsedTags = computed(() => {
  if (!myShop.value?.tags) return []
  if (Array.isArray(myShop.value.tags)) return myShop.value.tags
  try {
    return JSON.parse(myShop.value.tags)
  } catch {
    return []
  }
})

// 店主头像 URL
const ownerAvatarSeed = computed(() =>
  myShop.value?.ownerUsername || myShop.value?.ownerUserId || myShop.value?.name || 'shop'
)

const ownerAvatarCandidates = computed(() => {
  if (!myShop.value) return []
  return buildAvatarCandidates(myShop.value.ownerAvatarTemplate, 48)
})

// 状态相关计算属性
const statusClass = computed(() => {
  if (!myShop.value) return ''
  const classMap = {
    pending: 'status-pending',
    active: 'status-active',
    rejected: 'status-rejected',
    offline: 'status-offline'
  }
  return classMap[myShop.value.status] || ''
})

const statusText = computed(() => {
  if (!myShop.value) return ''
  const textMap = {
    pending: '审核中，请耐心等待',
    active: '已上架',
    rejected: '审核未通过',
    offline: '已下架'
  }
  return textMap[myShop.value.status] || ''
})

const statusTone = computed(() => ({
  pending: 'warning',
  active: 'success',
  rejected: 'danger',
  offline: 'neutral'
})[myShop.value?.status] || 'neutral')

// 标签样式类
const getTagClass = (tag) => {
  const tagClassMap = {
    '订阅': 'tag-subscription',
    '服务': 'tag-service',
    '小鸡': 'tag-vps',
    'AI': 'tag-ai',
    '娱乐': 'tag-entertainment',
    '公益站': 'tag-charity'
  }
  return tagClassMap[tag] || 'tag-default'
}

// 加载我的小店
async function loadMyShop() {
  loading.value = true
  loadError.value = ''
  try {
    const result = await fetchMyShopRequest()
    if (result.success && result.data) {
      myShop.value = result.data
    } else if (result.success) {
      myShop.value = null
    } else {
      throw new Error(result.error?.message || result.error || '无法读取小店资料')
    }
  } catch (e) {
    console.error('Load my shop failed:', e)
    loadError.value = e?.message || '网络异常，请稍后重试。'
  } finally {
    loading.value = false
  }
}

// 提交入驻申请
async function handleSubmit(formData) {
  submitting.value = true
  try {
    const result = await createShopRequest(formData)
    if (result.success) {
      toast.success('入驻申请已提交，请等待审核！')
      await loadMyShop()
    } else {
      toast.error(result.error?.message || result.error || '提交失败')
    }
  } catch (e) {
    toast.error('提交失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

// 更新小店信息
async function handleUpdate(formData) {
  submitting.value = true
  try {
    const result = await updateShopRequest(formData)
    if (result.success) {
      toast.success(result.message || '更新成功！')
      showEditForm.value = false
      await loadMyShop()
    } else {
      toast.error(result.error?.message || result.error || '更新失败')
    }
  } catch (e) {
    toast.error('更新失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

// 下架小店
async function handleOffline() {
  const confirmed = await dialog.confirmDanger('确定要下架小店吗？下架后将不再显示在小店集市中。', {
    title: '下架小店'
  })
  if (!confirmed) return

  submitting.value = true
  try {
    const result = await offlineShopRequest()
    if (result.success) {
      toast.success('小店已下架')
      await loadMyShop()
    } else {
      toast.error(result.error?.message || result.error || '下架失败')
    }
  } catch (e) {
    toast.error('下架失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadMyShop()
})
</script>

<style scoped>
.my-shop-page {
  min-height: 100vh;
  padding-bottom: 80px;
}

.page-container {
  max-width: 700px;
  margin: 0 auto;
  padding: 16px;
}

/* 返回导航 */
.back-nav {
  margin-bottom: 16px;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  padding: 8px 12px;
  border-radius: 10px;
  transition: color var(--motion-duration-fast) var(--motion-ease-standard), background-color var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard), transform var(--motion-duration-fast) var(--motion-ease-standard);
}

.back-link:hover {
  background: var(--bg-card);
  color: var(--text-primary);
}

.back-icon {
  font-size: 16px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 24px;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 状态横幅 */
.status-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 14px;
  margin-bottom: 20px;
}

.status-banner.status-pending {
  background: var(--color-warning-light);
  color: var(--color-warning);
}

.status-banner.status-active {
  background: var(--color-success-light);
  color: var(--color-success);
}

.status-banner.status-rejected {
  background: var(--color-danger-light);
  color: var(--color-danger);
}

.status-banner.status-offline {
  background: var(--bg-secondary);
  color: var(--text-tertiary);
}

.status-icon {
  font-size: 24px;
}

.status-content {
  flex: 1;
}

.status-text {
  display: block;
  font-weight: 600;
  font-size: 15px;
}

.reject-reason {
  display: block;
  font-size: 13px;
  margin-top: 4px;
  opacity: 0.9;
}

/* 小店卡片 */
.shop-card {
  background: var(--bg-card);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 20px;
  box-shadow: var(--shadow-sm);
}

.shop-image-wrapper {
  width: 100%;
  padding-top: 40%;
  position: relative;
  background: var(--bg-secondary);
}

.shop-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shop-image-placeholder {
  width: 100%;
  padding: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 60px;
  background: var(--bg-tertiary);
}

.shop-info {
  padding: 20px;
}

.shop-name {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px;
}

.shop-owner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.owner-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
}

.owner-name {
  font-size: 14px;
  color: var(--text-secondary);
}

.shop-description {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin: 0 0 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.shop-url {
  display: inline-block;
  font-size: 13px;
  color: var(--color-primary);
  text-decoration: none;
  margin-bottom: 14px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  word-break: break-all;
  transition: opacity 0.2s;
}

.shop-url:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.shop-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.shop-tag {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 12px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.shop-tag.tag-subscription { background: var(--color-success-light); color: var(--color-success); }
.shop-tag.tag-service { background: var(--color-info-light); color: var(--color-info); }
.shop-tag.tag-vps { background: var(--color-warning-light); color: var(--color-warning); }
.shop-tag.tag-ai { background: var(--palette-hex-f3e8ff); color: var(--palette-hex-7c3aed); }
.shop-tag.tag-entertainment { background: var(--palette-hex-ffe4e6); color: var(--palette-hex-be123c); }
.shop-tag.tag-charity { background: var(--palette-hex-fce7f3); color: var(--palette-hex-be185d); }

.shop-stats {
  font-size: 13px;
  color: var(--text-tertiary);
}

.shop-stats .stat {
  margin-right: 16px;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 20px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: color var(--motion-duration-fast) var(--motion-ease-standard), background-color var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard), transform var(--motion-duration-fast) var(--motion-ease-standard);
  border: none;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  color: var(--palette-hex-ffffff);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary);
}

.btn-secondary {
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
}

.btn-danger {
  background: var(--color-danger-light);
  color: var(--color-danger);
}

.btn-danger:hover:not(:disabled) {
  filter: brightness(0.95);
}

/* 入驻介绍 */
.intro-card {
  background: var(--color-success-light);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 24px;
}

.intro-card h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-success);
  margin: 0 0 12px;
}

.intro-card p {
  font-size: 14px;
  color: var(--color-success);
  margin: 0 0 16px;
  opacity: 0.9;
}

.intro-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.intro-list li {
  font-size: 13px;
  color: var(--color-success);
}

/* 区块标题 */
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.edit-section {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 20px;
}

/* Seller ledger layout */
.shop-management-grid,
.shop-application-grid {
  display: grid;
  gap: 18px;
  align-items: start;
}

.shop-preview-panel,
.shop-editor-panel,
.application-form-panel,
.intro-card,
.shop-error-state {
  border: 1px solid var(--seller-border);
  border-radius: 14px;
  background: var(--seller-surface);
  box-shadow: var(--seller-shadow-sm);
}

.shop-preview-panel,
.shop-editor-panel,
.application-form-panel {
  min-width: 0;
  padding: clamp(18px, 2vw, 26px);
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--seller-border);
}

.panel-heading h2 {
  margin: 0;
  color: var(--seller-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", STSong, serif;
  font-size: 19px;
}

.panel-eyebrow {
  margin: 0 0 4px;
  color: var(--seller-jade);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .14em;
}

.view-count {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--seller-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.status-banner {
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 16px;
  border: 1px solid var(--seller-border);
  background: var(--seller-surface-muted) !important;
  color: var(--seller-ink) !important;
}

.status-content {
  display: grid;
  flex: 1;
  min-width: 0;
  justify-items: start;
  gap: 10px;
}

.reject-reason {
  width: 100%;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  overflow: visible;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--seller-danger) 28%, var(--seller-border));
  border-radius: 9px;
  color: var(--seller-danger);
  background: color-mix(in srgb, var(--seller-danger) 7%, var(--seller-surface));
  line-height: 1.55;
  white-space: normal;
  overflow-wrap: anywhere;
}
.reject-reason > svg { margin-top: 2px; }
.reject-reason strong,
.reject-reason span { display: block; }
.reject-reason strong { margin-bottom: 2px; font-size: 12px; }
.reject-reason span { color: var(--seller-ink); font-size: 12px; }

.banner-action {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--seller-border-strong);
  border-radius: 9px;
  background: transparent;
  color: var(--seller-ink);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.shop-card {
  margin: 0;
  border: 1px solid var(--seller-border);
  border-radius: 12px;
  background: var(--seller-surface-strong);
  box-shadow: none;
}

.shop-name { color: var(--seller-ink); }
.shop-description,
.owner-name { color: var(--seller-muted); }
.shop-url { color: var(--seller-jade-strong); }

.shop-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  border-block: 1px solid var(--seller-border);
}

.shop-facts div {
  min-width: 0;
  padding: 15px 0;
}

.shop-facts div:nth-child(odd) { padding-right: 14px; }
.shop-facts div:nth-child(even) { padding-left: 14px; border-left: 1px solid var(--seller-border); }
.shop-facts dt { margin-bottom: 5px; color: var(--seller-muted); font-size: 11px; }
.shop-facts dd { margin: 0; color: var(--seller-ink); font-size: 13px; font-weight: 650; }
.truncate-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.panel-note {
  margin: 18px 0;
  padding: 12px 14px;
  border-left: 3px solid var(--seller-jade);
  background: var(--seller-surface-muted);
  color: var(--seller-muted);
  font-size: 12px;
  line-height: 1.65;
}

.action-buttons { margin-top: 18px; }
.btn { min-height: 44px; border-radius: 10px; }
.btn-primary { background: var(--seller-navy); box-shadow: none; }
.btn-secondary { border-color: var(--seller-border); background: var(--seller-surface); color: var(--seller-ink); }

.edit-section {
  padding: 0;
  margin: 0;
  border-radius: 0;
  background: transparent;
}

.danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid color-mix(in srgb, var(--seller-danger) 32%, var(--seller-border));
}

.danger-zone h3 { margin: 0 0 4px; color: var(--seller-ink); font-size: 14px; }
.danger-zone p { margin: 0; color: var(--seller-muted); font-size: 12px; }
.danger-zone .btn-danger { flex: 0 0 auto; }

.shop-application-grid .intro-card {
  position: sticky;
  top: 94px;
  margin: 0;
  padding: 24px;
  border-top: 4px solid var(--seller-jade);
  background: var(--seller-surface);
}

.intro-card > svg { color: var(--seller-jade); }
.intro-card h2 { margin-top: 14px; color: var(--seller-ink); font-family: "Noto Serif SC", "Source Han Serif SC", serif; }
.intro-card p { color: var(--seller-muted); line-height: 1.65; }
.intro-list { display: grid; grid-template-columns: 1fr; gap: 0; }
.intro-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 0;
  border-top: 1px solid var(--seller-border);
  color: var(--seller-ink);
}
.intro-list li span { color: var(--seller-jade); font-family: ui-monospace, monospace; font-size: 11px; }

.shop-error-state {
  display: grid;
  justify-items: start;
  gap: 10px;
  padding: 28px;
  color: var(--seller-muted);
}
.shop-error-state h2 { margin: 0; color: var(--seller-ink); font-size: 18px; }
.shop-error-state p { margin: 0 0 6px; }

@media (min-width: 980px) {
  .shop-management-grid { grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); }
  .shop-application-grid { grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr); }
}

@media (max-width: 979px) {
  .shop-editor-panel { order: -1; }
}

/* 移动端适配 */
@media (max-width: 640px) {
  .page-container {
    padding: 12px;
  }
  
  .page-title {
    font-size: 20px;
  }
  
  .intro-list {
    grid-template-columns: 1fr;
  }
  
  .action-buttons {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }

  .status-banner,
  .status-content,
  .danger-zone { align-items: stretch; flex-direction: column; }

  .reject-reason { white-space: normal; }

  .shop-facts { grid-template-columns: 1fr; }
  .shop-facts div:nth-child(odd),
  .shop-facts div:nth-child(even) { padding-inline: 0; border-left: 0; }
  .shop-facts div + div { border-top: 1px solid var(--seller-border); }

  .shop-application-grid .intro-card { position: static; order: 2; }
}
</style>
