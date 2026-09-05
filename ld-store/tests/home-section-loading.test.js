import { readFileSync } from 'node:fs'
import { URL } from 'node:url'
import { describe, expect, it } from 'vitest'
import { compileTemplate, parse } from '@vue/compiler-sfc'

const read = (relativePath) => readFileSync(new URL(relativePath, import.meta.url), 'utf8')
const home = read('../src/views/Home.vue')
const sections = [
  '../src/components/home/ProductsMarketplace.vue',
  '../src/components/home/StoresMarketplace.vue',
  '../src/components/home/BuyRequestMarketplace.vue',
  '../src/components/home/HotboardMarketplace.vue'
]

describe('home section loading boundaries', () => {
  it('loads every marketplace section asynchronously inside a local KeepAlive', () => {
    for (const section of ['ProductsMarketplace', 'StoresMarketplace', 'BuyRequestMarketplace', 'HotboardMarketplace']) {
      expect(home).toContain(`defineAsyncComponent(() => import('@/components/home/${section}.vue'))`)
    }
    expect(home).toContain('<KeepAlive :max="4">')
    expect(home).toContain('<Suspense>')
    expect(home).toContain('min-height: 420px')
  })

  it('keeps the shell free of direct API requests and preserves the section query contract', () => {
    expect(home).not.toContain("from '@/utils/api'")
    expect(home).toContain('route.query.section')
    expect(home).toContain("? value : 'products'")
    expect(home).toContain('router.replace')
  })

  it('keeps all section templates compilable with tabpanel semantics and deactivation cleanup', () => {
    for (const relativePath of sections) {
      const source = read(relativePath)
      const { descriptor, errors } = parse(source)
      expect(errors).toEqual([])
      expect(compileTemplate({ source: descriptor.template.content, filename: relativePath, id: relativePath }).errors).toEqual([])
      expect(source).toContain('role="tabpanel"')
      expect(source).toContain('onDeactivated')
    }
  })
})
