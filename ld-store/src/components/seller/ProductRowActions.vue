<template>
  <div class="product-row-actions" :class="{ mobile }">
    <button v-if="canManageCdk" type="button" class="row-action-secondary" :disabled="busy" @click="$emit('cdk', product)"><KeyRound :size="15" aria-hidden="true" />CDK</button>
    <button type="button" class="row-action-primary" :disabled="busy || restricted" @click="$emit('edit', product)"><Pencil :size="15" aria-hidden="true" />编辑</button>
    <div class="row-action-menu">
      <button
        ref="menuTrigger"
        type="button"
        class="row-action-menu-trigger"
        aria-label="更多物品操作"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        @click="toggleMenu"
      ><MoreHorizontal :size="18" aria-hidden="true" /></button>
      <Teleport to=".seller-shell">
        <div
          v-if="menuOpen"
          ref="menuPanel"
          class="row-action-menu-panel"
          role="menu"
          aria-label="物品操作"
          :style="menuPosition"
          @keydown="handleMenuKeydown"
        >
          <button v-if="canToggle" type="button" role="menuitem" :disabled="busy || restricted" @click="handleMenuAction('toggle')"><Power :size="15" aria-hidden="true" />{{ toggleLabel }}</button>
          <button type="button" role="menuitem" class="danger" :disabled="busy || restricted" @click="handleMenuAction('delete')"><Trash2 :size="15" aria-hidden="true" />{{ deleteLabel }}</button>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { KeyRound, MoreHorizontal, Pencil, Power, Trash2 } from '@lucide/vue'

const props = defineProps({
  product: { type: Object, required: true },
  canManageCdk: { type: Boolean, default: false },
  canToggle: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  restricted: { type: Boolean, default: false },
  toggleLabel: { type: String, default: '' },
  deleteLabel: { type: String, default: '删除' },
  mobile: { type: Boolean, default: false }
})
const emit = defineEmits(['edit', 'cdk', 'toggle', 'delete'])

const MENU_GAP = 6
const VIEWPORT_PADDING = 8
const menuTrigger = ref(null)
const menuPanel = ref(null)
const menuOpen = ref(false)
const menuPosition = ref({ top: '0px', left: '0px', visibility: 'hidden' })

function updateMenuPosition() {
  if (!menuTrigger.value || !menuPanel.value) return

  const triggerRect = menuTrigger.value.getBoundingClientRect()
  const panelRect = menuPanel.value.getBoundingClientRect()
  const viewportWidth = document.documentElement.clientWidth
  const viewportHeight = document.documentElement.clientHeight
  const spaceBelow = viewportHeight - triggerRect.bottom - VIEWPORT_PADDING
  const openAbove = spaceBelow < panelRect.height + MENU_GAP && triggerRect.top > spaceBelow
  const preferredTop = openAbove
    ? triggerRect.top - panelRect.height - MENU_GAP
    : triggerRect.bottom + MENU_GAP
  const top = Math.min(
    Math.max(VIEWPORT_PADDING, preferredTop),
    Math.max(VIEWPORT_PADDING, viewportHeight - panelRect.height - VIEWPORT_PADDING)
  )
  const left = Math.min(
    Math.max(VIEWPORT_PADDING, triggerRect.right - panelRect.width),
    Math.max(VIEWPORT_PADDING, viewportWidth - panelRect.width - VIEWPORT_PADDING)
  )

  menuPosition.value = {
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    visibility: 'visible'
  }
}

function addMenuListeners() {
  document.addEventListener('pointerdown', handleOutsidePointer)
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('resize', updateMenuPosition)
  window.addEventListener('scroll', updateMenuPosition, true)
}

function removeMenuListeners() {
  document.removeEventListener('pointerdown', handleOutsidePointer)
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('resize', updateMenuPosition)
  window.removeEventListener('scroll', updateMenuPosition, true)
}

function closeMenu({ restoreFocus = false } = {}) {
  if (!menuOpen.value) return
  menuOpen.value = false
  removeMenuListeners()
  if (restoreFocus) nextTick(() => menuTrigger.value?.focus())
}

async function openMenu() {
  menuPosition.value = { top: '0px', left: '0px', visibility: 'hidden' }
  menuOpen.value = true
  addMenuListeners()
  await nextTick()
  updateMenuPosition()
}

function toggleMenu() {
  if (menuOpen.value) closeMenu()
  else openMenu()
}

function handleOutsidePointer(event) {
  if (menuTrigger.value?.contains(event.target) || menuPanel.value?.contains(event.target)) return
  closeMenu()
}

function handleDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  event.preventDefault()
  closeMenu({ restoreFocus: true })
}

function handleMenuKeydown(event) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const items = [...menuPanel.value.querySelectorAll('[role="menuitem"]:not(:disabled)')]
  if (!items.length) return
  event.preventDefault()
  const currentIndex = items.indexOf(document.activeElement)
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? items.length - 1
      : event.key === 'ArrowDown'
        ? (currentIndex + 1) % items.length
        : (currentIndex <= 0 ? items.length : currentIndex) - 1
  items[nextIndex].focus()
}

function handleMenuAction(action) {
  closeMenu()
  emit(action, props.product)
}

onBeforeUnmount(removeMenuListeners)
</script>

<style scoped>
.product-row-actions { display: flex; align-items: center; justify-content: flex-end; gap: 4px; }
.product-row-actions button, .row-action-menu-panel button { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 5px; padding: 0 6px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-muted); background: var(--seller-surface); font-size: 12px; font-weight: 650; white-space: nowrap; cursor: pointer; }
.row-action-primary { color: var(--palette-hex-ffffff) !important; border-color: var(--seller-navy) !important; background: var(--seller-navy) !important; }
.row-action-primary, .row-action-secondary { min-width: 48px; }
.row-action-menu { position: relative; }
.row-action-menu-trigger { width: 36px; padding: 0 !important; }
.row-action-menu-panel { position: fixed; z-index: 120; min-width: 154px; padding: 6px; border: 1px solid var(--seller-border); border-radius: 10px; background: var(--seller-surface); box-shadow: var(--seller-shadow-md); }
.row-action-menu-panel button { width: 100%; justify-content: flex-start; border-color: transparent; }
.row-action-menu-panel button:hover { background: var(--seller-surface-soft); }
.row-action-menu-panel button.danger { color: var(--seller-danger); }
button:focus-visible { outline: 3px solid color-mix(in srgb, var(--seller-jade) 60%, transparent); outline-offset: 2px; }
button:disabled { opacity: .42; cursor: not-allowed; }
.product-row-actions.mobile { justify-content: flex-start; margin-top: 16px; }
.product-row-actions.mobile .row-action-primary, .product-row-actions.mobile .row-action-secondary { min-height: 44px; flex: 1; }
.product-row-actions.mobile .row-action-menu-trigger { width: 44px; height: 44px; }
</style>
