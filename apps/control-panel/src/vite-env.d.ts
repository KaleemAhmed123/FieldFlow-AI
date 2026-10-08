/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Orchestrator base URL. Defaults to http://localhost:8000. */
  readonly VITE_API_URL?: string;
  /** "true" serves captured fixtures instead of the live backend (offline UI dev/demo). */
  readonly VITE_USE_FIXTURES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
