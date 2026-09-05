import { sendAnnouncementEvents } from '@/services/announcementService'
let identity = 'guest', queue = [], timer = null, flushing = false, generation = 0
const syntheticSession = new URLSearchParams(globalThis.location?.search || '').get('context_synthetic') === 'true'
let sessionId
function session() {
  if (sessionId) return sessionId
  try { sessionId = sessionStorage.getItem('ld-announcement-metric-session') } catch { /* Memory fallback */ }
  if (!sessionId) { sessionId = crypto.randomUUID(); try { sessionStorage.setItem('ld-announcement-metric-session', sessionId) } catch { /* Memory fallback */ } }
  return sessionId
}
export function setAnnouncementTelemetryIdentity(value) {
  if (identity === value) return
  identity = value; generation++; queue = []; clearTimeout(timer); timer = null
}
function schedule() { if (!timer && queue.length) timer = setTimeout(() => { timer = null; void flushAnnouncementEvents() }, 5000) }
export async function flushAnnouncementEvents() {
  if (flushing || !queue.length) return
  flushing = true
  const ticket = generation, batch = queue.slice(0, 20)
  try {
    const result = await sendAnnouncementEvents(batch.map(({ attempts: _attempts, ...event }) => event))
    if (ticket !== generation) return
    if (result.success) queue = queue.filter(event => !batch.includes(event))
    else for (const event of batch) event.attempts++
  } catch { if(ticket === generation) for (const event of batch) event.attempts++ }
  finally { flushing = false; queue = queue.filter(event => event.attempts < 6); schedule() }
}
export function trackAnnouncement(item, event, placement) {
  if (!import.meta.env.PROD || syntheticSession || navigator.webdriver || navigator.globalPrivacyControl === true || navigator.doNotTrack === '1' || !item?.id) return
  queue.push({ eventId: crypto.randomUUID(), announcementId: item.id, contentVersion: item.contentVersion || 1, reminderVersion: item.reminderVersion || 1, placement, event, sessionId: session(), attempts: 0 })
  if (queue.length > 100) queue.shift()
  schedule()
}
// An impression requires at least half of the actual element to remain visible for one second.
const observations = new WeakMap()
function observe(element, binding) {
  observations.get(element)?.stop()
  const value = binding.value
  if (!value?.item || typeof IntersectionObserver === 'undefined') return
  let timer = null, ratio = 0, counted = false
  const clear = () => { clearTimeout(timer); timer = null }
  const update = () => {
    clear()
    if (!counted && value.event === 'open' && ratio > 0 && document.visibilityState !== 'hidden') { counted = true; trackAnnouncement(value.item, 'open', value.placement); return }
    if (!counted && ratio >= .5 && document.visibilityState !== 'hidden') timer = setTimeout(() => { counted = true; trackAnnouncement(value.item, value.event || 'impression', value.placement) }, 1000)
  }
  const observer = new IntersectionObserver(entries => { ratio = entries[0]?.intersectionRatio || 0; update() }, { threshold: [0, .5] })
  observer.observe(element); document.addEventListener('visibilitychange', update)
  observations.set(element, { signature: `${identity}:${value.item.id}:${value.item.contentVersion}:${value.item.reminderVersion}:${value.placement}`, stop() { clear(); observer.disconnect(); document.removeEventListener('visibilitychange', update) } })
}
export const announcementImpression = {
  mounted: observe,
  updated(element, binding) {
    const value = binding.value
    if (`${identity}:${value?.item?.id}:${value?.item?.contentVersion}:${value?.item?.reminderVersion}:${value?.placement}` !== observations.get(element)?.signature) observe(element,binding)
  },
  unmounted(element) { observations.get(element)?.stop(); observations.delete(element) }
}
