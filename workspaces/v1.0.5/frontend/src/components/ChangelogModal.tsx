import React from 'react';
import { Sparkles, CheckCircle2, X, PartyPopper, Shield, Zap, Layers, Cpu, Compass } from 'lucide-react';
import { HOUMI_VERSION_LABEL } from '../version';

interface ChangelogModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ChangelogModal: React.FC<ChangelogModalProps> = ({
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  const features = [
    {
      icon: <Shield size={16} className="text-amber-400" />,
      title: 'Multi-Key Priority & Auto-Failover Pool',
      desc: 'ระบบจัดการ API Key หลายตัวพร้อมปุ่มเลือกลำดับความสำคัญ (Priority 🔼/🔽) สลับ Key อัตโนมัติเมื่อติด Rate Limit (429)',
      badge: 'NEW',
    },
    {
      icon: <Zap size={16} className="text-rose-400" />,
      title: 'Gemini Quota Exceeded Protection',
      desc: 'เมื่อ Google Gemini แจ้งเตือนว่าโควตาเต็ม ระบบจะยกเลิกการทำ OCR ทันที แทนการวนลูป retry จนค้าง',
      badge: 'PROTECTION',
    },
    {
      icon: <Layers size={16} className="text-cyan-400" />,
      title: 'Text Engine Mode & ExtendScript (.JSX) Integration',
      desc: 'รวมโหมด ExtendScript เข้ากับการเลือกรูปแบบ Text Layer (Paragraph / Point Text) เรียบง่ายในกล่องเดียว',
      badge: 'ENHANCED',
    },
    {
      icon: <Cpu size={16} className="text-emerald-400" />,
      title: 'Single-Screen Combined Export Scope',
      desc: 'รวมการเลือกขอบเขตเฉพาะหน้าปัจจุบัน (Current Page) และ ทั้งโปรเจกต์ (Entire Project) เป็น 2 ปุ่มกดชัดเจน',
      badge: 'UI FIX',
    },
    {
      icon: <Compass size={16} className="text-purple-400" />,
      title: 'Photoshop Dock Rail Anchored Flyout',
      desc: 'แผงควบคุมสไตล์ Text & Formatting ยึดตำแหน่งลอยติดกับแถบไอคอนแนวตั้ง ps-dock-rail พอดี 100% เลื่อนตามตาม Sidebar',
      badge: 'LAYOUT',
    },
  ];

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-fade-in font-sans select-none">
      <div className="w-full max-w-xl bg-zinc-950 border border-amber-500/40 rounded-2xl shadow-[0_0_50px_rgba(245,158,11,0.2)] overflow-hidden text-slate-100 p-6 space-y-5 animate-slide-up">
        
        {/* Header Banner */}
        <div className="flex items-start justify-between border-b border-zinc-900 pb-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 flex items-center justify-center shadow-inner">
              <PartyPopper className="w-6 h-6 animate-bounce" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-pixel uppercase tracking-widest bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                  <Sparkles size={11} /> Version Changelog
                </span>
                <span className="text-xs font-mono font-semibold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 size={12} /> {HOUMI_VERSION_LABEL} Active
                </span>
              </div>
              <h2 className="text-lg font-bold text-white mt-1 font-pixel">
                🚀 มีอะไรใหม่ในเวอร์ชัน {HOUMI_VERSION_LABEL}
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

        {/* Feature Highlights List */}
        <div className="space-y-2.5 max-h-[55vh] overflow-y-auto pr-1 scrollbar-thin">
          {features.map((f, idx) => (
            <div key={idx} className="p-3.5 bg-zinc-900/70 border border-zinc-800 rounded-xl flex items-start gap-3 hover:border-zinc-700 transition-all">
              <div className="p-2 rounded-lg bg-zinc-950 border border-zinc-800 shrink-0 mt-0.5">
                {f.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-bold text-slate-100 font-pixel">{f.title}</h4>
                  <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {f.badge}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed mt-1 font-sans">
                  {f.desc}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-2 border-t border-zinc-900 font-pixel">
          <span className="text-[10px] text-slate-500">
            Houmi Studio {HOUMI_VERSION_LABEL} · Official Update
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black font-bold text-xs rounded-xl shadow-lg shadow-amber-500/20 transition cursor-pointer flex items-center gap-2"
          >
            <Sparkles size={13} /> รับทราบ (Got it)
          </button>
        </div>

      </div>
    </div>
  );
};
