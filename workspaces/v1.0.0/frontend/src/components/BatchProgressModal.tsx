import React, { useState } from 'react';
import { Loader2, CheckCircle2, AlertTriangle, XCircle, X, Pause } from 'lucide-react';
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
}) => {
  const [isCancelling, setIsCancelling] = useState(false);

  if (!isOpen) return null;

  const percentage = Math.min(100, Math.max(0, Math.round(progress * 100)));

  const handleCancel = async () => {
    if (!projectId || isCancelling) return;
    setIsCancelling(true);
    try {
      const response = await apiFetch(`${API_BASE}/pipeline/batch/cancel?project_id=${projectId}`, {
        method: 'POST',
      });
      const data = await response.json().catch(() => ({}));

      if (data.status === 'success') {
        console.log('Batch cancellation successful:', data.message);
      } else if (data.status === 'no_action') {
        console.warn('No active batch to cancel:', data.message);
      }
    } catch (err) {
      console.error('Failed to cancel batch workflow:', err);
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in font-sans select-none">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden p-6 text-slate-200 animate-in zoom-in-95 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100 font-pixel uppercase tracking-wider flex items-center gap-2">
            {status === 'running' && <Loader2 size={16} className="animate-spin text-amber-400" />}
            {status === 'cancelling' && <Pause size={16} className="animate-pulse text-amber-400" />}
            {status === 'success' && <CheckCircle2 size={16} className="text-emerald-400" />}
            {status === 'failed' && <XCircle size={16} className="text-rose-400" />}
            {status === 'cancelled' && <AlertTriangle size={16} className="text-amber-400" />}
            <span>Batch Processing Status</span>
          </h3>
          {status !== 'running' && status !== 'cancelling' && (
            <button
              onClick={onClose}
              className="text-zinc-400 hover:text-white p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
              title="Close"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Status text */}
        <div className="text-xs text-slate-400 flex justify-between items-center">
          <span className="truncate max-w-[260px]">
            {status === 'running' && (currentStep ? `Step: ${currentStep}` : 'Processing pages...')}
            {status === 'cancelling' && 'Cancelling workflow...'}
            {status === 'success' && 'Batch processing completed successfully!'}
            {status === 'failed' && `Error: ${error || 'Batch processing failed'}`}
            {status === 'cancelled' && 'Process cancelled by user'}
          </span>
          <span className="font-mono text-amber-400 font-semibold text-[11px]">
            {currentPage} / {totalPages} Pages
          </span>
        </div>

        {/* Progress Bar */}
        <div className="w-full h-3 bg-zinc-900 rounded-full overflow-hidden p-0.5 border border-zinc-800">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              status === 'failed'
                ? 'bg-rose-500'
                : status === 'cancelled' || status === 'cancelling'
                ? 'bg-amber-500'
                : 'bg-gradient-to-r from-amber-500 to-yellow-400 shadow-[0_0_12px_rgba(245,158,11,0.4)]'
            }`}
            style={{ width: `${percentage}%` }}
          />
        </div>

        <div className="flex justify-between items-center text-xs font-mono text-slate-400">
          <span className="font-pixel text-[10.5px]">Progress</span>
          <span className="text-amber-300 font-bold">{percentage}%</span>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-2">
          {status === 'running' || status === 'cancelling' ? (
            <button
              onClick={handleCancel}
              disabled={isCancelling || status === 'cancelling'}
              className="px-4 py-2 text-xs font-bold font-pixel bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40 rounded-xl transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCancelling || status === 'cancelling' ? 'Cancelling...' : 'Cancel Process'}
            </button>
          ) : (
            <button
              onClick={onClose}
              className="px-5 py-2 text-xs font-bold font-pixel bg-zinc-850 text-slate-200 hover:bg-zinc-800 border border-zinc-700 rounded-xl transition-colors cursor-pointer"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
