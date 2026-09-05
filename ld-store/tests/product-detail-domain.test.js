// @vitest-environment jsdom
/* global document, MouseEvent, KeyboardEvent */

import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProductPurchasePanel from '../src/components/product-detail/ProductPurchasePanel.vue'
import { useProductComments } from '../src/composables/product-detail/useProductComments'
import { useProductDetail } from '../src/composables/product-detail/useProductDetail'
import { useProductInteractions } from '../src/composables/product-detail/useProductInteractions'

afterEach(() => {
  document.body.style.overflow = ''
})

function createDetailContext(overrides = {}) {
  return {
    product: ref({
      id: 42,
      name: '可兑换物品',
      productType: 'normal',
      price: '100',
      discount: 0.8,
      availableStock: 5,
      sellerUserId: 9,
      purchaseTrustLevel: 2,
      ...overrides
    }),
    isLoggedIn: ref(true),
    userId: ref(7),
    trustLevel: ref(3)
  }
}

function purchasePanelProps(overrides = {}) {
  return {
    isStore: false,
    isPlatformOrder: true,
    isLegacyLink: false,
    isCdk: false,
    isOutOfStock: false,
    isTestMode: false,
    isSeller: false,
    maintenanceBlocked: false,
    ownProductBlocked: false,
    purchaseLimitReached: false,
    canPurchase: true,
    isLoggedIn: true,
    trustAllowed: true,
    purchaseTrustLevel: 0,
    purchasing: false,
    canEnterCheckout: true,
    restockSubscribed: false,
    restockBusy: false,
    restockButtonText: '到货提醒',
    ...overrides
  }
}

describe('typed product detail domain', () => {
  it('keeps price, trust, seller and stock checkout rules in one composable', () => {
    const context = createDetailContext()
    const detail = useProductDetail(context)

    expect(detail.finalPrice.value).toBe('80.00')
    expect(detail.hasDiscount.value).toBe(true)
    expect(detail.canEnterCheckout.value).toBe(true)

    context.trustLevel.value = 1
    expect(detail.canPurchaseByTrustLevel.value).toBe(false)
    expect(detail.canEnterCheckout.value).toBe(false)

    context.trustLevel.value = 3
    context.userId.value = 9
    expect(detail.isOwnProductPurchaseBlocked.value).toBe(true)
    expect(detail.canEnterCheckout.value).toBe(false)

    context.product.value.isTestMode = true
    expect(detail.canEnterCheckout.value).toBe(true)

    context.product.value.availableStock = 0
    expect(detail.isOutOfStock.value).toBe(true)
    expect(detail.canEnterCheckout.value).toBe(false)
  })

  it('renders mutually exclusive purchase states and emits only enabled actions', async () => {
    const wrapper = mount(ProductPurchasePanel, { props: purchasePanelProps() })
    expect(wrapper.get('.buy-btn').text()).toBe('立即兑换')
    expect(wrapper.text()).toContain('数量与优惠券将在下一步确认')
    await wrapper.get('.buy-btn').trigger('click')
    expect(wrapper.emitted('buy')).toHaveLength(1)

    await wrapper.setProps(purchasePanelProps({ isOutOfStock: true, isCdk: true, canEnterCheckout: false }))
    expect(wrapper.text()).toContain('已售罄')
    expect(wrapper.text()).toContain('到货提醒')

    await wrapper.setProps(purchasePanelProps({ trustAllowed: false, purchaseTrustLevel: 3, canEnterCheckout: false }))
    expect(wrapper.get('.buy-btn').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('需达到 TL3')
  })

  it('isolates request scopes, aborts stale work and releases loading state', () => {
    const comments = useProductComments()
    comments.activate()
    const stale = comments.beginRequest('comments')
    const current = comments.beginRequest('comments')
    const replies = comments.beginRequest('replies:42')

    expect(stale.signal.aborted).toBe(true)
    expect(comments.isCurrent('comments', current)).toBe(true)
    expect(comments.isCurrent('replies:42', replies)).toBe(true)
    comments.commentReplyLoadingMap.value[42] = true

    comments.deactivate()
    expect(current.signal.aborted).toBe(true)
    expect(replies.signal.aborted).toBe(true)
    expect(comments.loading.value).toBe(false)
    expect(comments.commentReplyLoadingMap.value).toEqual({})
    expect(comments.ownsRequest('comments', current)).toBe(false)
  })

  it('owns document listeners and restores body scroll when deactivated', () => {
    const modalOpen = ref(false)
    const onEscape = vi.fn()
    const onDocumentClick = vi.fn()
    const interactions = useProductInteractions({
      hasOpenModal: () => modalOpen.value,
      onEscape,
      onDocumentClick
    })

    interactions.activate()
    document.dispatchEvent(new MouseEvent('click'))
    expect(onDocumentClick).toHaveBeenCalledTimes(1)

    modalOpen.value = true
    interactions.syncModalState()
    expect(document.body.style.overflow).toBe('hidden')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onEscape).toHaveBeenCalledTimes(1)

    interactions.deactivate()
    expect(document.body.style.overflow).toBe('')
    document.dispatchEvent(new MouseEvent('click'))
    expect(onDocumentClick).toHaveBeenCalledTimes(1)
  })
})
