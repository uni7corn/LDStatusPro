import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parse, compileTemplate } from '@vue/compiler-sfc'

const homeSource = readFileSync(new globalThis.URL('../src/views/Home.vue', import.meta.url), 'utf8')
const productsSource = readFileSync(new globalThis.URL('../src/components/home/ProductsMarketplace.vue', import.meta.url), 'utf8')
const filterSheetSource = readFileSync(new globalThis.URL('../src/components/home/CatalogFilterSheet.vue', import.meta.url), 'utf8')
const buySource = readFileSync(new globalThis.URL('../src/components/home/BuyRequestMarketplace.vue', import.meta.url), 'utf8')
const indexHtml = readFileSync(new globalThis.URL('../index.html', import.meta.url), 'utf8')
const { descriptor } = parse(homeSource)

describe('home marketplace accessibility', () => {
  it('keeps the Home template compilable', () => {
    expect(compileTemplate({
      source: descriptor.template.content,
      filename: 'Home.vue',
      id: 'home-accessibility'
    }).errors).toEqual([])
  })

  it('allows browser zoom and labels both price inputs', () => {
    const viewport = indexHtml.match(/<meta name="viewport" content="([^"]+)">/)?.[1] || ''
    expect(viewport).not.toContain('user-scalable=no')
    expect(viewport).not.toContain('maximum-scale')
    expect(productsSource).toContain('for="home-price-min"')
    expect(productsSource).toContain('for="home-price-max"')
  })

  it('uses native and stateful controls for stock and sort filters', () => {
    expect(productsSource).toContain('type="checkbox"')
    expect(productsSource).toContain(':checked="inStockOnly"')
    expect(productsSource).toContain(':aria-pressed="currentSort === tab.value"')
    expect(productsSource).toContain('id="home-mobile-sort"')
    expect(productsSource).toContain('aria-haspopup="dialog"')
    expect(productsSource).toContain('class="mobile-filter-badge"')
    expect(productsSource).toContain(':aria-label="mobileFilterAriaLabel"')
    expect(productsSource).not.toContain('class="stock-filter" @click')
  })

  it('uses a semantic link for each buy request card', () => {
    expect(buySource).toContain(':to="`/buy-request/${item.id}`"')
    expect(buySource).toContain(':aria-label="`查看求购：${item.title}`"')
    expect(buySource).not.toContain('@click="goBuyRequestDetail(item.id)"')
  })

  it('retains mobile touch targets and visible keyboard focus', () => {
    expect(productsSource).toContain('min-height: 44px;')
    expect(buySource).toContain('.buy-card-link:focus-visible')
    expect(productsSource).toContain('.stock-filter-input:focus-visible + .checkbox')
  })

  it('replaces the three-row mobile filters with one compact toolbar', () => {
    const mobileStyles = productsSource.slice(productsSource.indexOf('@media (max-width: 768px)'))
    expect(mobileStyles).toContain('.sort-section { display: none; }')
    expect(mobileStyles).toContain('.mobile-catalog-toolbar { width: 100%; min-width: 0; display: flex;')
    expect(mobileStyles).toContain('.mobile-sort-control select { width: 100%; min-width: 0; min-height: 44px;')
    expect(mobileStyles).toContain('.mobile-filter-trigger { min-height: 44px;')
    expect(mobileStyles).not.toContain('overflow-x: auto')
  })

  it('gives the mobile filter sheet labels, safe-area spacing, and reduced-motion support', () => {
    expect(filterSheetSource).toContain('role="dialog"')
    expect(filterSheetSource).toContain('aria-modal="true"')
    expect(filterSheetSource).toContain('inputmode="decimal"')
    expect(filterSheetSource).toContain('env(safe-area-inset-bottom, 0px)')
    expect(filterSheetSource).toContain('@media (prefers-reduced-motion: reduce)')
  })
})
