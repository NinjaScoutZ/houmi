import { useDebugStore, type ActionCategory, type ActionLogItem } from '../stores/debugStore';

export function logAction(
  category: ActionCategory,
  name: string,
  payload?: any,
  options?: {
    durationMs?: number;
    status?: 'success' | 'warning' | 'error' | 'pending';
    error?: string;
  }
) {
  try {
    useDebugStore.getState().addAction({
      category,
      name,
      payload,
      durationMs: options?.durationMs,
      status: options?.status || 'success',
      error: options?.error,
    });
  } catch (e) {
    console.error('[ActionLogger] Failed to log action:', e);
  }
}

export async function logAsyncAction<T>(
  category: ActionCategory,
  name: string,
  actionFn: () => Promise<T>,
  payload?: any
): Promise<T> {
  const start = performance.now();
  try {
    const result = await actionFn();
    const durationMs = Math.round(performance.now() - start);
    logAction(category, name, payload, { durationMs, status: 'success' });
    return result;
  } catch (error: any) {
    const durationMs = Math.round(performance.now() - start);
    logAction(category, name, payload, {
      durationMs,
      status: 'error',
      error: error?.message || String(error),
    });
    throw error;
  }
}

if (typeof window !== 'undefined') {
  (window as any).__HOUMI_LOG_ACTION__ = logAction;
}
