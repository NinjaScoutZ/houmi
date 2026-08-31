export interface HoumiRuntimeConfig {
  mode?: 'local' | 'remote';
  apiBaseUrl?: string;
  wsBaseUrl?: string;
  localApiBaseUrl?: string;
}

declare global {
  interface Window {
    __HOUMI_RUNTIME_CONFIG__?: HoumiRuntimeConfig;
  }
}

let inMemoryAccessToken: string | null = null;
let inMemoryRefreshToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

const sleep = (milliseconds: number) => new Promise<void>((resolve) => {
  window.setTimeout(resolve, milliseconds);
});

function runtimeConfig(): HoumiRuntimeConfig {
  if (typeof window === 'undefined') return {};
  return window.__HOUMI_RUNTIME_CONFIG__ || {};
}

function currentOrigin(): string {
  if (typeof window === 'undefined') return 'http://127.0.0.1:4000';
  return window.location.origin;
}

/**
 * Tauri production windows are hosted on tauri.localhost.  The desktop
 * client keeps its local FastAPI engine on loopback so the UI remains usable
 * without Internet access.  Browser development and the hosted web client
 * continue to use their normal same-origin/proxy behavior.
 */
export function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  return window.location.hostname === 'tauri.localhost'
    || window.location.protocol === 'tauri:';
}

function localApiOrigin(): string {
  return stripTrailingSlash(
    runtimeConfig().localApiBaseUrl || 'http://127.0.0.1:4317',
  );
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export const DEFAULT_CENTRAL_SERVER_URL = 'https://houmi.click';

export function getApiOrigin(): string {
  if (typeof window !== 'undefined') {
    const customServerUrl = localStorage.getItem('houmi_central_server_url');
    if (customServerUrl && customServerUrl.trim()) {
      return stripTrailingSlash(customServerUrl.trim());
    }
  }
  const configuredApiBaseUrl = runtimeConfig().apiBaseUrl;
  if (configuredApiBaseUrl) return stripTrailingSlash(configuredApiBaseUrl);
  const configuredLocalApiBaseUrl = runtimeConfig().localApiBaseUrl;
  if (runtimeConfig().mode === 'local' && configuredLocalApiBaseUrl) {
    return stripTrailingSlash(configuredLocalApiBaseUrl);
  }
  if (isTauriRuntime()) return localApiOrigin();
  return stripTrailingSlash(currentOrigin());
}

export function getApiBaseUrl(): string {
  return `${getApiOrigin()}/api`;
}

export function getWebSocketOrigin(): string {
  const configured = runtimeConfig().wsBaseUrl;
  if (configured) return stripTrailingSlash(configured);
  return getApiOrigin().replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
}

export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
}

export function setSessionTokens(accessToken: string | null, refreshToken: string | null): void {
  inMemoryAccessToken = accessToken;
  inMemoryRefreshToken = refreshToken;
}

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

export function getRefreshToken(): string | null {
  return inMemoryRefreshToken;
}

export function isRemoteRuntime(): boolean {
  return runtimeConfig().mode === 'remote';
}

export function isLocalRuntime(): boolean {
  return !isRemoteRuntime();
}

