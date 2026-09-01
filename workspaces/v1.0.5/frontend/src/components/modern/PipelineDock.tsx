import React, { useState } from 'react';
import { Play, Sparkles, Check, Loader2, ArrowRight } from 'lucide-react';
import type { Project, Page } from '../../stores/projectStore';

interface PipelineDockProps {
  activeProject: Project | null;
  activePage: Page | null;
  isProcessing: boolean;
  onRunFullPipeline: (scope: 'page' | 'project') => void;
  onRunStep: (step: 'detect' | 'ocr' | 'mask' | 'inpaint' | 'typeset') => void;
}

export const PipelineDock: React.FC<PipelineDockProps> = ({
  activeProject,
  activePage,
  isProcessing,
  onRunFullPipeline,
  onRunStep,
}) => {
  const [scope, setScope] = useState<'page' | 'project'>('page');

  const totalPages = activeProject?.pages?.length || 1;
  const currentPageNum = activePage?.page_number || 1;

  const steps = [
    { id: 'detect' as const, num: '#1', label: 'Detect', desc: 'ตรวจจับบล็อก' },
    { id: 'ocr' as const, num: '#2', label: 'OCR', desc: 'อ่านข้อความ' },
    { id: 'mask' as const, num: '#3', label: 'Mask', desc: 'สร้างมาร์ก' },
    { id: 'inpaint' as const, num: '#4', label: 'Clean', desc: 'คลีนภาพ' },
    { id: 'typeset' as const, num: '#5', label: 'AI Font', desc: 'เลือกฟอนต์' },
  ];

  return (
    <div className="p-3 border-b border-[#20202c] bg-[#101018] flex flex-col gap-3 font-sans shrink-0">
      {/* Header with Scope Switcher */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-amber-400 font-bold">⚡</span>
          <span className="text-xs font-black tracking-wider text-slate-100 uppercase font-pixel">
            AI PIPELINE (5 STEPS)
          </span>
        </div>
        <span className="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
          {activePage?.status === 'processed' ? '5/5 (100%)' : 'READY'}
        </span>
      </div>

      {/* Segmented Scope Selector */}
      <div className="grid grid-cols-2 p-0.5 bg-[#09090e] border border-[#20202c] rounded-xl">
        <button
          type="button"
          onClick={() => setScope('page')}
          className={`py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
            scope === 'page'
              ? 'bg-[#181824] text-amber-300 shadow-sm border border-amber-500/30'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          หน้าปัจจุบัน <span className="font-mono text-[10px] opacity-75">P.{currentPageNum}</span>
        </button>
        <button
          type="button"
          onClick={() => setScope('project')}
          className={`py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
            scope === 'project'
              ? 'bg-[#181824] text-amber-300 shadow-sm border border-amber-500/30'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          ทุกหน้า <span className="font-mono text-[10px] opacity-75">{totalPages} หน้า</span>
        </button>
      </div>

      {/* Main 1-Click Master Action Button */}
      <button
        type="button"
        disabled={isProcessing}
        onClick={() => onRunFullPipeline(scope)}
        className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 via-amber-400 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-black font-black text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(245,158,11,0.3)] transition-all duration-200 active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed font-pixel"
      >
        {isProcessing ? (
          <>
            <Loader2 size={16} className="animate-spin text-black" />
            <span>PROCESSING AI PIPELINE...</span>
          </>
        ) : (
          <>
            <Sparkles size={15} className="text-black" />
            <span>RUN FULL 5-STEP PIPELINE ({scope === 'page' ? 'Auto 1-Click' : 'Batch All'})</span>
          </>
        )}
      </button>

      {/* 5 Circular Stage Steps Matrix */}
      <div className="grid grid-cols-5 gap-1.5 pt-1">
        {steps.map((s) => (
          <button
            key={s.id}
            type="button"
            disabled={isProcessing}
            onClick={() => onRunStep(s.id)}
            className="flex flex-col items-center p-1.5 rounded-xl border border-[#20202c] bg-[#12121a] hover:border-amber-500/50 hover:bg-[#181826] transition-all cursor-pointer group disabled:opacity-50"
            title={`คลิกเพื่อรันเฉพาะขั้นตอน: ${s.label} (${s.desc})`}
          >
            <div className="w-6 h-6 rounded-full bg-[#181824] border border-[#262638] group-hover:border-amber-400 flex items-center justify-center text-[10px] font-bold font-mono text-zinc-400 group-hover:text-amber-300 transition-colors mb-1">
              {s.num}
            </div>
            <span className="text-[10px] font-bold text-slate-200 group-hover:text-amber-300 transition-colors truncate">
              {s.label}
            </span>
            <span className="text-[8px] text-zinc-500 truncate mt-0.5 scale-90 origin-top">
              {s.desc}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};
