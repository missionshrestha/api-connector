/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  // Add future VITE_ variables here as they are introduced.
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}