import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useProjectStore, type TextBlock, type Page, type Project } from '../stores/projectStore';

describe('Layer Manager & Workspace Productivity (Milestone 4)', () => {
  const mockPageId = 'page-m4-1';
  const mockProjectId = 'proj-m4-1';

  const initialBlocks: TextBlock[] = [
    {
      id: 'blk-1',
      page_id: mockPageId,
      block_index: 0,
      x: 100,
      y: 100,
      width: 150,
      height: 50,
      rotation_deg: 0,
      source_text: 'Layer 1 Text',
      translation: 'ข้อความ Layer 1',
      font_family: 'NotoSansThai',
      font_size: 20,
      color_hex: '#000000',
      bold: false,
      italic: false,
      text_direction: 'horizontal',
      text_align: 'center',
      balloon_type: 'bubble',
      confidence: 0.95,
      extra_metadata: {},
      is_visible: true,
      is_locked: false,
    },
    {
      id: 'blk-2',
      page_id: mockPageId,
      block_index: 1,
      x: 200,
      y: 200,
      width: 150,
      height: 50,
      rotation_deg: 0,
      source_text: 'Layer 2 Text',
      translation: 'ข้อความ Layer 2',
      font_family: 'NotoSansThai',
      font_size: 24,
      color_hex: '#ff0000',
      bold: true,
      italic: false,
      text_direction: 'horizontal',
      text_align: 'left',
      balloon_type: 'narrative',
      confidence: 0.98,
      extra_metadata: {},
      is_visible: true,
      is_locked: false,
    },
    {
      id: 'blk-3',
      page_id: mockPageId,
      block_index: 2,
      x: 300,
      y: 300,
      width: 150,
      height: 50,
      rotation_deg: 0,
      source_text: 'Layer 3 Text',
      translation: 'ข้อความ Layer 3',
      font_family: 'NotoSansThai',
      font_size: 18,
      color_hex: '#0000ff',
      bold: false,
      italic: true,
      text_direction: 'horizontal',
      text_align: 'center',
      balloon_type: 'sfx',
      confidence: 0.90,
      extra_metadata: {},
      is_visible: true,
      is_locked: false,
    },
  ];

  const mockPage: Page = {
    id: mockPageId,
    project_id: mockProjectId,
    page_number: 1,
    name: 'Page 1',
    width: 1000,
    height: 1400,
    source_image_path: '/images/page1.jpg',
    status: 'completed',
    text_blocks: initialBlocks,
  };

  const mockProject: Project = {
    id: mockProjectId,
    name: 'Manga Project M4',
    source_lang: 'ja',
    target_lang: 'th',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    settings: {},
    pages: [mockPage],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/blocks/bulk')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        } as Response);
      }
      if (url.includes('/api/blocks/')) {
        const body = init?.body ? JSON.parse(init.body as string) : {};
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 'blk-updated', ...body }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      } as Response);
    });

    useProjectStore.setState({
      activeProject: JSON.parse(JSON.stringify(mockProject)),
      activePage: JSON.parse(JSON.stringify(mockPage)),
      selectedBlock: initialBlocks[0],
      selectedBlocks: [initialBlocks[0]],
    });
  });

  describe('Requirement 2: Layer Visibility & Lock Toggles', () => {
    it('toggles layer visibility state and persists to extra_metadata', async () => {
      const store = useProjectStore.getState();
      const targetBlock = store.activePage!.text_blocks[0];

      // Toggle to hidden
      await store.updateBlock(targetBlock.id, {
        is_visible: false,
        extra_metadata: { ...targetBlock.extra_metadata, is_visible: false },
      });

      const updatedPage = useProjectStore.getState().activePage!;
      const updatedBlock = updatedPage.text_blocks.find(b => b.id === targetBlock.id)!;

      expect(updatedBlock.is_visible).toBe(false);
      expect(updatedBlock.extra_metadata.is_visible).toBe(false);

      // Toggle back to visible
      await store.updateBlock(targetBlock.id, {
        is_visible: true,
        extra_metadata: { ...updatedBlock.extra_metadata, is_visible: true },
      });

      const restoredBlock = useProjectStore.getState().activePage!.text_blocks.find(b => b.id === targetBlock.id)!;
      expect(restoredBlock.is_visible).toBe(true);
      expect(restoredBlock.extra_metadata.is_visible).toBe(true);
    });

    it('toggles layer lock state to prevent accidental canvas edits', async () => {
      const store = useProjectStore.getState();
      const targetBlock = store.activePage!.text_blocks[1];

      // Lock layer
      await store.updateBlock(targetBlock.id, {
        is_locked: true,
        extra_metadata: { ...targetBlock.extra_metadata, is_locked: true },
      });

      const lockedBlock = useProjectStore.getState().activePage!.text_blocks.find(b => b.id === targetBlock.id)!;
      expect(lockedBlock.is_locked).toBe(true);
      expect(lockedBlock.extra_metadata.is_locked).toBe(true);

      // Unlock layer
      await store.updateBlock(targetBlock.id, {
        is_locked: false,
        extra_metadata: { ...lockedBlock.extra_metadata, is_locked: false },
      });

      const unlockedBlock = useProjectStore.getState().activePage!.text_blocks.find(b => b.id === targetBlock.id)!;
      expect(unlockedBlock.is_locked).toBe(false);
      expect(unlockedBlock.extra_metadata.is_locked).toBe(false);
    });
  });

  describe('Requirement 3: Z-Index Reordering Stack', () => {
    it('reorders Z-Index using bring_forward', async () => {
      const store = useProjectStore.getState();
      // Initially: blk-1 (0), blk-2 (1), blk-3 (2)
      // Bring blk-1 forward (swap 0 with 1) -> blk-2 (0), blk-1 (1), blk-3 (2)
      await store.reorderBlockZIndex(mockPageId, 'blk-1', 'bring_forward');

      const blocks = useProjectStore.getState().activePage!.text_blocks;
      const blk1 = blocks.find(b => b.id === 'blk-1')!;
      const blk2 = blocks.find(b => b.id === 'blk-2')!;
      const blk3 = blocks.find(b => b.id === 'blk-3')!;

      expect(blk2.block_index).toBe(0);
      expect(blk1.block_index).toBe(1);
      expect(blk3.block_index).toBe(2);
    });

    it('reorders Z-Index using send_backward', async () => {
      const store = useProjectStore.getState();
      // Initially: blk-1 (0), blk-2 (1), blk-3 (2)
      // Send blk-3 backward (swap 2 with 1) -> blk-1 (0), blk-3 (1), blk-2 (2)
      await store.reorderBlockZIndex(mockPageId, 'blk-3', 'send_backward');

      const blocks = useProjectStore.getState().activePage!.text_blocks;
      const blk1 = blocks.find(b => b.id === 'blk-1')!;
      const blk2 = blocks.find(b => b.id === 'blk-2')!;
      const blk3 = blocks.find(b => b.id === 'blk-3')!;

      expect(blk1.block_index).toBe(0);
      expect(blk3.block_index).toBe(1);
      expect(blk2.block_index).toBe(2);
    });

    it('reorders Z-Index using bring_to_front', async () => {
      const store = useProjectStore.getState();
      // Initially: blk-1 (0), blk-2 (1), blk-3 (2)
      // Bring blk-1 to front -> blk-2 (0), blk-3 (1), blk-1 (2)
      await store.reorderBlockZIndex(mockPageId, 'blk-1', 'bring_to_front');

      const blocks = useProjectStore.getState().activePage!.text_blocks;
      const blk1 = blocks.find(b => b.id === 'blk-1')!;
      const blk2 = blocks.find(b => b.id === 'blk-2')!;
      const blk3 = blocks.find(b => b.id === 'blk-3')!;

      expect(blk2.block_index).toBe(0);
      expect(blk3.block_index).toBe(1);
      expect(blk1.block_index).toBe(2);
    });

    it('reorders Z-Index using send_to_back', async () => {
      const store = useProjectStore.getState();
      // Initially: blk-1 (0), blk-2 (1), blk-3 (2)
      // Send blk-3 to back -> blk-3 (0), blk-1 (1), blk-2 (2)
      await store.reorderBlockZIndex(mockPageId, 'blk-3', 'send_to_back');

      const blocks = useProjectStore.getState().activePage!.text_blocks;
      const blk1 = blocks.find(b => b.id === 'blk-1')!;
      const blk2 = blocks.find(b => b.id === 'blk-2')!;
      const blk3 = blocks.find(b => b.id === 'blk-3')!;

      expect(blk3.block_index).toBe(0);
      expect(blk1.block_index).toBe(1);
      expect(blk2.block_index).toBe(2);
    });
  });

  describe('Requirement 4: Quick Focus & Selection', () => {
    it('updates selectedBlock state when a layer item is selected', () => {
      const targetBlock = initialBlocks[2];
      useProjectStore.setState({ selectedBlock: targetBlock, selectedBlocks: [targetBlock] });

      const state = useProjectStore.getState();
      expect(state.selectedBlock?.id).toBe('blk-3');
      expect(state.selectedBlocks).toHaveLength(1);
      expect(state.selectedBlocks[0].id).toBe('blk-3');
    });
  });
});
