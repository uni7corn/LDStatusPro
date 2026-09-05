<template>
  <form v-if="variant === 'seller'" class="seller-delivery-form" @submit.prevent="emit('submit')">
    <div><label :for="inputId">填写发货内容</label><p>{{ hint }}</p></div>
    <textarea :id="inputId" :value="modelValue" rows="3" :placeholder="placeholder" @input="updateValue" />
    <div><button type="button" class="seller-row-secondary" :disabled="submitting" @click="emit('cancel')">取消</button><button type="submit" class="seller-row-primary" :disabled="!modelValue.trim() || submitting">{{ submitting ? '发货中...' : '确认发货' }}</button></div>
  </form>
  <form v-else class="deliver-form" @submit.prevent="emit('submit')" @click.stop>
    <textarea :id="inputId" :value="modelValue" class="deliver-input" rows="3" :placeholder="placeholder" @input="updateValue" />
    <div class="deliver-actions"><button type="button" class="action-btn cancel-btn" :disabled="submitting" @click="emit('cancel')">取消</button><button type="submit" class="action-btn pay-btn" :disabled="!modelValue.trim() || submitting">确认发货</button></div>
    <div class="deliver-hint">{{ hint }}</div>
  </form>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  inputId: string
  placeholder: string
  hint: string
  submitting?: boolean
  variant?: 'buyer' | 'seller'
}>(), { submitting: false, variant: 'buyer' })
const emit = defineEmits<{ 'update:modelValue': [value: string]; submit: []; cancel: [] }>()
function updateValue(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}
</script>

<style scoped>
.deliver-form { margin-top: 12px; padding: 12px; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: 12px; }
.deliver-input { box-sizing: border-box; width: 100%; min-height: 72px; padding: 10px 12px; color: var(--text-primary); background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; resize: vertical; font-size: 13px; }
.deliver-input:focus { border-color: var(--color-primary); outline: none; }
.deliver-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
.deliver-hint { margin-top: 8px; color: var(--text-tertiary); font-size: 12px; }
.action-btn { min-height: 34px; padding: 0 14px; border: 0; border-radius: 10px; cursor: pointer; text-decoration: none; font-size: 13px; font-weight: 600; transition: background-color .2s, color .2s, opacity .2s; }
.action-btn:disabled { cursor: not-allowed; opacity: .6; }
.action-btn.cancel-btn { color: var(--text-tertiary); background: var(--bg-secondary); }
.action-btn.cancel-btn:hover { color: var(--text-secondary); background: var(--bg-tertiary); }
.action-btn.pay-btn { color: var(--palette-hex-ffffff); background: linear-gradient(135deg, var(--color-primary), var(--color-primary-hover)); }
.action-btn.pay-btn:hover { opacity: .9; }
.seller-delivery-form { display: grid; grid-template-columns: minmax(150px, .7fr) minmax(260px, 1.5fr) auto; align-items: end; gap: 14px; padding: 16px; border: 1px solid color-mix(in srgb, var(--seller-jade) 28%, var(--seller-border)); border-radius: 12px; background: var(--seller-surface-soft); }
.seller-delivery-form label { color: var(--seller-ink); font-size: 13px; font-weight: 700; }
.seller-delivery-form p { margin: 4px 0 0; color: var(--seller-muted); font-size: 11px; line-height: 1.45; }
.seller-delivery-form textarea { width: 100%; min-height: 78px; padding: 10px 12px; color: var(--seller-ink); background: var(--seller-surface); border: 1px solid var(--seller-border); border-radius: 10px; resize: vertical; }
.seller-delivery-form > div:last-child { display: flex; align-items: center; gap: 7px; }
.seller-row-primary, .seller-row-secondary { display: inline-flex; min-height: 36px; align-items: center; justify-content: center; gap: 6px; padding: 0 10px; color: var(--seller-muted); background: var(--seller-surface); border: 1px solid var(--seller-border); border-radius: 9px; font-size: 12px; font-weight: 700; }
.seller-row-primary { color: var(--palette-hex-ffffff); background: var(--seller-navy); border-color: var(--seller-navy); }
@media (max-width: 900px) { .seller-delivery-form { grid-template-columns: 1fr; align-items: stretch; } .seller-delivery-form > div:last-child { justify-content: flex-end; } }
@media (max-width: 767px) { .seller-delivery-form { margin-top: 15px; padding: 14px; } .seller-delivery-form > div:last-child > * { min-height: 44px; flex: 1; } }
</style>
