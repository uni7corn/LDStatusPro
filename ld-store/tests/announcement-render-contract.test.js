// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { renderAnnouncementContent } from '../src/utils/renderAnnouncementContent'
// Identical contract cases in storefront and admin; no cross-repository runtime dependency.
it('preserves readable HTML while stripping execution and inline styling', () => {
  const html=renderAnnouncementContent('<h2>标题</h2><p style="color:red" onclick="alert(1)">正文</p><table><tr><td>值</td></tr></table><iframe src="https://example.com"></iframe><a href="javascript:alert(1)">链接</a>', 'html')
  expect(html).toBe('<h2>标题</h2><p>正文</p><table><tbody><tr><td>值</td></tr></tbody></table><a>链接</a>')
  expect(renderAnnouncementContent('字'.repeat(6000), 'text')).toHaveLength(6000)
  expect(renderAnnouncementContent('## 标题\n\n**正文**', 'markdown')).toBe('<h2>标题</h2>\n<p><strong>正文</strong></p>\n')
})
