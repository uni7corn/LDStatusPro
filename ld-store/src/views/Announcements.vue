<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Megaphone, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, CalendarDays, Check, CircleCheck, Clock3, Copy, Search, SearchX, RotateCcw, X } from '@lucide/vue'
import { fetchAnnouncementCenter, fetchAnnouncementDetail, acknowledgeAnnouncement } from '@/services/announcementService'
import AnnouncementContent from '@/components/common/AnnouncementContent.vue'
import { announcementIdentity } from '@/utils/announcementPreferences'
import { announcementImpression as vAnnouncementImpression, trackAnnouncement } from '@/utils/announcementTelemetry'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const items = ref([])
const item = ref(null)
const pages = ref(1)
const total = ref(0)
const search = ref('')
const loading = ref(false)
const error = ref('')
const feedback = ref('')
const acknowledging = ref(false)
const acknowledged = ref(false)
const detail = computed(() => Boolean(route.params.id))
const filters = [ { value: '', label: '全部公告' }, { value: 'active', label: '当前公告' }, { value: 'expired', label: '历史公告' } ]
const status = computed(() => ['active', 'expired'].includes(route.query.status) ? route.query.status : '')
const page = computed(() => Math.max(1, Math.min(100000, Number.parseInt(String(route.query.page), 10) || 1)))
const keyword = computed(() => typeof route.query.q === 'string' ? route.query.q.slice(0, 200) : '')
const hasFilters = computed(() => Boolean(keyword.value || status.value || page.value > 1))
const centerLink = computed(() => ({ path: '/announcements', query: route.query }))
let controller = null
let sequence = 0

function date(value, options = {}) {
  if (!value) return ''
  return new Date(value).toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: 'long', day: 'numeric', ...options })
}
const publishedAt = entry => entry.publishedAt || entry.createdAt
const isoDate = value => value ? new Date(value).toISOString() : undefined
const dateStamp = entry => date(publishedAt(entry), { year: undefined, month: '2-digit', day: '2-digit' }).replace('/', '.')
const dateYear = entry => date(publishedAt(entry), { year: 'numeric', month: undefined, day: undefined })

async function load() {
  const ticket = ++sequence
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  feedback.value = ''
  acknowledging.value = false
  acknowledged.value = false
  try {
    const result = detail.value
      ? await fetchAnnouncementDetail(String(route.params.id), controller.signal)
      : await fetchAnnouncementCenter({ page: page.value, search: keyword.value, status: status.value }, controller.signal)
    if (ticket !== sequence) return
    if (!result.success) throw new Error(typeof result.error === 'string' ? result.error : '公告加载失败')
    if (detail.value) {
      item.value = result.data.item
      acknowledged.value = Boolean(item.value.acknowledged)
    } else {
      items.value = result.data.items
      pages.value = result.data.pagination.totalPages || 1
      total.value = result.data.pagination.total
    }
  } catch (err) {
    if (ticket === sequence) error.value = err.message || '公告加载失败，请稍后重试'
  } finally {
    if (ticket === sequence) loading.value = false
  }
}

function query(next = {}) {
  const updated = { ...route.query, q: search.value.trim() || undefined, status: status.value || undefined, page: undefined, ...next }
  if (router.resolve({ path: '/announcements', query: updated }).fullPath === route.fullPath) void load()
  else void router.push({ path: '/announcements', query: updated })
}
function resetFilters() {
  search.value = ''
  query({ q: undefined, status: undefined })
}
async function copyLink() {
  const ticket = sequence
  try {
    await navigator.clipboard.writeText(`${window.location.origin}${route.path}`)
    if (ticket === sequence) feedback.value = '公告链接已复制'
  } catch {
    if (ticket === sequence) feedback.value = '复制失败，可以复制浏览器地址'
  }
}
async function acknowledge() {
  const ticket = sequence
  const current = item.value
  acknowledging.value = true
  try {
    const result = await acknowledgeAnnouncement(current.id, current.contentVersion)
    if (ticket !== sequence) return
    if (result.success) {
      acknowledged.value = true
      feedback.value = '已记录本版本的知悉确认'
    } else feedback.value = result.error || '确认失败，请重试'
  } catch {
    if (ticket === sequence) feedback.value = '确认失败，请重试'
  } finally {
    if (ticket === sequence) acknowledging.value = false
  }
}

