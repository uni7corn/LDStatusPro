import { computed, ref, type Ref } from 'vue'
import type { Product } from '@/contracts/catalog'
import { formatPrice } from '@/utils/format'
import {
  isCdkProduct,
  isLegacyLinkProduct,
  isOutOfStock as isProductOutOfStock,
  isPlatformOrderProduct,
  isStoreProduct
} from '@/utils/shopProduct'
import {
  formatPurchaseLimitLabel,
  formatPurchaseLimitReleaseTime,
  getPurchaseLimit,
  isPurchaseLimitReached
} from '@/utils/purchaseLimit'
import { isMaintenanceFeatureEnabled, isRestrictedMaintenanceMode } from '@/config/maintenance'

export type DetailProduct = Product & Record<string, unknown>

interface ProductDetailContext {
  product: Ref<DetailProduct | null>
  isLoggedIn: Ref<boolean>
  userId: Ref<string | number | null | undefined>
  trustLevel: Ref<string | number | null | undefined>
}

const COVER_FALLBACKS = [
  'linear-gradient(135deg, #e0f2fe, #bae6fd)',
  'linear-gradient(135deg, #fce7f3, #fbcfe8)',
  'linear-gradient(135deg, #d1fae5, #a7f3d0)',
  'linear-gradient(135deg, #fef3c7, #fde68a)',
  'linear-gradient(135deg, #ede9fe, #ddd6fe)',
  'linear-gradient(135deg, #ffedd5, #fed7aa)'
]

