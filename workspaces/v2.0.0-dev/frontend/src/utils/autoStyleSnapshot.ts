import type { TextBlock } from '../stores/projectStore';

/** Minimal per-block snapshot for undoing Auto Style Page. */
export interface BlockStyleSnapshot {
  blockId: string;
  font_family: string;
  font_size: number;
  color_hex: string;
  bold: boolean;
  italic: boolean;
  text_align: TextBlock['text_align'];
  text_direction: TextBlock['text_direction'];
  balloon_type: TextBlock['balloon_type'];
  extra_metadata: Record<string, unknown>;
}

export interface AutoStyleSnapshot {
  pageId: string;
  createdAt: number;
  blocks: BlockStyleSnapshot[];
}

export function captureAutoStyleSnapshot(
  pageId: string,
  blocks: TextBlock[],
): AutoStyleSnapshot {
  return {
    pageId,
    createdAt: Date.now(),
    blocks: blocks.map((b) => ({
      blockId: b.id,
      font_family: b.font_family,
      font_size: b.font_size,
      color_hex: b.color_hex,
      bold: Boolean(b.bold),
      italic: Boolean(b.italic),
      text_align: b.text_align,
      text_direction: b.text_direction,
      balloon_type: b.balloon_type,
      // Deep-ish copy of metadata so typesetting_spec is frozen
      extra_metadata: JSON.parse(JSON.stringify(b.extra_metadata || {})),
    })),
  };
}

export function snapshotToBulkUpdates(
  snapshot: AutoStyleSnapshot,
): Array<{ blockId: string; data: Partial<TextBlock> }> {
  return snapshot.blocks.map((s) => ({
    blockId: s.blockId,
    data: {
      font_family: s.font_family,
      font_size: s.font_size,
      color_hex: s.color_hex,
      bold: s.bold,
      italic: s.italic,
      text_align: s.text_align,
      text_direction: s.text_direction,
      balloon_type: s.balloon_type,
      extra_metadata: s.extra_metadata,
    },
  }));
}
