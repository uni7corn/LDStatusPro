<template>
  <div
    ref="tabsContainer"
    class="liquid-tabs"
    :class="[`liquid-tabs--${size}`, `liquid-tabs--${layout}`]"
    :role="mode === 'tabs' ? 'tablist' : 'group'"
    :aria-label="ariaLabel"
    :aria-disabled="disabled || undefined"
    @focusout="handleFocusOut"
  >
    <div class="liquid-indicator" :style="indicatorStyle" aria-hidden="true">
      <div class="liquid-glass"></div>
      <div class="liquid-shine"></div>
    </div>
    <button
      v-for="tab in tabs"
      :id="tabId(tab)"
      :key="tab.value"
      :ref="el => setTabRef(el, tab.value)"
      type="button"
      :class="['liquid-tab', { active: modelValue === tab.value, 'has-description': tab.description }]"
      :disabled="isDisabled(tab)"
      :role="mode === 'tabs' ? 'tab' : undefined"
      :aria-selected="mode === 'tabs' ? modelValue === tab.value : undefined"
      :aria-pressed="mode === 'select' ? modelValue === tab.value : undefined"
      :aria-controls="mode === 'tabs' ? tab.panelId : undefined"
      :aria-describedby="tab.description ? `${tabId(tab)}-description` : undefined"
      :tabindex="mode === 'tabs' ? (tab.value === focusEntryValue ? 0 : -1) : undefined"
      @click="activateTab(tab)"
      @keydown="handleKeydown($event, tab)"
      @focus="handleFocus(tab)"
    >
      <span v-if="tab.iconComponent || tab.icon" class="tab-icon" aria-hidden="true">
        <component :is="tab.iconComponent" v-if="tab.iconComponent" :size="16" :stroke-width="2" />
        <template v-else>{{ tab.icon }}</template>
      </span>
      <span class="tab-copy">
        <span class="tab-text">{{ tab.label }}</span>
        <span v-if="tab.description" :id="`${tabId(tab)}-description`" class="tab-description">{{ tab.description }}</span>
      </span>
      <span v-if="tab.badge !== undefined && tab.badge !== null" class="tab-badge">{{ tab.badge }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'

// Panels stay with the caller. In tabs mode supply each item's id/panelId and
// connect the panel's aria-labelledby to that id; filters use select mode.
const props = defineProps({
  tabs: { type: Array, required: true },
  modelValue: { type: [String, Number], required: true },
  mode: { type: String, default: 'select', validator: value => ['select', 'tabs'].includes(value) },
  activation: { type: String, default: 'manual', validator: value => ['manual', 'automatic'].includes(value) },
  size: { type: String, default: 'md', validator: value => ['sm', 'md'].includes(value) },
  layout: { type: String, default: 'content', validator: value => ['content', 'equal'].includes(value) },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '选项切换' }
})
const emit = defineEmits(['update:modelValue', 'activate'])
const instanceId = `liquid-tabs-${getCurrentInstance().uid}`
const tabsContainer = ref(null)
const tabRefs = new Map()
const focusedValue = ref(undefined)
const indicatorStyle = ref({ opacity: 0 })
let resizeObserver = null
let frameId = null
let observing = false
let revealPending = false

const enabledTabs = computed(() => props.tabs.filter(tab => !isDisabled(tab)))
const focusEntryValue = computed(() => {
  const enabled = enabledTabs.value
  if (enabled.some(tab => tab.value === focusedValue.value)) return focusedValue.value
  if (enabled.some(tab => tab.value === props.modelValue)) return props.modelValue
  return enabled[0]?.value
})

function tabId(tab) {
  return tab.id || `${instanceId}-${typeof tab.value}-${encodeURIComponent(tab.value)}`
}

function isDisabled(tab) {
  return props.disabled || Boolean(tab.disabled)
}

function setTabRef(element, value) {
  const previous = tabRefs.get(value)
  if (previous === element) return
  if (previous) resizeObserver?.unobserve(previous)
  if (element) {
    tabRefs.set(value, element)
    resizeObserver?.observe(element)
  } else {
    tabRefs.delete(value)
  }
  scheduleMeasure()
}

