import { computed, ref, type Ref } from 'vue'
import { validatePrice, validateProductDescription, validateProductName } from '@/utils/security'
import {
  getProductImageUrlError,
  preloadProductImage
} from '@/utils/productImageValidation'
import type {
  ProductCreatePayload,
  ProductEditorFormState,
  ProductEditorProductType,
  ProductUpdatePayload
} from '@/contracts/commerce'

export interface ProductEditorOptions {
  minimumStock?: number
  requireCdkCodes?: boolean
}

export interface ProductEditorErrors {
  name: string
  description: string
  price: string
  discount: string
  imageUrl: string
  stock: string
  cdkCodes: string
  maxPurchaseQuantity: string
  purchaseLimitPeriodDays: string
}

export function createProductEditorFormState(
  overrides: Partial<ProductEditorFormState> = {}
): ProductEditorFormState {
  return {
    name: '',
    description: '',
    categoryId: null,
    price: '',
    discount: 1,
    imageUrl: '',
    productType: 'normal',
    stock: '',
    purchaseTrustLevel: 0,
    cdkCodes: '',
    sharedCdkEnabled: false,
    sharedCdkCode: '',
    isTestMode: false,
    purchaseLimitType: 'none',
    maxPurchaseQuantity: '',
    purchaseLimitPeriodDays: 0,
    ...overrides
  }
}

function numericError(value: string | number, minimum: number, maximum: number, label: string): string {
  const raw = String(value ?? '').trim()
  if (!raw) return `请输入${label}`
  const parsed = Number(raw)
  if (!Number.isInteger(parsed) || parsed < minimum) {
    return minimum === 0
      ? `${label}必须是大于等于 0 的整数`
      : `${label}必须是大于 0 的整数`
  }
  if (parsed > maximum) return `${label}不能超过 ${maximum}`
  return ''
}

export function getProductEditorErrors(
  form: ProductEditorFormState,
  options: ProductEditorOptions = {}
): ProductEditorErrors {
  const minimumStock = options.minimumStock ?? 1
  const nameResult = validateProductName(form.name)
  const descriptionResult = validateProductDescription(form.description)
  const priceResult = validatePrice(form.price)
  const discount = Number(form.discount)
  const cdkSource = form.sharedCdkEnabled ? form.sharedCdkCode : form.cdkCodes
  const cdkLines = String(cdkSource || '').split('\n').map(value => value.trim()).filter(Boolean)

  let cdkCodes = ''
  if (form.productType === 'cdk') {
    if (form.sharedCdkEnabled && cdkLines.length === 0) cdkCodes = '请输入共享 CDK 卡密'
    else if (form.sharedCdkEnabled && options.requireCdkCodes && cdkLines.length !== 1) cdkCodes = '共享卡密模式下只能填写 1 个 CDK 卡密'
    else if (!form.sharedCdkEnabled && options.requireCdkCodes && cdkLines.length === 0) cdkCodes = '请至少填写 1 个 CDK 卡密'
  }

  let purchaseLimitPeriodDays = ''
  if (form.purchaseLimitType === 'per_user') {
    const raw = String(form.purchaseLimitPeriodDays ?? '').trim()
    const period = Number(raw || 0)
    if (!raw) purchaseLimitPeriodDays = '请输入滚动周期'
    else if (period !== 0 && (!Number.isInteger(period) || period < 1 || period > 365)) {
      purchaseLimitPeriodDays = '滚动周期必须是 1-365 天之间的整数'
    }
  }

  return {
    name: nameResult.valid ? '' : (nameResult.error || '物品名称无效'),
    description: descriptionResult.valid ? '' : (descriptionResult.error || '物品描述无效'),
    price: priceResult.valid ? '' : (priceResult.error || '价格无效'),
    discount: Number.isFinite(discount) && discount >= 0.01 && discount <= 1
      ? ''
      : (String(form.discount ?? '').trim() ? '折扣范围需在 0.01-1 之间' : '请填写折扣'),
    imageUrl: getProductImageUrlError(form.imageUrl),
    stock: form.productType === 'normal'
      ? numericError(form.stock, minimumStock, 1_000_000, '库存')
      : '',
    cdkCodes,
    maxPurchaseQuantity: form.purchaseLimitType === 'none'
      ? ''
      : numericError(form.maxPurchaseQuantity, 1, 1_000, '购买上限'),
    purchaseLimitPeriodDays
  }
}

export function getProductFinalPrice(form: ProductEditorFormState): number {
  return (Number.parseFloat(form.price) || 0) * (Number.parseFloat(String(form.discount)) || 1)
}

export function getPurchaseLimitSummary(form: ProductEditorFormState): string {
  if (form.productType === 'cdk' && form.sharedCdkEnabled) return '每位用户永久累计 1 件'
  const quantity = Number(form.maxPurchaseQuantity || 0)
  if (form.purchaseLimitType === 'per_order' && quantity > 0) return `每单 ${quantity} 件`
  if (form.purchaseLimitType === 'per_user' && quantity > 0) {
    const periodDays = Number(form.purchaseLimitPeriodDays || 0)
    return periodDays > 0
      ? `每位用户最近 ${periodDays} 天 ${quantity} 件`
      : `每位用户永久累计 ${quantity} 件`
  }
  return '不限制'
}

