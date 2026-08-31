import React, { useEffect, useRef } from 'react';
import { 
  Scan, 
  Paintbrush, 
  Wand2, 
  Eye, 
  EyeOff, 
  Lock, 
  Unlock, 
  Copy, 
  Clipboard, 
  Scissors, 
  Sparkles, 
  Trash2, 
  Layers, 
  Merge, 
  ArrowUpDown, 
  Maximize2,
  RefreshCw,
  RotateCw,
  AlertTriangle
} from 'lucide-react';

export interface CanvasContextMenuProps {
  x: number;
  y: number;
  blockId: string | null;
  selectedBlockIds?: string[];
  onClose: () => void;
  onRunOCR?: (blockId: string) => void;
  onCleanMask?: (blockId: string) => void;
  onAutoFitFont?: (blockId: string) => void;
  onExtractStyle?: (blockId: string) => void;
  onToggleView?: () => void;
  onDeleteBlock?: (blockId: string) => void;
  onDeleteAndInpaint?: (blockId: string) => void;
  onMergeBlocks?: (blockIds: string[]) => void;
  onEqualizeSize?: (blockIds: string[], dimension: 'width' | 'height') => void;
  onSortReadingOrder?: (blockIds: string[]) => void;
  onToggleVisibility?: (blockId: string) => void;
  onMakeSplit?: (blockId: string, direction: 'horizontal' | 'vertical') => void;
  onCopyStyle?: (blockId: string) => void;
  onPasteStyle?: (blockId: string) => void;
  hasCopiedStyle?: boolean;
  onToggleLock?: (blockId: string) => void;
  onReorderZIndex?: (blockId: string, action: 'bring_to_front' | 'bring_forward' | 'send_backward' | 'send_to_back') => void;
  onRefreshPage?: () => void;
  onRefitPageText?: () => void;
  onResetPageMasks?: () => void;
  onResetProjectMasks?: () => void;
  isVisible?: boolean;
  isLocked?: boolean;
}

