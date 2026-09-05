import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export const EXPECTED_NOINDEX_POLICY = 'noindex, nofollow, noarchive'

function readFile(filePath, violations, label) {
  if (!fs.existsSync(filePath)) {
    violations.push(`${label} is missing`)
    return ''
  }
  return fs.readFileSync(filePath, 'utf8')
}

function validateHtml(html, label, violations) {
  const robotsTags = [...html.matchAll(/<meta\s+[^>]*name=["']robots["'][^>]*>/gi)]
  if (robotsTags.length !== 1) {
    violations.push(`${label} must contain exactly one robots meta tag, found ${robotsTags.length}`)
  } else {
    const content = robotsTags[0][0].match(/content=["']([^"']*)["']/i)?.[1]?.trim()
    if (content !== EXPECTED_NOINDEX_POLICY) {
      violations.push(`${label} robots policy must be ${EXPECTED_NOINDEX_POLICY}`)
    }
  }

  if (/<meta\s+[^>]*name=["']keywords["']/i.test(html)) {
    violations.push(`${label} must not contain meta keywords`)
  }
  if (/application\/ld\+json/i.test(html)) {
    violations.push(`${label} must not contain search-oriented JSON-LD while noindex is active`)
  }
}

function validateHeaders(headers, label, violations) {
  const policies = [...headers.matchAll(/^\s*X-Robots-Tag:\s*(.+?)\s*$/gim)].map(match => match[1])
  if (!policies.includes(EXPECTED_NOINDEX_POLICY)) {
    violations.push(`${label} must set X-Robots-Tag: ${EXPECTED_NOINDEX_POLICY}`)
  }
}

function validateRobots(robots, label, violations) {
  const directives = robots
    .split('\n')
    .map(line => line.replace(/#.*$/, '').trim().toLowerCase())
    .filter(Boolean)

  if (!directives.includes('user-agent: *')) violations.push(`${label} must address all crawlers`)
  if (!directives.includes('allow: /')) violations.push(`${label} must allow / so crawlers can observe noindex`)
  if (directives.some(line => /^disallow:\s*\/?\*?$/.test(line))) {
    violations.push(`${label} must not block the whole site while noindex is active`)
  }
}

function validateWorker(worker, label, violations) {
  if (!worker.includes(`export const NOINDEX_POLICY = '${EXPECTED_NOINDEX_POLICY}'`)) {
    violations.push(`${label} must define the canonical noindex policy`)
  }

  const imageResponse = worker.slice(worker.indexOf('function imageResponse'), worker.indexOf('async function fetchValidatedPng'))
  const ogHandler = worker.slice(worker.indexOf('export async function handleOgImage'), worker.indexOf('function isRedirectStatus'))
  const jsonResponse = worker.slice(worker.indexOf('function jsonResponse'), worker.indexOf('export async function handleOembed'))
  const htmlHandler = worker.slice(worker.indexOf('async function handleHtmlRequest'), worker.indexOf('export default'))

  if (!imageResponse.includes("'x-robots-tag': NOINDEX_POLICY")) {
    violations.push(`${label} OG image success responses must set X-Robots-Tag`)
  }
  if (!ogHandler.includes("'x-robots-tag': NOINDEX_POLICY")) {
    violations.push(`${label} OG image error responses must set X-Robots-Tag`)
  }
  if (!jsonResponse.includes("'x-robots-tag': NOINDEX_POLICY")) {
    violations.push(`${label} oEmbed responses must set X-Robots-Tag`)
  }
  if (!htmlHandler.includes("headers.set('x-robots-tag', NOINDEX_POLICY)")) {
    violations.push(`${label} rewritten HTML responses must set X-Robots-Tag`)
  }
}

function validateArtifactSet({ indexPath, headersPath, robotsPath, workerPath, sitemapPath, label }, violations) {
  validateHtml(readFile(indexPath, violations, `${label} index.html`), `${label} index.html`, violations)
  validateHeaders(readFile(headersPath, violations, `${label} _headers`), `${label} _headers`, violations)
  validateRobots(readFile(robotsPath, violations, `${label} robots.txt`), `${label} robots.txt`, violations)
  validateWorker(readFile(workerPath, violations, `${label} _worker.js`), `${label} _worker.js`, violations)
  if (fs.existsSync(sitemapPath)) violations.push(`${label} must not publish sitemap.xml while noindex is active`)
}

function validateAdr(adr, violations) {
  for (const marker of [
    '状态：已接受',
    EXPECTED_NOINDEX_POLICY,
    'robots.txt',
    'Allow: /',
    'index.html',
    'public/_worker.js',
    'tests/',
    '重新评估收录的前置条件'
  ]) {
    if (!adr.includes(marker)) violations.push(`noindex ADR is missing required marker: ${marker}`)
  }
}

export function validateNoindexPolicy({
  rootDir = path.resolve(import.meta.dirname, '..'),
  includeBuild = false
} = {}) {
  const violations = []
  validateArtifactSet({
    indexPath: path.join(rootDir, 'index.html'),
    headersPath: path.join(rootDir, 'public', '_headers'),
    robotsPath: path.join(rootDir, 'public', 'robots.txt'),
    workerPath: path.join(rootDir, 'public', '_worker.js'),
    sitemapPath: path.join(rootDir, 'public', 'sitemap.xml'),
    label: 'source'
  }, violations)

  const adrPath = path.join(rootDir, 'docs', 'adr', '0001-noindex-sharing-metadata.md')
  validateAdr(readFile(adrPath, violations, 'noindex ADR'), violations)
  for (const testPath of [
    path.join(rootDir, 'tests', 'noindex-policy.test.js'),
    path.join(rootDir, 'tests', 'worker-open-graph.test.js')
  ]) {
    if (!fs.existsSync(testPath)) violations.push(`${path.relative(rootDir, testPath)} is required by the noindex policy`)
  }

  if (includeBuild) {
    const distDir = path.join(rootDir, 'dist')
    validateArtifactSet({
      indexPath: path.join(distDir, 'index.html'),
      headersPath: path.join(distDir, '_headers'),
      robotsPath: path.join(distDir, 'robots.txt'),
      workerPath: path.join(distDir, '_worker.js'),
      sitemapPath: path.join(distDir, 'sitemap.xml'),
      label: 'production build'
    }, violations)
  }

  return { violations }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const includeBuild = process.argv.includes('--build')
  const result = validateNoindexPolicy({ includeBuild })
  if (result.violations.length) {
    console.error(`Noindex policy validation failed with ${result.violations.length} violation(s):`)
    for (const violation of result.violations) console.error(`- ${violation}`)
    process.exit(1)
  }
  console.log(`Noindex policy passed for source${includeBuild ? ' and the production build' : ''}.`)
}