watch([() => route.fullPath, () => announcementIdentity(userStore)], () => {
  search.value = keyword.value
  items.value = []
  item.value = null
  void load()
}, { immediate: true })
onUnmounted(() => { sequence++; controller?.abort() })
</script>

<template>
  <main class="announcements-page" :class="{ 'is-detail': detail }">
    <nav class="announcement-navigation" aria-label="公告导航">
      <router-link :to="detail ? centerLink : '/'" class="announcement-back">
        <ArrowLeft :size="17" aria-hidden="true" />{{ detail ? '返回公告中心' : '返回物品广场' }}
      </router-link>
      <span class="announcement-navigation-label">LD 士多 <span aria-hidden="true">/</span> {{ detail ? '公告详情' : '公告中心' }}</span>
    </nav>

    <template v-if="!detail">
      <header class="announcement-heading">
        <div class="announcement-heading-copy">
          <p class="announcement-eyebrow"><Megaphone :size="17" aria-hidden="true" />LD 士多 · 站内公告</p>
          <h1>士多的近况，都在这里。</h1>
          <p class="announcement-intro">平台动态、服务调整与规则更新，随时回来查阅。</p>
        </div>
        <router-link to="/docs" class="announcement-help">
          <BookOpen :size="22" :stroke-width="1.5" aria-hidden="true" />
          <span><strong>想了解如何使用士多？</strong><small>前往帮助中心</small></span>
          <ArrowUpRight :size="18" aria-hidden="true" />
        </router-link>
      </header>

      <section class="announcement-board" aria-label="公告中心">
        <div class="announcement-toolbar">
          <div class="announcement-filters" role="group" aria-label="公告范围">
            <button v-for="filter in filters" :key="filter.value" type="button" :aria-pressed="status === filter.value" @click="query({ status: filter.value || undefined })">
              {{ filter.label }}
            </button>
          </div>
          <form class="announcement-search" role="search" @submit.prevent="query()">
            <label class="sr-only" for="announcement-search">搜索公告标题或正文</label>
            <Search :size="18" aria-hidden="true" />
            <input id="announcement-search" v-model="search" type="search" maxlength="200" placeholder="搜索标题或正文" autocomplete="off">
            <button type="submit" aria-label="搜索公告"><ArrowRight :size="18" aria-hidden="true" /></button>
          </form>
        </div>
        <div class="announcement-results-caption" role="status">
          <span>{{ loading ? '正在查找公告…' : error ? '公告加载失败' : `共 ${total} 条公告` }}<span v-if="keyword"> · “{{ keyword }}”</span></span>
          <button v-if="hasFilters" type="button" class="announcement-reset" @click="resetFilters"><X :size="14" aria-hidden="true" />清除筛选</button>
          <span v-else class="announcement-timezone">日期均为北京时间</span>
        </div>

        <div v-if="error" class="announcement-state" role="alert">
          <RotateCcw :size="28" :stroke-width="1.5" aria-hidden="true" />
          <h2>公告暂时未能加载</h2><p>{{ error }}</p>
          <button type="button" class="announcement-button secondary" @click="load">重新加载</button>
        </div>
        <div v-else-if="loading" class="announcement-skeleton" aria-hidden="true">
          <div v-for="line in 3" :key="line" class="announcement-skeleton-row"><span></span><div><i></i><i></i><i></i></div></div>
        </div>
        <div v-else-if="!items.length" class="announcement-state">
          <SearchX v-if="hasFilters" :size="32" :stroke-width="1.5" aria-hidden="true" />
          <Megaphone v-else :size="32" :stroke-width="1.5" aria-hidden="true" />
          <h2>{{ hasFilters ? '没有找到相关公告' : '暂时没有公告' }}</h2>
          <p>{{ hasFilters ? '换个关键词，或查看全部公告。' : '有新的平台动态时，会在这里与你分享。' }}</p>
          <button v-if="hasFilters" type="button" class="announcement-button secondary" @click="resetFilters">查看全部公告</button>
        </div>
        <ul v-else class="announcement-list">
          <li v-for="entry in items" :key="entry.id">
            <router-link :to="{ path: `/announcements/${entry.id}`, query: route.query }" v-announcement-impression="{ item: entry, placement: 'center' }" class="announcement-list-item">
              <div class="announcement-date-stamp" aria-hidden="true"><strong>{{ dateStamp(entry) }}</strong><span>{{ dateYear(entry) }}</span></div>
              <div class="announcement-list-copy">
                <div class="announcement-list-meta">
                  <span class="announcement-status" :class="{ expired: entry.status === 'expired' }"><span aria-hidden="true"></span>{{ entry.status === 'expired' ? '历史公告' : '当前公告' }}</span>
                  <time class="announcement-list-date" :datetime="isoDate(publishedAt(entry))">{{ date(publishedAt(entry)) }}</time>
                </div>
                <h2>{{ entry.title || '站内公告' }}</h2>
                <p v-if="entry.summary">{{ entry.summary }}</p>
                <span class="announcement-read">阅读全文<ArrowRight :size="15" aria-hidden="true" /></span>
              </div>
              <span class="announcement-row-arrow" aria-hidden="true"><ArrowUpRight :size="22" :stroke-width="1.5" /></span>
            </router-link>
          </li>
        </ul>
        <nav v-if="!loading && !error && total" class="announcement-pagination" aria-label="公告分页">
          <button type="button" class="announcement-button secondary" :disabled="page <= 1" @click="query({ q: keyword || undefined, page: String(page - 1) })"><ArrowLeft :size="16" aria-hidden="true" /><span>上一页</span></button>
          <span>第 <strong>{{ page }}</strong> / {{ pages }} 页</span>
          <button type="button" class="announcement-button secondary" :disabled="page >= pages" @click="query({ q: keyword || undefined, page: String(page + 1) })"><span>下一页</span><ArrowRight :size="16" aria-hidden="true" /></button>
        </nav>
      </section>
      <p class="announcement-footnote"><Clock3 :size="15" aria-hidden="true" />已结束的公告仍可在「历史公告」中查阅。</p>
    </template>

    <template v-else>
      <div v-if="loading" class="announcement-state announcement-document" role="status"><BookOpen :size="30" :stroke-width="1.5" aria-hidden="true" /><p>正在打开公告…</p></div>
      <div v-else-if="error" class="announcement-state announcement-document" role="alert"><RotateCcw :size="28" :stroke-width="1.5" aria-hidden="true" /><h1>暂时无法打开这条公告</h1><p>{{ error }}</p><button type="button" class="announcement-button secondary" @click="load">重新加载</button></div>
      <article v-else-if="item" class="announcement-document">
        <header v-announcement-impression="{ item, event: 'open', placement: 'detail' }" class="announcement-document-header">
          <div class="announcement-document-kicker"><span class="announcement-eyebrow"><Megaphone :size="17" aria-hidden="true" />LD 士多 · 站内公告</span><span class="announcement-status" :class="{ expired: item.status === 'expired' }"><span aria-hidden="true"></span>{{ item.status === 'expired' ? '历史公告' : '当前公告' }}</span></div>
          <h1>{{ item.title || '站内公告' }}</h1>
          <p v-if="item.summary" class="announcement-document-summary">{{ item.summary }}</p>
          <div class="announcement-meta"><span><CalendarDays :size="15" aria-hidden="true" /><time :datetime="isoDate(publishedAt(item))">{{ date(publishedAt(item)) }}</time>发布</span><span v-if="item.contentVersion">版本 {{ item.contentVersion }}</span><span>北京时间</span></div>
        </header>
        <div v-if="item.status === 'expired'" class="announcement-expired-note"><Clock3 :size="19" aria-hidden="true" /><p>这条公告已结束，内容保留供查阅。最新安排请以当前公告为准。</p></div>
        <AnnouncementContent class="announcement-document-body" :content="item.content" :content-type="item.contentType" />
        <footer class="announcement-document-footer">
          <div class="announcement-document-actions">
            <a v-if="item.actionUrl" class="announcement-button" :href="item.actionUrl" :target="item.actionUrl.startsWith('/') ? undefined : '_blank'" rel="noopener noreferrer" @click="trackAnnouncement(item, 'action', 'detail')">{{ item.actionLabel }}<ArrowUpRight :size="17" aria-hidden="true" /></a>
            <button type="button" class="announcement-button secondary" @click="copyLink"><Copy :size="16" aria-hidden="true" />复制公告链接</button>
          </div>
          <div v-if="item.requiresAcknowledgement" class="announcement-acknowledgement">
            <CircleCheck :size="22" :stroke-width="1.5" aria-hidden="true" />
            <div><h2>{{ acknowledged ? '你已知悉这版公告' : '读完了，留个确认' }}</h2><p>{{ acknowledged ? '本次确认已保存到你的账号。' : '确认仅记录你已知悉当前版本的内容。' }}</p></div>
            <button v-if="userStore.isLoggedIn" type="button" class="announcement-button secondary" :disabled="acknowledging || acknowledged" @click="acknowledge"><Check v-if="acknowledged" :size="16" aria-hidden="true" />{{ acknowledged ? '已知悉' : acknowledging ? '正在记录…' : '我已阅读并知悉' }}</button>
            <router-link v-else to="/login" class="announcement-button secondary">登录后确认<ArrowRight :size="16" aria-hidden="true" /></router-link>
          </div>
          <p v-if="feedback" class="announcement-feedback" role="status">{{ feedback }}</p>
        </footer>
      </article>
      <div class="announcement-reading-footer"><router-link :to="centerLink" class="announcement-back"><ArrowLeft :size="16" aria-hidden="true" />查看其他公告</router-link><router-link to="/docs" class="announcement-back"><BookOpen :size="16" aria-hidden="true" />帮助中心</router-link></div>
    </template>
  </main>
