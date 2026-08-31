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

  // Calculate completed steps count & percentage
  const completedCount = stageOrder.filter((id) => stageDoneMap[id]).length;
  const progressPercent = Math.round((completedCount / stageOrder.length) * 100);

  return (
    <div className="flex flex-col gap-2 bg-[#121216] border border-zinc-800/90 p-3 rounded-xl shadow-lg select-none font-sans text-xs">
      {/* Header & Scope Selector (Matches Staging v1.0.1) */}
      <div className="flex items-center justify-between font-pixel">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${completedCount === 5 ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
          <span className="text-xs font-bold tracking-wide text-white">AI PIPELINE (5 STEPS)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-emerald-400 font-bold">
            {completedCount}/5 ({progressPercent}%)
          </span>
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
            className="px-2 py-0.5 bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 rounded font-pixel text-[9px] font-bold transition flex items-center gap-1 cursor-pointer disabled:opacity-40"
            title="จัดเรียงลำดับอ่านกล่องข้อความมังงะตามตำแหน่ง Y,X (Sort Reading Order)"
          >
            <span>🔄</span>
            <span>Sort</span>
          </button>
        </div>
      </div>

      {/* Scope Switcher */}
      <div className="grid grid-cols-2 bg-[#09090c] border border-zinc-850 p-0.5 rounded-lg text-[10px] font-pixel">
        <button
          type="button"
          onClick={() => setPipelineScope('current')}
          className={`py-1 rounded-md font-bold transition-all cursor-pointer flex items-center justify-center gap-1 ${
            pipelineScope === 'current'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <span>📄</span>
          <span>หน้าปัจจุบัน</span>
        </button>
        <button
          type="button"
          onClick={() => setPipelineScope('all')}
          className={`py-1 rounded-md font-bold transition-all cursor-pointer flex items-center justify-center gap-1 ${
            pipelineScope === 'all'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <span>📚</span>
          <span>ทั้งโปรเจกต์ ({activeProject?.pages?.length || 0})</span>
        </button>
      </div>

      {/* Main RUN PIPELINE Button (Staging Gold Button) */}
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
          className="w-full h-8 rounded-lg border border-rose-500/50 bg-rose-500/20 text-[10.5px] font-bold text-rose-200 hover:bg-rose-500/30 cursor-pointer shadow-md active:scale-[0.98] transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
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
            className="flex-1 h-8 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-black text-[11px] font-pixel cursor-pointer shadow-[0_4px_16px_rgba(245,158,11,0.3)] active:scale-[0.98] transition-all flex items-center justify-center gap-1.5 disabled:opacity-40"
            title="รัน 5 ขั้นตอน AI อัตโนมัติในคลิกเดียว"
          >
            <Play size={11} className="fill-black" />
            <span>⚡ RUN FULL 5-STEP PIPELINE ▶</span>
          </button>
          {onOpenCustomWorkflowModal && (
            <button
              type="button"
              onClick={onOpenCustomWorkflowModal}
              className="h-8 px-2 bg-[#09090c] hover:bg-zinc-800 border border-zinc-800 text-slate-300 hover:text-amber-400 rounded-lg text-xs font-bold transition-colors cursor-pointer shrink-0"
              title="ตั้งค่า Custom Workflow"
            >
              ⚙️
            </button>
          )}
        </div>
      )}

      {/* 5 Step Pipeline Rows (Exact Staging v1.0.1 Design) */}
      <div className="flex flex-col gap-1.5 pt-0.5">
        {stages.map((stage) => {
          const isDone = Boolean(stageDoneMap[stage.id]);
          const isNext = stage.id === nextRecommendedStage;

          // Status subtitle
          let statusBadge = 'พร้อมรัน';
          if (isDone) {
            if (stage.id === 'detect') statusBadge = `${activePage?.text_blocks?.length || 0} บอลลูน`;
            else if (stage.id === 'ocr') statusBadge = 'RapidOCR';
            else if (stage.id === 'mask') statusBadge = 'Auto Mask';
            else if (stage.id === 'inpaint') statusBadge = 'Cleaned';
            else if (stage.id === 'font_judge') statusBadge = 'Typeset';
          }

          return (
            <div
              key={stage.id}
              className={`flex items-center justify-between px-3 py-1.5 rounded-lg border transition-all ${
                isDone
                  ? 'border-emerald-500/30 bg-emerald-500/10'
                  : isNext
                  ? 'border-amber-500/60 bg-amber-500/10 shadow-[0_0_12px_rgba(245,158,11,0.2)]'
                  : 'border-zinc-850 bg-[#09090c]/80 hover:border-zinc-750'
              }`}
            >
              {/* Left Label */}
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-bold font-pixel ${isDone ? 'text-emerald-300' : isNext ? 'text-amber-300 font-black' : 'text-slate-400'}`}>
                  {isDone ? '✓' : isNext ? '⚡' : '○'} {stage.label}
                </span>
                <span className="text-[9px] text-zinc-500 hidden sm:inline">({stage.id === 'detect' ? 'ตรวจจับ' : stage.id === 'ocr' ? 'อ่านข้อความ' : stage.id === 'mask' ? 'สร้างมาสก์' : stage.id === 'inpaint' ? 'ลบตัวอักษร' : 'จัดพิมพ์'})</span>
              </div>

              {/* Right Action / Status Pill */}
              <div className="flex items-center gap-1.5">
                {isDone ? (
                  <span className="text-[8.5px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-1.5 py-0.5 rounded font-mono font-bold">
                    {statusBadge}
                  </span>
                ) : (
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
                    className={`px-2 py-0.5 rounded text-[9.5px] font-pixel font-bold transition-all cursor-pointer disabled:opacity-30 ${
                      isNext
                        ? 'bg-amber-500 text-black shadow hover:bg-amber-400'
                        : 'bg-zinc-800 border border-zinc-700 text-slate-300 hover:bg-amber-500/20 hover:border-amber-500/40 hover:text-amber-300'
                    }`}
                  >
                    RUN ▶
                  </button>
                )}

                {stage.id === 'font_judge' ? (
                  <button
                    type="button"
                    disabled={isProcessing || isBatchRunning || !onOpenAIProviderSettings}
                    onClick={onOpenAIProviderSettings}
                    className="p-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 rounded text-[9px] cursor-pointer"
                    title="ตั้งค่า AI Provider"
                  >
                    <Settings size={10} />
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
                        },
                      });
                    }}
                    className="p-1 bg-zinc-900 hover:bg-rose-950/60 border border-zinc-800 hover:border-rose-700/50 text-zinc-500 hover:text-rose-300 rounded text-[9px] cursor-pointer"
                    title={`ล้างข้อมูลสเต็ป ${stage.name}`}
                  >
                    <Trash2 size={10} />
                  </button>
                )}
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


