import { check, type Update } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';
import { isTauriRuntime } from '../api/runtime';

export interface FastApiUpdateInfo {
  current_version: string;
  latest_version: string;
  update_available: boolean;
  patch_notes?: string;
  download_size_mb?: number;
  download_url?: string;
}

export type PatchCheckResult =
  | { status: 'unsupported' }
  | { status: 'disabled' }
  | { status: 'current' }
  | { status: 'available'; update?: Update; info?: FastApiUpdateInfo }
  | { status: 'error'; message: string };

export async function checkForPatch(updatesEnabled: boolean = true): Promise<PatchCheckResult> {
  if (!updatesEnabled) return { status: 'disabled' };

  // 1. Try FastAPI backend updater (/api/system/check-update)
  try {
    const resp = await fetch('/api/system/check-update');
    if (resp.ok) {
      const data: FastApiUpdateInfo = await resp.json();
      if (data.update_available) {
        return { status: 'available', info: data };
      } else {
        return { status: 'current' };
      }
    }
  } catch (_e) {
    // Fall through to Tauri runtime check if backend endpoint is unmounted
  }

  // 2. Try Tauri plugin updater if running in Tauri
  if (isTauriRuntime()) {
    try {
      const update = await check({ timeout: 15_000 });
      return update ? { status: 'available', update } : { status: 'current' };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { status: 'error', message };
    }
  }

  return { status: 'current' };
}

export async function installPatch(
  updateObj?: { update?: Update; info?: FastApiUpdateInfo },
  onProgress?: (percent: number | null) => void
) {
  if (onProgress) onProgress(10);

  // 1. FastAPI backend update via /api/system/apply-patch
  try {
    if (onProgress) onProgress(30);
    const resp = await fetch('/api/system/apply-patch', { method: 'POST' });
    if (onProgress) onProgress(80);
    if (resp.ok) {
      const result = await resp.json();
      if (result.status === 'success') {
        if (updateObj?.info) {
          localStorage.setItem('houmi_just_updated_version', updateObj.info.latest_version);
          localStorage.setItem('houmi_just_updated_notes', updateObj.info.patch_notes || '');
        }
        if (onProgress) onProgress(100);
        setTimeout(() => {
          window.location.reload();
        }, 1000);
        return;
      } else {
        throw new Error(result.message || 'ติดตั้งแพตช์ไม่สำเร็จ');
      }
    }
  } catch (_err) {
    // Fallback to Tauri update if present
  }

  // 2. Tauri update
  if (updateObj?.update && isTauriRuntime()) {
    let downloaded = 0;
    let contentLength: number | undefined;

    await updateObj.update.downloadAndInstall((event) => {
      if (event.event === 'Started') {
        contentLength = event.data.contentLength;
        if (onProgress) onProgress(contentLength ? 0 : null);
      } else if (event.event === 'Progress') {
        downloaded += event.data.chunkLength;
        if (onProgress) onProgress(contentLength ? Math.min(100, Math.round((downloaded / contentLength) * 100)) : null);
      } else if (event.event === 'Finished') {
        if (onProgress) onProgress(100);
      }
    }, { timeout: 120_000 });

    await relaunch();
  }
}
