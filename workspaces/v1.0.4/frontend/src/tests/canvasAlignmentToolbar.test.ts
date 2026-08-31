import { describe, it, expect, beforeEach } from 'vitest';
import { useProjectStore } from '../stores/projectStore';

describe('CanvasAlignment Operations', () => {
  beforeEach(() => {
    useProjectStore.setState({
      activePage: {
        id: 'p1',
        project_id: 'proj1',
        page_number: 1,
        width: 1000,
        height: 1500,
        image_path: '/path/to/p1.jpg',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        text_blocks: [
          {
            id: 'b1',
            page_id: 'p1',
            block_index: 0,
            x: 100,
            y: 100,
            width: 80,
            height: 40,
            source_text: 'Top',
            translation: 'บน',
            confidence: 0.95,
            font_size: 20,
            font_family: 'Tahoma',
          } as any,
          {
            id: 'b2',
            page_id: 'p1',
            block_index: 1,
            x: 200,
            y: 300,
            width: 120,
            height: 60,
            source_text: 'Middle',
            translation: 'กลาน',
            confidence: 0.95,
            font_size: 24,
            font_family: 'Tahoma',
          } as any,
          {
            id: 'b3',
            page_id: 'p1',
            block_index: 2,
            x: 150,
            y: 600,
            width: 100,
            height: 50,
            source_text: 'Bottom',
            translation: 'ล่าง',
            confidence: 0.95,
            font_size: 22,
            font_family: 'Tahoma',
          } as any,
        ],
      } as any,
    });
  });

  it('aligns blocks to the left (min X)', () => {
    const blocks = useProjectStore.getState().activePage!.text_blocks;
    const minX = Math.min(...blocks.map((b) => b.x));
    expect(minX).toBe(100);

    blocks.forEach((b) => {
      useProjectStore.getState().updateBlock(b.id, { x: minX });
    });

    const updated = useProjectStore.getState().activePage!.text_blocks;
    expect(updated.every((b) => b.x === 100)).toBe(true);
  });

  it('aligns blocks to the right (max X + width)', () => {
    const blocks = useProjectStore.getState().activePage!.text_blocks;
    const maxRight = Math.max(...blocks.map((b) => b.x + b.width));
    expect(maxRight).toBe(320);

    blocks.forEach((b) => {
      useProjectStore.getState().updateBlock(b.id, { x: maxRight - b.width });
    });

    const updated = useProjectStore.getState().activePage!.text_blocks;
    expect(updated[0].x).toBe(320 - 80);
    expect(updated[1].x).toBe(320 - 120);
    expect(updated[2].x).toBe(320 - 100);
  });

  it('aligns blocks to vertical middle', () => {
    const blocks = useProjectStore.getState().activePage!.text_blocks;
    const centers = blocks.map((b) => b.y + b.height / 2);
    const avgCenter = centers.reduce((a, c) => a + c, 0) / centers.length;

    blocks.forEach((b) => {
      const newY = Math.round(avgCenter - b.height / 2);
      useProjectStore.getState().updateBlock(b.id, { y: newY });
    });

    const updated = useProjectStore.getState().activePage!.text_blocks;
    expect(updated[0].y).toBe(Math.round(avgCenter - 20));
    expect(updated[1].y).toBe(Math.round(avgCenter - 30));
  });

  it('distributes vertical spacing evenly', () => {
    const blocks = useProjectStore.getState().activePage!.text_blocks;
    const sorted = [...blocks].sort((a, b) => a.y - b.y);
    const minY = sorted[0].y;
    const maxY = sorted[sorted.length - 1].y;
    const totalHeight = sorted.reduce((sum, b) => sum + b.height, 0);
    const gap = (maxY + sorted[sorted.length - 1].height - minY - totalHeight) / (sorted.length - 1);

    let currentY = minY;
    sorted.forEach((b) => {
      useProjectStore.getState().updateBlock(b.id, { y: Math.round(currentY) });
      currentY += b.height + gap;
    });

    const updated = useProjectStore.getState().activePage!.text_blocks;
    expect(updated[0].y).toBe(100);
    expect(updated[1].y).toBe(100 + 40 + 200);
    expect(updated[2].y).toBe(340 + 60 + 200);
  });
});