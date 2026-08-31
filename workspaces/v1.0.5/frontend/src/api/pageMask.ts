import { apiFetch } from './runtime';

export interface PageMaskResponse {
  page_id: string;
  width?: number;
  height?: number;
  mask_data_url?: string;
}

async function requireSuccessfulMaskResponse(response: Response, fallbackMessage: string): Promise<PageMaskResponse> {
  if (!response.ok) {
    let detail = fallbackMessage;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // The status code and fallback retain enough context for non-JSON failures.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<PageMaskResponse>;
}

export async function loadEffectivePageMask(pageId: string, signal?: AbortSignal): Promise<PageMaskResponse> {
  const response = await apiFetch(`/api/pipeline/pages/${pageId}/effective-mask?overlay=true`, { signal });
  return requireSuccessfulMaskResponse(response, 'Failed to load the page mask');
}

export async function generateAutomaticPageMask(pageId: string, signal?: AbortSignal): Promise<PageMaskResponse> {
  const response = await apiFetch(`/api/pipeline/pages/${pageId}/auto-mask?overlay=true`, { method: 'POST', signal });
  return requireSuccessfulMaskResponse(response, 'Failed to generate the automatic page mask');
}

export async function saveEffectivePageMask(pageId: string, mask: Blob): Promise<PageMaskResponse> {
  const formData = new FormData();
  formData.append('file', mask, 'manual_mask.png');
  // The server queues the full-page clean and returns as soon as the mask is
  // durable. Do not make Mark Mode wait for the inpainting model.
  const response = await apiFetch(`/api/pipeline/pages/${pageId}/effective-mask?reclean=true&return_mask=false`, {
    method: 'POST',
    body: formData,
  });
  return requireSuccessfulMaskResponse(response, 'Failed to save and clean the page mask');
}
