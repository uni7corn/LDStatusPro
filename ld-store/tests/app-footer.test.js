import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { compileTemplate, parse } from '@vue/compiler-sfc'

const source = readFileSync(new globalThis.URL('../src/components/layout/AppFooter.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)

describe('mobile app footer', () => {
  it('keeps the footer template compilable and labels the primary navigation', () => {
    expect(compileTemplate({
      source: descriptor.template.content,
      filename: 'AppFooter.vue',
      id: 'app-footer'
    }).errors).toEqual([])
    expect(source).toContain('aria-label="移动端主导航"')
    expect(source).toContain(':aria-current="isActive(item.path) ? \'page\' : undefined"')
  })

  it('uses one vector icon family instead of platform-dependent emoji', () => {
    expect(source).toContain("from '@lucide/vue'")
    for (const icon of ['House', 'Search', 'ClipboardList', 'UserRound', 'LogIn']) {
      expect(source).toContain(`iconComponent: ${icon}`)
    }
    expect(source).not.toMatch(/[🏪🔍📋👤🔐]/u)
    expect(source).toContain('aria-hidden="true"')
  })
})
