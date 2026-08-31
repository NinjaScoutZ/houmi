import React from 'react';
import { 
  Merge, 
  AlignLeft, 
  AlignCenter, 
  AlignRight, 
  AlignStartVertical, 
  AlignCenterVertical, 
  AlignEndVertical, 
  AlignHorizontalDistributeCenter, 
  AlignVerticalDistributeCenter, 
  X 
} from 'lucide-react';
import { useProjectStore } from '../stores/projectStore';

export interface CanvasAlignmentToolbarProps {
  selectedBlockIds: string[];
  onClearSelection?: () => void;
}

export const CanvasAlignmentToolbar: React.FC<CanvasAlignmentToolbarProps> = ({
  selectedBlockIds,
  onClearSelection,
}) => {
  const activePage = useProjectStore((state) => state.activePage);
  const updateBlock = useProjectStore((state) => state.updateBlock);

  if (!activePage || selectedBlockIds.length < 2) return null;

  const selectedBlocks = activePage.text_blocks.filter((b) => selectedBlockIds.includes(b.id));
  if (selectedBlocks.length < 2) return null;

  // Alignment functions
  const alignLeft = () => {
    const minX = Math.min(...selectedBlocks.map((b) => b.x));
    selectedBlocks.forEach((b) => {
      if (b.x !== minX) updateBlock(b.id, { x: minX });
    });
  };

  const alignCenter = () => {
    const centers = selectedBlocks.map((b) => b.x + b.width / 2);
    const avgCenter = centers.reduce((a, c) => a + c, 0) / centers.length;
    selectedBlocks.forEach((b) => {
      const newX = Math.round(avgCenter - b.width / 2);
      if (b.x !== newX) updateBlock(b.id, { x: newX });
    });
  };

  const alignRight = () => {
    const maxRight = Math.max(...selectedBlocks.map((b) => b.x + b.width));
    selectedBlocks.forEach((b) => {
      const newX = maxRight - b.width;
      if (b.x !== newX) updateBlock(b.id, { x: newX });
    });
  };

  const alignTop = () => {
    const minY = Math.min(...selectedBlocks.map((b) => b.y));
    selectedBlocks.forEach((b) => {
      if (b.y !== minY) updateBlock(b.id, { y: minY });
    });
  };

  const alignMiddle = () => {
    const centers = selectedBlocks.map((b) => b.y + b.height / 2);
    const avgCenter = centers.reduce((a, c) => a + c, 0) / centers.length;
    selectedBlocks.forEach((b) => {
      const newY = Math.round(avgCenter - b.height / 2);
      if (b.y !== newY) updateBlock(b.id, { y: newY });
    });
  };

  const alignBottom = () => {
    const maxBottom = Math.max(...selectedBlocks.map((b) => b.y + b.height));
    selectedBlocks.forEach((b) => {
      const newY = maxBottom - b.height;
      if (b.y !== newY) updateBlock(b.id, { y: newY });
    });
  };

  const distributeHorizontally = () => {
    if (selectedBlocks.length < 3) return;
    const sorted = [...selectedBlocks].sort((a, b) => a.x - b.x);
    const minX = sorted[0].x;
    const maxX = sorted[sorted.length - 1].x;
    const totalWidth = sorted.reduce((sum, b) => sum + b.width, 0);
    const gap = (maxX + sorted[sorted.length - 1].width - minX - totalWidth) / (sorted.length - 1);

    let currentX = minX;
    sorted.forEach((b) => {
      const newX = Math.round(currentX);
      if (b.x !== newX) updateBlock(b.id, { x: newX });
      currentX += b.width + gap;
    });
  };

  const distributeVertically = () => {
    if (selectedBlocks.length < 3) return;
    const sorted = [...selectedBlocks].sort((a, b) => a.y - b.y);
    const minY = sorted[0].y;
    const maxY = sorted[sorted.length - 1].y;
    const totalHeight = sorted.reduce((sum, b) => sum + b.height, 0);
    const gap = (maxY + sorted[sorted.length - 1].height - minY - totalHeight) / (sorted.length - 1);

    let currentY = minY;
    sorted.forEach((b) => {
      const newY = Math.round(currentY);
      if (b.y !== newY) updateBlock(b.id, { y: newY });
      currentY += b.height + gap;
    });
  };

  const mergeBlocks = async () => {
    if (selectedBlocks.length < 2) return;
    const deleteBlocks = useProjectStore.getState().deleteBlocks;

    const minX = Math.min(...selectedBlocks.map((b) => b.x));
    const minY = Math.min(...selectedBlocks.map((b) => b.y));
    const maxX = Math.max(...selectedBlocks.map((b) => b.x + b.width));
    const maxY = Math.max(...selectedBlocks.map((b) => b.y + b.height));

    const sorted = [...selectedBlocks].sort((a, b) => a.y - b.y);
    const combinedSource = sorted.map((b) => b.source_text).filter(Boolean).join('\n');
    const combinedTrans = sorted.map((b) => b.translation).filter(Boolean).join('\n');

    const primaryBlock = sorted[0];
    const otherBlockIds = sorted.slice(1).map((b) => b.id);

    await updateBlock(primaryBlock.id, {
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY,
      source_text: combinedSource,
      translation: combinedTrans,
    });

    if (otherBlockIds.length > 0) {
      await deleteBlocks(otherBlockIds);
    }
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 px-2.5 py-1.5 bg-zinc-950/95 backdrop-blur-md border border-zinc-800 rounded-xl shadow-2xl text-xs text-slate-200 animate-in fade-in slide-in-from-top-2 duration-150 flex-wrap justify-center font-sans select-none">
      <span className="font-bold text-[10.5px] text-amber-400 mr-1 border-r border-zinc-800 pr-2 font-pixel flex items-center gap-1">
        {selectedBlocks.length} Selected
      </span>

      {/* Merge Action */}
      <button
        onClick={mergeBlocks}
        className="px-2 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg font-semibold transition-colors flex items-center gap-1 mr-1 text-[11px] cursor-pointer"
        title="Merge selected overlapping speech balloons into one block (Ctrl+M)"
      >
        <Merge size={12} className="text-amber-400" />
        <span>Merge</span>
      </button>

      <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />

      {/* Horizontal Alignments */}
      <button
        onClick={alignLeft}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Left Edges"
      >
        <AlignLeft size={13} />
      </button>

      <button
        onClick={alignCenter}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Horizontal Center"
      >
        <AlignCenter size={13} />
      </button>

      <button
        onClick={alignRight}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Right Edges"
      >
        <AlignRight size={13} />
      </button>

      <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />

      {/* Vertical Alignments */}
      <button
        onClick={alignTop}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Top Edges"
      >
        <AlignStartVertical size={13} />
      </button>

      <button
        onClick={alignMiddle}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Vertical Middle"
      >
        <AlignCenterVertical size={13} />
      </button>

      <button
        onClick={alignBottom}
        className="p-1.5 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300 rounded-lg transition-colors cursor-pointer"
        title="Align Bottom Edges"
      >
        <AlignEndVertical size={13} />
      </button>

      <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />

      {/* Distribution */}
      <button
        onClick={distributeHorizontally}
        disabled={selectedBlocks.length < 3}
        className={`p-1.5 rounded-lg border transition-colors cursor-pointer ${
          selectedBlocks.length < 3
            ? 'bg-zinc-900/40 border-zinc-900 text-zinc-600 cursor-not-allowed'
            : 'bg-zinc-900/80 hover:bg-zinc-800 border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300'
        }`}
        title="Distribute Horizontal Spacing (3+ Blocks)"
      >
        <AlignHorizontalDistributeCenter size={13} />
      </button>

      <button
        onClick={distributeVertically}
        disabled={selectedBlocks.length < 3}
        className={`p-1.5 rounded-lg border transition-colors cursor-pointer ${
          selectedBlocks.length < 3
            ? 'bg-zinc-900/40 border-zinc-900 text-zinc-600 cursor-not-allowed'
            : 'bg-zinc-900/80 hover:bg-zinc-800 border-zinc-800/80 hover:border-amber-500/40 text-slate-300 hover:text-amber-300'
        }`}
        title="Distribute Vertical Spacing (3+ Blocks)"
      >
        <AlignVerticalDistributeCenter size={13} />
      </button>

      {onClearSelection && (
        <>
          <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />
          <button
            onClick={onClearSelection}
            className="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
            title="Deselect All"
          >
            <X size={13} />
          </button>
        </>
      )}
    </div>
  );
};