export function buildApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${getApiOrigin()}${path.startsWith('/') ? path : `/${path}`}`;
}

async function refreshAccessToken(): Promise<boolean> {
  if (!inMemoryRefreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = fetchWithRuntimeRetry(buildApiUrl('/api/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: inMemoryRefreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) {
          setSessionTokens(null, null);
          window.dispatchEvent(new CustomEvent('auth-expired'));
          return false;
        }
        const tokens = await response.json() as { access_token?: string; refresh_token?: string };
        if (!tokens.access_token || !tokens.refresh_token) {
          setSessionTokens(null, null);
          window.dispatchEvent(new CustomEvent('auth-expired'));
          return false;
        }
        setSessionTokens(tokens.access_token, tokens.refresh_token);
        return true;
      })
      .catch(() => {
        setSessionTokens(null, null);
        window.dispatchEvent(new CustomEvent('auth-expired'));
        return false;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function fetchWithRuntimeRetry(url: string, init: RequestInit): Promise<Response> {
  // A packaged desktop window can render before its Python sidecar finishes
  // loading OCR/ONNX modules. Retry only the loopback runtime; remote calls
  // should fail quickly and let the UI show the cloud/offline state.
  const attempts = isTauriRuntime() ? 12 : 1;
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await fetch(url, init);
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await sleep(500);
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Network request failed');
}

export async function apiFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const url = buildApiUrl(String(input));
  const headers = new Headers(init.headers || {});
  if (inMemoryAccessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${inMemoryAccessToken}`);
  }
  const response = await fetchWithRuntimeRetry(url, { ...init, headers });
  if (response.status === 401 && (url.endsWith('/api/auth/refresh') || !inMemoryRefreshToken)) {
    setSessionTokens(null, null);
    window.dispatchEvent(new CustomEvent('auth-expired'));
    return response;
  }
  if (response.status !== 401 || url.endsWith('/api/auth/refresh') || !inMemoryRefreshToken) {
    return response;
  }
  if (!(await refreshAccessToken())) {
    window.dispatchEvent(new CustomEvent('auth-expired'));
    return response;
  }
  const retryHeaders = new Headers(init.headers || {});
  if (inMemoryAccessToken) retryHeaders.set('Authorization', `Bearer ${inMemoryAccessToken}`);
  return fetchWithRuntimeRetry(url, { ...init, headers: retryHeaders });
}

export function getCentralServerUrl(): string {
  if (typeof window !== 'undefined') {
    const customServerUrl = localStorage.getItem('houmi_central_server_url');
    if (customServerUrl && customServerUrl.trim()) {
      return stripTrailingSlash(customServerUrl.trim());
    }
  }
  return DEFAULT_CENTRAL_SERVER_URL;
}

export async function centralApiFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const baseUrl = getCentralServerUrl();
  const path = String(input);
  const url = /^https?:\/\//i.test(path) ? path : `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
  
  const headers = new Headers(init.headers || {});
  if (inMemoryAccessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${inMemoryAccessToken}`);
  }
  
  try {
    const response = await fetch(url, { ...init, headers });
    
    if (response.status === 401 && (url.endsWith('/api/auth/refresh') || !inMemoryRefreshToken)) {
      setSessionTokens(null, null);
      window.dispatchEvent(new CustomEvent('auth-expired'));
      return response;
    }
    if (response.status !== 401 || url.endsWith('/api/auth/refresh') || !inMemoryRefreshToken) {
      return response;
    }
    if (!(await refreshAccessToken())) {
      window.dispatchEvent(new CustomEvent('auth-expired'));
      return response;
    }
    const retryHeaders = new Headers(init.headers || {});
    if (inMemoryAccessToken) retryHeaders.set('Authorization', `Bearer ${inMemoryAccessToken}`);
    return await fetch(url, { ...init, headers: retryHeaders });
  } catch (error) {
    // If direct HTTPS call fails (e.g. browser CORS restriction, Tauri network boundary, DNS or offline),
    // fall back to local loopback backend proxy which forwards requests via Python SSL without CORS issues.
    if (!url.includes('127.0.0.1') && !url.includes('localhost')) {
      return localApiFetch(path, init);
    }
    throw error;
  }
}

export async function localApiFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const baseUrl = isTauriRuntime() ? localApiOrigin() : currentOrigin();
  const path = String(input);
  const url = /^https?:\/\//i.test(path) ? path : `${stripTrailingSlash(baseUrl)}${path.startsWith('/') ? path : `/${path}`}`;
  
  const headers = new Headers(init.headers || {});
  if (inMemoryAccessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${inMemoryAccessToken}`);
  }
  
  return fetchWithRuntimeRetry(url, { ...init, headers });
}
