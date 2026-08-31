import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { useProjectStore } from '../stores/projectStore';

describe('R3: Advanced Settings & GPU/Model Management Store Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
      const body = options?.body ? JSON.parse(options.body as string) : {};
      const current = useProjectStore.getState().activeProject!;
      const updatedSettings = body.settings || {};
      return {
        ok: true,
        json: async () => ({
          ...current,
          settings: { ...current.settings, ...updatedSettings },
        }),
      } as Response;
    });

    useProjectStore.setState({
      activeProject: {
        id: 'proj-r3',
        name: 'Milestone 3 Test Project',
        source_lang: 'ja',
        target_lang: 'th',
        created_at: '2026-07-27T00:00:00Z',
        updated_at: '2026-07-27T00:00:00Z',
        pages: [],
        settings: {
          gpu_execution_provider: 'CUDA',
          ocr_model: 'manga_ocr',
          inpaint_engine: 'lama_onnx',
          batch_size: 1,
          auto_ocr: true,
          auto_inpaint: true,
          auto_translate: false,
        },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('updates GPU Execution Provider settings in project store', async () => {
    const store = useProjectStore.getState();
    expect(store.activeProject?.settings.gpu_execution_provider).toBe('CUDA');

    await store.updateProjectSettings('proj-r3', {
      ...store.activeProject!.settings,
      gpu_execution_provider: 'DirectML',
      execution_provider: 'DirectML',
    });

    const updated = useProjectStore.getState().activeProject?.settings;
    expect(updated?.gpu_execution_provider).toBe('DirectML');
    expect(updated?.execution_provider).toBe('DirectML');
  });

  test('updates Active OCR Model and Active Inpaint Engine', async () => {
    const store = useProjectStore.getState();
    await store.updateProjectSettings('proj-r3', {
      ...store.activeProject!.settings,
      ocr_model: 'gemini',
      ocr_engine: 'gemini',
      inpaint_engine: 'telea',
      active_inpaint_engine: 'telea',
      default_image_inpaint_method: 'Telea',
    });

    const updated = useProjectStore.getState().activeProject?.settings;
    expect(updated?.ocr_model).toBe('gemini');
    expect(updated?.ocr_engine).toBe('gemini');
    expect(updated?.inpaint_engine).toBe('telea');
    expect(updated?.default_image_inpaint_method).toBe('Telea');
  });

  test('updates Batch Size and Automated Pipeline Triggers', async () => {
    const store = useProjectStore.getState();
    await store.updateProjectSettings('proj-r3', {
      ...store.activeProject!.settings,
      batch_size: 4,
      auto_ocr: true,
      auto_inpaint: false,
      auto_translate: true,
    });

    const updated = useProjectStore.getState().activeProject?.settings;
    expect(updated?.batch_size).toBe(4);
    expect(updated?.auto_ocr).toBe(true);
    expect(updated?.auto_inpaint).toBe(false);
    expect(updated?.auto_translate).toBe(true);
  });
});
