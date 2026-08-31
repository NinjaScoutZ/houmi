import React from 'react';
import type { PageMaskTool } from '../utils/pageMaskCanvas';
import { 
  Paintbrush, 
  Eraser, 
  Square, 
  Sparkles, 
  Trash2, 
  Save, 
  X, 
  RotateCcw,
  Sliders,
  Plus,
  Minus
} from 'lucide-react';

export type MaskTool = PageMaskTool;

interface MaskToolbarProps {
  activeTool: MaskTool;
  setActiveTool: (tool: MaskTool) => void;
  brushSize: number;
  setBrushSize: (size: number | ((prev: number) => number)) => void;
  maskOpacity: number;
  setMaskOpacity: (opacity: number) => void;
  onClear: () => void;
  onAutoDetect: () => void;
  onSaveAndClean: () => void;
  onClose: () => void;
  isDetecting: boolean;
  isSaving: boolean;
  canUndo: boolean;
  onUndo: () => void;
}

export const MaskToolbar: React.FC<MaskToolbarProps> = ({
  activeTool,
  setActiveTool,
  brushSize,
  setBrushSize,
  maskOpacity,
  setMaskOpacity,
  onClear,
  onAutoDetect,
  onSaveAndClean,
  onClose,
  isDetecting,
  isSaving,
  canUndo,
  onUndo,
}) => {
  const [showSliders, setShowSliders] = React.useState<boolean>(false);

  return (
    <div className="fixed top-24 left-6 z-50 flex flex-col items-center gap-2 p-2 bg-zinc-950/95 backdrop-blur-md border border-zinc-800 rounded-2xl shadow-2xl text-white select-none transition-all duration-200 hover:border-zinc-700">
      
      {/* Primary Tools - Vertical Stack (Photoshop Left Sidebar Style) */}
      <div className="flex flex-col gap-1 p-1 bg-zinc-900/90 rounded-xl border border-zinc-800/80">
        <button
          type="button"
          onClick={() => setActiveTool('brush')}
          title="แปรงวาด Mask (Brush)"
          className={`p-2 rounded-lg transition-all cursor-pointer ${
            activeTool === 'brush'
              ? 'bg-amber-500 text-zinc-950 font-bold shadow-lg shadow-amber-500/25 scale-105'
              : 'text-zinc-300 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <Paintbrush className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={() => setActiveTool('eraser')}
          title="ยางลบ Mask (Eraser)"
          className={`p-2 rounded-lg transition-all cursor-pointer ${
            activeTool === 'eraser'
              ? 'bg-amber-500 text-zinc-950 font-bold shadow-lg shadow-amber-500/25 scale-105'
              : 'text-zinc-300 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <Eraser className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={() => setActiveTool('box')}
          title="กรอบสี่เหลี่ยม Mask (Box)"
          className={`p-2 rounded-lg transition-all cursor-pointer ${
            activeTool === 'box'
              ? 'bg-amber-500 text-zinc-950 font-bold shadow-lg shadow-amber-500/25 scale-105'
              : 'text-zinc-300 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <Square className="w-4 h-4" />
        </button>
      </div>

      <div className="w-6 h-px bg-zinc-800/80" />

      {/* Brush Size Indicator & Quick Adjustment */}
      <div className="flex flex-col items-center gap-1">
        <button
          type="button"
          onClick={() => setShowSliders(!showSliders)}
          title="ปรับขนาดแปรงและความโปร่งแสง (หรือใช้คีย์บอร์ด [ / ])"
          className={`flex flex-col items-center p-1.5 rounded-xl border transition-all cursor-pointer ${
            showSliders 
              ? 'bg-zinc-800 border-amber-500/50 text-amber-400 shadow-md' 
              : 'bg-zinc-900/60 border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          <span className="text-[9px] font-mono font-bold text-amber-400 mt-0.5">{brushSize}px</span>
        </button>

        {/* Quick Size Increment / Decrement Buttons */}
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setBrushSize(prev => Math.max(4, prev - 4))}
            title="ลดขนาดแปรง (-4px)"
            className="p-1 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors cursor-pointer"
          >
            <Minus className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={() => setBrushSize(prev => Math.min(100, prev + 4))}
            title="เพิ่มขนาดแปรง (+4px)"
            className="p-1 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors cursor-pointer"
          >
            <Plus className="w-3 h-3" />
          </button>
        </div>
      </div>

      {showSliders && (
        <div className="absolute left-14 top-16 z-50 flex flex-col gap-3 p-3 bg-zinc-950/95 backdrop-blur-md border border-zinc-800 rounded-xl shadow-2xl min-w-[190px]">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-300 font-medium font-pixel text-[11px]">Brush Size</span>
            <span className="font-mono font-bold text-amber-400">{brushSize}px</span>
          </div>
          <input
            type="range"
            min="4"
            max="100"
            value={brushSize}
            onChange={(e) => setBrushSize(Number(e.target.value))}
            className="accent-amber-500 h-1.5 bg-zinc-800 rounded-lg cursor-pointer"
          />
          <div className="text-[9px] text-zinc-400">คีย์ลัด: <kbd className="px-1 bg-zinc-800 rounded text-amber-300">[</kbd> เล็ก | <kbd className="px-1 bg-zinc-800 rounded text-amber-300">]</kbd> ใหญ่</div>

          <div className="flex items-center justify-between text-xs pt-1.5 border-t border-zinc-800">
            <span className="text-zinc-300 font-medium font-pixel text-[11px]">Overlay Opacity</span>
            <span className="font-mono font-bold text-amber-400">{Math.round(maskOpacity * 100)}%</span>
          </div>
          <input
            type="range"
            min="0.1"
            max="1.0"
            step="0.05"
            value={maskOpacity}
            onChange={(e) => setMaskOpacity(Number(e.target.value))}
            className="accent-amber-500 h-1.5 bg-zinc-800 rounded-lg cursor-pointer"
          />
        </div>
      )}

      <div className="w-6 h-px bg-zinc-800/80" />

      {/* Utility Buttons */}
      <button
        type="button"
        onClick={onUndo}
        disabled={!canUndo}
        title="ย้อนกลับ (Undo)"
        className="p-2 text-zinc-400 hover:text-white disabled:opacity-30 disabled:hover:text-zinc-400 hover:bg-zinc-900 rounded-xl transition-colors cursor-pointer"
      >
        <RotateCcw className="w-4 h-4" />
      </button>

      <button
        type="button"
        onClick={onClear}
        title="ลบ Mask ทั้งหมด"
        className="p-2 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded-xl transition-colors cursor-pointer"
      >
        <Trash2 className="w-4 h-4" />
      </button>

      <div className="w-6 h-px bg-zinc-800/80" />

      {/* Primary Action Buttons */}
      <button
        type="button"
        onClick={onAutoDetect}
        disabled={isDetecting}
        title="ตรวจจับมาร์กอัตโนมัติด้วย Manga UNet++"
        className="p-2.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 disabled:opacity-50 rounded-xl transition-all shadow-md shadow-amber-500/10 cursor-pointer"
      >
        <Sparkles className={`w-4 h-4 ${isDetecting ? 'animate-spin' : ''}`} />
      </button>

      <button
        type="button"
        onClick={onSaveAndClean}
        disabled={isSaving}
        title="บันทึก Mask และสั่งลบข้อความ (Clean Inpaint)"
        className="p-2.5 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 disabled:opacity-50 rounded-xl transition-all shadow-md shadow-emerald-500/10 cursor-pointer"
      >
        <Save className="w-4 h-4" />
      </button>

      <button
        type="button"
        onClick={onClose}
        title="ปิดโหมด Mask"
        className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-900 rounded-xl transition-colors mt-1 cursor-pointer"
      >
        <X className="w-4 h-4" />
      </button>

    </div>
  );
};