function basePayload(form: ProductEditorFormState) {
  return {
    name: form.name.trim(),
    categoryId: Number(form.categoryId),
    description: form.description.trim(),
    price: Number.parseFloat(form.price),
    discount: Number.parseFloat(String(form.discount)) || 1,
    imageUrl: form.imageUrl.trim(),
    purchaseTrustLevel: Number(form.purchaseTrustLevel) || 0,
    purchaseLimitType: form.purchaseLimitType,
    maxPurchaseQuantity: form.purchaseLimitType === 'none' ? 0 : Number(form.maxPurchaseQuantity),
    purchaseLimitPeriodDays: form.purchaseLimitType === 'per_user'
      ? Number(form.purchaseLimitPeriodDays || 0)
      : 0
  }
}

export function buildProductCreatePayload(form: ProductEditorFormState): ProductCreatePayload {
  const payload: ProductCreatePayload = { ...basePayload(form), productType: form.productType }
  if (form.productType === 'normal') payload.stock = Number(form.stock)
  if (form.productType === 'cdk') {
    payload.sharedCdkEnabled = form.sharedCdkEnabled
    payload.sharedCdkCode = form.sharedCdkEnabled ? form.sharedCdkCode.trim() : ''
    const cdkCodes = form.sharedCdkEnabled ? form.sharedCdkCode.trim() : form.cdkCodes.trim()
    if (cdkCodes) payload.cdkCodes = cdkCodes
    if (form.isTestMode) payload.isTestMode = true
  }
  return payload
}

export function buildProductUpdatePayload(
  form: ProductEditorFormState,
  productType: ProductEditorProductType,
  options: { includeTestMode?: boolean } = {}
): ProductUpdatePayload {
  const payload: ProductUpdatePayload = basePayload(form)
  if (productType === 'normal') payload.stock = Number(form.stock)
  if (productType === 'cdk') {
    payload.sharedCdkEnabled = form.sharedCdkEnabled
    payload.sharedCdkCode = form.sharedCdkEnabled ? form.sharedCdkCode.trim() : ''
    if (options.includeTestMode) payload.isTestMode = form.isTestMode
  }
  return payload
}

export function useProductEditor(form: Ref<ProductEditorFormState>, options: ProductEditorOptions = {}) {
  const imageValidating = ref(false)
  const imageValidated = ref(false)
  const imageLoadError = ref('')
  const imagePreviewUrl = ref('')
  const lastValidatedUrl = ref('')
  let sequence = 0
  let pending: Promise<boolean> | null = null
  let pendingUrl = ''

  const errors = computed(() => getProductEditorErrors(form.value, options))
  const finalPrice = computed(() => getProductFinalPrice(form.value))
  const purchaseLimitSummary = computed(() => getPurchaseLimitSummary(form.value))

  function resetImageValidation() {
    sequence += 1
    pending = null
    pendingUrl = ''
    imageValidating.value = false
    imageValidated.value = false
    imageLoadError.value = ''
    imagePreviewUrl.value = ''
    lastValidatedUrl.value = ''
  }

  async function validateImageLoad(): Promise<boolean> {
    const url = form.value.imageUrl.trim()
    if (!url || errors.value.imageUrl) {
      resetImageValidation()
      return false
    }
    if (url === lastValidatedUrl.value && imageValidated.value) return true
    if (pending && pendingUrl === url) return pending

    const currentSequence = ++sequence
    pendingUrl = url
    imageValidating.value = true
    imageValidated.value = false
    imageLoadError.value = ''
    imagePreviewUrl.value = ''

    let validation: Promise<boolean> = Promise.resolve(false)
    validation = (async () => {
      try {
        await preloadProductImage(url)
        if (currentSequence !== sequence || form.value.imageUrl.trim() !== url) return false
        imageValidated.value = true
        imagePreviewUrl.value = url
        lastValidatedUrl.value = url
        return true
      } catch {
        if (currentSequence !== sequence || form.value.imageUrl.trim() !== url) return false
        imageLoadError.value = '图片无法加载，请检查链接是否有效'
        lastValidatedUrl.value = ''
        return false
      } finally {
        if (currentSequence === sequence) imageValidating.value = false
        if (pending === validation) {
          pending = null
          pendingUrl = ''
        }
      }
    })()
    pending = validation
    return validation
  }

  function onPreviewError() {
    sequence += 1
    imageLoadError.value = '图片加载失败，请检查链接是否有效'
    imagePreviewUrl.value = ''
    imageValidated.value = false
    lastValidatedUrl.value = ''
  }

  return {
    errors,
    finalPrice,
    purchaseLimitSummary,
    imageValidating,
    imageValidated,
    imageLoadError,
    imagePreviewUrl,
    lastValidatedUrl,
    resetImageValidation,
    validateImageLoad,
    onPreviewError
  }
}
