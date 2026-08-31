import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { discardPendingBlockUpdates, useProjectStore } from '../stores/projectStore';
import {
  clearAllMutationRevisions,
  getPageMutationRevision,
  shouldAcceptPageResponse,
} from '../utils/blockUpdateTracker';
import type { TextBlock } from '../stores/projectStore';

const responseFor = (block: TextBlock): Response => ({
  ok: true,
  json: async () => block,
} as Response);

describe('Project Store Async & Integration Tests', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    discardPendingBlockUpdates();
    clearAllMutationRevisions();
    
    // Set up default initial store state
    const block1: TextBlock = {
      id: 'blk-1',
      page_id: 'page-1',
      block_index: 0,
      x: 10,
      y: 20,
      width: 100,
      height: 50,
      rotation_deg: 0,
      source_text: 'Hello',
      translation: 'สวัสดี',
      font_family: 'Tahoma',
      font_size: 14,
      color_hex: '#000000',
      bold: false,
      italic: false,
      text_direction: 'horizontal',
      text_align: 'center',
      balloon_type: 'bubble',
      confidence: 1,
      extra_metadata: {},
    };

    const block2: TextBlock = {
      id: 'blk-2',
      page_id: 'page-2', // non-active page
      block_index: 0,
      x: 10,
      y: 20,
      width: 100,
      height: 50,
      rotation_deg: 0,
      source_text: 'World',
      translation: 'โลก',
      font_family: 'Tahoma',
      font_size: 14,
      color_hex: '#000000',
      bold: false,
      italic: false,
      text_direction: 'horizontal',
      text_align: 'center',
      balloon_type: 'bubble',
      confidence: 1,
      extra_metadata: {},
    };

    const page1 = {
      id: 'page-1',
      project_id: 'proj-1',
      page_number: 1,
      name: 'Page 1',
      width: 1000,
      height: 1000,
      source_image_path: '',
      status: 'pending',
      text_blocks: [block1],
    };

    const page2 = {
      id: 'page-2',
      project_id: 'proj-1',
      page_number: 2,
      name: 'Page 2',
      width: 1000,
      height: 1000,
      source_image_path: '',
      status: 'pending',
      text_blocks: [block2],
    };

    const project = {
      id: 'proj-1',
      name: 'Proj 1',
      source_lang: 'en',
      target_lang: 'th',
      created_at: '',
      updated_at: '',
      settings: {},
      pages: [page1, page2],
    };

    useProjectStore.setState({
      activeProject: project,
      activePage: page1,
      selectedBlock: block1,
      selectedBlocks: [block1],
      statusMessage: 'Ready',
      isProcessing: false,
    });
  });

  afterEach(() => {
    discardPendingBlockUpdates();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  test('text debounce keeps layout recompute locked until the server save finishes', async () => {
    let resolveFetch!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveFetch = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => pending);

    void useProjectStore.getState().updateBlock('blk-1', { translation: 'ข้อความใหม่' });
    expect(useProjectStore.getState().isSavingBlocks).toBe(true);

    await vi.advanceTimersByTimeAsync(600);
    expect(useProjectStore.getState().isSavingBlocks).toBe(true);

    resolveFetch(responseFor({
      ...useProjectStore.getState().activePage!.text_blocks[0],
      translation: 'ข้อความใหม่',
    }));
    await vi.advanceTimersByTimeAsync(0);

    expect(useProjectStore.getState().isSavingBlocks).toBe(false);
    expect(useProjectStore.getState().selectedBlock?.translation).toBe('ข้อความใหม่');
  });

  test('text edit immediately invalidates the optimistic typesetting spec', async () => {
    const block = useProjectStore.getState().activePage!.text_blocks[0];
    const withSpec = {
      ...block,
      extra_metadata: {
        typesetting_spec: {
          layout_status: 'valid',
          schema_version: '2.0.0',
          layout_version: '2.0.2',
          layout_engine_version: '2.0.2',
          explicit_lines: ['ข้อความเก่า'],
        },
      },
    };
    const page = { ...useProjectStore.getState().activePage!, text_blocks: [withSpec] };
    useProjectStore.setState({ activePage: page, selectedBlock: withSpec, selectedBlocks: [withSpec] });

    await useProjectStore.getState().updateBlock('blk-1', {
      translation: 'บรรทัดแรก\nบรรทัดสอง',
    });

    const updated = useProjectStore.getState().activePage!.text_blocks[0];
    expect(updated.translation).toBe('บรรทัดแรก\nบรรทัดสอง');
    expect(updated.extra_metadata.typesetting_spec.layout_status).toBe('stale');
  });

  test('Scenario 1: A dispatched, B queued but not dispatched, A returns and is rejected', async () => {
    // We mock fetch with a deferred promise for request A
    let resolveFetchA!: (response: Response) => void;
    const fetchAPromise = new Promise<Response>((resolve) => {
      resolveFetchA = resolve;
    });

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      if (url.toString().includes('blk-1')) {
        return fetchAPromise;
      }
      return Promise.reject(new Error('Unknown url'));
    });

    const store = useProjectStore.getState();

    // Trigger update A (text update)
    store.updateBlock('blk-1', { translation: 'A' });

    // A is debounced. Fast-forward debounce time (600ms) to dispatch A
    await vi.advanceTimersByTimeAsync(600);
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Before A returns, we queue B (another text update)
    store.updateBlock('blk-1', { translation: 'B' });

    // Now resolve A's network request with update A block data
    const updatedBlockA: TextBlock = {
      ...store.activePage!.text_blocks[0],
      translation: 'A',
    };
    resolveFetchA(responseFor(updatedBlockA));

    // Let microtasks flush so A's response callback runs
    await vi.advanceTimersByTimeAsync(0);

    // Verify that the activePage block translation is NOT A (retains B's optimistic update)
    const currentBlock = useProjectStore.getState().activePage?.text_blocks[0];
    expect(currentBlock?.translation).toBe('B');
  });

  test('Scenario 2: A and B dispatched, B returns first, A later; final block/spec is B', async () => {
    let resolveFetchA!: (response: Response) => void;
    const fetchAPromise = new Promise<Response>((resolve) => {
      resolveFetchA = resolve;
    });

    let resolveFetchB!: (response: Response) => void;
    const fetchBPromise = new Promise<Response>((resolve) => {
      resolveFetchB = resolve;
    });

    let requestCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      requestCount++;
      if (requestCount === 1) return fetchAPromise;
      return fetchBPromise;
    });

    const store = useProjectStore.getState();

    // Trigger update A
    store.updateBlock('blk-1', { translation: 'A' });
    await vi.advanceTimersByTimeAsync(600); // Flush debounce A -> Dispatched A
    expect(requestCount).toBe(1);

    // Trigger update B (flushes B)
    store.updateBlock('blk-1', { translation: 'B' });
    await vi.advanceTimersByTimeAsync(600); // Flush debounce B -> Dispatched B
    expect(requestCount).toBe(2);

    // B returns first
    const updatedBlockB: TextBlock = {
      ...useProjectStore.getState().activePage!.text_blocks[0],
      translation: 'B',
      extra_metadata: { typesetting_spec: { layout_status: 'valid', schema_version: '1.0.0', layout_version: '1.0.7', font_size: 12, explicit_lines: ['B'] } }
    };
    resolveFetchB(responseFor(updatedBlockB));
    await vi.advanceTimersByTimeAsync(0);

    // Verify state has B
    expect(useProjectStore.getState().activePage?.text_blocks[0].translation).toBe('B');

    // A returns later
    const updatedBlockA: TextBlock = {
      ...useProjectStore.getState().activePage!.text_blocks[0],
      translation: 'A',
      extra_metadata: { typesetting_spec: { layout_status: 'valid', schema_version: '1.0.0', layout_version: '1.0.7', font_size: 14, explicit_lines: ['A'] } }
    };
    resolveFetchA(responseFor(updatedBlockA));
    await vi.advanceTimersByTimeAsync(0);

    // Verify state still retains B's value because A was discarded
    expect(useProjectStore.getState().activePage?.text_blocks[0].translation).toBe('B');
  });

  test('Scenario 3: different blocks return out of order without overwriting each other', async () => {
    let resolveFetch1!: (response: Response) => void;
    const fetch1Promise = new Promise<Response>((resolve) => { resolveFetch1 = resolve; });

    let resolveFetch2!: (response: Response) => void;
    const fetch2Promise = new Promise<Response>((resolve) => { resolveFetch2 = resolve; });

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      if (url.toString().includes('blk-1')) return fetch1Promise;
      if (url.toString().includes('blk-2')) return fetch2Promise;
      return Promise.reject(new Error('Unknown url'));
    });

    const store = useProjectStore.getState();

    // Trigger update for blk-1
    store.updateBlock('blk-1', { translation: 'A' });
    await vi.advanceTimersByTimeAsync(600);

    store.updateBlock('blk-2', { translation: 'B' });
    await vi.advanceTimersByTimeAsync(600);

    expect(fetchSpy).toHaveBeenCalledTimes(2);

    // blk-2 (fetch 2) returns first
    const updatedBlock2: TextBlock = {
      ...store.activeProject!.pages[1].text_blocks[0],
      translation: 'B',
    };
    resolveFetch2(responseFor(updatedBlock2));
    await vi.advanceTimersByTimeAsync(0);

    // blk-1 (fetch 1) returns later
    const updatedBlock1: TextBlock = {
      ...store.activePage!.text_blocks[0],
      translation: 'A',
    };
    resolveFetch1(responseFor(updatedBlock1));
    await vi.advanceTimersByTimeAsync(0);

    const latestState = useProjectStore.getState();
    expect(latestState.activeProject?.pages[0].text_blocks[0].translation).toBe('A');
    expect(latestState.activeProject?.pages[1].text_blocks[0].translation).toBe('B');
  });

  test('bulk template update preserves text and updates all selected layers atomically', async () => {
    const before = useProjectStore.getState().activeProject!;
    const block1 = before.pages[0].text_blocks[0];
    const block2 = before.pages[1].text_blocks[0];
    const updated1 = { ...block1, font_size: 42, bold: true };
    const updated2 = { ...block2, font_size: 42, bold: true };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => [updated1, updated2],
    } as Response);

    await useProjectStore.getState().updateBlocksBulk([
      { blockId: block1.id, data: { font_size: 42, bold: true } },
      { blockId: block2.id, data: { font_size: 42, bold: true } },
    ]);

    const after = useProjectStore.getState().activeProject!;
    expect(after.pages[0].text_blocks[0].translation).toBe('สวัสดี');
    expect(after.pages[1].text_blocks[0].translation).toBe('โลก');
    expect(after.pages[0].text_blocks[0].font_size).toBe(42);
    expect(after.pages[1].text_blocks[0].font_size).toBe(42);
  });

  test('a pending single-block save cannot commit after and revert a newer bulk preset', async () => {
    const original = useProjectStore.getState().activePage!.text_blocks[0];
    let resolveSingle!: (response: Response) => void;
    const pendingSingle = new Promise<Response>((resolve) => { resolveSingle = resolve; });
    const requestOrder: string[] = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const path = url.toString();
      if (path.endsWith('/blocks/bulk')) {
        requestOrder.push('bulk');
        return Promise.resolve({
          ok: true,
          json: async () => [{ ...original, font_size: 60, bold: true }],
        } as Response);
      }
      requestOrder.push('single');
      return pendingSingle;
    });

    const singleSave = useProjectStore.getState().updateBlock('blk-1', { font_size: 24 });
    const bulkSave = useProjectStore.getState().updateBlocksBulk([
      { blockId: 'blk-1', data: { font_size: 60, bold: true } },
    ]);
    await vi.advanceTimersByTimeAsync(0);

    // The bulk request waits for the older save instead of racing it in the API.
    expect(requestOrder).toEqual(['single']);
    expect(useProjectStore.getState().activePage?.text_blocks[0].font_size).toBe(24);

    resolveSingle(responseFor({ ...original, font_size: 24 }));
    await singleSave;
    await bulkSave;

    expect(requestOrder).toEqual(['single', 'bulk']);
    expect(useProjectStore.getState().activePage?.text_blocks[0].font_size).toBe(60);
    expect(useProjectStore.getState().selectedBlock?.font_size).toBe(60);
  });

  test('Scenario 4: response for a non-active page updates activeProject but not activePage', async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchPromise = new Promise<Response>((resolve) => { resolveFetch = resolve; });

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => fetchPromise);

    const store = useProjectStore.getState();

    // blk-2 belongs to page-2 (non-active page)
    store.updateBlock('blk-2', { translation: 'updated-non-active' });
    await vi.advanceTimersByTimeAsync(600);

    const updatedBlock2: TextBlock = {
      ...store.activeProject!.pages[1].text_blocks[0],
      translation: 'updated-non-active',
    };
    resolveFetch(responseFor(updatedBlock2));
    await vi.advanceTimersByTimeAsync(0);

    const latestState = useProjectStore.getState();
    // activeProject.pages[1].text_blocks[0] (page 2) is updated!
    expect(latestState.activeProject?.pages[1].text_blocks[0].translation).toBe('updated-non-active');
    // activePage (page 1) is NOT updated and does NOT contain blk-2
    expect(latestState.activePage?.id).toBe('page-1');
    expect(latestState.activePage?.text_blocks.find(b => b.id === 'blk-2')).toBeUndefined();
  });

  test('Scenario 5: selectedBlock and selectedBlocks update correctly', async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchPromise = new Promise<Response>((resolve) => { resolveFetch = resolve; });

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => fetchPromise);

    const store = useProjectStore.getState();

    store.updateBlock('blk-1', { translation: 'new-selected-val' });
    await vi.advanceTimersByTimeAsync(600);

    const updatedBlock: TextBlock = {
      ...store.selectedBlock!,
      translation: 'new-selected-val',
    };
    resolveFetch(responseFor(updatedBlock));
    await vi.advanceTimersByTimeAsync(0);

    const latestState = useProjectStore.getState();
    expect(latestState.selectedBlock?.translation).toBe('new-selected-val');
    expect(latestState.selectedBlocks[0].translation).toBe('new-selected-val');
  });

  test('auto-fit sync updates Inspector state and canonical spec without an API call', () => {
    const current = useProjectStore.getState().selectedBlock!;
    const spec = { font_size: 36, line_height: 43.2, layout_status: 'valid' };
    useProjectStore.setState({
      selectedBlock: { ...current, font_size: 36, extra_metadata: { typesetting_spec: spec } },
      selectedBlocks: [{ ...current, font_size: 36, extra_metadata: { typesetting_spec: spec } }],
      activePage: {
        ...useProjectStore.getState().activePage!,
        text_blocks: [{ ...current, font_size: 36, extra_metadata: { typesetting_spec: spec } }],
      },
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    useProjectStore.getState().syncAutoFitFontSize('blk-1', 18);

    const state = useProjectStore.getState();
    expect(state.selectedBlock?.font_size).toBe(18);
    expect(state.selectedBlock?.extra_metadata.typesetting_spec.font_size).toBe(18);
    expect(state.selectedBlock?.extra_metadata.typesetting_spec.line_height).toBeCloseTo(21.6);
    expect(state.activePage?.text_blocks[0].font_size).toBe(18);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test('delete holds the save lock and invalidates an older page refresh', async () => {
    let resolveDelete!: (response: Response) => void;
    const pendingDelete = new Promise<Response>((resolve) => { resolveDelete = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => pendingDelete);
    const refreshRevision = getPageMutationRevision('page-1');

    const deletion = useProjectStore.getState().deleteBlocks(['blk-1']);
    await vi.advanceTimersByTimeAsync(0);

    expect(useProjectStore.getState().isSavingBlocks).toBe(true);
    expect(shouldAcceptPageResponse('page-1', refreshRevision)).toBe(false);

    resolveDelete({ ok: true } as Response);
    await deletion;
    await Promise.resolve();

    expect(useProjectStore.getState().activePage?.text_blocks).toHaveLength(0);
    expect(useProjectStore.getState().isSavingBlocks).toBe(false);
  });

  test('settings saves do not activate the global processing lock', async () => {
    let resolveFetch!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveFetch = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => pending);

    const save = useProjectStore.getState().updateProjectSettings('proj-1', { performance_profile: 'balanced' });
    expect(useProjectStore.getState().isProcessing).toBe(false);
    expect(useProjectStore.getState().statusMessage).toBe('Ready');

    resolveFetch({
      ok: true,
      json: async () => ({ ...useProjectStore.getState().activeProject!, settings: { performance_profile: 'balanced' }, pages: [] }),
    } as Response);
    await save;
    expect(useProjectStore.getState().isProcessing).toBe(false);
  });

  test('an older settings response cannot overwrite the newest settings', async () => {
    let resolveFirst!: (response: Response) => void;
    let resolveSecond!: (response: Response) => void;
    const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    const second = new Promise<Response>((resolve) => { resolveSecond = resolve; });
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => first)
      .mockImplementationOnce(() => second);

    const store = useProjectStore.getState();
    const saveFirst = store.updateProjectSettings('proj-1', { performance_profile: 'eco' });
    const saveSecond = store.updateProjectSettings('proj-1', { performance_profile: 'maximum' });

    resolveSecond({ ok: true, json: async () => ({ ...store.activeProject!, settings: { performance_profile: 'maximum' } }) } as Response);
    await saveSecond;
    resolveFirst({ ok: true, json: async () => ({ ...store.activeProject!, settings: { performance_profile: 'eco' } }) } as Response);
    await saveFirst;

    expect(useProjectStore.getState().activeProject?.settings.performance_profile).toBe('maximum');
  });
});
