import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const fixtureRoot = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(fixtureRoot, '../../..')

export default defineConfig({
  root: fixtureRoot,
  publicDir: path.join(projectRoot, 'public'),
  plugins: [vue()],
  resolve: {
    alias: { '@': path.join(projectRoot, 'src') }
  },
  css: {
    postcss: path.join(projectRoot, 'postcss.config.js')
  },
  build: {
    outDir: path.join(projectRoot, '.csp-smoke-dist'),
    emptyOutDir: true,
    sourcemap: false,
    minify: 'terser'
  }
})
