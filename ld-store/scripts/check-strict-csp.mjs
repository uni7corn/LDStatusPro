import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { STOREFRONT_CSP } from '../public/_worker.js'

function normalizePolicy(policy) {
  return String(policy || '').replace(/\s+/g, ' ').trim()
}

function directives(policy) {
  return new Map(
    normalizePolicy(policy)
      .split(';')
      .map(item => item.trim())
      .filter(Boolean)
      .map((item) => {
        const [name, ...values] = item.split(/\s+/)
        return [name, values]
      })
  )
}

function walk(directory, extensions) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = path.join(directory, entry.name)
    if (entry.isDirectory()) return walk(absolutePath, extensions)
    return extensions.some(extension => entry.name.endsWith(extension)) ? [absolutePath] : []
  })
}

function lineNumber(source, index) {
  return source.slice(0, index).split('\n').length
}

function extractHeadersPolicy(headers) {
  const line = headers.split('\n').find(item => item.trim().startsWith('Content-Security-Policy:'))
  return line?.slice(line.indexOf(':') + 1).trim() || ''
}

function validateHtml(source, relativePath, violations) {
  for (const match of source.matchAll(/<style(?:\s|>)/gi)) {
    violations.push(`${relativePath}:${lineNumber(source, match.index)} inline style element`)
  }
  for (const match of source.matchAll(/<[a-z][^>]*\sstyle\s*=/gi)) {
    violations.push(`${relativePath}:${lineNumber(source, match.index)} static style attribute`)
  }
}

