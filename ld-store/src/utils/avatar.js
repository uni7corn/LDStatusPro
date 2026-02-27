// 统一处理头像地址
const AVATAR_DEFAULT_ORIGIN = 'https://linux.do'

export function toAbsoluteAvatarUrl(rawValue, size = 128) {
  if (rawValue === undefined || rawValue === null) return ''

  const value = String(rawValue).trim()
  if (!value) return ''

  const withSize = value.replace('{size}', String(size))

  if (withSize.startsWith('data:') || withSize.startsWith('blob:')) return withSize
  if (/^https?:\/\//i.test(withSize)) return withSize
  if (withSize.startsWith('//')) return `https:${withSize}`
  if (withSize.startsWith('/')) return `${AVATAR_DEFAULT_ORIGIN}${withSize}`
  return withSize
}

export function resolveAvatarUrl(rawValue, size = 128) {
  return toAbsoluteAvatarUrl(rawValue, size)
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function buildFallbackAvatar(seed = '', size = 128) {
  const text = String(seed || '').trim()
  const char = Array.from(text)[0] || '?'

  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i)
    hash |= 0
  }
  const hue = Math.abs(hash) % 360
  const bg = `hsl(${hue} 55% 50%)`
  const letter = escapeXml(char.toUpperCase())

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 100 100"><rect width="100" height="100" rx="50" fill="${bg}"/><text x="50" y="50" dy="0.02em" text-anchor="middle" dominant-baseline="middle" font-family="Segoe UI, PingFang SC, Microsoft YaHei, Helvetica, Arial, sans-serif" font-size="46" font-weight="700" fill="#fff">${letter}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
