<template>
  <div class="form-card" :class="`is-${variant}`">
    <h2 class="card-title">基本信息</h2>

    <div class="form-group">
      <label class="form-label required" for="product-editor-name">物品名称</label>
      <input
        id="product-editor-name"
        ref="nameInput"
        v-model="model.name"
        type="text"
        class="form-input"
        :class="{ 'input-error': errors.name }"
        placeholder="请输入物品名称（2-50字符）"
        maxlength="50"
        @input="emit('touched', 'name')"
      />
      <p class="form-counter">{{ model.name.length }}/50</p>
      <p v-if="errors.name" class="form-error">{{ errors.name }}</p>
    </div>

    <div class="form-group">
      <div class="form-label-row">
        <label class="form-label required" for="product-editor-description">物品描述</label>
        <div class="desc-mode-tabs" role="group" aria-label="描述模式">
          <button type="button" :class="['desc-mode-tab', { active: descMode === 'write' }]" @click="emit('update:descMode', 'write')">编辑</button>
          <button type="button" :class="['desc-mode-tab', { active: descMode === 'preview' }]" @click="emit('update:descMode', 'preview')">预览</button>
        </div>
      </div>
      <textarea
        v-if="descMode === 'write'"
        id="product-editor-description"
        ref="descriptionInput"
        v-model="model.description"
        class="form-textarea"
        :class="{ 'input-error': errors.description }"
        :placeholder="descriptionPlaceholder"
        rows="4"
        maxlength="1000"
        @input="emit('touched', 'description')"
      ></textarea>
      <div
        v-else
        class="form-textarea-preview markdown-content"
        :class="{ 'is-empty': !descriptionPreview }"
        v-html="descriptionPreview || '暂无内容，切换到「编辑」填写物品描述'"
      ></div>
      <p class="form-hint">支持 Markdown：**加粗**、*斜体*、++下划线++、`代码`；网址和图片语法显示为可点击链接（新窗口打开）</p>
      <p class="form-counter">{{ model.description.length }}/1000</p>
      <p v-if="errors.description" class="form-error">{{ errors.description }}</p>
    </div>

    <div class="form-group">
      <span class="form-label required">物品分类</span>
      <div class="category-select" role="group" aria-label="物品分类">
        <button
          v-for="category in categories"
          :key="category.id || category.name"
          type="button"
          :class="['category-btn', { active: Number(model.categoryId) === Number(category.id) }]"
          :aria-pressed="Number(model.categoryId) === Number(category.id)"
          @click="model.categoryId = category.id"
        >
          {{ category.name }}
        </button>
      </div>
      <p v-if="categoriesLoading" class="form-hint">正在加载物品分类...</p>
      <div v-else-if="categoriesLoadError" class="category-load-error" role="alert">
        <p class="form-error">{{ categoriesLoadError }}</p>
        <button type="button" class="category-retry-btn" @click="emit('retryCategories')">重新加载</button>
      </div>
      <div v-if="isRuzhanCategory" class="category-price-notice">
        <span class="notice-icon">注意</span>
        <span class="notice-text">始皇指导价：入站分类物品<strong>折后价格不得低于 500 LDC</strong></span>
      </div>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label class="form-label required" for="product-editor-price">价格 (LDC)</label>
        <input
          id="product-editor-price"
          ref="priceInput"
          v-model="model.price"
          type="number"
          class="form-input"
          :class="{ 'input-error': errors.price || ruzhanPriceError }"
          placeholder="0.00"
          min="0.01"
          max="99999999"
          step="0.01"
          @input="emit('touched', 'price')"
        />
        <p v-if="errors.price" class="form-error">{{ errors.price }}</p>
        <p v-else-if="ruzhanPriceError" class="form-error">{{ ruzhanPriceError }}</p>
      </div>
      <div class="form-group">
        <label class="form-label" for="product-editor-discount">折扣</label>
        <input
          id="product-editor-discount"
          ref="discountInput"
          v-model="model.discount"
          type="number"
          class="form-input"
          :class="{ 'input-error': errors.discount || ruzhanPriceError }"
          placeholder="1"
          min="0.01"
          max="1"
          step="0.01"
          @input="emit('touched', 'discount')"
        />
        <p v-if="errors.discount" class="form-error">{{ errors.discount }}</p>
        <p v-else class="form-hint">{{ variant === 'publish' ? '范围 0.01-1，0.8 表示8折，1 表示原价' : '范围 0.01-1' }}</p>
      </div>
    </div>
    <div v-if="isRuzhanCategory && finalPrice > 0" class="final-price-display">
      <span class="price-label">折后价格：</span>
      <span class="price-value" :class="{ 'price-error': finalPrice < 500 }">{{ finalPrice.toFixed(2) }} LDC</span>
      <span v-if="finalPrice < 500" class="price-warning">（最低 500 LDC）</span>
    </div>

    <div class="form-group">
      <label class="form-label required" for="product-editor-image">物品图片</label>
      <input
        id="product-editor-image"
        ref="imageInput"
        v-model="model.imageUrl"
        type="url"
        class="form-input"
        :class="{ 'input-error': errors.image }"
        placeholder="https://..."
        :maxlength="MAX_PRODUCT_IMAGE_URL_LENGTH"
        @blur="emit('validateImage')"
        @input="emit('touched', 'image')"
      />
      <p v-if="errors.image" class="form-error">{{ errors.image }}</p>
      <p v-else-if="imageLoadError" class="form-error">{{ imageLoadError }}</p>
      <p v-else-if="imageValidating" class="form-hint loading-hint">正在验证图片...</p>
      <p v-else-if="imageValidated" class="form-hint success-hint">图片验证通过</p>
      <div v-else-if="variant === 'publish'" class="form-hint-with-link">
        <p class="form-hint">推荐尺寸 16:9，必须使用 HTTPS 链接，不支持 linux.do 图床</p>
        <router-link to="/ld-image" target="_blank" class="image-bed-link">没有图床？试试 <strong>士多图床</strong>，即刻上传图片并获取在线链接</router-link>
      </div>
      <p v-else class="form-hint">推荐尺寸 16:9，必须使用 HTTPS 链接，不支持 linux.do 图床</p>
      <div v-if="imagePreviewUrl && !imageLoadError" class="image-preview">
        <img :src="imagePreviewUrl" alt="图片预览" @error="emit('previewError')" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ProductEditorFormState } from '@/contracts/commerce'
