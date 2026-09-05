import { readFile, stat } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'
import path from 'node:path'

const KiB = 1024
const budgets = {
  entryJs: 140 * KiB,
  entryCss: 28 * KiB,
  asyncJs: 190 * KiB
}

const distDir = path.resolve(process.cwd(), 'dist')
const manifestPath = path.join(distDir, '.vite', 'manifest.json')

async function gzipBytes(relativePath) {
  const absolutePath = path.join(distDir, relativePath)
  await stat(absolutePath)
  return gzipSync(await readFile(absolutePath), { level: 9 }).byteLength
}

function collectStaticEntries(manifest, entryKey) {
  const visited = new Set()

  function visit(key) {
    if (!key || visited.has(key)) return
    const chunk = manifest[key]
    if (!chunk) throw new Error(`Manifest import not found: ${key}`)
    visited.add(key)
    for (const importedKey of chunk.imports || []) visit(importedKey)
  }

  visit(entryKey)
  return visited
}

function formatKiB(bytes) {
  return `${(bytes / KiB).toFixed(2)} KiB`
}

const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
const entryKey = Object.keys(manifest).find((key) => manifest[key].isEntry)
if (!entryKey) throw new Error('Vite manifest does not contain an entry chunk')

const staticKeys = collectStaticEntries(manifest, entryKey)
const entryJsFiles = new Set()
const entryCssFiles = new Set()

for (const key of staticKeys) {
  const chunk = manifest[key]
  if (chunk.file?.endsWith('.js')) entryJsFiles.add(chunk.file)
  for (const cssFile of chunk.css || []) entryCssFiles.add(cssFile)
}

const entryJsBytes = (await Promise.all([...entryJsFiles].map(gzipBytes))).reduce((sum, bytes) => sum + bytes, 0)
const entryCssBytes = (await Promise.all([...entryCssFiles].map(gzipBytes))).reduce((sum, bytes) => sum + bytes, 0)

const asyncJsFiles = [...new Set(
  Object.entries(manifest)
    .filter(([key, chunk]) => !staticKeys.has(key) && chunk.file?.endsWith('.js'))
    .map(([, chunk]) => chunk.file)
)]
const asyncSizes = await Promise.all(asyncJsFiles.map(async (file) => ({ file, bytes: await gzipBytes(file) })))
const largestAsync = asyncSizes.sort((a, b) => b.bytes - a.bytes)[0] || { file: '(none)', bytes: 0 }

const results = [
  { label: 'Entry JS', bytes: entryJsBytes, budget: budgets.entryJs },
  { label: 'Entry CSS', bytes: entryCssBytes, budget: budgets.entryCss },
  { label: `Largest async JS (${largestAsync.file})`, bytes: largestAsync.bytes, budget: budgets.asyncJs }
]

for (const result of results) {
  const state = result.bytes <= result.budget ? 'PASS' : 'FAIL'
  console.log(`${state} ${result.label}: ${formatKiB(result.bytes)} / ${formatKiB(result.budget)}`)
}

const failures = results.filter((result) => result.bytes > result.budget)
if (failures.length > 0) {
  process.exitCode = 1
}