function updateIndicator() {
  const container = tabsContainer.value
  const tab = tabRefs.get(props.modelValue)
  if (!container || !tab || !container.clientWidth || !tab.offsetWidth || !tab.offsetHeight) {
    indicatorStyle.value = { ...indicatorStyle.value, opacity: 0 }
    return
  }
  // Offset geometry is local to the scroll container, unaffected by viewport
  // scrolling, border widths, or the drawer's entrance animation.
  indicatorStyle.value = {
    transform: `translate(${tab.offsetLeft}px, ${tab.offsetTop}px)`,
    width: `${tab.offsetWidth}px`,
    height: `${tab.offsetHeight}px`,
    opacity: 1,
    transition: indicatorStyle.value.opacity ? undefined : 'none'
  }
}

function revealTab(value) {
  const container = tabsContainer.value
  const tab = tabRefs.get(value)
  if (!container || !tab || !container.clientWidth || !tab.offsetWidth) return
  const margin = 5
  const start = tab.offsetLeft - margin
  const end = tab.offsetLeft + tab.offsetWidth + margin
  let left = container.scrollLeft
  if (start < left) left = start
  else if (end > left + container.clientWidth) left = end - container.clientWidth
  left = Math.max(0, Math.min(left, container.scrollWidth - container.clientWidth))
  if (Math.abs(left - container.scrollLeft) < 1) return
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  // Never use scrollIntoView: it can scroll the page and enclosing drawers too.
  container.scrollTo({ left, behavior: reduceMotion ? 'auto' : 'smooth' })
}

function scheduleMeasure(reveal = false) {
  if (!observing) return
  revealPending ||= reveal
  if (frameId !== null) return
  frameId = window.requestAnimationFrame(() => {
    frameId = null
    updateIndicator()
    if (revealPending) revealTab(focusedValue.value ?? props.modelValue)
    revealPending = false
  })
}

function activateTab(tab) {
  if (isDisabled(tab)) return
  // The parent owns selection. Repeated activation is separate so adapters can
  // preserve refresh behavior without duplicating model updates.
  if (tab.value !== props.modelValue) emit('update:modelValue', tab.value)
  emit('activate', tab.value)
}

function handleFocus(tab) {
  focusedValue.value = tab.value
  scheduleMeasure(true)
}

function handleFocusOut(event) {
  if (!tabsContainer.value?.contains(event.relatedTarget)) focusedValue.value = undefined
}

function handleKeydown(event, tab) {
  if (props.mode !== 'tabs' || isDisabled(tab) || event.altKey || event.ctrlKey || event.metaKey) return
  if (event.key === 'Enter' || event.key === ' ') {
    // Own tab activation explicitly; prevent the native follow-up click so
    // keyboard activation and the repeat-click event are each emitted once.
    event.preventDefault()
    if (!event.repeat) activateTab(tab)
    return
  }
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const enabled = enabledTabs.value
  const index = enabled.findIndex(item => item.value === tab.value)
  const step = event.key === 'ArrowLeft' ? -1 : 1
  const targetIndex = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : (index + step + enabled.length) % enabled.length
  const target = enabled[targetIndex]
  if (!target) return
  tabRefs.get(target.value)?.focus({ preventScroll: true })
  if (props.activation === 'automatic') activateTab(target)
}

function handleResize() {
  scheduleMeasure(true)
}

function startObserving() {
  if (observing) return
  observing = true
  if (window.ResizeObserver) {
    resizeObserver = new window.ResizeObserver(handleResize)
    if (tabsContainer.value) resizeObserver.observe(tabsContainer.value)
    tabRefs.forEach(element => resizeObserver.observe(element))
  }
  window.addEventListener('resize', handleResize)
  document.fonts?.addEventListener('loadingdone', handleResize)
  document.fonts?.ready.then(() => { if (observing) scheduleMeasure(true) })
  scheduleMeasure(true)
}

function stopObserving() {
  observing = false
  resizeObserver?.disconnect()
  resizeObserver = null
  if (frameId !== null) window.cancelAnimationFrame(frameId)
  frameId = null
  revealPending = false
  focusedValue.value = undefined
  indicatorStyle.value = { ...indicatorStyle.value, opacity: 0 }
  window.removeEventListener('resize', handleResize)
  document.fonts?.removeEventListener('loadingdone', handleResize)
}

watch(() => [props.modelValue, props.tabs, props.disabled, props.layout, props.size], () => {
  if (!enabledTabs.value.some(tab => tab.value === focusedValue.value)) focusedValue.value = undefined
  scheduleMeasure(true)
}, { deep: true, flush: 'post' })

