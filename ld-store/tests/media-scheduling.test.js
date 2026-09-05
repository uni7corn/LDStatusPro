import { readFileSync } from 'node:fs'
import { URL } from 'node:url'
import { describe, expect, it } from 'vitest'
import { compileTemplate, parse } from '@vue/compiler-sfc'

const productCardSource = readFileSync(new URL('../src/components/product/ProductCard.vue', import.meta.url), 'utf8')
const productsSource = readFileSync(new URL('../src/components/home/ProductsMarketplace.vue', import.meta.url), 'utf8')
const dashboardSource = readFileSync(new URL('../src/views/seller/SellerDashboard.vue', import.meta.url), 'utf8')

describe('visible media and chart scheduling', () => {
  it('gives ProductCard safe lazy defaults and binds browser priority attributes', () => {
    expect(productCardSource).toContain("default: 'lazy'")
    expect(productCardSource).toContain("default: 'auto'")
    expect(productCardSource).toContain(':loading="imageLoading"')
    expect(productCardSource).toContain(':fetchpriority="fetchPriority"')
    expect(productCardSource).toContain('height: 140px;')
  })

  it('prioritizes only the first four marketplace products that have images', () => {
    expect(productsSource).toContain("filter((product) => !!product?.imageUrl).slice(0, 4)")
    expect(productsSource).toContain("priorityImageIds.has(product.id) ? 'eager' : 'lazy'")
    expect(productsSource).toContain("priorityImageIds.has(product.id) ? 'high' : 'auto'")
  })

  it('defers the ECharts component until the trend card nears the viewport', () => {
    const { descriptor } = parse(dashboardSource)
    expect(compileTemplate({ source: descriptor.template.content, filename: 'SellerDashboard.vue', id: 'media-scheduling' }).errors).toEqual([])
    expect(dashboardSource).toContain('v-if="shouldLoadChart"')
    expect(dashboardSource).toContain("rootMargin: '200px 0px'")
    expect(dashboardSource).toContain("typeof IntersectionObserver !== 'function'")
    expect(dashboardSource).toContain('shouldLoadChart.value = true')
    expect(dashboardSource).toContain('min-height: 300px;')
  })
})
