import { describe, test, expect, beforeEach } from 'vitest';
import {
  incrementMutationRevision,
  shouldAcceptResponse,
  applyBlockResponse,
  clearAllMutationRevisions,
  getPageMutationRevision,
  incrementPageMutationRevision,
  shouldAcceptPageResponse,
} from '../utils/blockUpdateTracker';
import type { MinimalProjectState } from '../utils/blockUpdateTracker';
import type { TextBlock } from '../stores/projectStore';

describe('Block Update Tracker Verification', () => {
  beforeEach(() => {
    clearAllMutationRevisions();
  });

  const createDummyBlock = (id: string, translation: string): TextBlock => ({
    id,
    page_id: 'page-1',
    block_index: 0,
    x: 10,
    y: 20,
    width: 100,
    height: 50,
    rotation_deg: 0,
    source_text: 'source',
    translation,
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
  });

  test('Scenario A: In-flight response rejected by newer queued mutation', () => {
    const blockId = 'blk-1';
    
    // User mutation A starts
    const revA = incrementMutationRevision(blockId); // rev = 1
    
    // While request A is in flight, user mutation B is applied optimistically and queued
    const revB = incrementMutationRevision(blockId); // rev = 2
    
    // Request A returns
    const acceptA = shouldAcceptResponse(blockId, revA);
    expect(acceptA).toBe(false); // Rejected!
    
    // Request B returns
    const acceptB = shouldAcceptResponse(blockId, revB);
    expect(acceptB).toBe(true); // Accepted!
  });

  test('Scenario B: Out-of-order response resolving (B returns first, then A)', () => {
    const blockId = 'blk-1';
    
    const revA = incrementMutationRevision(blockId); // rev = 1
    const revB = incrementMutationRevision(blockId); // rev = 2
    
    // B returns first
    expect(shouldAcceptResponse(blockId, revB)).toBe(true); // B accepted
    
    // A returns later
    expect(shouldAcceptResponse(blockId, revA)).toBe(false); // A rejected!
  });

  test('Scenario C: Independent concurrent updates to different blocks', () => {
    const block1Id = 'blk-1';
    const block2Id = 'blk-2';
    
    const rev1 = incrementMutationRevision(block1Id); // rev = 1
    const rev2 = incrementMutationRevision(block2Id); // rev = 1
    
    expect(shouldAcceptResponse(block1Id, rev1)).toBe(true);
    expect(shouldAcceptResponse(block2Id, rev2)).toBe(true);
    
    const block1 = createDummyBlock(block1Id, 'orig1');
    const block2 = createDummyBlock(block2Id, 'orig2');
    
    const page = {
      id: 'page-1',
      project_id: 'proj-1',
      page_number: 1,
      name: 'Page 1',
      width: 1000,
      height: 1000,
      source_image_path: '',
      status: 'pending',
      text_blocks: [block1, block2],
    };
    
    const project = {
      id: 'proj-1',
      name: 'Proj 1',
      source_lang: 'ja',
      target_lang: 'th',
      created_at: '',
      updated_at: '',
      settings: {},
      pages: [page],
    };
    
    const state: MinimalProjectState = {
      activeProject: project,
      activePage: page,
      selectedBlock: block1,
      selectedBlocks: [block1],
    };
    
    const updatedBlock1 = { ...block1, translation: 'new1' };
    
    // Apply update to block-1
    const nextState = applyBlockResponse(state, block1Id, updatedBlock1);
    
    // Verify block 1 changed, block 2 remains unchanged
    expect(nextState.activePage?.text_blocks.find(b => b.id === block1Id)?.translation).toBe('new1');
    expect(nextState.activePage?.text_blocks.find(b => b.id === block2Id)?.translation).toBe('orig2');
  });

  test('stale page refresh is rejected after a resize or delete begins', () => {
    const pageId = 'page-1';
    const refreshRevision = getPageMutationRevision(pageId);

    incrementPageMutationRevision(pageId);

    expect(shouldAcceptPageResponse(pageId, refreshRevision)).toBe(false);
    expect(shouldAcceptPageResponse(pageId, getPageMutationRevision(pageId))).toBe(true);
  });

  test('Scenario D: Propagates response correctly to all store targets', () => {
    const blockId = 'blk-1';
    const block = createDummyBlock(blockId, 'original');
    
    const page = {
      id: 'page-1',
      project_id: 'proj-1',
      page_number: 1,
      name: 'Page 1',
      width: 1000,
      height: 1000,
      source_image_path: '',
      status: 'pending',
      text_blocks: [block],
    };
    
    const project = {
      id: 'proj-1',
      name: 'Proj 1',
      source_lang: 'ja',
      target_lang: 'th',
      created_at: '',
      updated_at: '',
      settings: {},
      pages: [page],
    };
    
    const state: MinimalProjectState = {
      activeProject: project,
      activePage: page,
      selectedBlock: block,
      selectedBlocks: [block],
    };
    
    const updatedBlock = { ...block, translation: 'updated' };
    const nextState = applyBlockResponse(state, blockId, updatedBlock);
    
    // Assert all state pieces are updated correctly
    expect(nextState.activePage?.text_blocks[0].translation).toBe('updated');
    expect(nextState.activeProject?.pages[0].text_blocks[0].translation).toBe('updated');
    expect(nextState.selectedBlock?.translation).toBe('updated');
    expect(nextState.selectedBlocks?.[0]?.translation).toBe('updated');
  });
});
