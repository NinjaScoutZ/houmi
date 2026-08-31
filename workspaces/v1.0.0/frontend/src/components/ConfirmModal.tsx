import React from 'react';
import { AlertTriangle, Trash2, HelpCircle, X } from 'lucide-react';

export interface ConfirmModalProps {
  isOpen: boolean;
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  type?: 'warning' | 'danger' | 'info';
  onConfirm: () => void;
  onClose: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title = 'ยืนยันการดำเนินการ',
  message,
  confirmText = 'ตกลง / ยืนยัน',
  cancelText = 'ยกเลิก',
  type = 'warning',
  onConfirm,
  onClose,
}) => {
  if (!isOpen) return null;

  const isDanger = type === 'danger' || message.includes('ลบ') || title.includes('ลบ');

  return (
    <div className="fixed inset-0 z-[20000] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in font-sans select-none">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.8)] overflow-hidden text-slate-100 p-6 space-y-5 animate-slide-up">
        
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-inner ${
              isDanger 
                ? 'bg-rose-500/15 border border-rose-500/30 text-rose-400' 
                : 'bg-amber-500/15 border border-amber-500/30 text-amber-400'
            }`}>
              {isDanger ? <Trash2 size={20} /> : <AlertTriangle size={20} />}
            </div>
            <div>
              <h3 className="text-sm font-bold text-white font-pixel uppercase tracking-wider">
                {title}
              </h3>
              <p className="text-[10px] text-slate-400 font-sans">
                กรุณายืนยันก่อนดำเนินการต่อไป
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition hover:bg-zinc-900 cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content Message */}
        <div className="p-3.5 bg-zinc-900/70 border border-zinc-800 rounded-xl text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-line">
          {message}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5 pt-1 font-pixel">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-slate-300 border border-zinc-800 hover:border-zinc-700 font-bold text-xs rounded-xl transition cursor-pointer"
          >
            {cancelText}
          </button>

          <button
            type="button"
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className={`px-5 py-2 text-xs font-bold rounded-xl shadow-lg transition cursor-pointer flex items-center gap-1.5 ${
              isDanger
                ? 'bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white shadow-rose-500/20'
                : 'bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black shadow-amber-500/20'
            }`}
          >
            <span>{confirmText}</span>
          </button>
        </div>

      </div>
    </div>
  );
};