onMounted(startObserving)
onActivated(startObserving)
onDeactivated(stopObserving)
onUnmounted(stopObserving)
</script>

<style scoped>
.liquid-tabs {
  position: relative;
  display: inline-flex;
  align-items: stretch;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  gap: 2px;
  padding: 5px;
  overflow-x: auto;
  scrollbar-width: none;
  overscroll-behavior-x: contain;
  background: var(--liquid-tabs-shell-bg, var(--glass-bg-heavy));
  border: 1px solid var(--liquid-tabs-shell-border, var(--glass-border));
  border-radius: var(--liquid-tabs-radius, 16px);
  box-shadow: var(--liquid-tabs-shell-shadow, 0 4px 20px var(--glass-shadow), 0 1px 3px var(--glass-shadow-light), inset 0 1px 0 var(--glass-shine-strong));
}
.liquid-tabs::-webkit-scrollbar { display: none; }
.liquid-tabs--equal { display: flex; width: 100%; }
.liquid-tabs--equal .liquid-tab { flex: 1 0 0; min-width: max-content; }

.liquid-indicator {
  position: absolute;
  top: 0;
  left: 0;
  border-radius: var(--liquid-tab-radius, 12px);
  pointer-events: none;
  z-index: 0;
  transition: transform 220ms cubic-bezier(.4, 0, .2, 1), width 180ms cubic-bezier(.4, 0, .2, 1), opacity 120ms ease;
}
.liquid-glass {
  position: absolute;
  inset: 0;
  background: var(--liquid-indicator-bg, var(--glass-bg-heavy));
  border-radius: inherit;
  border: 1px solid var(--liquid-indicator-border, var(--glass-border-light));
  box-shadow: var(--liquid-indicator-shadow, 0 4px 16px var(--glass-shadow), 0 2px 8px var(--glass-shadow-light), inset 0 1px 2px var(--glass-shine-strong));
}
.liquid-shine {
  position: absolute;
  top: 1px;
  left: 10%;
  right: 10%;
  height: 45%;
  border-radius: 10px 10px 50% 50%;
  background: var(--liquid-shine-bg, linear-gradient(180deg, var(--glass-shine) 0%, var(--palette-rgba-255-255-255-p12) 50%, transparent 100%));
}

.liquid-tab {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 44px;
  padding: 10px 20px;
  border: none;
  border-radius: var(--liquid-tab-radius, 12px);
  background: transparent;
  color: var(--liquid-tab-text, var(--text-secondary));
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
  transition: color 160ms ease;
}
.liquid-tab:hover:not(:disabled), .liquid-tab.active { color: var(--liquid-tab-active-text, var(--text-primary)); }
.liquid-tab.active { font-weight: 600; }
.liquid-tab:disabled { opacity: .5; cursor: not-allowed; }
/* Inset focus stays visible at the edges of the scroll strip, including inside
   the seller shell's global button focus treatment. */
.liquid-tabs .liquid-tab:focus-visible { outline: 2px solid var(--liquid-tab-focus, var(--text-primary)); outline-offset: -2px; }
.tab-icon { display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; font-size: 16px; line-height: 1; }
.tab-copy { display: grid; gap: 3px; min-width: 0; }
.tab-text { letter-spacing: .3px; }
.tab-description { color: var(--liquid-tab-text, var(--text-secondary)); font-size: 12px; font-weight: 400; white-space: normal; }
.has-description { text-align: left; gap: 10px; }
.tab-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 22px; min-height: 22px; padding: 0 6px; border-radius: 7px; background: var(--liquid-badge-bg, var(--bg-secondary)); color: var(--liquid-tab-text, var(--text-secondary)); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.active .tab-badge { background: var(--liquid-badge-active-bg, var(--bg-tertiary)); color: var(--liquid-tab-active-text, var(--text-primary)); }
.liquid-tabs--sm .liquid-tab { min-height: 40px; padding: 8px 13px; font-size: 13px; }

@media (max-width: 767px) {
  .liquid-tabs { border-radius: var(--liquid-tabs-radius, 14px); }
  .liquid-tabs .liquid-tab { min-height: 44px; padding: 10px 14px; font-size: 13px; }
  .liquid-tabs--equal .has-description { flex-direction: column; gap: 4px; text-align: center; }
  /* Description remains associated through aria-describedby on compact screens. */
  .liquid-tabs--equal .tab-description { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .liquid-indicator, .liquid-tab { transition: none !important; }
}
</style>
