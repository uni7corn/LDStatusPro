/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_AUTH_API_BASE?: string
  readonly VITE_IMAGE_API_BASE?: string
  readonly VITE_BUILD_VERSION?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