import { MAX_PRODUCT_IMAGE_URL_LENGTH } from '@/utils/productImageValidation'

type Field = 'name' | 'description' | 'price' | 'discount' | 'image'
interface CategoryOption { id: string | number; name: string }
interface DisplayErrors { name?: string; description?: string; price?: string; discount?: string; image?: string }

withDefaults(defineProps<{
  variant?: 'publish' | 'edit'
  categories: CategoryOption[]
  categoriesLoading?: boolean
  categoriesLoadError?: string
  descMode: 'write' | 'preview'
  descriptionPreview?: string
  descriptionPlaceholder?: string
  errors?: DisplayErrors
  isRuzhanCategory?: boolean
  ruzhanPriceError?: string | null
  finalPrice?: number
  imageValidating?: boolean
  imageValidated?: boolean
  imageLoadError?: string
  imagePreviewUrl?: string
}>(), {
  variant: 'publish', categoriesLoading: false, categoriesLoadError: '', descriptionPreview: '',
  descriptionPlaceholder: '请输入物品描述（10-1000字符）', errors: () => ({}), isRuzhanCategory: false,
  ruzhanPriceError: '', finalPrice: 0, imageValidating: false, imageValidated: false,
  imageLoadError: '', imagePreviewUrl: ''
})

const model = defineModel<ProductEditorFormState>({ required: true })
const emit = defineEmits<{
  'update:descMode': [value: 'write' | 'preview']
  touched: [field: Field]
  retryCategories: []
  validateImage: []
  previewError: []
}>()
const nameInput = ref<HTMLInputElement | null>(null)
const descriptionInput = ref<HTMLTextAreaElement | null>(null)
const priceInput = ref<HTMLInputElement | null>(null)
const discountInput = ref<HTMLInputElement | null>(null)
const imageInput = ref<HTMLInputElement | null>(null)

function focusField(field: Field) {
  const target = { name: nameInput, description: descriptionInput, price: priceInput, discount: discountInput, image: imageInput }[field].value
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target?.focus({ preventScroll: true })
}

defineExpose({ focusField })
</script>