export function useProductDetail(context: ProductDetailContext) {
  const coverAspectRatio = ref<number | null>(null)
  let coverProbeRequestId = 0

  const isCdk = computed(() => isCdkProduct(context.product.value))
  const isStore = computed(() => isStoreProduct(context.product.value))
  const isLegacyLink = computed(() => isLegacyLinkProduct(context.product.value))
  const isPlatformOrder = computed(() => isPlatformOrderProduct(context.product.value))
  const supportsComments = computed(() => isPlatformOrder.value)
  const isLandscapeDetailLayout = computed(() => {
    const ratio = Number(coverAspectRatio.value)
    return Number.isFinite(ratio) && ratio > 1
  })
  const isTestMode = computed(() => Boolean(context.product.value?.isTestMode))
  const isSeller = computed(() => Boolean(
    context.product.value
    && context.userId.value !== null
    && context.userId.value !== undefined
    && String(context.userId.value) === String(context.product.value.sellerUserId)
  ))
  const viewerTrustLevel = computed(() => {
    const parsed = Number.parseInt(String(context.trustLevel.value ?? 0), 10)
    return Number.isInteger(parsed) ? parsed : 0
  })
  const price = computed(() => Number.parseFloat(String(context.product.value?.price ?? '')) || 0)
  const discount = computed(() => Number.parseFloat(String(context.product.value?.discount ?? '')) || 1)
  const hasDiscount = computed(() => discount.value < 1)
  const discountPercent = computed(() => Math.round((1 - discount.value) * 100))
  const finalPrice = computed(() => formatPrice(price.value * discount.value))
  const originalPrice = computed(() => formatPrice(price.value))
  const isOutOfStock = computed(() => isProductOutOfStock(context.product.value))
  const canPurchase = computed(() => context.product.value?.canPurchase !== false)
  const soldCount = computed(() => Number.parseInt(String(context.product.value?.soldCount ?? 0), 10) || 0)
  const purchaseLimit = computed(() => getPurchaseLimit(context.product.value))
  const purchaseLimitReached = computed(() => isPurchaseLimitReached(purchaseLimit.value))
  const purchaseLimitReservedQuantity = computed(() => Number(purchaseLimit.value.reservedQuantity || 0))
  const purchaseLimitReleaseText = computed(() => purchaseLimit.value.periodDays > 0
    ? formatPurchaseLimitReleaseTime(purchaseLimit.value.nextAvailableAt)
    : '')
  const purchaseTrustLevel = computed(() => {
    const raw = Number(context.product.value?.purchaseTrustLevel ?? 0)
    return Number.isInteger(raw) && raw >= 0 ? Math.min(raw, 4) : 0
  })
  const canPurchaseByTrustLevel = computed(() => viewerTrustLevel.value >= purchaseTrustLevel.value)
  const purchaseTrustBlockMessage = computed(() => {
    if (purchaseTrustLevel.value <= 0 || canPurchaseByTrustLevel.value) return ''
    if (!context.isLoggedIn.value) return `该商品需登录且信任等级达到 TL${purchaseTrustLevel.value} 才可兑换`
    return `当前账号信任等级为 TL${viewerTrustLevel.value}，需达到 TL${purchaseTrustLevel.value} 才可兑换`
  })
  const exchangeQuantityText = computed(() => isOutOfStock.value
    ? '当前无货'
    : formatPurchaseLimitLabel(purchaseLimit.value, { loggedIn: context.isLoggedIn.value }))
  const purchaseAccountText = computed(() => {
    if (purchaseTrustLevel.value <= 0) return context.isLoggedIn.value ? '无等级限制' : '登录后即可兑换'
    if (!context.isLoggedIn.value) return `需 TL${purchaseTrustLevel.value} · 登录后核验`
    return canPurchaseByTrustLevel.value
      ? `需 TL${purchaseTrustLevel.value} · 当前 TL${viewerTrustLevel.value}，已满足`
      : `需 TL${purchaseTrustLevel.value} · 当前 TL${viewerTrustLevel.value}，差 ${purchaseTrustLevel.value - viewerTrustLevel.value} 级`
  })
  const purchaseAccountTone = computed(() => {
    if (!context.isLoggedIn.value) return ''
    return purchaseTrustLevel.value <= 0 || canPurchaseByTrustLevel.value ? 'is-satisfied' : 'is-blocked'
  })
  const deliveryConditionText = computed(() => isCdk.value ? '支付成功后自动发放' : '支付后联系卖家履约')
  const isOwnProductPurchaseBlocked = computed(() => isPlatformOrder.value && isSeller.value && !isTestMode.value)
  const isOrderCreationMaintenanceBlocked = computed(() => isRestrictedMaintenanceMode() && !isMaintenanceFeatureEnabled('orderCreate'))
  const canEnterCheckout = computed(() => isPlatformOrder.value
    && !isOutOfStock.value
    && !purchaseLimitReached.value
    && !isOrderCreationMaintenanceBlocked.value
    && canPurchase.value
    && !isOwnProductPurchaseBlocked.value
    && !(isCdk.value && isTestMode.value && !isSeller.value)
    && (!context.isLoggedIn.value || canPurchaseByTrustLevel.value))
  const maintenancePurchaseHint = computed(() => isOrderCreationMaintenanceBlocked.value
    ? '因 LinuxDo Credit 积分服务维护中，当前暂不支持创建新订单。'
    : '')
  const coverStyle = computed<Record<string, string>>(() => {
    if (context.product.value?.imageUrl) return {} as Record<string, string>
    const id = Number(context.product.value?.id || 0)
    return { background: COVER_FALLBACKS[Math.abs(id) % COVER_FALLBACKS.length] ?? COVER_FALLBACKS[0] }
  })

  function setCoverAspectRatio(width: unknown, height: unknown) {
    const naturalWidth = Number(width)
    const naturalHeight = Number(height)
    coverAspectRatio.value = Number.isFinite(naturalWidth) && Number.isFinite(naturalHeight)
      && naturalWidth > 0 && naturalHeight > 0
      ? naturalWidth / naturalHeight
      : null
  }

  async function syncCoverAspectRatio(imageUrl: unknown) {
    const requestId = ++coverProbeRequestId
    coverAspectRatio.value = null
    if (!imageUrl || typeof window === 'undefined') return
    const image = new window.Image()
    image.decoding = 'async'
    image.src = String(imageUrl)
    if (image.complete && image.naturalWidth > 0 && image.naturalHeight > 0) {
      if (requestId === coverProbeRequestId) setCoverAspectRatio(image.naturalWidth, image.naturalHeight)
      return
    }
    await new Promise<void>((resolve) => {
      image.onload = () => {
        if (requestId === coverProbeRequestId) setCoverAspectRatio(image.naturalWidth, image.naturalHeight)
        resolve()
      }
      image.onerror = () => {
        if (requestId === coverProbeRequestId) coverAspectRatio.value = null
        resolve()
      }
    })
  }

  function stop() {
    coverProbeRequestId += 1
  }

  return {
    coverAspectRatio, isCdk, isStore, isLegacyLink, isPlatformOrder, supportsComments,
    isLandscapeDetailLayout, isTestMode, isSeller, viewerTrustLevel, hasDiscount, discountPercent,
    finalPrice, originalPrice, isOutOfStock, canPurchase, soldCount, purchaseLimit,
    purchaseLimitReached, purchaseLimitReservedQuantity, purchaseLimitReleaseText, purchaseTrustLevel,
    canPurchaseByTrustLevel, purchaseTrustBlockMessage, exchangeQuantityText, purchaseAccountText,
    purchaseAccountTone, deliveryConditionText, isOwnProductPurchaseBlocked,
    isOrderCreationMaintenanceBlocked, canEnterCheckout, maintenancePurchaseHint, coverStyle,
    setCoverAspectRatio, syncCoverAspectRatio, stop
  }
}
