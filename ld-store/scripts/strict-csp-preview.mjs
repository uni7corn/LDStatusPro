import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { STOREFRONT_CSP } from '../public/_worker.js'

const rootDir = path.resolve(import.meta.dirname, '..')
const configuredDistDir = String(process.env.STRICT_CSP_DIST_DIR || 'dist').trim() || 'dist'
const distDir = path.isAbsolute(configuredDistDir)
  ? configuredDistDir
  : path.resolve(rootDir, configuredDistDir)
const requestedPort = Number.parseInt(process.env.STRICT_CSP_PORT || '4175', 10)
const port = Number.isInteger(requestedPort) && requestedPort > 0 ? requestedPort : 4175

const contentTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml']
])

async function resolveAsset(pathname) {
  let decoded = '/'
  try {
    decoded = decodeURIComponent(pathname)
  } catch {
    return null
  }
  const relativePath = decoded === '/' ? 'index.html' : decoded.replace(/^\/+/, '')
  const candidate = path.resolve(distDir, relativePath)
  if (candidate !== distDir && !candidate.startsWith(`${distDir}${path.sep}`)) return null
  try {
    const metadata = await fs.stat(candidate)
    if (metadata.isFile()) return candidate
  } catch {
    // Client-side routes fall back to the built index.
  }
  return path.join(distDir, 'index.html')
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || '/', `http://${request.headers.host || `127.0.0.1:${port}`}`)
  const assetPath = await resolveAsset(url.pathname)
  if (!assetPath) {
    response.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' })
    response.end('Bad Request')
    return
  }

  try {
    const body = await fs.readFile(assetPath)
    const extension = path.extname(assetPath).toLowerCase()
    const isHtml = extension === '.html'
    response.writeHead(200, {
      'content-type': contentTypes.get(extension) || 'application/octet-stream',
      'cache-control': isHtml ? 'no-store' : 'public, max-age=60',
      'content-security-policy': STOREFRONT_CSP,
      'x-content-type-options': 'nosniff',
      'x-robots-tag': 'noindex, nofollow, noarchive'
    })
    response.end(request.method === 'HEAD' ? undefined : body)
  } catch {
    response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
    response.end('Not Found')
  }
})

server.listen(port, '127.0.0.1', () => {
  console.log(`Strict CSP preview ready at http://127.0.0.1:${port}`)
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => server.close(() => process.exit(0)))
}
