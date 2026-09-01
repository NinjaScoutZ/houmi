import React, { useState } from 'react';
import { 
  Pipette, 
  AlignLeft, 
  AlignCenter, 
  AlignRight, 
  Wand2, 
  Copy, 
  Trash2, 
  Sparkles,
  Minus,
  Plus,
  Crosshair,
  X
} from 'lucide-react';
import { useProjectStore } from '../stores/projectStore';
import { apiFetch } from '../api/runtime';

export interface FloatingLetteringBarProps {
  blockId: string;
  canvasScale: number;
  blockX: number;
  blockY: number;
  blockWidth: number;
  blockHeight: number;
  onAutoFit?: (blockId: string) => void;
  onDuplicate?: (blockId: string) => void;
  onDelete?: (blockId: string) => void;
  onClose?: () => void;
}

export const FloatingLetteringBar: React.FC<FloatingLetteringBarProps> = ({
  blockId,
  canvasScale,
  blockX,
  blockY,
  blockWidth,
  blockHeight,
  onAutoFit,
  onDuplicate,
  onDelete,
  onClose,
}) => {
  const activePage = useProjectStore((state) => state.activePage);
  const updateBlock = useProjectStore((state) => state.updateBlock);
  const [showStrokePopover, setShowStrokePopover] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);

  const block = activePage?.text_blocks.find((b) => b.id === blockId);
  if (!block) return null;

  const fontSize = block.font_size || 16;
  const fontColor = block.color_hex || block.font_color || '#000000';
  const strokeColor = block.stroke_color || '#ffffff';
  const strokeWidth = block.stroke_width || 0;
  const alignment = block.text_align || 'center';
  const isVertical = block.text_direction === 'vertical' || block.direction === 'vertical';

  const handleFontSizeChange = (delta: number) => {
    const newSize = Math.max(8, Math.min(120, fontSize + delta));
    updateBlock(block.id, { font_size: newSize });
  };

  const handleEyedropper = async (target: 'font' | 'stroke') => {
    if ((window as any).EyeDropper) {
      try {
        const eyeDropper = new (window as any).EyeDropper();
        const result = await eyeDropper.open();
        if (result?.sRGBHex) {
          if (target === 'font') {
            updateBlock(block.id, { color_hex: result.sRGBHex, font_color: result.sRGBHex });
          } else {
            updateBlock(block.id, { stroke_color: result.sRGBHex, stroke_width: strokeWidth || 2 });
          }
        }
      } catch {
        // User cancelled eyedropper
      }
    }
  };

  const handleAutoExtractStyle = async () => {
    if (!activePage) return;
    setIsExtracting(true);
    try {
      const res = await apiFetch('/api/pipeline/extract-style', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_id: activePage.id,
          bbox: [Math.round(block.x), Math.round(block.y), Math.round(block.width), Math.round(block.height)],
          block_id: block.id,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.style) {
          const updates: Record<string, any> = {
            color_hex: data.style.text_color || '#000000',
            font_color: data.style.text_color || '#000000',
          };
          if (data.style.has_stroke && data.style.stroke_color) {
            updates.stroke_color = data.style.stroke_color;
            updates.stroke_width = data.style.stroke_width || 2;
          }
          if (data.style.rotation_deg) {
            updates.rotation_deg = data.style.rotation_deg;
          }
          updateBlock(block.id, updates);
        }
      }
    } catch (e) {
      console.error('Failed to extract style:', e);
    } finally {
      setIsExtracting(false);
    }
  };

  const [isCentering, setIsCentering] = useState(false);

  const handleCenterInBalloon = async () => {
    if (!block) return;
    setIsCentering(true);
    try {
      const res = await apiFetch(`/api/pipeline/blocks/${block.id}/smart-balloon/recompute`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        if (data.smart_x != null && data.smart_width != null) {
          updateBlock(block.id, {
            x: Number(data.smart_x),
            y: Number(data.smart_y),
            width: Number(data.smart_width),
            height: Number(data.smart_height),
            smart_x: Number(data.smart_x),
            smart_y: Number(data.smart_y),
            smart_width: Number(data.smart_width),
            smart_height: Number(data.smart_height),
          });
        }
      }
    } catch (e) {
      console.error('Failed to center in balloon:', e);
    } finally {
      setIsCentering(false);
    }
  };

  // Smart positioning: flip below textbox if too close to top edge of page
  const isNearTop = blockY * canvasScale < 75;
  const topPos = isNearTop
    ? (blockY + blockHeight) * canvasScale + 24
    : blockY * canvasScale - 65;
  // Clamp left position so the 380px toolbar is never clipped on the left edge
  const rawCenter = (blockX + blockWidth / 2) * canvasScale;
  const leftPos = Math.max(195, rawCenter);

  return (
    <div
      className="absolute z-50 flex items-center gap-1 px-2.5 py-1.5 bg-zinc-950/95 backdrop-blur-md border border-zinc-800 rounded-xl shadow-2xl text-xs text-slate-200 animate-in fade-in zoom-in-95 duration-100 font-sans select-none"
      style={{
        top: `${topPos}px`,
        left: `${leftPos}px`,
        transform: 'translateX(-50%)',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Font Size Stepper */}
      <div className="flex items-center bg-zinc-900/90 rounded-lg p-0.5 border border-zinc-800/80">
        <button
          onClick={() => handleFontSizeChange(-1)}
          className="p-1 hover:bg-zinc-800 rounded text-slate-300 hover:text-white transition-colors cursor-pointer"
          title="Decrease font size"
        >
          <Minus size={12} />
        </button>
        <span className="px-1.5 font-mono text-[11px] font-semibold text-amber-400 min-w-[28px] text-center">
          {Math.round(fontSize)}
        </span>
        <button
          onClick={() => handleFontSizeChange(1)}
          className="p-1 hover:bg-zinc-800 rounded text-slate-300 hover:text-white transition-colors cursor-pointer"
          title="Increase font size"
        >
          <Plus size={12} />
        </button>
      </div>

      <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />

      {/* Font Fill Color Picker */}
      <div className="relative flex items-center gap-1 group" title="Font Color">
        <label className="flex items-center gap-1 px-1.5 py-1 bg-zinc-900/90 hover:bg-zinc-800/90 rounded-lg border border-zinc-800/80 hover:border-amber-500/40 cursor-pointer transition-colors">
          <span
            className="w-3.5 h-3.5 rounded-full border border-zinc-600 shadow-sm"
            style={{ backgroundColor: fontColor }}
          />
          <input
            type="color"
            value={fontColor.startsWith('#') ? fontColor : '#000000'}
            onChange={(e) => updateBlock(block.id, { color_hex: e.target.value, font_color: e.target.value })}
            className="sr-only"
          />
        </label>
        {(window as any).EyeDropper && (
          <button
            onClick={() => handleEyedropper('font')}
            className="p-1 hover:bg-zinc-800 rounded text-slate-400 hover:text-amber-400 transition-colors cursor-pointer"
            title="Pick text color from screen"
          >
            <Pipette size={12} />
          </button>
        )}
      </div>

      {/* Stroke / Outline Popover */}
      <div className="relative">
        <button
          onClick={() => setShowStrokePopover(!showStrokePopover)}
          className={`flex items-center gap-1 px-1.5 py-1 rounded-lg border transition-colors cursor-pointer text-[11px] ${
            strokeWidth > 0 
              ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' 
              : 'bg-zinc-900/90 border-zinc-800/80 text-slate-400 hover:text-slate-200 hover:border-zinc-700'
          }`}
          title="Text Outline / Stroke Settings"
        >
          <span
            className="w-3 h-3 rounded-full border border-zinc-600 shadow-sm"
            style={{ backgroundColor: strokeWidth > 0 ? strokeColor : 'transparent' }}
          />
          <span>{strokeWidth > 0 ? `${strokeWidth}px` : 'No Stroke'}</span>
        </button>

        {showStrokePopover && (
          <div className="absolute top-full left-0 mt-1.5 p-2.5 bg-zinc-950/95 border border-zinc-800 rounded-xl shadow-2xl flex flex-col gap-2 min-w-[200px] z-50 animate-in fade-in zoom-in-95 backdrop-blur-md">
            <div className="flex items-center justify-between text-[11px] text-slate-300 font-semibold">
              <span>Outline Stroke</span>
              <button
                onClick={() => updateBlock(block.id, { stroke_width: 0 })}
                className="text-[10px] text-rose-400 hover:underline cursor-pointer"
              >
                Clear
              </button>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={12}
                step={1}
                value={strokeWidth}
                onChange={(e) => updateBlock(block.id, { stroke_width: parseInt(e.target.value, 10) })}
                className="w-full accent-amber-400 cursor-pointer"
              />
              <span className="font-mono text-[11px] min-w-[20px] text-amber-300">{strokeWidth}px</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400">Color:</span>
              <label className="flex items-center gap-1 px-1.5 py-0.5 bg-zinc-900 rounded-lg border border-zinc-800 hover:border-amber-500/40 cursor-pointer transition-colors">
                <span className="w-3 h-3 rounded-full border border-zinc-600" style={{ backgroundColor: strokeColor }} />
                <input
                  type="color"
                  value={strokeColor.startsWith('#') ? strokeColor : '#ffffff'}
                  onChange={(e) => updateBlock(block.id, { stroke_color: e.target.value })}
                  className="sr-only"
                />
              </label>
              {(window as any).EyeDropper && (
                <button
                  onClick={() => handleEyedropper('stroke')}
                  className="p-1 hover:bg-zinc-800 rounded text-slate-400 hover:text-amber-400 cursor-pointer transition-colors"
                  title="Pick stroke color from screen"
                >
                  <Pipette size={11} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />

      {/* Alignment Toggles */}
      <div className="flex items-center bg-zinc-900/90 rounded-lg p-0.5 border border-zinc-800/80">
        <button
          onClick={() => updateBlock(block.id, { text_align: 'left' })}
          className={`p-1 rounded transition-colors cursor-pointer ${alignment === 'left' ? 'bg-amber-500/20 text-amber-300' : 'text-slate-400 hover:text-slate-200'}`}
          title="Align Left"
        >
          <AlignLeft size={12} />
        </button>
        <button
          onClick={() => updateBlock(block.id, { text_align: 'center' })}
          className={`p-1 rounded transition-colors cursor-pointer ${alignment === 'center' ? 'bg-amber-500/20 text-amber-300' : 'text-slate-400 hover:text-slate-200'}`}
          title="Align Center"
        >
          <AlignCenter size={12} />
        </button>
        <button
          onClick={() => updateBlock(block.id, { text_align: 'right' })}
          className={`p-1 rounded transition-colors cursor-pointer ${alignment === 'right' ? 'bg-amber-500/20 text-amber-300' : 'text-slate-400 hover:text-slate-200'}`}
          title="Align Right"
        >
          <AlignRight size={12} />
        </button>
      </div>

      {/* Orientation Toggle */}
      <button
        onClick={() => updateBlock(block.id, { 
          text_direction: isVertical ? 'horizontal' : 'vertical',
          direction: isVertical ? 'horizontal' : 'vertical'
        })}
        className={`px-1.5 py-1 rounded-lg border transition-colors cursor-pointer font-bold text-[11px] ${
          isVertical 
            ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' 
            : 'bg-zinc-900/90 border-zinc-800/80 text-slate-400 hover:text-slate-200 hover:border-zinc-700'
        }`}
        title={isVertical ? 'Switch to Horizontal' : 'Switch to Vertical CJK'}
      >
        {isVertical ? '↕ CJK' : '↔ LTR'}
      </button>

      {/* Auto Extract Style from Image */}
      <button
        onClick={handleAutoExtractStyle}
        disabled={isExtracting}
        className="p-1.5 bg-zinc-900/90 hover:bg-amber-500/20 border border-zinc-800/80 hover:border-amber-500/40 rounded-lg text-amber-400 transition-colors cursor-pointer disabled:opacity-50"
        title="Auto-Extract Text Color and Stroke from Original Image"
      >
        <Sparkles size={12} className={isExtracting ? 'animate-spin' : ''} />
      </button>

      {/* Center in Balloon */}
      <button
        onClick={handleCenterInBalloon}
        disabled={isCentering}
        className="p-1.5 bg-zinc-900/90 hover:bg-cyan-500/20 border border-zinc-800/80 hover:border-cyan-500/40 rounded-lg text-cyan-400 transition-colors cursor-pointer disabled:opacity-50"
        title="🎯 จัดกึ่งกลางบอลลูน (Center in Balloon)"
      >
        <Crosshair size={12} className={isCentering ? 'animate-spin' : ''} />
      </button>

      {/* Auto-Fit Font */}
      {onAutoFit && (
        <button
          onClick={() => onAutoFit(block.id)}
          className="p-1.5 bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-800/80 hover:border-amber-500/40 rounded-lg text-amber-400 transition-colors cursor-pointer"
          title="Auto-fit font size to bubble contour"
        >
          <Wand2 size={12} />
        </button>
      )}

      {/* Clone & Delete */}
      {onDuplicate && (
        <button
          onClick={() => onDuplicate(block.id)}
          className="p-1.5 hover:bg-zinc-800 rounded-lg text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
          title="Duplicate Block"
        >
          <Copy size={12} />
        </button>
      )}
      {onDelete && (
        <button
          onClick={() => onDelete(block.id)}
          className="p-1.5 hover:bg-rose-500/20 rounded-lg text-rose-400 transition-colors cursor-pointer"
          title="Delete Block"
        >
          <Trash2 size={12} />
        </button>
      )}

      {onClose && (
        <>
          <div className="w-[1px] h-4 bg-zinc-800 mx-0.5" />
          <button
            type="button"
            onClick={onClose}
            className="p-1 hover:bg-zinc-800 rounded-lg text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"
            title="ซ่อนแถบเครื่องมือลอยนี้ (เปิดใหม่ได้ที่เมนู View > Floating Toolbar หรือปุ่ม 🎛️)"
          >
            <X size={12} />
          </button>
        </>
      )}
    </div>
  );
};
