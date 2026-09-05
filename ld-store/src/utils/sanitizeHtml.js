import DOMPurify from 'dompurify'

const SANITIZE_OPTIONS = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'],
  FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onmouseenter']
}

export function sanitizeHtml(value, options = {}) {
  if (value === undefined || value === null) return ''
  return DOMPurify.sanitize(String(value), {
    ...SANITIZE_OPTIONS,
    ...options,
    FORBID_TAGS: [...SANITIZE_OPTIONS.FORBID_TAGS, ...(options.FORBID_TAGS || [])],
    FORBID_ATTR: [...SANITIZE_OPTIONS.FORBID_ATTR, ...(options.FORBID_ATTR || [])]
  })
}
