<script setup>
import { announcementImpression as vAnnouncementImpression, trackAnnouncement } from '@/utils/announcementTelemetry'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Megaphone, X } from '@lucide/vue'
import { useAnnouncement } from '@/composables/useAnnouncement'
import { useUserStore } from '@/stores/user'
import { announcementIdentity, announcementPreferenceRevision, sessionHasPopup, markPopupShown, isAnnouncementDismissed, dismissAnnouncement } from '@/utils/announcementPreferences'
import AnnouncementContent from './AnnouncementContent.vue'
const route = useRoute(), store = useUserStore()
const { announcementItems, announcementPreferencesReady } = useAnnouncement()
const identity = computed(() => announcementIdentity(store))
const active = ref(null), dialog = ref(null), title = ref(null)
const safeRoutes = new Set(['Home','Category','Search','MerchantProfile','ShopDetail','Shop','SellerDashboard'])
let returnFocus = null, previousOverflow = '', openedIdentity = ''
function dismiss(mode = 'session', countClose = true) {
  if (!active.value) return
  if (countClose) trackAnnouncement(active.value, 'close', route.meta.layout === 'seller' ? 'seller' : 'storefront')
  dismissAnnouncement(openedIdentity, active.value, mode)
  active.value = null
}
function backdrop(event) {
  if (event.target !== dialog.value) return
  const rect = dialog.value.getBoundingClientRect()
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dismiss()
}
watch([announcementItems, announcementPreferencesReady, () => route.name, identity, announcementPreferenceRevision, () => store.sessionReady], () => {
  if (active.value) {
    const latest = announcementItems.value.find(item => item.id === active.value.id)
    if (identity.value !== openedIdentity || !safeRoutes.has(route.name) || !latest || isAnnouncementDismissed(identity.value, latest)) active.value = null
    else active.value = latest
    return
  }
  if (!store.sessionReady || !announcementPreferencesReady.value || !safeRoutes.has(route.name) || sessionHasPopup(identity.value)) return
  const item = announcementItems.value.find(item => item.mode === 'popup' && !isAnnouncementDismissed(identity.value, item))
  if (item) { openedIdentity = identity.value; active.value = item }
}, { immediate: true })
watch(active, async (item, old) => {
  await nextTick()
  if (item && active.value && dialog.value && !dialog.value.open) {
    returnFocus = document.activeElement; previousOverflow = document.body.style.overflow
    dialog.value.showModal(); document.body.style.overflow = 'hidden'; title.value?.focus()
    markPopupShown(openedIdentity)
  } else if (!item && old) {
    dialog.value?.close(); document.body.style.overflow = previousOverflow; returnFocus?.focus?.()
  }
}, { immediate: true })
onBeforeUnmount(() => { if (dialog.value?.open) { dialog.value.close(); document.body.style.overflow = previousOverflow; returnFocus?.focus?.() } })
</script>
<template>
  <Teleport to="body"><dialog ref="dialog" class="announcement-dialog" aria-labelledby="announcement-popup-title" @cancel.prevent="dismiss()" @click="backdrop">
    <template v-if="active"><header><div><p><Megaphone :size="16" aria-hidden="true" />站内公告</p><h2 id="announcement-popup-title" ref="title" tabindex="-1">{{ active.title || '公告提醒' }}</h2></div><button class="announcement-close" aria-label="本次关闭公告" @click="dismiss()"><X :size="22" aria-hidden="true" /></button></header>
      <div v-announcement-impression="{item:active,placement:route.meta.layout === 'seller' ? 'seller' : 'storefront'}" class="announcement-dialog-body"><AnnouncementContent :content="active.content" :content-type="active.contentType" /></div>
      <footer><a v-if="active.actionUrl" class="announcement-dismiss announcement-action" :href="active.actionUrl" :target="active.actionUrl.startsWith('/') ? undefined : '_blank'" rel="noopener noreferrer" @click="trackAnnouncement(active, 'action', route.meta.layout === 'seller' ? 'seller' : 'storefront')">{{ active.actionLabel }}</a><router-link :to="`/announcements/${active.id}`" class="announcement-detail-link" @click="dismiss('session', false)">查看详情与历史公告</router-link><p>关闭后仍可在公告中心查阅。</p><div><button class="announcement-dismiss secondary" @click="dismiss('today')">今日不提醒</button><button class="announcement-dismiss" @click="dismiss('forever')">不再提醒本条</button></div></footer>
    </template>
  </dialog></Teleport>
</template>
<style scoped>
.announcement-dialog{width:min(calc(100% - 32px),680px);max-height:86dvh;max-height:min(86dvh,800px);margin:auto;padding:0;border:1px solid var(--border-default-semantic);border-radius:var(--radius-lg);background:var(--surface-card);color:var(--text-primary-semantic);box-shadow:var(--elevation-lg);overflow:hidden}.announcement-dialog[open]{display:flex;flex-direction:column}.announcement-dialog::backdrop{background:var(--surface-overlay)}.announcement-dialog header{display:flex;justify-content:space-between;align-items:start;gap:var(--space-4);padding:var(--space-6);flex-shrink:0;border-bottom:1px solid var(--border-default-semantic)}.announcement-dialog header>div{min-width:0}.announcement-dialog header p{display:flex;align-items:center;gap:var(--space-2);color:var(--text-secondary-semantic);font-size:var(--text-size-sm);margin:0 0 var(--space-2)}.announcement-dialog h2{font-weight:600;font-size:var(--text-size-lg);line-height:1.5;margin:0;overflow-wrap:anywhere}.announcement-close{display:flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;border:1px solid var(--border-default-semantic);background:var(--surface-subtle);color:inherit;border-radius:var(--radius-sm);cursor:pointer}.announcement-dialog-body{min-height:0;padding:var(--space-6);overflow-y:auto;overscroll-behavior:contain}.announcement-dialog footer{flex-shrink:0;border-top:1px solid var(--border-default-semantic);padding:var(--space-4) var(--space-6)}.announcement-dialog footer p{font-size:var(--text-size-xs);color:var(--text-muted-semantic);margin:var(--space-2) 0 var(--space-3)}.announcement-dialog footer>div{display:flex;justify-content:flex-end;gap:var(--space-3);flex-wrap:wrap}.announcement-action{display:inline-flex;align-items:center;margin-bottom:var(--space-2);margin-right:var(--space-3);text-decoration:none}.announcement-detail-link{color:var(--text-link);text-decoration:underline;display:inline-flex;min-height:44px;align-items:center}.announcement-dismiss{min-height:44px;padding:var(--space-2) var(--space-4);border:1px solid var(--border-default-semantic);border-radius:var(--radius-sm);background:var(--action-primary);color:var(--action-primary-text);cursor:pointer}.announcement-dismiss.secondary{background:var(--action-secondary);color:var(--action-secondary-text)}@media(max-width:600px){.announcement-dialog{max-height:90dvh;margin:auto auto max(12px,env(safe-area-inset-bottom))}.announcement-dialog header,.announcement-dialog-body{padding:var(--space-4)}.announcement-dialog footer{padding:var(--space-3) var(--space-4)}.announcement-dismiss{flex:1}}
</style>
