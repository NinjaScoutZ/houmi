import React, { useEffect } from 'react';
import { Keyboard, X } from 'lucide-react';

export interface HotkeyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const HOTKEY_GROUPS = [
  {
    category: 'Canvas & Tool Modes (โหมดเครื่องมือ)',
    shortcuts: [
      { keys: ['V'], description: 'Select Mode (โหมดเลือก)' },
      { keys: ['M'], description: 'Draw Box Mode (วาดกล่องคำ)' },
      { keys: ['B'], description: 'Mask Brush Mode (ระบายมาสก์ลบ)' },
      { keys: ['A'], description: 'Toggle Clean / Original (สลับคลีน/ต้นฉบับ)' },
      { keys: ['Space', 'Drag'], description: 'Pan Workspace (เลื่อนหน้ากระดาษ)' },
      { keys: ['Ctrl', 'Wheel'], description: 'Zoom In / Out (ซูมเข้า/ออก)' },
    ],
  },
  {
    category: 'Text & Box Actions (จัดการกล่องข้อความ)',
    shortcuts: [
      { keys: ['Tab'], description: 'Jump to Next Box (กล่องถัดไป)' },
      { keys: ['Shift', 'Tab'], description: 'Jump to Prev Box (กล่องก่อนหน้า)' },
      { keys: ['Enter'], description: 'Edit Selected Box (เริ่มพิมพ์ลงคำ)' },
      { keys: ['Delete'], description: 'Delete Selected Box (ลบกล่อง)' },
      { keys: ['Esc'], description: 'Deselect / Close Modal (ออกจากพิมพ์/ยกเลิก)' },
      { keys: ['Right Click'], description: 'Context Menu (เมนูจัดการกล่อง)' },
    ],
  },
  {
    category: 'Navigation & Search (ค้นหาและนำทาง)',
    shortcuts: [
      { keys: ['Ctrl', 'F'], description: 'Find Balloon (ค้นหากล่องและวาร์ป)' },
      { keys: ['['], description: 'Previous Page (หน้าก่อนหน้า)' },
      { keys: [']'], description: 'Next Page (หน้าถัดไป)' },
      { keys: ['Shift', 'C'], description: 'Toggle Inpaint View (สลับดูภาพคลีน)' },
    ],
  },
  {
    category: 'System & Export (ระบบและส่งออก)',
    shortcuts: [
      { keys: ['Ctrl', 'Z'], description: 'Undo (เลิกทำ)' },
      { keys: ['Ctrl', 'Y'], description: 'Redo (ทำซ้ำ)' },
      { keys: ['Ctrl', 'Shift', 'S'], description: 'Export OCR Text (ส่งออกข้อความสแกน)' },
      { keys: ['?'], description: 'Toggle Shortcuts (เปิด/ปิด หน้ารวมคีย์ลัด)' },
    ],
  },
];

export const HotkeyModal: React.FC<HotkeyModalProps> = ({ isOpen, onClose }) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-150 font-sans select-none"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hotkey-modal-title"
    >
      <div className="w-full max-w-3xl bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden text-slate-200 animate-in zoom-in-95">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/80">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-400 font-pixel">
              <Keyboard size={16} />
            </div>
            <div>
              <h3 id="hotkey-modal-title" className="text-sm font-bold text-slate-100 font-pixel uppercase tracking-wider">
                Keyboard Shortcuts Cheat Sheet
              </h3>
              <p className="text-[11px] text-slate-400">คีย์ลัดทั้งหมดสำหรับเพิ่มความเร็วในการทำงาน</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close (Esc)"
            aria-label="Close modal"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6 max-h-[70vh] overflow-y-auto">
          {HOTKEY_GROUPS.map((group) => (
            <div key={group.category} className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 border-b border-zinc-800 pb-1.5 font-pixel">
                {group.category}
              </h4>
              <div className="space-y-2">
                {group.shortcuts.map((sc, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs py-0.5">
                    <span className="text-slate-300 font-medium">{sc.description}</span>
                    <div className="flex items-center gap-1 shrink-0 ml-2">
                      {sc.keys.map((k, kIdx) => (
                        <kbd
                          key={kIdx}
                          className="px-2 py-0.5 text-[10px] font-mono font-semibold text-amber-300 bg-zinc-900 border border-zinc-800 rounded shadow-sm"
                        >
                          {k}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center px-6 py-3.5 bg-zinc-900/80 border-t border-zinc-800 text-xs text-slate-400 font-pixel">
          <span>กด <kbd className="px-1.5 py-0.5 text-[10px] bg-zinc-800 rounded font-mono text-amber-400 border border-zinc-700">?</kbd> หรือ <kbd className="px-1.5 py-0.5 text-[10px] bg-zinc-800 rounded font-mono text-amber-400 border border-zinc-700">Esc</kbd> เพื่อเปิด/ปิด</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 font-semibold bg-zinc-850 hover:bg-zinc-800 text-slate-200 rounded-lg border border-zinc-700 transition-colors cursor-pointer"
          >
            Got it (เข้าใจแล้ว)
          </button>
        </div>
      </div>
    </div>
  );
};

