// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getApiBaseUrl,
  getWebSocketOrigin,
  apiFetch,
  setSessionTokens,
  setAccessToken,
} from '../api/runtime';

describe('runtime API binding', () => {
  beforeEach(() => {
    setAccessToken(null);
    setSessionTokens(null, null);
    window.__HOUMI_RUNTIME_CONFIG__ = undefined;
  });

  it('uses the current origin for Local Mode instead of a hardcoded port', () => {
    expect(getApiBaseUrl()).toBe(`${window.location.origin}/api`);
    expect(getWebSocketOrigin()).toBe(window.location.origin.replace(/^http:/, 'ws:'));
  });

  it('supports injected Remote Mode API and WebSocket origins', () => {
    window.__HOUMI_RUNTIME_CONFIG__ = {
      mode: 'remote',
      apiBaseUrl: 'https://host.example.com/',
      wsBaseUrl: 'wss://host.example.com/',
    };
    expect(getApiBaseUrl()).toBe('https://host.example.com/api');
    expect(getWebSocketOrigin()).toBe('wss://host.example.com');
  });

  it('supports a loopback Local Engine override for the desktop shell', () => {
    window.__HOUMI_RUNTIME_CONFIG__ = {
      mode: 'local',
      localApiBaseUrl: 'http://127.0.0.1:4317/',
    };
    expect(getApiBaseUrl()).toBe('http://127.0.0.1:4317/api');
  });

  it('adds the in-memory bearer token to API requests', async () => {
    setAccessToken('access-token');
    const response = new Response('{}', { status: 200 });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
    await apiFetch('/api/projects');
    expect(fetchMock).toHaveBeenCalledWith(
      `${window.location.origin}/api/projects`,
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer access-token');
    fetchMock.mockRestore();
  });
});
