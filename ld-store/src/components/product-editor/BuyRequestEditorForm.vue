<template>
  <form class="publish-form" @submit.prevent="submit">
    <div class="form-card">
      <h3 class="card-title">求购信息</h3>

      <div class="form-group">
        <label class="form-label required" for="buy-request-title">求购标题</label>
        <input
          id="buy-request-title"
          ref="titleInput"
          v-model="form.title"
          type="text"
          class="form-input"
          :class="{ 'input-error': showError('title', titleError) }"
          placeholder="例如：收一个月 Claude 会员"
          maxlength="60"
          @input="touched.title = true"
        />
        <p class="form-counter">{{ form.title.length }}/60</p>
        <p v-if="showError('title', titleError)" class="form-error">{{ titleError }}</p>
      </div>

      <div class="form-group">
        <label class="form-label required" for="buy-request-details">详细需求</label>
        <textarea
          id="buy-request-details"
          ref="detailsInput"
          v-model="form.details"
          class="form-textarea"
          :class="{ 'input-error': showError('details', detailsError) }"
          placeholder="请写清楚具体需求、交付方式、时效要求等（10-2000 字）"
          rows="6"
          maxlength="2000"
          @input="touched.details = true"
        ></textarea>
        <p class="form-counter">{{ form.details.length }}/2000</p>
        <p v-if="showError('details', detailsError)" class="form-error">{{ detailsError }}</p>
      </div>

      <div class="form-group">
        <label class="form-label required" for="buy-request-price">预算价格 (LDC)</label>
        <input
          id="buy-request-price"
          ref="priceInput"
          v-model="form.price"
          type="number"
          class="form-input"
          :class="{ 'input-error': showError('price', priceError) }"
          placeholder="0.00"
          min="0.01"
          max="99999999"
          step="0.01"
          @input="touched.price = true"
        />
        <p v-if="showError('price', priceError)" class="form-error">{{ priceError }}</p>
        <p class="form-hint">发布后可在会话中继续协商，并可随时调价。</p>
      </div>
    </div>

    <div class="form-card buy-safe-card">
      <h3 class="card-title">安全说明</h3>
      <p class="form-hint">平台会展示随机用户名与密码进行沟通，真实信息默认不公开。</p>
      <p class="form-hint">聊天内容会自动检测违禁词，命中后无法发送。</p>
    </div>

    <div class="form-actions">
      <button type="submit" class="submit-btn" :disabled="!canSubmit || submitting">
        {{ submitting ? '发布中...' : '发布求购' }}
      </button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import { validatePrice } from '@/utils/security'
import { createBuyRequestRequest } from '@/services/shop/buyRequestService'

type Field = 'title' | 'details' | 'price'

const emit = defineEmits<{ busy: [value: boolean] }>()
const router = useRouter()
const toast = useToast()
const submitting = ref(false)
const attempted = ref(false)
const form = reactive({ title: '', details: '', price: '' })
const touched = reactive<Record<Field, boolean>>({ title: false, details: false, price: false })
const titleInput = ref<HTMLInputElement | null>(null)
const detailsInput = ref<HTMLTextAreaElement | null>(null)
const priceInput = ref<HTMLInputElement | null>(null)

const titleError = computed(() => {
  const value = form.title.trim()
  if (!value) return '请输入求购标题'
  return value.length < 2 || value.length > 60 ? '标题需要 2-60 个字符' : ''
})
const detailsError = computed(() => {
  const value = form.details.trim()
  if (!value) return '请输入详细需求'
  return value.length < 10 || value.length > 2000 ? '详细需求需要 10-2000 个字符' : ''
})
const priceError = computed(() => {
  const result = validatePrice(form.price)
  return result.valid ? '' : (result.error || '价格无效')
})
const canSubmit = computed(() => !titleError.value && !detailsError.value && !priceError.value)

function showError(field: Field, error: string) {
  return Boolean(error) && (touched[field] || attempted.value)
}

function focus(field: Field) {
  const target = { title: titleInput, details: detailsInput, price: priceInput }[field].value
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target?.focus({ preventScroll: true })
}

async function submit() {
  attempted.value = true
  const firstError = ([['title', titleError.value], ['details', detailsError.value], ['price', priceError.value]] as const)
    .find(([, error]) => Boolean(error))
  if (firstError) {
    toast.error(firstError[1])
    focus(firstError[0])
    return
  }

  submitting.value = true
  emit('busy', true)
  try {
    const result = await createBuyRequestRequest({
      title: form.title.trim(),
      details: form.details.trim(),
      price: Number.parseFloat(form.price)
    })
    if (!result.success) {
      toast.error(result.error || '发布求购失败')
      return
    }
    toast.success('求购发布成功，已提交管理员审核')
    await router.push('/user/buy-requests')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '发布求购失败')
  } finally {
    submitting.value = false
    emit('busy', false)
  }
}
</script>

<style scoped>
.publish-form { display: flex; flex-direction: column; gap: 0; }
.form-card { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 16px; padding: 20px; margin-bottom: 16px; box-shadow: var(--shadow-sm); }
.card-title { margin: 0 0 16px; color: var(--text-primary); font-size: 16px; font-weight: 600; }
.form-group { position: relative; margin-bottom: 16px; }
.form-group:last-child { margin-bottom: 0; }
.form-label { display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 14px; font-weight: 500; }
.form-label.required::after { content: '*'; margin-left: 4px; color: var(--color-danger); }
.form-input, .form-textarea { width: 100%; box-sizing: border-box; padding: 14px 16px; color: var(--text-primary); background: var(--input-bg); border: 1px solid var(--border-color); border-radius: 12px; outline: none; font-size: 14px; transition: border-color 0.2s, background-color 0.2s; }
.form-textarea { min-height: 100px; resize: vertical; }
.form-input:focus, .form-textarea:focus { border-color: var(--color-success); background: var(--input-focus-bg); }
.input-error { border-color: var(--color-danger); }
.form-counter { position: absolute; right: 12px; bottom: -20px; margin: 0; color: var(--text-tertiary); font-size: 12px; }
.form-error { margin: 8px 0 0; color: var(--color-danger); font-size: 13px; line-height: 1.5; }
.form-hint { margin: 8px 0 0; color: var(--text-tertiary); font-size: 13px; line-height: 1.5; }
.buy-safe-card .form-hint { margin-top: 6px; }
.form-actions { display: flex; justify-content: flex-end; margin-top: 8px; }
.submit-btn { min-height: 48px; padding: 14px 32px; border: none; border-radius: 12px; color: var(--palette-hex-ffffff); background: var(--color-success); cursor: pointer; font-size: 15px; font-weight: 600; }
.submit-btn:disabled { cursor: not-allowed; opacity: 0.55; }
@media (max-width: 480px) { .submit-btn { width: 100%; } }
</style>
