// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Skeleton from '../src/components/common/Skeleton.vue'

const categorySource = readFileSync(resolve('src/views/Category.vue'), 'utf8')

describe('分类页加载骨架', () => {
  it('使用 Skeleton 支持的卡片类型', () => {
    expect(categorySource).toContain('<Skeleton type="card" :count="4" />')
    expect(categorySource).not.toContain('<Skeleton type="product"')
  })

  it('渲染四张与商品列表结构一致的卡片占位', () => {
    const wrapper = mount(Skeleton, {
      props: { type: 'card', count: 4, columns: 2 }
    })

    expect(wrapper.findAll('.skeleton-card')).toHaveLength(4)
    expect(wrapper.get('.skeleton-container').attributes('style')).toContain('grid-template-columns: repeat(2, 1fr)')
  })
})