</template>

<style scoped>
.announcements-page {
  width: min(calc(100% - 64px), 1120px);
  margin: 0 auto;
  padding: var(--space-6) 0 120px;
  color: var(--text-primary-semantic);
  font-family: var(--font-sans);
}
.announcements-page.is-detail { max-width: 940px; }
.announcements-page :focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 4px; }
.announcements-page button, .announcements-page input { font: inherit; }
.announcements-page button { cursor: pointer; }
.announcements-page svg { flex-shrink: 0; }
.announcement-navigation, .announcement-back { display: flex; align-items: center; gap: var(--space-2); }
.announcement-navigation { justify-content: space-between; margin-bottom: var(--space-5); }
.announcement-back { width: fit-content; min-height: 44px; color: var(--text-link); text-decoration: none; font-size: var(--text-size-sm); }
.announcement-back:hover { text-decoration: underline; text-underline-offset: 4px; }
.announcement-navigation-label { display: flex; gap: var(--space-3); font-size: var(--text-size-xs); color: var(--text-muted-semantic); }
.announcement-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-8); padding: var(--space-5) 0 40px; }
.announcement-eyebrow { display: inline-flex; align-items: center; gap: var(--space-2); color: var(--action-primary); font-size: var(--text-size-xs); font-weight: 600; letter-spacing: .06em; margin: 0; }
.announcement-heading h1 { margin: var(--space-4) 0 var(--space-3); font-family: var(--font-serif); font-size: clamp(27px, 3.2vw, 38px); font-weight: 600; letter-spacing: .02em; line-height: 1.45; text-wrap: balance; }
.announcement-intro { margin: 0; color: var(--text-secondary-semantic); line-height: 1.8; font-size: var(--text-size-sm); }
.announcement-help { display: flex; flex-shrink: 0; align-items: center; gap: var(--space-3); max-width: 290px; padding: var(--space-5); border-left: 1px solid var(--border-default-semantic); color: var(--text-link); text-decoration: none; }
.announcement-help strong { display: block; font-weight: 500; font-size: var(--text-size-sm); }
.announcement-help small { display: block; margin-top: var(--space-1); color: var(--text-muted-semantic); font-size: var(--text-size-xs); }
.announcement-help:hover small { color: var(--text-link); text-decoration: underline; text-underline-offset: 4px; }
.announcement-board, .announcement-document { background: var(--surface-paper-card); border: 1px solid var(--border-default-semantic); border-radius: var(--radius-lg); box-shadow: var(--elevation-paper-sm); }
.announcement-toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-6); padding: var(--space-6) var(--space-8); border-bottom: 1px solid var(--border-default-semantic); }
.announcement-filters { display: flex; gap: var(--space-1); padding: var(--space-1); background: var(--surface-subtle); border-radius: var(--radius-md); }
.announcement-filters button { min-height: 44px; padding: var(--space-2) var(--space-4); border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary-semantic); white-space: nowrap; font-size: var(--text-size-sm); transition: background .18s ease, color .18s ease; }
.announcement-filters button[aria-pressed="true"] { background: var(--surface-paper-strong); color: var(--text-primary-semantic); border-color: var(--border-default-semantic); box-shadow: var(--elevation-sm); font-weight: 600; }
.announcement-filters button:hover:not([aria-pressed="true"]) { color: var(--text-primary-semantic); background: var(--action-secondary-hover); }
.announcement-search { display: flex; align-items: center; gap: var(--space-2); width: min(100%, 320px); min-width: 180px; padding-left: var(--space-3); border: 1px solid var(--border-default-semantic); border-radius: var(--radius-sm); background: var(--surface-card); color: var(--text-muted-semantic); }
.announcement-search:focus-within { border-color: var(--border-interactive); }
.announcement-search input { width: 100%; min-width: 0; min-height: 44px; padding: 0; border: 0; border-radius: var(--radius-xs); color: var(--text-primary-semantic); background: transparent; font-size: var(--text-size-sm); }
.announcement-search input::placeholder { color: var(--text-muted-semantic); }
.announcement-search button { display: grid; place-items: center; min-width: 44px; min-height: 44px; background: transparent; color: var(--text-link); border: 0; border-radius: var(--radius-sm); }
.announcement-search button:hover { background: var(--surface-subtle); }
.announcement-results-caption { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); min-height: 56px; padding: var(--space-2) var(--space-8); color: var(--text-muted-semantic); font-size: var(--text-size-xs); overflow-wrap: anywhere; }
.announcement-reset { display: inline-flex; align-items: center; gap: var(--space-1); flex-shrink: 0; min-height: 44px; border: 0; padding: 0; background: transparent; color: var(--text-link); }
.announcement-list { list-style: none; padding: 0 var(--space-8); margin: 0; }
.announcement-list li + li { border-top: 1px solid var(--border-default-semantic); }
.announcement-list-item { position: relative; display: flex; align-items: flex-start; gap: var(--space-8); padding: var(--space-8) 0; color: inherit; text-decoration: none; }
.announcement-date-stamp { display: flex; flex-direction: column; gap: var(--space-1); flex-shrink: 0; width: 84px; padding-top: var(--space-1); font-variant-numeric: tabular-nums; color: var(--text-muted-semantic); }
.announcement-date-stamp strong { font-size: 27px; font-weight: 400; line-height: 1.2; color: var(--action-primary); letter-spacing: -.02em; }
.announcement-date-stamp span { font-size: var(--text-size-xs); }
.announcement-list-copy { min-width: 0; flex: 1; }
.announcement-list-meta { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.announcement-status { display: inline-flex; align-items: center; gap: 6px; padding: var(--space-1) var(--space-2); border-radius: var(--radius-xs); background: var(--action-paper-accent-soft); color: var(--action-document-accent-strong); font-size: var(--text-size-xs); white-space: nowrap; }
.announcement-status > span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.announcement-status.expired { background: var(--surface-subtle); color: var(--text-muted-semantic); }
.announcement-list-date { font-size: var(--text-size-xs); color: var(--text-muted-semantic); }
.announcement-list-copy h2 { margin: var(--space-3) 0 var(--space-2); font-family: var(--font-serif); font-size: 23px; font-weight: 600; line-height: 1.55; overflow-wrap: anywhere; }
.announcement-list-copy > p { margin: 0; color: var(--text-secondary-semantic); font-size: var(--text-size-sm); line-height: 1.85; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.announcement-read { display: inline-flex; align-items: center; gap: var(--space-2); margin-top: var(--space-4); color: var(--text-link); font-size: var(--text-size-xs); }
.announcement-row-arrow { display: grid; place-items: center; width: 40px; height: 40px; flex-shrink: 0; margin-top: var(--space-8); color: var(--text-link); border: 1px solid var(--border-default-semantic); border-radius: 50%; transition: background .18s ease, transform .18s ease; }
.announcement-list-item:hover h2 { color: var(--action-primary); }
.announcement-list-item:hover .announcement-row-arrow { transform: translate(2px, -2px); background: var(--surface-subtle); }
.announcement-list-item:hover .announcement-read { text-decoration: underline; text-underline-offset: 4px; }
.announcement-pagination { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-6) var(--space-8); border-top: 1px solid var(--border-default-semantic); color: var(--text-muted-semantic); font-size: var(--text-size-xs); }
.announcement-pagination strong { color: var(--text-primary-semantic); font-weight: 600; }
.announcement-button { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); min-height: 44px; padding: 10px var(--space-4); border: 1px solid transparent; border-radius: var(--radius-sm); background: var(--action-primary); color: var(--action-primary-text); font-size: var(--text-size-sm) !important; line-height: 1.5; text-decoration: none; transition: background .18s ease; }
.announcement-button:hover { background: var(--action-primary-hover); }
.announcement-button.secondary { background: transparent; color: var(--text-link); border-color: var(--border-default-semantic); }
.announcement-button.secondary:hover { background: var(--action-secondary-hover); }
.announcement-button:disabled { opacity: .45; cursor: default; }
.announcement-button:disabled:hover { background: transparent; }
.announcement-footnote { display: flex; align-items: center; justify-content: center; gap: var(--space-2); margin: var(--space-6) 0 0; color: var(--text-muted-semantic); font-size: var(--text-size-xs); line-height: 1.7; }
.announcement-state { display: flex; align-items: center; flex-direction: column; padding: 64px var(--space-6); text-align: center; color: var(--text-secondary-semantic); }
.announcement-state > svg { color: var(--action-primary); margin-bottom: var(--space-4); }
.announcement-state h1, .announcement-state h2 { font-family: var(--font-serif); color: var(--text-primary-semantic); font-size: 22px; font-weight: 600; line-height: 1.5; margin: 0 0 var(--space-2); }
.announcement-state p { margin: 0 0 var(--space-5); max-width: 100%; overflow-wrap: anywhere; font-size: var(--text-size-sm); line-height: 1.8; }
.announcement-skeleton { padding: 0 var(--space-8); }
.announcement-skeleton-row { display: flex; gap: var(--space-8); padding: var(--space-8) 0; }
.announcement-skeleton-row > span, .announcement-skeleton-row i { display: block; background: var(--surface-subtle); border-radius: var(--radius-xs); }
.announcement-skeleton-row > span { width: 84px; height: 60px; }
.announcement-skeleton-row > div { flex: 1; }
.announcement-skeleton-row i { width: 90%; height: 18px; margin-bottom: var(--space-4); }
.announcement-skeleton-row i:first-child { width: 72px; height: 22px; }
.announcement-skeleton-row i:last-child { width: 65%; }
.announcement-document { position: relative; padding: 44px clamp(24px, 6vw, 88px) var(--space-8); border-top: 3px solid var(--border-strong-semantic); }
.announcement-document-header { margin-bottom: var(--space-8); padding-bottom: var(--space-8); border-bottom: 1px solid var(--border-default-semantic); }
.announcement-document-kicker { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.announcement-document-header h1 { margin: var(--space-6) 0 var(--space-4); font-family: var(--font-serif); font-size: clamp(26px, 3.3vw, 36px); font-weight: 600; line-height: 1.55; letter-spacing: .015em; overflow-wrap: anywhere; text-wrap: pretty; }
.announcement-document-summary { margin: 0 0 var(--space-5); font-size: var(--text-size-md); line-height: 1.9; color: var(--text-secondary-semantic); overflow-wrap: anywhere; }
.announcement-meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-4); color: var(--text-muted-semantic); font-size: var(--text-size-xs); }
.announcement-meta > span { display: inline-flex; align-items: center; gap: 6px; }
.announcement-expired-note { display: flex; align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-8); padding: var(--space-4); border-radius: var(--radius-sm); background: var(--surface-subtle); color: var(--text-secondary-semantic); }
.announcement-expired-note svg { margin-top: 3px; }
.announcement-expired-note p { margin: 0; font-size: var(--text-size-sm); line-height: 1.8; }
.announcement-document-body { font-size: var(--text-size-md); line-height: 1.95; }
.announcement-document-body :deep(h1), .announcement-document-body :deep(h2), .announcement-document-body :deep(h3) { font-family: var(--font-serif); margin-top: var(--space-8); }
.announcement-document-body :deep(> :first-child) { margin-top: 0; }
.announcement-document-body :deep(p), .announcement-document-body :deep(ul), .announcement-document-body :deep(ol) { margin-bottom: var(--space-5); }
.announcement-document-body :deep(li + li) { margin-top: var(--space-2); }
.announcement-document-body :deep(blockquote) { padding: var(--space-4) var(--space-5); background: var(--surface-subtle); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.announcement-document-body :deep(blockquote > :last-child) { margin-bottom: 0; }
.announcement-document-body :deep(table) { font-size: var(--text-size-sm); line-height: 1.8; }
.announcement-document-body :deep(th) { background: var(--surface-subtle); font-weight: 600; text-align: left; }
.announcement-document-body :deep(th), .announcement-document-body :deep(td) { padding: var(--space-3) var(--space-4); min-width: 100px; vertical-align: top; }
.announcement-document-footer { margin-top: 40px; padding-top: var(--space-6); border-top: 1px solid var(--border-default-semantic); }
.announcement-document-actions { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.announcement-acknowledgement { display: flex; align-items: center; gap: var(--space-3); margin-top: var(--space-6); padding: var(--space-5); border-radius: var(--radius-md); background: var(--surface-subtle); }
.announcement-acknowledgement > svg { color: var(--action-primary); }
.announcement-acknowledgement > div { flex: 1; }
.announcement-acknowledgement h2 { font-size: var(--text-size-sm); font-weight: 600; margin: 0 0 var(--space-1); }
.announcement-acknowledgement p { font-size: var(--text-size-xs); color: var(--text-secondary-semantic); line-height: 1.7; margin: 0; }
.announcement-acknowledgement .announcement-button { flex-shrink: 0; }
.announcement-feedback { margin: var(--space-4) 0 0; color: var(--text-link); font-size: var(--text-size-sm); }
.announcement-reading-footer { display: flex; justify-content: space-between; gap: var(--space-4); margin-top: var(--space-4); }
@media (min-width: 601px) {
  .announcement-list-date { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
}
@media (max-width: 900px) {
  .announcement-help { display: none; }
  .announcement-toolbar { flex-wrap: wrap; gap: var(--space-4); }
  .announcement-search { flex: 1; }
  .announcement-date-stamp { width: 68px; }
  .announcement-list-item { gap: var(--space-6); }
  .announcement-acknowledgement { flex-wrap: wrap; }
}
@media (max-width: 600px) {
  .announcements-page { width: calc(100% - 32px); padding-top: var(--space-3); }
  .announcement-navigation { margin-bottom: var(--space-3); }
  .announcement-navigation-label { font-size: 11px; gap: 6px; }
  .announcement-heading { padding: var(--space-4) 0 var(--space-6); }
  .announcement-heading h1 { font-size: 28px; max-width: 10em; }
  .announcement-intro { max-width: 23em; }
  .announcement-toolbar { padding: var(--space-4); }
  .announcement-filters { width: 100%; }
  .announcement-filters button { flex: 1; padding: var(--space-2); }
  .announcement-search { flex-basis: 100%; width: 100%; max-width: none; }
  .announcement-results-caption { padding: var(--space-2) var(--space-5); }
  .announcement-timezone { display: none; }
  .announcement-list { padding: 0 var(--space-5); }
  .announcement-list-item { padding: var(--space-6) 0; gap: var(--space-3); }
  .announcement-date-stamp, .announcement-row-arrow { display: none; }
  .announcement-list-copy h2 { font-size: 21px; }
  .announcement-list-meta { justify-content: space-between; }
  .announcement-pagination { padding: var(--space-5) var(--space-4); gap: var(--space-2); }
  .announcement-pagination .announcement-button { padding: var(--space-2) var(--space-3); font-size: var(--text-size-xs) !important; }
  .announcement-footnote { align-items: flex-start; padding: 0 var(--space-2); }
  .announcement-footnote svg { margin-top: 3px; }
  .announcement-document { padding: var(--space-6) var(--space-5); }
  .announcement-document-header { padding-bottom: var(--space-6); margin-bottom: var(--space-6); }
  .announcement-document-header h1 { font-size: 27px; margin-top: var(--space-5); }
  .announcement-document-kicker { gap: var(--space-2); }
  .announcement-document-kicker .announcement-eyebrow { font-size: 11px; letter-spacing: 0; }
  .announcement-document-summary { font-size: var(--text-size-sm); }
  .announcement-meta { gap: var(--space-2) var(--space-3); }
  .announcement-document-actions .announcement-button { flex: 1 1 auto; }
  .announcement-acknowledgement { padding: var(--space-4); align-items: flex-start; }
  .announcement-acknowledgement .announcement-button { width: 100%; }
  .announcement-skeleton { padding: 0 var(--space-5); }
  .announcement-skeleton-row > span { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .announcement-filters button, .announcement-row-arrow, .announcement-button { transition: none; }
}
</style>
