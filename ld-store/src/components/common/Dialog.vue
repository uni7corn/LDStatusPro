<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="dialog.visible" class="dialog-overlay" @click.self="handleCancel">
        <div ref="container" class="dialog-container" role="dialog" aria-modal="true" aria-labelledby="app-dialog-title" aria-describedby="app-dialog-content" tabindex="-1" @keydown="handleKeydown">
          <div class="dialog-header">
            <span v-if="dialog.icon" class="dialog-icon" aria-hidden="true">
              <component v-if="dialogIconComponent" :is="dialogIconComponent" :size="40" :stroke-width="1.7" />
              <template v-else>{{ dialog.icon }}</template>
            </span>
            <h3 id="app-dialog-title" class="dialog-title">{{ dialog.title }}</h3>
          </div>
          
          <div id="app-dialog-content" class="dialog-body">{{ dialog.content }}</div>
          
          <div class="dialog-footer">
            <button
              v-if="dialog.showCancel"
              class="dialog-btn dialog-btn-cancel"
              @click="handleCancel"
            >
              {{ dialog.cancelText }}
            </button>
            <button
              v-if="dialog.secondaryText"
              class="dialog-btn dialog-btn-secondary"
              @click="handleSecondary"
            >
              {{ dialog.secondaryText }}
            </button>
            <button
              :class="['dialog-btn', 'dialog-btn-confirm', { 'danger': dialog.danger }]"
              @click="handleConfirm"
            >
              {{ dialog.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { LockKeyhole, ShieldAlert, Trash2 } from '@lucide/vue'
import { useUiStore } from '@/stores/ui'

const uiStore = useUiStore()
const dialog = computed(() => uiStore.dialog)
const container = ref(null)
let returnFocus = null
watch(() => dialog.value.visible, async visible => {
  if (visible) {
    returnFocus = document.activeElement
    await nextTick()
    await nextTick()
    // Prefer the safe action for destructive confirmations.
    if (dialog.value.visible) (container.value?.querySelector('.dialog-btn-cancel') || container.value?.querySelector('button') || container.value)?.focus()
  } else {
    await nextTick()
    // The caller may clear its busy state in the confirmation promise's finally.
    await nextTick()
    restoreFocus()
  }
}, { flush: 'sync' })
function restoreFocus() {
  if (returnFocus?.isConnected) {
    const target = returnFocus.disabled ? returnFocus.closest('[tabindex="-1"]') : returnFocus
    target?.focus({ preventScroll: true })
  }
  returnFocus = null
}
function handleKeydown(event) {
  if (event.key === 'Escape') { event.preventDefault(); handleCancel(); return }
  if (event.key !== 'Tab') return
  const controls = [...container.value.querySelectorAll('a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
  const first = controls[0]
  const last = controls.at(-1)
  if (!first) { event.preventDefault(); container.value.focus(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === container.value)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onUnmounted(restoreFocus)
const dialogIconMap = {
  'lock-keyhole': LockKeyhole,
  'shield-alert': ShieldAlert,
  'trash-2': Trash2
}
const dialogIconComponent = computed(() => dialogIconMap[dialog.value.icon] || null)

function handleConfirm() {
  if (dialog.value.onConfirm) {
    dialog.value.onConfirm()
  }
}

function handleCancel() {
  if (dialog.value.onCancel) {
    dialog.value.onCancel()
  }
}

function handleSecondary() {
  if (dialog.value.onSecondary) {
    dialog.value.onSecondary()
  }
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-bg);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9998;
  padding: 20px;
}

.dialog-container {
  background: var(--dropdown-bg);
  border-radius: 20px;
  width: 100%;
  max-width: 360px;
  box-shadow: var(--dropdown-shadow);
  border: 1px solid var(--border-light);
  overflow: hidden;
}

.dialog-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 24px 12px;
  gap: 8px;
}

.dialog-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  line-height: 1;
  color: var(--color-primary);
}

.dialog-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.dialog-body {
  padding: 12px 24px 24px;
  font-size: 14px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.6;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.dialog-footer {
  display: flex;
  border-top: 1px solid var(--border-light);
}

.dialog-btn {
  min-height: 44px;
  flex: 1;
  padding: 14px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
  border: none;
  background: transparent;
}

.dialog-btn-cancel {
  color: var(--text-tertiary);
  border-right: 1px solid var(--border-light);
}

.dialog-btn-cancel:hover {
  background: var(--bg-secondary);
}

.dialog-btn-secondary {
  color: var(--color-primary);
  border-right: 1px solid var(--border-light);
}

.dialog-btn-secondary:hover {
  background: var(--color-primary-light);
}

.dialog-btn-confirm {
  color: var(--color-primary);
}

.dialog-btn-confirm:hover {
  background: var(--color-primary-light);
}

.dialog-btn-confirm.danger {
  color: var(--color-danger);
}

/* 动画 */
.dialog-enter-active {
  animation: dialogIn 0.25s ease-out;
}

.dialog-leave-active {
  animation: dialogOut 0.2s ease-in;
}

.dialog-enter-active .dialog-container {
  animation: dialogContainerIn 0.2s ease-out;
}

.dialog-leave-active .dialog-container {
  animation: dialogContainerOut 0.2s ease-in;
}

@keyframes dialogIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes dialogOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

@keyframes dialogContainerIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes dialogContainerOut {
  from {
    opacity: 1;
    transform: scale(1);
  }
  to {
    opacity: 0;
    transform: scale(0.9);
  }
}

/* 移动端适配 */
@media (max-width: 640px) {
  .dialog-overlay {
    padding: 16px;
    align-items: flex-end;
  }

  .dialog-container {
    max-width: 100%;
    margin-bottom: env(safe-area-inset-bottom, 0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .dialog-enter-active, .dialog-leave-active,
  .dialog-enter-active .dialog-container, .dialog-leave-active .dialog-container { animation: none; }
  .dialog-btn { transition: none; }
}
</style>
