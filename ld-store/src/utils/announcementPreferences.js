import { ref } from 'vue'
import { fetchAnnouncementStates, saveAnnouncementState } from '@/services/announcementService'
export const announcementPreferenceRevision = ref(0)
const memory = new Map()
export function announcementIdentity(store) {
  const user = store.currentUser
  return store.isLoggedIn && user ? `${user.site || 'linux.do'}:${user.userId || user.id}` : 'guest'
}
function read(storage, key) {
  try { return JSON.parse(globalThis[storage].getItem(key) || 'null') } catch { return memory.get(key) || null }
}
function write(storage, key, value) {
  memory.set(key, value)
  try { globalThis[storage].setItem(key, JSON.stringify(value)) } catch { /* The in-memory record still suppresses this visit. */ }
  announcementPreferenceRevision.value++
}
export function preferenceKey(identity, item) { return `ld-announcement:${identity}:${item.id}:${item.reminderVersion || 1}` }
export function sessionHasPopup(identity) { return Boolean(read('sessionStorage', `ld-announcement-session:${identity}`)) }
export function markPopupShown(identity) { write('sessionStorage', `ld-announcement-session:${identity}`, true) }
export function isAnnouncementDismissed(identity, item) {
  const record = read('localStorage', preferenceKey(identity, item))
  if (record?.forever || record?.dismissedUntil > Date.now()) return true
  // Old unscoped records remain device-only; never upload them as account state.
  if ((item.reminderVersion || 1) === 1) {
    try {
      const raw = localStorage.getItem(`ld-shop-popup-read:${item.popupDismissKey || `popup-${item.id}`}`)
      if (raw === 'permanent' || /^\d+$/.test(raw || '')) return true
      const old = raw && JSON.parse(raw)
      if (old?.mode === 'forever' || old?.expiresAt > Date.now()) return true
    } catch { /* Malformed legacy records are ignored. */ }
  }
  return false
}
export function dismissAnnouncement(identity, item, mode) {
  if (mode === 'session') return
  const now = Date.now()
  const end = Math.floor((now + 8 * 3600000) / 86400000) * 86400000 + 86400000 - 8 * 3600000
  write('localStorage', preferenceKey(identity, item), { forever: mode === 'forever', dismissedUntil: mode === 'today' ? end : null })
  if (identity !== 'guest') {
    const pending = read('localStorage', `ld-announcement-pending:${identity}`) || {}
    pending[`${item.id}:${item.reminderVersion || 1}`] = { id: item.id, reminderVersion: item.reminderVersion || 1, mode }
    write('localStorage', `ld-announcement-pending:${identity}`, pending)
    void syncAnnouncementPreferences(identity)
  }
}

let currentIdentity = 'guest'
export function setAnnouncementPreferenceIdentity(identity) { currentIdentity = identity }
export async function syncAnnouncementPreferences(identity) {
  if (identity === 'guest' || identity !== currentIdentity) return true
  try {
    const pendingKey = `ld-announcement-pending:${identity}`
    const pending = read('localStorage', pendingKey) || {}
    for (const [key, record] of Object.entries(pending)) {
      if (identity !== currentIdentity) return false
      const response = await saveAnnouncementState(record.id, { reminderVersion: record.reminderVersion, mode: record.mode })
      if (identity !== currentIdentity) return false
      if (response.success || response.status === 404 || response.status === 409) {
        const latest = read('localStorage', pendingKey) || {}
        if (JSON.stringify(latest[key]) === JSON.stringify(record)) { delete latest[key]; write('localStorage', pendingKey, latest) }
      }
    }
    if (identity !== currentIdentity) return false
    const response = await fetchAnnouncementStates()
    if (!response.success || identity !== currentIdentity) return false
    for (const state of response.data.items) {
      const key = preferenceKey(identity, { id: state.announcementId, reminderVersion: state.reminderVersion })
      const old = read('localStorage', key) || {}
      write('localStorage', key, { forever: old.forever || state.forever, dismissedUntil: Math.max(old.dismissedUntil || 0, state.dismissedUntil || 0) })
    }
    return true
  } catch { return false }
}
