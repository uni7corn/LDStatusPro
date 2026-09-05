<template>
  <Teleport to="body">
    <Transition name="catalog-filter-sheet">
      <div
        v-if="open"
        class="catalog-filter-layer"
        @click.self="requestClose"
      >
        <section
          id="home-catalog-filter-sheet"
          ref="dialogRef"
          class="catalog-filter-sheet"
          role="dialog"
          aria-modal="true"
          aria-labelledby="catalog-filter-title"
          :aria-busy="loading"
          @keydown="handleKeydown"
        >
          <header class="catalog-filter-header">
            <div>
              <p>缩小首页物品范围</p>
              <h2 id="catalog-filter-title">筛选物品</h2>
            </div>
            <button
              ref="closeButtonRef"
              type="button"
              class="catalog-filter-close"
              aria-label="关闭筛选"
              :disabled="loading"
              @click="requestClose"
            >
              <X :size="20" aria-hidden="true" />
            </button>
          </header>

          <div class="catalog-filter-body">
            <fieldset class="catalog-filter-group">
              <legend>折后价格</legend>
              <p id="catalog-price-help" class="catalog-filter-help">留空表示不限，价格单位为 LDC。</p>
              <div class="catalog-price-grid">
                <label for="catalog-price-min">
                  <span>最低价</span>
                  <input
                    id="catalog-price-min"
                    v-model.trim="draftPriceMin"
                    type="number"
                    min="0"
                    step="0.01"
                    inputmode="decimal"
                    placeholder="不限"
                    aria-describedby="catalog-price-help"
                    :disabled="loading"
                  />
                </label>
                <label for="catalog-price-max">
                  <span>最高价</span>
                  <input
                    id="catalog-price-max"
                    v-model.trim="draftPriceMax"
                    type="number"
                    min="0"
                    step="0.01"
                    inputmode="decimal"
                    placeholder="不限"
                    aria-describedby="catalog-price-help"
                    :disabled="loading"
                  />
                </label>
              </div>
            </fieldset>

            <fieldset class="catalog-filter-group stock-group">
              <legend>库存状态</legend>
              <label class="catalog-stock-option">
                <span class="catalog-stock-copy">
                  <strong>只看有货</strong>
                  <small>隐藏当前已经售罄的物品</small>
                </span>
                <input v-model="draftInStockOnly" type="checkbox" :disabled="loading" />
              </label>
            </fieldset>
          </div>

          <footer class="catalog-filter-footer">
            <button type="button" class="catalog-filter-reset" :disabled="loading" @click="resetDraft">
              重置
            </button>
            <button type="button" class="catalog-filter-apply" :disabled="loading" @click="applyDraft">
              <LoaderCircle v-if="loading" :size="17" class="catalog-filter-spinner" aria-hidden="true" />
              {{ loading ? '应用中…' : '应用筛选' }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { LoaderCircle, X } from '@lucide/vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  priceMin: { type: [Number, String], default: null },
  priceMax: { type: [Number, String], default: null },
  inStockOnly: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'apply'])
const dialogRef = ref(null)
const closeButtonRef = ref(null)
const draftPriceMin = ref('')
const draftPriceMax = ref('')
const draftInStockOnly = ref(false)
let returnFocusElement = null
let previousBodyOverflow = ''

function toDraftValue(value) {
  return value === null || value === undefined || value === '' ? '' : String(value)
}

function syncDraft() {
  draftPriceMin.value = toDraftValue(props.priceMin)
  draftPriceMax.value = toDraftValue(props.priceMax)
  draftInStockOnly.value = props.inStockOnly
}

function requestClose() {
  if (props.loading) return
  emit('close')
}

function resetDraft() {
  if (props.loading) return
  draftPriceMin.value = ''
  draftPriceMax.value = ''
  draftInStockOnly.value = false
}

function applyDraft() {
  if (props.loading) return
  emit('apply', {
    priceMin: draftPriceMin.value,
    priceMax: draftPriceMax.value,
    inStockOnly: draftInStockOnly.value
  })
}

function getFocusableElements() {
  return Array.from(dialogRef.value?.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
  ) || [])
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = getFocusableElements()
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function restorePageState() {
  document.body.style.overflow = previousBodyOverflow
  nextTick(() => returnFocusElement?.focus?.())
}

watch(
  () => props.open,
  async open => {
    if (!open) {
      restorePageState()
      return
    }
    syncDraft()
    returnFocusElement = document.activeElement
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    closeButtonRef.value?.focus()
  }
)

