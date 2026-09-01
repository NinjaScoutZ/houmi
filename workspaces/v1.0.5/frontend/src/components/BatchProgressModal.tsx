import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  X,
  Pause,
  Minimize2,
  Zap,
  ChevronUp,
} from 'lucide-react';
import { API_BASE } from '../stores/projectStore';
import { apiFetch } from '../api/runtime';

export interface BatchProgressModalProps {
  isOpen: boolean;
  projectId: string | null;
  progress: number; // 0.0 to 1.0
  currentPage: number;
  totalPages: number;
  currentStep?: string;
  status: 'idle' | 'running' | 'success' | 'failed' | 'cancelled' | 'cancelling';
  error?: string | null;
  onClose: () => void;
  onCancel?: () => void;
}

export const BatchProgressModal: React.FC<BatchProgressModalProps> = ({
  isOpen,
  projectId,
  progress,
  currentPage,
  totalPages,
  currentStep,
  status,
  error,
  onClose,
  onCancel,
}) => {
  const [isCancelling, setIsCancelling] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Timer tracking while running
  useEffect(() => {
    if (!isOpen || status !== 'running') {
      if (status !== 'running' && status !== 'cancelling') {
        // Keep elapsed time when done
      } else {
        setElapsedSeconds(0);
      }
      return;
    }

    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen, status]);

  if (!isOpen) return null;

  const percentage = Math.min(100, Math.max(0, Math.round(progress * 100)));

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const handleCancel = async () => {
    if (onCancel) {
      onCancel();
      return;
    }
    if (!projectId || isCancelling) return;
    setIsCancelling(true);
    try {
      const response = await apiFetch(`${API_BASE}/pipeline/batch/cancel?project_id=${projectId}`, {
        method: 'POST',
      });
      const data = await response.json().catch(() => ({}));
      if (data.status === 'success') {
        console.log('Batch cancellation successful:', data.message);
      }
    } catch (err) {
      console.error('Failed to cancel batch workflow:', err);
    } finally {
      setIsCancelling(false);
    }
  };

  const pipelineStages = [
    { key: 'detect', label: 'DETECT' },
    { key: 'ocr', label: 'OCR' },
    { key: 'mask', label: 'MASK' },
    { key: 'inpaint', label: 'INPAINT' },
    { key: 'render', label: 'RENDER' },
  ];

  const currentStageKey = (currentStep || '').toLowerCase();

  // -------------------------------------------------------------
  // STATE A: COMPACT FLOATING ISLAND PILL (MINIMIZED HUD)
  // -------------------------------------------------------------
  if (isMinimized) {
    return (
      <aside
        aria-label="Batch progress indicator"
        onClick={() => setIsMinimized(false)}
        className="fixed bottom-6 right-6 z-40 select-none cursor-pointer group"
      >
        <div className="flex items-center gap-3 px-3.5 py-2.5 rounded-2xl bg-zinc-950/85 backdrop-blur-xl border border-yellow-500/35 shadow-[0_15px_35px_rgba(0,0,0,0.7),0_0_20px_rgba(234,179,8,0.15)] hover:border-yellow-400/70 hover:scale-102 active:scale-98 transition-all font-pixel text-xs text-slate-200">
          {/* Animated Spinner Halo */}
          <div className="relative flex items-center justify-center">
            {status === 'running' && (
              <div className="w-4 h-4 rounded-full border-2 border-yellow-400/30 border-t-yellow-400 animate-spin" />
            )}
            {status === 'cancelling' && <Pause size={14} className="text-amber-400 animate-pulse" />}
            {status === 'success' && <CheckCircle2 size={14} className="text-emerald-400" />}
            {status === 'failed' && <XCircle size={14} className="text-rose-400" />}
            {status === 'cancelled' && <AlertTriangle size={14} className="text-amber-400" />}
          </div>

          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className="font-bold text-yellow-300 text-[10.5px]">
                {status === 'running' ? `Batch ${percentage}%` : status.toUpperCase()}
              </span>
              {currentStep && (
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/40 uppercase">
                  {currentStep}
                </span>
              )}
            </div>
            <span className="text-[9px] text-slate-400 font-mono">
              P.{currentPage}/{totalPages} · ⏱️ {formatTimer(elapsedSeconds)}
            </span>
          </div>

          <div className="pl-1 text-slate-400 group-hover:text-yellow-400 transition-colors">
            <ChevronUp size={14} />
          </div>
        </div>
      </aside>
    );
  }

  // -------------------------------------------------------------
  // STATE B: EXPANDED SPATIAL HUD CARD (NON-BLOCKING FLOATING DOCK)
  // -------------------------------------------------------------
  return (
    <aside
      aria-label="Batch processing status details"
      className="fixed bottom-6 right-6 z-40 select-none font-sans"
    >
      <div className="w-[360px] p-4.5 rounded-2xl bg-gradient-to-b from-zinc-950/95 via-zinc-900/90 to-zinc-950/95 backdrop-blur-2xl border border-yellow-500/35 shadow-[0_25px_60px_rgba(0,0,0,0.85),0_0_30px_rgba(234,179,8,0.12)] flex flex-col gap-3.5 text-slate-200 animate-in slide-in-from-bottom-4 zoom-in-95">
        
        {/* Header Bar */}
        <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2.5">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-lg bg-yellow-500/15 border border-yellow-500/30 text-yellow-400">
              {status === 'running' ? (
                <Zap size={14} className="animate-pulse" />
              ) : status === 'success' ? (
                <CheckCircle2 size={14} className="text-emerald-400" />
              ) : (
                <Sparkles size={14} />
              )}
            </div>
            <div>
              <h3 className="text-[11px] font-bold text-yellow-300 font-pixel uppercase tracking-wider">
                Batch Pipeline HUD
              </h3>
              <p className="text-[9px] text-slate-400 leading-none mt-0.5">Non-blocking background runner</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-yellow-400 bg-yellow-950/40 border border-yellow-500/25 px-1.5 py-0.5 rounded">
              ⏱️ {formatTimer(elapsedSeconds)}
            </span>
            <button
              onClick={() => setIsMinimized(true)}
              className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition cursor-pointer"
              title="ย่อเป็น Pill เล็ก"
            >
              <Minimize2 size={13} />
            </button>
            {status !== 'running' && status !== 'cancelling' && (
              <button
                onClick={onClose}
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition cursor-pointer"
                title="ปิด"
              >
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        {/* Pipeline Stage Stepper */}
        <div className="grid grid-cols-5 gap-1 text-center font-pixel">
          {pipelineStages.map((stage) => {
            const isCurrent = currentStageKey.includes(stage.key);
            return (
              <div
                key={stage.key}
                className={`py-1 px-0.5 rounded-md border text-[8px] font-bold tracking-tight transition-all ${
                  isCurrent && status === 'running'
                    ? 'bg-yellow-500/20 border-yellow-400 text-yellow-300 shadow-[0_0_10px_rgba(234,179,8,0.3)] animate-pulse'
                    : status === 'success'
                    ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-400'
                    : 'bg-zinc-950/60 border-zinc-800/80 text-slate-500'
                }`}
              >
                {stage.label}
              </div>
            );
          })}
        </div>

        {/* Status text & Page counter */}
        <div className="flex justify-between items-center text-[11px] text-slate-300">
          <span className="truncate max-w-[220px] font-medium">
            {status === 'running' && (currentStep ? `Step: Processing ${currentStep.toUpperCase()}...` : 'Processing pages...')}
            {status === 'cancelling' && 'Cancelling workflow...'}
            {status === 'success' && '🎉 Batch completed successfully!'}
            {status === 'failed' && `Error: ${error || 'Batch processing failed'}`}
            {status === 'cancelled' && 'Process cancelled by user'}
          </span>
          <span className="font-mono text-yellow-400 font-bold text-xs shrink-0">
            {currentPage} / {totalPages} Pages
          </span>
        </div>

        {/* Shimmer Glowing Progress Bar */}
        <div className="w-full h-2.5 bg-zinc-950 rounded-full overflow-hidden p-0.5 border border-zinc-800">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              status === 'failed'
                ? 'bg-rose-500'
                : status === 'cancelled' || status === 'cancelling'
                ? 'bg-amber-500'
                : status === 'success'
                ? 'bg-gradient-to-r from-emerald-500 to-teal-400 shadow-[0_0_12px_rgba(16,185,129,0.6)]'
                : 'bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-300 shadow-[0_0_14px_rgba(234,179,8,0.7)]'
            }`}
            style={{ width: `${percentage}%` }}
          />
        </div>

        <div className="flex justify-between items-center text-[10px] font-mono text-slate-400">
          <span className="font-pixel text-[9px] uppercase tracking-wider text-slate-500">Progress</span>
          <span className="text-yellow-300 font-bold">{percentage}%</span>
        </div>

        {/* Concurrency Hint & Action Buttons */}
        <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60">
          <span className="text-[9px] text-slate-500">
            ✨ แก้ไขหน้าอื่นได้ตลอดเวลา
          </span>

          {status === 'running' || status === 'cancelling' ? (
            <button
              onClick={handleCancel}
              disabled={isCancelling || status === 'cancelling'}
              className="px-3 py-1.5 text-[10px] font-bold font-pixel bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40 rounded-xl transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-95"
            >
              {isCancelling || status === 'cancelling' ? 'Cancelling...' : 'Cancel Process'}
            </button>
          ) : (
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-[10px] font-bold font-pixel bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40 rounded-xl transition-all cursor-pointer active:scale-95"
            >
              Done / Close
            </button>
          )}
        </div>

      </div>
    </aside>
  );
};
