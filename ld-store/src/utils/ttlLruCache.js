export function createTtlLruCache({ ttl, max, now = Date.now } = {}) {
  if (!Number.isFinite(ttl) || ttl <= 0) throw new TypeError('ttl must be a positive number')
  if (!Number.isInteger(max) || max <= 0) throw new TypeError('max must be a positive integer')

  const entries = new Map()

  function get(key) {
    const entry = entries.get(key)
    if (!entry) return undefined
    if (entry.expiresAt <= now()) {
      entries.delete(key)
      return undefined
    }
    entries.delete(key)
    entries.set(key, entry)
    return entry.value
  }

  function set(key, value) {
    entries.delete(key)
    entries.set(key, { value, expiresAt: now() + ttl })
    while (entries.size > max) {
      entries.delete(entries.keys().next().value)
    }
    return value
  }

  return {
    get,
    set,
    delete: (key) => entries.delete(key),
    clear: () => entries.clear(),
    get size() {
      return entries.size
    }
  }
}