export const CanvasContextMenu: React.FC<CanvasContextMenuProps> = ({
  x,
  y,
  blockId,
  selectedBlockIds = [],
  onClose,
  onRunOCR,
  onCleanMask,
  onAutoFitFont,
  onExtractStyle,
  onToggleView,
  onDeleteBlock,
  onDeleteAndInpaint,
  onMergeBlocks,
  onEqualizeSize,
  onSortReadingOrder,
  onToggleVisibility,
  onMakeSplit,
  onCopyStyle,
  onPasteStyle,
  hasCopiedStyle = false,
  onToggleLock,
  onReorderZIndex,
  onRefreshPage,
  onRefitPageText,
  onResetPageMasks,
  onResetProjectMasks,
  isVisible = true,
  isLocked = false,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const isMultiSelect = selectedBlockIds.length > 1;

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  if (!blockId && !isMultiSelect && !onRefreshPage) return null;

  return (
    <div
      ref={menuRef}
      className="fixed z-[99999] min-w-[230px] bg-zinc-950/95 backdrop-blur-xl border border-zinc-800 rounded-xl shadow-[-10px_15px_40px_rgba(0,0,0,0.85)] py-1.5 text-xs text-slate-200 animate-in fade-in zoom-in-95 duration-100 font-sans select-none"
      style={{ top: `${y}px`, left: `${x}px` }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="px-3 py-1.5 text-[10px] font-bold tracking-wider text-amber-400 uppercase border-b border-zinc-800 mb-1 font-pixel flex items-center justify-between">
        <span>{isMultiSelect ? `เลือก ${selectedBlockIds.length} กล่อง (Multi-Select)` : 'จัดการบล็อกข้อความ'}</span>
      </div>

      {isMultiSelect ? (
        <>
          {onMergeBlocks && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-amber-500/20 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onMergeBlocks(selectedBlockIds);
                onClose();
              }}
            >
              <Merge size={13} className="text-amber-400" />
              <span>รวมกล่องที่เลือก (Merge Ctrl+M)</span>
            </button>
          )}

          {onSortReadingOrder && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onSortReadingOrder(selectedBlockIds);
                onClose();
              }}
            >
              <ArrowUpDown size={13} className="text-blue-400" />
              <span>จัดลำดับการอ่าน (Sort Order)</span>
            </button>
          )}

          {onEqualizeSize && (
            <>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-slate-200 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onEqualizeSize(selectedBlockIds, 'width');
                  onClose();
                }}
              >
                <Maximize2 size={13} className="text-slate-400" />
                <span>ปรับความกว้างให้เท่ากัน</span>
              </button>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-slate-200 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onEqualizeSize(selectedBlockIds, 'height');
                  onClose();
                }}
              >
                <Maximize2 size={13} className="text-slate-400" />
                <span>ปรับความสูงให้เท่ากัน</span>
              </button>
            </>
          )}
        </>
      ) : (
        <>
          {blockId && onCleanMask && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-amber-500/20 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onCleanMask(blockId);
                onClose();
              }}
            >
              <Paintbrush size={13} className="text-amber-400" />
              <span>แก้ไขมาสก์ข้อความ (Clean Mask)</span>
            </button>
          )}

          {blockId && onRunOCR && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-amber-500/20 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onRunOCR(blockId);
                onClose();
              }}
            >
              <Scan size={13} className="text-amber-400" />
              <span>สแกน OCR กล่องนี้ใหม่</span>
            </button>
          )}

          {blockId && onExtractStyle && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-amber-500/20 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onExtractStyle(blockId);
                onClose();
              }}
            >
              <Sparkles size={13} className="text-amber-400" />
              <span>ดูดสี & ขอบจากภาพ (Auto Style)</span>
            </button>
          )}

          {blockId && onAutoFitFont && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-amber-500/20 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onAutoFitFont(blockId);
                onClose();
              }}
            >
              <Wand2 size={13} className="text-amber-400" />
              <span>ปรับขนาดฟอนต์ให้พอดีบอลลูน</span>
            </button>
          )}

          <div className="my-1 border-t border-zinc-800" />

          {blockId && onMakeSplit && (
            <>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onMakeSplit(blockId, 'horizontal');
                  onClose();
                }}
              >
                <Scissors size={13} className="text-blue-400" />
                <span>ผ่าครึ่งแนวนอน (บน / ล่าง)</span>
              </button>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onMakeSplit(blockId, 'vertical');
                  onClose();
                }}
              >
                <Scissors size={13} className="text-blue-400" />
                <span>ผ่าครึ่งแนวตั้ง (ซ้าย / ขวา)</span>
              </button>
            </>
          )}

          <div className="my-1 border-t border-zinc-800" />

          {blockId && onCopyStyle && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onCopyStyle(blockId);
                onClose();
              }}
            >
              <Copy size={13} className="text-purple-400" />
              <span>คัดลอกสไตล์ตัวหนังสือ (Copy Style)</span>
            </button>
          )}

          {blockId && onPasteStyle && (
            <button
              disabled={!hasCopiedStyle}
              className={`w-full px-3 py-1.5 text-left flex items-center gap-2.5 transition-colors text-[11px] ${
                hasCopiedStyle ? 'hover:bg-zinc-800 hover:text-amber-300 cursor-pointer text-slate-200' : 'opacity-40 cursor-not-allowed text-slate-500'
              }`}
              onClick={() => {
                if (hasCopiedStyle) {
                  onPasteStyle(blockId);
                  onClose();
                }
              }}
            >
              <Clipboard size={13} className="text-purple-400" />
              <span>วางสไตล์ตัวหนังสือ (Paste Style)</span>
            </button>
          )}

          <div className="my-1 border-t border-zinc-800" />

          {blockId && onToggleVisibility && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onToggleVisibility(blockId);
                onClose();
              }}
            >
              {isVisible ? <EyeOff size={13} className="text-slate-400" /> : <Eye size={13} className="text-emerald-400" />}
              <span>{isVisible ? 'ซ่อนข้อความ (Hide)' : 'แสดงข้อความ (Show)'}</span>
            </button>
          )}

          {blockId && onToggleLock && (
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
              onClick={() => {
                onToggleLock(blockId);
                onClose();
              }}
            >
              {isLocked ? <Unlock size={13} className="text-emerald-400" /> : <Lock size={13} className="text-amber-400" />}
              <span>{isLocked ? 'ปลดล็อคตำแหน่ง (Unlock)' : 'ล็อคตำแหน่ง (Lock)'}</span>
            </button>
          )}

          {blockId && onReorderZIndex && (
            <>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-cyan-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onReorderZIndex(blockId, 'bring_to_front');
                  onClose();
                }}
              >
                <Layers size={13} className="text-cyan-400" />
                <span>นำขึ้นหน้าสุด (Bring to Front)</span>
              </button>
              <button
                className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-cyan-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                onClick={() => {
                  onReorderZIndex(blockId, 'send_to_back');
                  onClose();
                }}
              >
                <Layers size={13} className="text-cyan-400" />
                <span>ส่งไปหลังสุด (Send to Back)</span>
              </button>
            </>
          )}

          {/* Page level actions */}
          {(onRefreshPage || onRefitPageText || onResetPageMasks || onResetProjectMasks) && (
            <>
              <div className="my-1 border-t border-zinc-800" />
              {onRefreshPage && (
                <button
                  className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-cyan-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                  onClick={() => {
                    onRefreshPage();
                    onClose();
                  }}
                >
                  <RotateCw size={13} className="text-cyan-400" />
                  <span>รีเฟรชข้อมูลหน้านี้</span>
                </button>
              )}
              {onRefitPageText && (
                <button
                  className="w-full px-3 py-1.5 text-left hover:bg-zinc-800 hover:text-amber-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                  onClick={() => {
                    onRefitPageText();
                    onClose();
                  }}
                >
                  <RefreshCw size={13} className="text-amber-400" />
                  <span>คำนวณ Text ใหม่ทั้งหน้า</span>
                </button>
              )}
              {onResetPageMasks && (
                <button
                  className="w-full px-3 py-1.5 text-left hover:bg-rose-950/40 text-rose-300 hover:text-rose-200 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                  onClick={() => {
                    onResetPageMasks();
                    onClose();
                  }}
                >
                  <RefreshCw size={13} className="text-rose-400" />
                  <span>ล้าง Mask และ Clean หน้านี้</span>
                </button>
              )}
              {onResetProjectMasks && (
                <button
                  className="w-full px-3 py-1.5 text-left hover:bg-rose-950/40 text-rose-400 hover:text-rose-200 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
                  onClick={() => {
                    onResetProjectMasks();
                    onClose();
                  }}
                >
                  <AlertTriangle size={13} className="text-rose-500" />
                  <span>ล้างและ Clean ทั้งโปรเจกต์</span>
                </button>
              )}
            </>
          )}
        </>
      )}

      {blockId && onDeleteAndInpaint && !isMultiSelect && (
        <>
          <div className="my-1 border-t border-zinc-800" />
          <button
            className="w-full px-3 py-1.5 text-left hover:bg-rose-500/20 text-rose-300 hover:text-rose-200 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
            onClick={() => {
              onDeleteAndInpaint(blockId);
              onClose();
            }}
          >
            <Trash2 size={13} className="text-rose-400" />
            <span>ลบกล่องพร้อมคลีนภาพพื้นหลัง</span>
          </button>
        </>
      )}

      {blockId && onDeleteBlock && (
        <button
          className="w-full px-3 py-1.5 text-left hover:bg-rose-500/20 text-rose-400 hover:text-rose-300 flex items-center gap-2.5 transition-colors cursor-pointer text-[11px]"
          onClick={() => {
            onDeleteBlock(blockId);
            onClose();
          }}
        >
          <Trash2 size={13} />
          <span>{isMultiSelect ? 'ลบบล็อกที่เลือกทั้งหมด' : 'ลบกล่องคำพูด'}</span>
        </button>
      )}
    </div>
  );
};
