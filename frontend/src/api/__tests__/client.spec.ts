import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiClient } from '../client';
import {
  getStoredToken,
  getStoredRefreshToken,
  storeToken,
  storeRefreshToken,
  clearStoredTokens
} from '../auth';
import { eventBus } from '../../utils/eventBus';

// Minimal shape for a resolved axios adapter response.
function okResponse(data: unknown, config: unknown) {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

// Minimal AxiosError-shaped rejection. The response interceptor in
// client.ts only inspects `.response`, `.request` and `.config`, so a
// real AxiosError instance is not required.
function axiosErrorRejection(config: unknown, status: number, data: unknown = {}) {
  return {
    response: { status, statusText: statusTextFor(status), data },
    config,
    isAxiosError: true,
    message: `Request failed with status code ${status}`
  };
}

function statusTextFor(status: number): string {
  const map: Record<number, string> = {
    401: 'Unauthorized',
    500: 'Internal Server Error'
  };
  return map[status] || 'Error';
}

describe('apiClient', () => {
  let adapterMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    adapterMock = vi.fn();
    apiClient.defaults.adapter = adapterMock as any;
    localStorage.clear();
    delete apiClient.defaults.headers.Authorization;
  });

  afterEach(() => {
    localStorage.clear();
    delete apiClient.defaults.headers.Authorization;
    vi.useRealTimers();
  });

  describe('request interceptor', () => {
    it('attaches Authorization header from stored token', async () => {
      storeToken('abc');
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ code: 0, msg: 'ok', data: {} }, config)
      );

      await apiClient.get('/whatever');

      expect(adapterMock).toHaveBeenCalledTimes(1);
      const config = adapterMock.mock.calls[0][0];
      expect(config.headers.Authorization).toBe('Bearer abc');
    });

    it('does not set Authorization header when no token is stored', async () => {
      clearStoredTokens();
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ code: 0, msg: 'ok', data: {} }, config)
      );

      await apiClient.get('/whatever');

      const config = adapterMock.mock.calls[0][0];
      expect(config.headers.Authorization).toBeUndefined();
    });
  });

  describe('response interceptor - success envelope', () => {
    it('passes the full axios response through unchanged for code === 0', async () => {
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ code: 0, msg: 'ok', data: { foo: 1 } }, config)
      );

      const response = await apiClient.get('/whatever');

      expect(response.data.data.foo).toBe(1);
    });

    it('rejects with a shaped ApiError for a business-error envelope (code !== 0)', async () => {
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ code: 42, msg: 'bad thing' }, config)
      );

      await expect(apiClient.get('/whatever')).rejects.toEqual({
        code: 42,
        message: 'bad thing',
        details: { code: 42, msg: 'bad thing' }
      });
    });
  });

  describe('401 refresh flow', () => {
    it('refreshes the token once and retries the original request', async () => {
      storeToken('old');
      storeRefreshToken('oldr');

      // 1) original request -> 401
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw axiosErrorRejection(config, 401);
      });
      // 2) /auth/refresh -> new tokens
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ data: { access_token: 'new', refresh_token: 'newr' } }, config)
      );
      // 3) retried original request -> success
      adapterMock.mockImplementationOnce(async (config: any) =>
        okResponse({ code: 0, msg: 'ok', data: { ok: true } }, config)
      );

      const response = await apiClient.get('/foo');

      expect(response.data.data.ok).toBe(true);
      expect(adapterMock).toHaveBeenCalledTimes(3);
      expect(getStoredToken()).toBe('new');

      const refreshCallConfig = adapterMock.mock.calls[1][0];
      expect(refreshCallConfig.url).toBe('/auth/refresh');

      const retryCallConfig = adapterMock.mock.calls[2][0];
      expect(retryCallConfig.headers.Authorization).toBe('Bearer new');
    });

    it('queues concurrent 401s behind a single refresh call', async () => {
      storeToken('old');
      storeRefreshToken('oldr');
      let refreshCalls = 0;

      adapterMock.mockImplementation(async (config: any) => {
        if (config.url === '/auth/refresh') {
          refreshCalls += 1;
          return okResponse({ data: { access_token: 'new2', refresh_token: 'newr2' } }, config);
        }
        if (!config._retry) {
          throw axiosErrorRejection(config, 401);
        }
        return okResponse({ code: 0, msg: 'ok', data: {} }, config);
      });

      const [r1, r2] = await Promise.all([apiClient.get('/a'), apiClient.get('/b')]);

      expect(refreshCalls).toBe(1);
      expect(r1.status).toBe(200);
      expect(r2.status).toBe(200);
      expect(getStoredToken()).toBe('new2');
    });

    it('clears tokens and emits auth:logout when the refresh request itself fails', async () => {
      vi.useFakeTimers();
      storeToken('old');
      storeRefreshToken('oldr');
      const logoutSpy = vi.fn();
      eventBus.on('auth:logout', logoutSpy);

      // 1) original request -> 401
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw axiosErrorRejection(config, 401);
      });
      // 2) /auth/refresh -> also 401
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw axiosErrorRejection(config, 401);
      });

      await expect(apiClient.get('/foo')).rejects.toBeDefined();

      expect(getStoredToken()).toBeNull();
      expect(getStoredRefreshToken()).toBeNull();
      expect(logoutSpy).toHaveBeenCalledTimes(1);

      eventBus.off('auth:logout', logoutSpy);
    });

    it('rejects directly with "Token refresh failed" for __isRefreshRequest configs, skipping the retry loop', async () => {
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw axiosErrorRejection(config, 401, { detail: 'bad refresh' });
      });

      await expect(
        apiClient.post('/auth/refresh', {}, { __isRefreshRequest: true } as any)
      ).rejects.toEqual({
        code: 401,
        message: 'Token refresh failed',
        details: { detail: 'bad refresh' }
      });

      expect(adapterMock).toHaveBeenCalledTimes(1);
    });
  });

  describe('generic error shaping', () => {
    it('shapes a non-401 error using the response statusText', async () => {
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw axiosErrorRejection(config, 500, 'oops');
      });

      await expect(apiClient.get('/foo')).rejects.toEqual({
        code: 500,
        message: 'Internal Server Error'
      });
    });

    it('shapes a network error (error.request, no response) with code 503', async () => {
      adapterMock.mockImplementationOnce(async (config: any) => {
        throw { request: {}, config, isAxiosError: true, message: 'Network Error' };
      });

      await expect(apiClient.get('/foo')).rejects.toEqual({
        code: 503,
        message: 'Network error, please check your connection'
      });
    });
  });
});
