<template>
  <span class="seller-reason-wrap">
    <button
      ref="triggerRef"
      type="button"
      class="seller-reason-trigger"
      :aria-describedby="visible ? tooltipId : undefined"
      :aria-expanded="visible"
      @mouseenter="openReason"
      @mouseleave="scheduleClose"
      @focus="openReason"
      @blur="scheduleClose"
      @click.stop="openReason"
      @keydown.esc="closeReason"
    >
      <CircleAlert :size="13" aria-hidden="true" />
      <span>{{ text }}</span>
      <ChevronDown :size="12" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <Transition name="seller-reason-popover">
        <div
          v-if="visible"
          :id="tooltipId"
          ref="popoverRef"
          class="seller-reason-popover"
          :style="popoverStyle"
          :data-placement="coordinates.placement"
          role="tooltip"
          @mouseenter="cancelClose"
          @mouseleave="scheduleClose"
        >
          <span class="seller-reason-arrow" aria-hidden="true"></span>
          <div class="seller-reason-sheet">
            <header>
              <span class="seller-reason-heading">
                <CircleAlert :size="15" aria-hidden="true" />
                <strong>{{ label }}</strong>
              </span>
              <small>完整说明</small>
            </header>
            <p>{{ text }}</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </span>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ChevronDown, CircleAlert } from '@lucide/vue'

defineProps({
  text: { type: String, required: true },
  label: { type: String, default: '状态说明' }
})

const triggerRef = ref(null)
const popoverRef = ref(null)
const visible = ref(false)
const coordinates = ref({ top: 0, left: 0, width: 320, placement: 'bottom', arrowLeft: 28 })
const themeTokens = ref({})
const tooltipId = `seller-reason-${Math.random().toString(36).slice(2, 10)}`
let closeTimer = null

const popoverStyle = computed(() => ({
  ...themeTokens.value,
  top: `${coordinates.value.top}px`,
  left: `${coordinates.value.left}px`,
  width: `${coordinates.value.width}px`,
  '--seller-reason-arrow-left': `${coordinates.value.arrowLeft}px`,
  transform: coordinates.value.placement === 'top' ? 'translateY(-100%)' : 'none'
}))

function syncThemeTokens() {
  const trigger = triggerRef.value
  if (!trigger || typeof window === 'undefined') return

  const styles = window.getComputedStyle(trigger)
  const readToken = (name, fallback) => styles.getPropertyValue(name).trim() || fallback
  themeTokens.value = {
    '--seller-reason-surface': readToken('--seller-surface', 'var(--palette-hex-fcfbf7)'),
    '--seller-reason-surface-soft': readToken('--seller-surface-soft', 'var(--palette-hex-eeebe2)'),
    '--seller-reason-ink': readToken('--seller-ink', 'var(--palette-hex-1f2a34)'),
    '--seller-reason-muted': readToken('--seller-muted', 'var(--palette-hex-68737c)'),
    '--seller-reason-danger': readToken('--seller-danger', 'var(--palette-hex-a5534d)'),
    '--seller-reason-border': readToken('--seller-border', 'var(--palette-hex-d8d2c7)'),
    '--seller-reason-shadow': readToken('--seller-shadow-md', '0 18px 48px var(--palette-rgba-31-42-52-0p16)')
  }
}

function cancelClose() {
  if (!closeTimer) return
  window.clearTimeout(closeTimer)
  closeTimer = null
}

function scheduleClose() {
  cancelClose()
  closeTimer = window.setTimeout(closeReason, 120)
}

function updatePosition() {
  const trigger = triggerRef.value
  if (!trigger || typeof window === 'undefined') return
  const rect = trigger.getBoundingClientRect()
  const viewportPadding = 12
  const width = Math.max(160, Math.min(380, window.innerWidth - viewportPadding * 2))
  const left = Math.min(
    Math.max(viewportPadding, rect.left),
    window.innerWidth - width - viewportPadding
  )
  const availableBelow = window.innerHeight - rect.bottom
  const placement = availableBelow < 180 && rect.top > availableBelow ? 'top' : 'bottom'
  const top = placement === 'top' ? rect.top - 8 : rect.bottom + 8
  const arrowLeft = Math.min(width - 24, Math.max(24, rect.left + rect.width / 2 - left))
  coordinates.value = { top, left, width, placement, arrowLeft }
}

async function openReason() {
  cancelClose()
  syncThemeTokens()
  visible.value = true
  await nextTick()
  updatePosition()
}

function closeReason() {
  cancelClose()
  visible.value = false
}

function handleOutsidePointer(event) {
  if (!visible.value) return
  if (triggerRef.value?.contains(event.target) || popoverRef.value?.contains(event.target)) return
  closeReason()
}

function handleWindowScroll(event) {
  if (popoverRef.value?.contains(event.target)) return
  closeReason()
}

