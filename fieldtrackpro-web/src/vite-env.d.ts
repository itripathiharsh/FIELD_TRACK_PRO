/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_APP_ENV: string
  readonly VITE_MAPLIBRE_TILE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
