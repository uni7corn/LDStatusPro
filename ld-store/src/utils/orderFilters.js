const ORDER_STATUS_TABS = new Set(['paid', 'delivered', 'cancelled', 'other'])
const OTHER_ORDER_STATUSES = ['refund_pending', 'refunded', 'external_dispute']

export function normalizeOrderStatusFilter(value) {
  const status = String(value || '').trim()
  if (OTHER_ORDER_STATUSES.includes(status)) return 'other'
  return ORDER_STATUS_TABS.has(status) ? status : ''
}

export function toOrderApiStatusFilter(value) {
  const status = normalizeOrderStatusFilter(value)
  return status === 'other' ? OTHER_ORDER_STATUSES.join(',') : status
}
