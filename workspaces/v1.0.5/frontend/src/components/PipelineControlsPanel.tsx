import React, { useState } from 'react';
import { Play, RotateCcw, Trash2, Settings } from 'lucide-react';
import { apiFetch } from '../api/runtime';
import { useProjectStore } from '../stores/projectStore';
import { ConfirmModal } from './ConfirmModal';

interface PipelineControlsPanelProps {
  activeProject: any;
  activePage: any;
  isProcessing: boolean;
  isBatchRunning: boolean;
  isPageWorkflowRunning?: boolean;
  trainStatus?: any;
  runBatchPipeline: (stages: string) => void;
  runPipelineStep: (step: 'detect' | 'ocr' | 'sort' | 'mask' | 'inpaint' | 'font_judge' | 'render' | 'auto', blockIds?: string[]) => void | Promise<boolean>;
  cancelPageWorkflow?: () => void;
  onOpenAIProviderSettings?: () => void;
  onOpenCustomWorkflowModal?: () => void;
}

export const PipelineControlsPanel: React.FC<PipelineControlsPanelProps> = ({
  activeProject,
  activePage,
  isProcessing,
  isBatchRunning,
  isPageWorkflowRunning = false,
  trainStatus,
  runBatchPipeline,
  runPipelineStep,
  cancelPageWorkflow,
  onOpenAIProviderSettings,
  onOpenCustomWorkflowModal,
}) => {
  const [pipelineScope, setPipelineScope] = useState<'current' | 'all'>('all');
  const [isCancelling, setIsCancelling] = useState(false);
  const [confirmConfig, setConfirmConfig] = useState<{
    isOpen: boolean;
    title?: string;
    message: string;
    onConfirm: () => void;
  }>({ isOpen: false, message: '', onConfirm: () => {} });

  // --- Checkmark & Next Step Recommendation Logic ---
  const pagesToCheck = pipelineScope === 'all'
    ? (activeProject?.pages || [])
    : (activePage ? [activePage] : []);

  const hasBlocks = pagesToCheck.some((p: any) => (p.text_blocks || []).length > 0);
  const hasOcr = pagesToCheck.some((p: any) =>
    (p.text_blocks || []).some((b: any) => Boolean(b.source_text && b.source_text.trim()))
  );
  const hasMask = pagesToCheck.some((p: any) =>
    (p.text_blocks || []).some((b: any) =>
      Boolean(b.smart_mask_path || b.extra_metadata?.layout_region?.mask_path || b.extra_metadata?.mask_path)
    )
  );
  const hasInpaint = pagesToCheck.some((p: any) => Boolean(p.inpainted_image_path));
  const hasFontJudge = pagesToCheck.some((p: any) =>
    (p.text_blocks || []).some((b: any) =>
      Boolean(b.extra_metadata?.typesetting_spec || b.extra_metadata?.font_decision || (b.font_family && b.font_family !== 'Inter'))
    )
  );

  const stageDoneMap: Record<string, boolean> = {
    detect: hasBlocks,
    ocr: hasOcr || hasInpaint || hasFontJudge,
    sort: hasBlocks,
    mask: hasMask || hasInpaint || hasFontJudge,
    inpaint: hasInpaint || hasFontJudge,
    font_judge: hasFontJudge,
  };

  const stageOrder = ['detect', 'ocr', 'mask', 'inpaint', 'font_judge'];
  const nextRecommendedStage = stageOrder.find((id) => !stageDoneMap[id]) || null;

  const stages = [
    { id: 'detect', icon: '🎈', label: '1. Detect', name: 'Detect Balloons' },
    { id: 'ocr', icon: '📝', label: '2. OCR', name: 'OCR Text' },
    { id: 'mask', icon: '🎭', label: '3. Mask', name: 'Create Mask' },
    { id: 'inpaint', icon: '🧹', label: '4. Clean', name: 'Clean / Inpaint' },
    { id: 'font_judge', icon: '✨', label: '5. AI Font', name: 'AI Font Judge' },
  ];

  return (
    <div className="flex flex-col gap-2.5 bg-zinc-950/80 border border-zinc-800/80 p-3 rounded-xl shadow-lg select-none font-sans text-xs">
      {/* Header & Scope Selector (Matches HTML mockup top bar) */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-bold text-amber-400 uppercase tracking-wider text-[11px]">⚡ Pipeline Controls</span>
          <button
            type="button"
            disabled={!activeProject || isProcessing || isBatchRunning}
            onClick={() => {
              if (pipelineScope === 'all') {
                runBatchPipeline('sort');
              } else {
                runPipelineStep('sort');
              }
            }}
            className="px-2 py-0.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded font-pixel text-[9.5px] font-bold transition flex items-center gap-1 cursor-pointer disabled:opacity-40"
            title="จัดเรียงลำดับอ่านกล่องข้อความมังงะตามตำแหน่ง Y,X (Sort Reading Order)"
          >
            <span>🔄</span>
            <span>Sort</span>
          </button>
        </div>
        <div className="flex items-center bg-zinc-900 border border-zinc-800 p-0.5 rounded-lg text-[10px]">
          <button
            type="button"
            onClick={() => setPipelineScope('current')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all cursor-pointer ${
              pipelineScope === 'current'
                ? 'bg-zinc-800 text-white font-semibold shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            หน้าปัจจุบัน
          </button>
          <button
            type="button"
            onClick={() => setPipelineScope('all')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all cursor-pointer ${
              pipelineScope === 'all'
                ? 'bg-zinc-800 text-white font-semibold shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            ทั้งโปรเจกต์ ({activeProject?.pages?.length || 0})
          </button>
        </div>
      </div>

      {/* Main RUN PIPELINE Button (Exact HTML Mockup Amber Gradient Button) */}
      {isBatchRunning || isPageWorkflowRunning ? (
        <button
          type="button"
          disabled={isCancelling}
          onClick={async () => {
            if (isCancelling) return;
            setIsCancelling(true);

            try {
              const prjId = activeProject?.id;
              const pageId = activePage?.id;

              const cancelRequests = [];
              if (prjId) {
                cancelRequests.push(apiFetch(`/api/pipeline/batch/cancel?project_id=${prjId}`, { method: 'POST' }));
              }
              if (pageId) {
                cancelRequests.push(apiFetch(`/api/pipeline/auto/cancel?page_id=${pageId}`, { method: 'POST' }));
              }

              await Promise.all(cancelRequests);

              if (cancelPageWorkflow) {
                cancelPageWorkflow();
              }
            } catch (error) {
              console.error('Failed to cancel workflow:', error);
            } finally {
              setIsCancelling(false);
            }
          }}
          className="w-full h-9 rounded-lg border border-rose-500/50 bg-rose-500/20 text-[11px] font-bold text-rose-200 hover:bg-rose-500/30 cursor-pointer shadow-md active:scale-[0.98] transition-all flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isCancelling ? (
            <>
              <span className="w-2 h-2 rounded-full bg-rose-400 animate-pulse" />
              <span>CANCELLING...</span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping" />
              <span>■ CANCEL WORKFLOW</span>
            </>
          )}
        </button>
      ) : (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={!activeProject || isProcessing || (trainStatus && trainStatus.is_training)}
            onClick={() => {
              if (onOpenCustomWorkflowModal) {
                onOpenCustomWorkflowModal();
              } else if (pipelineScope === 'all') {
                runBatchPipeline('resume');
              } else {
                runPipelineStep('auto');
              }
            }}
            className="flex-1 h-9 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-extrabold text-[11.5px] cursor-pointer shadow-[0_4px_16px_rgba(245,158,11,0.3)] active:scale-[0.98] transition-all flex items-center justify-center gap-1.5 disabled:opacity-40"
            title="เปิดหน้าต่างจัดการ Custom Workflow และสั่งประมวลผล"
          >
            <Play size={12} className="fill-black" />
            <span>▶ RUN PIPELINE ({pipelineScope === 'all' ? 'ทั้งโปรเจกต์' : 'หน้าปัจจุบัน'})</span>
          </button>
          {onOpenCustomWorkflowModal && (
            <button
              type="button"
              onClick={onOpenCustomWorkflowModal}
              className="h-9 px-2.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-amber-500/50 text-slate-300 hover:text-amber-400 rounded-lg text-xs font-bold transition-colors cursor-pointer shrink-0"
              title="เปิดหน้าจัดการ Custom Workflow (ปรับแต่งลำดับขั้นตอน)"
            >
              ⚙️
            </button>
          )}
        </div>
      )}

      {/* Direct 1-Click Pipeline Stage Matrix Grid (Matches HTML Mockup direct-pipeline-grid) */}
      <div className="flex flex-col gap-1.5 mt-0.5">
        {stages.map((stage) => {
          const isDone = Boolean(stageDoneMap[stage.id]);
          const isNext = stage.id === nextRecommendedStage;

          return (
            <div
              key={stage.id}
              className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
                isNext
                  ? 'border-amber-500 bg-amber-500/10 shadow-[0_0_12px_rgba(245,158,11,0.25)]'
                  : isDone
                  ? 'border-emerald-500/40 bg-emerald-500/10'
                  : 'border-zinc-800/80 bg-zinc-900/80 hover:border-zinc-700'
              }`}
            >
              {/* Left Info: Badge + Icon + Title */}
              <div className="flex items-center gap-2">
                <span
                  className={`text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    isDone
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : isNext
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-zinc-800 text-zinc-400'
                  }`}
                >
                  {isDone ? '✓' : isNext ? '👉' : ''} {stage.id === 'detect' ? '1' : stage.id === 'ocr' ? '2' : stage.id === 'sort' ? '3' : stage.id === 'mask' ? '4' : stage.id === 'inpaint' ? '5' : '6'}
                </span>
                <span className="text-sm">{stage.icon}</span>
                <span className="text-[11px] font-bold text-white">{stage.label}</span>
              </div>

              {/* Right Action Buttons: ➕ เพิ่ม | 🗑️ | 🔄 (Direct 1-Click Buttons) */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={!activeProject || isProcessing || isBatchRunning}
                  onClick={() => {
                    if (pipelineScope === 'all') {
                      runBatchPipeline(stage.id);
                    } else {
                      runPipelineStep(stage.id as any);
                    }
                  }}
                  className={`px-2 py-1 rounded text-[10px] font-semibold flex items-center gap-1 transition-all cursor-pointer disabled:opacity-30 ${
                    isNext
                      ? 'bg-amber-500 text-black font-bold shadow-sm hover:bg-amber-400'
                      : 'bg-zinc-800 hover:bg-amber-500/20 border border-zinc-700 hover:border-amber-500/40 text-slate-200 hover:text-amber-300'
                  }`}
                  title={`เพิ่ม/รัน ${stage.name}`}
                >
                  <span>➕</span>
                  <span>{stage.id === 'font_judge' ? 'ตัดสิน' : 'เพิ่ม'}</span>
                </button>

                {stage.id === 'font_judge' ? (
                  <button
                    type="button"
                    disabled={isProcessing || isBatchRunning || !onOpenAIProviderSettings}
                    onClick={onOpenAIProviderSettings}
                    className="px-1.5 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 rounded text-[10px] cursor-pointer disabled:opacity-30"
                    title="ตั้งค่า AI Provider"
                  >
                    <Settings size={11} />
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={!activeProject || isProcessing || isBatchRunning}
                    onClick={() => {
                      if (!activeProject) return;
                      const isAll = pipelineScope === 'all';
                      const scopeText = isAll ? 'ทั้งโปรเจกต์' : 'หน้าปัจจุบัน';
                      setConfirmConfig({
                        isOpen: true,
                        title: `ลบข้อมูล ${stage.name}`,
                        message: `คุณต้องการลบข้อมูลสเต็ป ${stage.name} (${scopeText}) ใช่หรือไม่?`,
                        onConfirm: async () => {
                          try {
                            if (stage.id === 'detect') {
                              if (isAll) {
                                await apiFetch(`/api/projects/${activeProject.id}/blocks`, { method: 'DELETE' });
                              } else if (activePage) {
                                await apiFetch(`/api/pages/${activePage.id}/blocks`, { method: 'DELETE' });
                              }
                            } else if (stage.id === 'ocr') {
                              const query = isAll ? `project_id=${activeProject.id}` : (activePage ? `page_id=${activePage.id}` : '');
                              if (query) {
                                await apiFetch(`/api/blocks/clear-all-text?${query}`, { method: 'POST' });
                              }
                            } else if (stage.id === 'mask' || stage.id === 'inpaint') {
                              const query = isAll ? `project_id=${activeProject.id}` : (activePage ? `page_id=${activePage.id}` : '');
                              if (query) {
                                await apiFetch(`/api/pipeline/masks?${query}`, { method: 'DELETE' });
                              }
                            }

                            const store = useProjectStore.getState();
                            const currentProjectId = activeProject.id;
                            const currentPageId = activePage?.id;
                            await store.selectProject(currentProjectId);
                            if (currentPageId) {
                              await store.selectPage(currentPageId);
                            }
                          } catch (e) {
                            console.error('Clear stage error:', e);
                          }
                        }
                      });
                    }}
                    className="px-1.5 py-1 bg-zinc-800 hover:bg-rose-500/20 border border-zinc-700 hover:border-rose-500/40 text-rose-300 rounded text-[10px] cursor-pointer disabled:opacity-30"
                    title={`ลบข้อมูล ${stage.name}`}
                  >
                    <Trash2 size={11} />
                  </button>
                )}

                <button
                  type="button"
                  disabled={!activeProject || isProcessing || isBatchRunning}
                  onClick={() => {
                    if (pipelineScope === 'all') {
                      runBatchPipeline(stage.id);
                    } else {
                      runPipelineStep(stage.id as any);
                    }
                  }}
                  className="px-1.5 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 rounded text-[10px] cursor-pointer disabled:opacity-30"
                  title={`รัน ${stage.name} ใหม่`}
                >
                  <RotateCcw size={11} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <ConfirmModal
        isOpen={confirmConfig.isOpen}
        title={confirmConfig.title}
        message={confirmConfig.message}
        onConfirm={confirmConfig.onConfirm}
        onClose={() => setConfirmConfig(prev => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
};


