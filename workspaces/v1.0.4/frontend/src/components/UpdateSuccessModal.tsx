import React from 'react';
import { Sparkles, CheckCircle2, X, PartyPopper, FileText } from 'lucide-react';

interface UpdateSuccessModalProps {
  isOpen: boolean;
  version: string;
  patchNotes: string;
  onClose: () => void;
}

export const UpdateSuccessModal: React.FC<UpdateSuccessModalProps> = ({
  isOpen,
  version,
  patchNotes,
  onClose,
}) => {
  if (!isOpen) return null;

  // Split patch notes into readable lines/bullet points if formatted with dashes/newlines
  const notesLines = patchNotes
    ? patchNotes.split(/\r?\n/).filter(line => line.trim().length > 0)
    : ['อัปเดตปรับปรุงประสิทธิภาพและการทำงานของระบบ'];

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-fade-in font-sans">
      <div className="w-full max-w-xl bg-zinc-950 border border-amber-500/40 rounded-2xl shadow-[0_0_50px_rgba(245,158,11,0.15)] overflow-hidden text-slate-100 p-6 space-y-5 animate-slide-up">
        
        {/* Header Banner */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 flex items-center justify-center shadow-inner">
              <PartyPopper className="w-6 h-6 animate-bounce" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-pixel uppercase tracking-widest bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                  <Sparkles size={11} /> Patch Updated
                </span>
                <span className="text-xs font-mono font-semibold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 size={12} /> v{version} Active
                </span>
              </div>
              <h2 className="text-xl font-bold text-white mt-1">
                🎉 อัปเดตแพตช์ล่าสุดสำเร็จแล้ว!
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg transition hover:bg-zinc-900 cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Success Alert Callout */}
        <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-xs flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>
            ระบบได้ทำการอัปเดตและปรับใช้ซอร์สโค้ดเวอร์ชันล่าสุด <strong>v{version}</strong> เรียบร้อยแล้ว พร้อมใช้งานทันที!
          </span>
        </div>

        {/* Changelog & Patch Notes Card */}
        <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider font-pixel flex items-center gap-1.5">
            <FileText size={14} /> Changelog / รายละเอียดสิ่งที่ปรับปรุง (Patch Notes)
          </h3>
          
          <div className="max-h-56 overflow-y-auto pr-1 space-y-2 text-xs text-slate-200">
            {notesLines.map((line, idx) => {
              const cleanLine = line.replace(/^[\-\*\•]\s*/, '').trim();
              return (
                <div key={idx} className="flex items-start gap-2 bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/60">
                  <span className="text-amber-400 font-bold shrink-0 mt-0.5">•</span>
                  <span className="leading-relaxed font-sans">{cleanLine}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer Action */}
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-slate-500 font-pixel">
            Houmi Studio v{version} · Official Release
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2.5 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black font-bold font-pixel text-xs rounded-xl shadow-lg shadow-amber-500/20 transition cursor-pointer flex items-center gap-2"
          >
            <Sparkles size={14} /> เริ่มใช้งานทันที (Get Started)
          </button>
        </div>

      </div>
    </div>
  );
};