<style scoped>
.form-card { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 16px; padding: 20px; margin-bottom: 16px; box-shadow: var(--shadow-sm); }
.card-title { margin: 0 0 16px; color: var(--text-primary); font-size: 16px; font-weight: 600; }
.form-group { position: relative; margin-bottom: 16px; }
.form-group:last-child { margin-bottom: 0; }
.form-label { display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 14px; font-weight: 500; }
.form-label.required::after { content: '*'; margin-left: 4px; color: var(--color-danger); }
.form-label-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.form-label-row .form-label { margin-bottom: 0; }
.desc-mode-tabs { display: inline-flex; gap: 2px; padding: 3px; background: var(--bg-secondary); border-radius: 10px; }
.desc-mode-tab { padding: 4px 12px; color: var(--text-secondary); background: none; border: 0; border-radius: 8px; cursor: pointer; font-size: 12px; line-height: 1.4; transition: background-color 0.2s, color 0.2s; }
.desc-mode-tab:hover { color: var(--editor-accent, var(--color-success)); }
.desc-mode-tab.active { color: var(--palette-hex-ffffff); background: var(--editor-accent, var(--color-success)); font-weight: 600; }
.is-edit { --editor-accent: var(--color-primary); }
.form-input, .form-textarea { width: 100%; box-sizing: border-box; padding: 14px 16px; color: var(--text-primary); background: var(--input-bg, var(--bg-secondary)); border: 1px solid var(--border-color, var(--border-light)); border-radius: 12px; outline: none; font-size: 14px; transition: border-color 0.2s, background-color 0.2s; }
.form-textarea { min-height: 100px; resize: vertical; }
.form-input:focus, .form-textarea:focus { border-color: var(--editor-accent, var(--color-success)); background: var(--input-focus-bg, var(--bg-secondary)); }
.input-error { border-color: var(--color-danger); }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.form-counter { position: absolute; right: 12px; bottom: -20px; margin: 0; color: var(--text-tertiary); font-size: 12px; }
.form-hint { margin: 8px 0 0; color: var(--text-tertiary); font-size: 13px; line-height: 1.5; }
.loading-hint { color: var(--color-warning); }
.success-hint { color: var(--color-success); }
.form-error { margin: 8px 0 0; color: var(--color-danger); font-size: 13px; line-height: 1.5; }
.category-select { display: flex; flex-wrap: wrap; gap: 10px; }
.category-btn { min-height: 44px; padding: 10px 18px; color: var(--text-secondary); background: var(--bg-secondary); border: 2px solid transparent; border-radius: 24px; cursor: pointer; font-size: 14px; transition: background-color 0.2s, border-color 0.2s, color 0.2s; }
.category-btn:hover { background: var(--bg-tertiary); }
.category-btn.active { color: var(--color-success); background: var(--color-success-bg); border-color: var(--editor-accent, var(--color-success)); }
.category-load-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; }
.category-load-error .form-error { margin: 0; }
.category-retry-btn { min-height: 44px; padding: 7px 12px; color: var(--color-danger); background: transparent; border: 1px solid var(--color-danger); border-radius: 9px; cursor: pointer; }
.category-price-notice { display: flex; align-items: flex-start; gap: 8px; margin-top: 12px; padding: 10px 14px; background: var(--color-warning-bg, var(--palette-rgba-245-158-11-0p1)); border: 1px solid var(--color-warning, var(--palette-hex-f59e0b)); border-radius: 10px; }
.category-price-notice .notice-text { color: var(--text-secondary); font-size: 13px; line-height: 1.5; }
.category-price-notice strong { color: var(--color-warning); }
.final-price-display { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 12px 0 16px; padding: 10px 14px; background: var(--bg-secondary); border-radius: 10px; }
.price-label { color: var(--text-tertiary); font-size: 13px; }
.price-value { color: var(--color-success); font-size: 16px; font-weight: 600; }
.price-error, .price-warning { color: var(--color-danger); }
.price-warning { font-size: 12px; }
.form-hint-with-link { margin-top: 8px; }
.form-hint-with-link .form-hint { margin: 0 0 6px; }
.image-bed-link { display: block; padding: 10px 12px; color: var(--color-success); background: var(--color-success-bg); border: 1px dashed var(--color-success); border-radius: 10px; text-decoration: none; font-size: 13px; line-height: 1.5; }
.image-preview { margin-top: 12px; overflow: hidden; background: var(--bg-tertiary); border: 1px solid var(--border-light); border-radius: 12px; }
.image-preview img { display: block; width: 100%; max-height: 200px; object-fit: contain; }
.form-textarea-preview { min-height: 100px; padding: 14px 16px; overflow-wrap: anywhere; color: var(--text-primary); background: var(--input-bg, var(--bg-secondary)); border: 1px solid var(--border-color, var(--border-light)); border-radius: 12px; }
.form-textarea-preview.is-empty { color: var(--text-tertiary); }
@media (max-width: 480px) { .form-row { flex-direction: column; gap: 0; } }
</style>