onMounted(() => {
  document.addEventListener('pointerdown', handleOutsidePointer)
  window.addEventListener('resize', closeReason)
  window.addEventListener('scroll', handleWindowScroll, true)
})

onUnmounted(() => {
  cancelClose()
  document.removeEventListener('pointerdown', handleOutsidePointer)
  window.removeEventListener('resize', closeReason)
  window.removeEventListener('scroll', handleWindowScroll, true)
})
</script>

<style scoped>
.seller-reason-wrap {
  display: block;
  min-width: 0;
  margin-top: 7px;
}

.seller-reason-trigger {
  max-width: 100%;
  min-height: 28px;
  display: inline-grid;
  grid-template-columns: 13px minmax(0, 1fr) 12px;
  align-items: center;
  gap: 5px;
  padding: 4px 7px;
  border: 1px solid color-mix(in srgb, var(--seller-danger) 24%, var(--seller-border));
  border-radius: 8px;
  color: var(--seller-danger);
  background: color-mix(in srgb, var(--seller-danger) 6%, var(--seller-surface));
  font-size: 11px;
  line-height: 1.35;
  cursor: help;
}

.seller-reason-trigger span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.seller-reason-trigger svg:last-child {
  transition: transform 160ms ease;
}

.seller-reason-trigger[aria-expanded="true"] svg:last-child {
  transform: rotate(180deg);
}

.seller-reason-trigger:hover,
.seller-reason-trigger:focus-visible {
  border-color: color-mix(in srgb, var(--seller-danger) 48%, var(--seller-border));
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--seller-danger) 13%, transparent);
}

.seller-reason-popover {
  --seller-reason-surface: var(--surface-paper-card);
  --seller-reason-surface-soft: var(--surface-paper-soft);
  --seller-reason-ink: var(--text-paper-primary);
  --seller-reason-muted: var(--text-paper-secondary);
  --seller-reason-danger: var(--status-paper-danger);
  --seller-reason-border: var(--border-paper-default);
  --seller-reason-shadow: var(--elevation-paper-overlay);
  position: fixed;
  z-index: 2100;
  isolation: isolate;
  border: 1px solid color-mix(in srgb, var(--seller-reason-danger) 28%, var(--seller-reason-border));
  border-radius: 12px;
  color: var(--seller-reason-ink);
  background: var(--seller-reason-surface);
  box-shadow:
    var(--seller-reason-shadow),
    0 6px 18px color-mix(in srgb, var(--seller-reason-ink) 12%, transparent);
}

.seller-reason-sheet {
  position: relative;
  z-index: 1;
  max-height: min(60vh, 360px);
  overflow-y: auto;
  border-radius: 11px;
  background: var(--seller-reason-surface);
  overscroll-behavior: contain;
}

.seller-reason-sheet::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  z-index: 2;
  width: 4px;
  border-radius: 11px 0 0 11px;
  background: var(--seller-reason-danger);
}

.seller-reason-arrow {
  position: absolute;
  left: var(--seller-reason-arrow-left);
  z-index: 0;
  width: 12px;
  height: 12px;
  border: 1px solid color-mix(in srgb, var(--seller-reason-danger) 28%, var(--seller-reason-border));
  background: var(--seller-reason-surface);
  transform: translateX(-50%) rotate(45deg);
}

.seller-reason-popover[data-placement='bottom'] .seller-reason-arrow {
  top: -7px;
  border-right: 0;
  border-bottom: 0;
}

.seller-reason-popover[data-placement='top'] .seller-reason-arrow {
  bottom: -7px;
  border-top: 0;
  border-left: 0;
}

.seller-reason-sheet header {
  min-height: 43px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 14px 9px 17px;
  border-bottom: 1px solid color-mix(in srgb, var(--seller-reason-border) 78%, transparent);
  border-radius: 11px 11px 0 0;
  background: var(--seller-reason-surface-soft);
}

.seller-reason-heading {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: color-mix(in srgb, var(--seller-reason-danger) 88%, var(--seller-reason-ink));
}

.seller-reason-heading strong {
  font-size: 12px;
  font-weight: 750;
  letter-spacing: .04em;
}

.seller-reason-sheet header small {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--seller-reason-muted) 76%, var(--seller-reason-ink));
  font-size: 10px;
  letter-spacing: .08em;
}

.seller-reason-sheet p {
  margin: 0;
  padding: 13px 15px 15px 18px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  color: var(--seller-reason-ink);
  font-size: 13px;
  line-height: 1.7;
}

.seller-reason-popover-enter-active,
.seller-reason-popover-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.seller-reason-popover-enter-from,
.seller-reason-popover-leave-to {
  opacity: 0;
}

@media (max-width: 767px) {
  .seller-reason-trigger {
    min-height: 44px;
    cursor: pointer;
  }
}

@media (prefers-reduced-motion: reduce) {
  .seller-reason-trigger svg:last-child,
  .seller-reason-popover-enter-active,
  .seller-reason-popover-leave-active {
    transition: none;
  }
}
</style>