function validateVueSource(source, relativePath, violations) {
  for (const match of source.matchAll(/<[a-z][^>]*\sstyle\s*=/gi)) {
    violations.push(`${relativePath}:${lineNumber(source, match.index)} static style attribute`)
  }
  for (const match of source.matchAll(/(?:\b:style|\bv-bind:style)\s*=\s*(["'])([\s\S]*?)\1/g)) {
    const expression = match[2].trim()
    if (/^["'`]/.test(expression)) {
      violations.push(`${relativePath}:${lineNumber(source, match.index)} string-form dynamic style`)
    }
  }
  for (const pattern of [
    /\bcssText\b/g,
    /setAttribute\s*\(\s*(["'])style\1/g,
    /\.style\s*=/g
  ]) {
    for (const match of source.matchAll(pattern)) {
      violations.push(`${relativePath}:${lineNumber(source, match.index)} unsafe style mutation ${match[0]}`)
    }
  }
}

function validatePolicy(policy, violations, label) {
  const parsed = directives(policy)
  const exactDirectives = [
    ['style-src', ["'self'"]],
    ['style-src-elem', ["'self'"]],
    ['style-src-attr', ["'none'"]]
  ]

  for (const [name, expected] of exactDirectives) {
    const actual = parsed.get(name) || []
    if (actual.join(' ') !== expected.join(' ')) {
      violations.push(`${label} ${name} expected ${expected.join(' ')}, received ${actual.join(' ') || '(missing)'}`)
    }
  }

  const scriptSource = parsed.get('script-src') || []
  for (const forbidden of ["'unsafe-inline'", "'unsafe-eval'"]) {
    if (scriptSource.includes(forbidden)) violations.push(`${label} script-src contains ${forbidden}`)
  }

  for (const [name, value] of [
    ['object-src', "'none'"],
    ['base-uri', "'self'"],
    ['form-action', "'self'"],
    ['frame-ancestors', "'none'"]
  ]) {
    if (!(parsed.get(name) || []).includes(value)) violations.push(`${label} missing ${name} ${value}`)
  }
}

export function validateStrictCspPolicy({
  rootDir = path.resolve(import.meta.dirname, '..'),
  includeBuild = false
} = {}) {
  const violations = []
  const indexPath = path.join(rootDir, 'index.html')
  const headersPath = path.join(rootDir, 'public', '_headers')
  const themeScriptPath = path.join(rootDir, 'public', 'theme-bootstrap.js')
  const themeStylePath = path.join(rootDir, 'public', 'theme-bootstrap.css')
  const indexHtml = fs.readFileSync(indexPath, 'utf8')
  const headers = fs.readFileSync(headersPath, 'utf8')
  const headersPolicy = extractHeadersPolicy(headers)

  validateHtml(indexHtml, 'index.html', violations)
  validatePolicy(headersPolicy, violations, 'public/_headers')

  if (normalizePolicy(headersPolicy) !== normalizePolicy(STOREFRONT_CSP)) {
    violations.push('public/_headers CSP differs from Worker STOREFRONT_CSP')
  }
  if (!fs.existsSync(themeScriptPath)) violations.push('public/theme-bootstrap.js is missing')
  if (!fs.existsSync(themeStylePath)) violations.push('public/theme-bootstrap.css is missing')

  const scriptIndex = indexHtml.indexOf('src="/theme-bootstrap.js"')
  const styleIndex = indexHtml.indexOf('href="/theme-bootstrap.css"')
  const appIndex = indexHtml.indexOf('src="/src/main.js"')
  if (scriptIndex < 0 || styleIndex < 0 || appIndex < 0 || !(scriptIndex < styleIndex && styleIndex < appIndex)) {
    violations.push('index.html must load theme script, blocking theme CSS, then the app entry in that order')
  }

  const sourceFiles = walk(path.join(rootDir, 'src'), ['.vue', '.js', '.ts'])
  for (const filePath of sourceFiles) {
    const source = fs.readFileSync(filePath, 'utf8')
    validateVueSource(source, path.relative(rootDir, filePath), violations)
  }

  const fixtureRoot = path.join(rootDir, 'tests', 'fixtures', 'strict-csp-smoke')
  const fixtureIndexPath = path.join(fixtureRoot, 'index.html')
  if (fs.existsSync(fixtureIndexPath)) {
    const fixtureIndex = fs.readFileSync(fixtureIndexPath, 'utf8')
    validateHtml(fixtureIndex, path.relative(rootDir, fixtureIndexPath), violations)
    const fixtureScriptIndex = fixtureIndex.indexOf('src="/theme-bootstrap.js"')
    const fixtureStyleIndex = fixtureIndex.indexOf('href="/theme-bootstrap.css"')
    const fixtureAppIndex = fixtureIndex.indexOf('src="/main.ts"')
    if (!(fixtureScriptIndex >= 0 && fixtureScriptIndex < fixtureStyleIndex && fixtureStyleIndex < fixtureAppIndex)) {
      violations.push('strict CSP smoke fixture must load theme script, theme CSS, then its app entry')
    }
    for (const fixtureFile of walk(fixtureRoot, ['.vue', '.js', '.ts'])) {
      validateVueSource(fs.readFileSync(fixtureFile, 'utf8'), path.relative(rootDir, fixtureFile), violations)
    }
  }

  if (includeBuild) {
    const distDir = path.join(rootDir, 'dist')
    const builtIndexPath = path.join(distDir, 'index.html')
    const builtThemeStyle = path.join(distDir, 'theme-bootstrap.css')
    if (!fs.existsSync(builtIndexPath)) {
      violations.push('dist/index.html is missing; run the production build first')
    } else {
      const builtIndex = fs.readFileSync(builtIndexPath, 'utf8')
      validateHtml(builtIndex, 'dist/index.html', violations)
      if (!builtIndex.includes('src="/theme-bootstrap.js"') || !builtIndex.includes('href="/theme-bootstrap.css"')) {
        violations.push('dist/index.html is missing external theme bootstrap assets')
      }
    }
    if (!fs.existsSync(builtThemeStyle)) violations.push('dist/theme-bootstrap.css is missing')
  }

  return { sourceFiles: sourceFiles.length, violations }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = validateStrictCspPolicy({ includeBuild: process.argv.includes('--build') })
  if (result.violations.length) {
    console.error(`Strict CSP policy failed with ${result.violations.length} violation(s):`)
    for (const violation of result.violations) console.error(`- ${violation}`)
    process.exit(1)
  }
  console.log(`Strict CSP policy passed for ${result.sourceFiles} source files${process.argv.includes('--build') ? ' and the production build' : ''}.`)
}