onBeforeUnmount(() => {
  if (props.open) document.body.style.overflow = previousBodyOverflow
})
</script>

<style scoped>
.catalog-filter-layer {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: grid;
  place-items: end stretch;
  background: var(--overlay-bg);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
}

.catalog-filter-sheet {
  width: 100%;
  max-height: min(80dvh, 520px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-bottom: 0;
  border-radius: 24px 24px 0 0;
  background: var(--dropdown-bg);
  box-shadow: var(--dropdown-shadow);
}

.catalog-filter-header,
.catalog-filter-footer {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
}

.catalog-filter-header {
  border-bottom: 1px solid var(--border-light);
}

.catalog-filter-header p,
.catalog-filter-header h2,
.catalog-filter-help {
  margin: 0;
}

.catalog-filter-header p {
  margin-bottom: 2px;
  color: var(--text-secondary);
  font-size: 12px;
}

.catalog-filter-header h2 {
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1.3;
}

.catalog-filter-close {
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-light);
  border-radius: 13px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background-color var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard);
}

.catalog-filter-body {
  min-height: 0;
  display: grid;
  gap: 14px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 16px;
}

.catalog-filter-group {
  min-width: 0;
  margin: 0;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 16px;
  background: var(--bg-secondary);
}

.catalog-filter-group legend {
  padding: 0 4px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
}

.catalog-filter-help {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.catalog-price-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.catalog-price-grid label {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.catalog-price-grid label > span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.catalog-price-grid input {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--border-medium);
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}

.catalog-price-grid input::placeholder {
  color: var(--text-secondary);
}

.stock-group {
  padding-bottom: 10px;
}

.catalog-stock-option {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  cursor: pointer;
}

.catalog-stock-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.catalog-stock-copy strong {
  color: var(--text-primary);
  font-size: 14px;
}

.catalog-stock-copy small {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.catalog-stock-option input {
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  accent-color: var(--action-primary);
}

.catalog-filter-footer {
  display: grid;
  grid-template-columns: minmax(0, .72fr) minmax(0, 1.28fr);
  border-top: 1px solid var(--border-light);
  padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px));
}

.catalog-filter-reset,
.catalog-filter-apply {
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 13px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  touch-action: manipulation;
  transition: background-color var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard);
}

.catalog-filter-reset {
  border: 1px solid var(--border-medium);
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.catalog-filter-apply {
  border: 0;
  background: var(--action-primary);
  box-shadow: var(--elevation-sm);
  color: var(--action-primary-text);
}

.catalog-filter-close:hover,
.catalog-filter-reset:hover {
  background: var(--action-secondary-hover);
}

.catalog-filter-apply:hover {
  background: var(--action-primary-hover);
}

.catalog-filter-close:active,
.catalog-filter-reset:active,
.catalog-filter-apply:active {
  opacity: .78;
}

.catalog-filter-close:disabled,
.catalog-price-grid input:disabled,
.catalog-stock-option input:disabled,
.catalog-filter-reset:disabled,
.catalog-filter-apply:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.catalog-filter-close:focus-visible,
.catalog-price-grid input:focus-visible,
.catalog-stock-option input:focus-visible,
.catalog-filter-reset:focus-visible,
.catalog-filter-apply:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 3px;
}

.catalog-filter-spinner {
  animation: catalog-filter-spin .8s linear infinite;
}

.catalog-filter-sheet-enter-active,
.catalog-filter-sheet-leave-active {
  transition: opacity .18s ease;
}

.catalog-filter-sheet-enter-active .catalog-filter-sheet,
.catalog-filter-sheet-leave-active .catalog-filter-sheet {
  transition: transform .22s ease, opacity .18s ease;
}

.catalog-filter-sheet-enter-from,
.catalog-filter-sheet-leave-to {
  opacity: 0;
}

.catalog-filter-sheet-enter-from .catalog-filter-sheet,
.catalog-filter-sheet-leave-to .catalog-filter-sheet {
  opacity: 0;
  transform: translateY(20px);
}

@media (min-width: 769px) {
  .catalog-filter-layer {
    place-items: center;
    padding: 20px;
  }

  .catalog-filter-sheet {
    width: min(100%, 460px);
    border-bottom: 1px solid var(--border-light);
    border-radius: 24px;
  }
}

@keyframes catalog-filter-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .catalog-filter-layer,
  .catalog-filter-sheet,
  .catalog-filter-spinner {
    animation: none;
    transition: none;
  }
}
</style>
