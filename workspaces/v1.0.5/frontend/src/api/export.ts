import { apiFetch, getApiUrl } from './runtime';

export function getNativePsdExportUrl(pageId: string, dpi: number = 600): string {
  return `${getApiUrl()}/api/export/page/${pageId}/native-psd?dpi=${dpi}`;
}

export function getNativeClipExportUrl(pageId: string, dpi: number = 600): string {
  return `${getApiUrl()}/api/export/page/${pageId}/native-clip?dpi=${dpi}`;
}

export async function downloadNativePsd(pageId: string, filename: string = 'export.psd', dpi: number = 600): Promise<void> {
  const url = getNativePsdExportUrl(pageId, dpi);
  const res = await apiFetch(`/api/export/page/${pageId}/native-psd?dpi=${dpi}`);
  if (!res.ok) throw new Error('Failed to export native PSD');
  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}

export async function downloadNativeClip(pageId: string, filename: string = 'export.clip', dpi: number = 600): Promise<void> {
  const res = await apiFetch(`/api/export/page/${pageId}/native-clip?dpi=${dpi}`);
  if (!res.ok) throw new Error('Failed to export native CLIP');
  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}
