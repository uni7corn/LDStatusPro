// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { sanitizeHtml } from '../src/utils/sanitizeHtml'

describe('sanitized HTML style policy', () => {
  it('removes style and event attributes from user-controlled markup', () => {
    const result = sanitizeHtml('<p style="position:fixed;color:red" onclick="alert(1)">安全文本</p>')

    expect(result).toBe('<p>安全文本</p>')
  })
})
