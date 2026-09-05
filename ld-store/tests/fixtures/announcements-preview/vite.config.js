import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
export default defineConfig({root:fileURLToPath(new globalThis.URL('.',import.meta.url)),envDir:false,plugins:[vue()],resolve:{alias:{'@':fileURLToPath(new globalThis.URL('../../../src',import.meta.url))}},server:{host:'127.0.0.1',port:4318,strictPort:true,fs:{allow:[fileURLToPath(new globalThis.URL('../../../',import.meta.url))]}}})
