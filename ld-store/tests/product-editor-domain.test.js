// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ProductEditorForm from '../src/components/product-editor/ProductEditorForm.vue'
import {
  buildProductCreatePayload,
  buildProductUpdatePayload,
  createProductEditorFormState,
  getProductEditorErrors,
  getProductFinalPrice,
  getPurchaseLimitSummary
} from '../src/composables/product-editor/useProductEditor'
import {
  hasExpectedProductState,
  isUncertainMutationResult,
  reconcileByPolling
} from '../src/composables/product-editor/useSubmissionReconciliation'

function validForm(overrides = {}) {
  return createProductEditorFormState({
    name: '测试物品',
    description: '这是一段长度足够的物品描述',
    categoryId: 3,
    price: '100',
    discount: 0.8,
    imageUrl: 'https://images.example.com/product',
    stock: '5',
    purchaseLimitType: 'per_user',
    maxPurchaseQuantity: '2',
    purchaseLimitPeriodDays: 7,
    ...overrides
  })
}

describe('product editor domain', () => {
  it('normalizes create/update payloads without leaking unrelated state', () => {
    const createPayload = buildProductCreatePayload(validForm())
    expect(createPayload).toMatchObject({
      name: '测试物品', categoryId: 3, price: 100, discount: 0.8, stock: 5,
      purchaseLimitType: 'per_user', maxPurchaseQuantity: 2, purchaseLimitPeriodDays: 7
    })
    expect(createPayload).not.toHaveProperty('submissionToken')

    const updatePayload = buildProductUpdatePayload(validForm({
      productType: 'cdk', sharedCdkEnabled: true, sharedCdkCode: 'SHARED', isTestMode: true
    }), 'cdk', { includeTestMode: false })
    expect(updatePayload).toMatchObject({ sharedCdkEnabled: true, sharedCdkCode: 'SHARED' })
    expect(updatePayload).not.toHaveProperty('isTestMode')
    expect(updatePayload).not.toHaveProperty('cdkCodes')
  })

  it('keeps price, inventory and purchase-limit rules in one typed boundary', () => {
    const form = validForm()
    expect(getProductEditorErrors(form)).toMatchObject({
      name: '', description: '', price: '', discount: '', imageUrl: '', stock: '',
      maxPurchaseQuantity: '', purchaseLimitPeriodDays: ''
    })
    expect(getProductFinalPrice(form)).toBe(80)
    expect(getPurchaseLimitSummary(form)).toBe('每位用户最近 7 天 2 件')
    expect(getProductEditorErrors(validForm({ stock: '0' }))).toMatchObject({ stock: '库存必须是大于 0 的整数' })
    expect(getProductEditorErrors(validForm({ stock: '0' }), { minimumStock: 0 })).toMatchObject({ stock: '' })
  })

  it('renders shared labelled fields and emits typed interaction boundaries', async () => {
    const wrapper = mount(ProductEditorForm, {
      props: {
        modelValue: validForm(),
        descMode: 'write',
        categories: [{ id: 3, name: 'AI' }],
        errors: {}
      },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } }
    })
    expect(wrapper.get('label[for="product-editor-name"]').text()).toContain('物品名称')
    expect(wrapper.get('button[aria-pressed="true"]').text()).toBe('AI')
    await wrapper.get('#product-editor-name').setValue('更新名称')
    expect(wrapper.emitted('touched')?.[0]).toEqual(['name'])
  })
})

describe('submission reconciliation', () => {
  it('classifies only transport-uncertain failures for polling', () => {
    expect(isUncertainMutationResult({ success: false, status: 0, error: '请求超时', aborted: false, kind: 'network' })).toBe(true)
    expect(isUncertainMutationResult({ success: false, status: 400, error: '参数错误', aborted: false, kind: 'http' })).toBe(false)
  })

  it('polls within a bounded retry budget and confirms the expected product state', async () => {
    const values = [null, { name: '旧名称' }, {
      name: '测试物品', description: '这是一段长度足够的物品描述', categoryId: 3,
      price: 100, discount: 0.8, imageUrl: 'https://images.example.com/product', stock: 5,
      purchaseTrustLevel: 0, purchaseLimitConfig: { mode: 'per_user', quantity: 2, periodDays: 7 }
    }]
    const expected = buildProductUpdatePayload(validForm(), 'normal')
    const wait = vi.fn(async () => {})
    const result = await reconcileByPolling(
      async () => values.shift() ?? null,
      product => hasExpectedProductState(product, expected, 'normal'),
      { retries: 3, intervalMs: 10, wait }
    )
    expect(result.confirmed).toBe(true)
    expect(wait).toHaveBeenCalledTimes(2)
  })
})
