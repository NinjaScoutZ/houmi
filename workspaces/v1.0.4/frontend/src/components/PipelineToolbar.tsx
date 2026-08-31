import React, { useState, useRef, useEffect } from 'react';
import type { WorkspaceMode } from '../utils/textTemplates';

export interface PipelineToolbarProps {
  onRunStep?: (step: 'detect' | 'ocr' | 'inpaint' | 'render' | 'font_judge' | 'auto') => void;
  onReorderBlocks?: (direction: 'rtl' | 'ltr') => void;
  onOpenBatchModal?: () => void;
  onOpenSettings?: () => void;
  onExport?: () => void;
  isProcessing?: boolean;
  pageCount?: number;
  backendStatus?: 'online' | 'degraded' | 'offline' | 'loading';
  latencyMs?: number;
  onOpenDiagnostics?: () => void;

  // Extended Sub-toolbar Controls
  workspaceMode?: WorkspaceMode;
  ocrEngine?: string;
  onChangeOcrEngine?: (engine: string) => void;
  aiOcrCorrection?: boolean;
  onToggleAiOcrCorrection?: (val: boolean) => void;
  liveMaskOverlay?: boolean;
  onToggleLiveMaskOverlay?: (val: boolean) => void;
  activeProjectSettings?: Record<string, any>;
  onToggleProjectSetting?: (key: string, val: boolean) => void;
  activePage?: any;
  decisionCounts?: { AUTO_APPLIED?: number; DEFAULTED?: number; NEEDS_REVIEW?: number; with_text?: boolean };
  onRunAutoStylePage?: (applyTemplate: boolean) => void;
  onUndoAutoStylePage?: () => void;
  onRunSuggestOnly?: () => void;
  onReorganizePageText?: () => void;
  layerDecisionFilter?: string;
  onToggleReviewQueueFilter?: () => void;
  onClearTranslationData?: (mode: 'layers' | 'page' | 'project', clearSource?: boolean) => void;
  onRecomputeSmartBalloons?: () => void;
  hasAutoStyleSnapshot?: boolean;
  leftSidebarOpen?: boolean;
  activeProjectName?: string;
  ocrEngineStatuses?: Record<string, { available: boolean; reason?: string } | boolean>;
}

export const PipelineToolbar: React.FC<PipelineToolbarProps> = ({
  onRunStep,
  onReorderBlocks,
  onOpenBatchModal,
  onOpenSettings,
  onExport,
  isProcessing = false,
  pageCount = 1,
  backendStatus = 'online',
  latencyMs,
  onOpenDiagnostics,
  workspaceMode = 'ocr',
  ocrEngine = 'gemini',
  onChangeOcrEngine,
  aiOcrCorrection = false,
  onToggleAiOcrCorrection,
  liveMaskOverlay = true,
  onToggleLiveMaskOverlay,
  activeProjectSettings = {},
  onToggleProjectSetting,
  activePage,
  decisionCounts,
  onRunAutoStylePage,
  onUndoAutoStylePage,
  onRunSuggestOnly,
  onReorganizePageText,
  layerDecisionFilter = 'all',
  onToggleReviewQueueFilter,
  onClearTranslationData,
  onRecomputeSmartBalloons,
  hasAutoStyleSnapshot = false,
  ocrEngineStatuses,
}) => {
  const [showToolsDropdown, setShowToolsDropdown] = useState(false);
  const [showStepsDropdown, setShowStepsDropdown] = useState(false);

  const toolsDropdownRef = useRef<HTMLDivElement>(null);
  const stepsDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (toolsDropdownRef.current && !toolsDropdownRef.current.contains(target)) {
        setShowToolsDropdown(false);
      }
      if (stepsDropdownRef.current && !stepsDropdownRef.current.contains(target)) {
        setShowStepsDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);
  const getEngineStatus = (engineId: string): { available: boolean; reason?: string } => {
    if (!ocrEngineStatuses) return { available: true };
    const status = ocrEngineStatuses[engineId];
    if (typeof status === 'boolean') {
      return { available: status, reason: status ? undefined : 'Engine currently unavailable' };
    }
    if (status && typeof status === 'object') {
      return { available: status.available ?? true, reason: status.reason };
    }
    return { available: true };
  };

  const currentEngineStatus = getEngineStatus(ocrEngine);

  return (
    <div className="w-full bg-zinc-950/80 backdrop-blur-md border-b border-zinc-900 px-4 h-13 py-1 flex items-center justify-between text-xs text-slate-300 z-20 shrink-0 shadow-sm overflow-x-auto gap-3">
      {/* Left side Sub-toolbar controls */}
      <div className="flex items-center gap-3 shrink-0">
        {workspaceMode === 'ocr' && (
          <>
            {/* OCR Engine selector with categorized groups */}
            {onChangeOcrEngine && (
              <div className="flex items-center gap-1 shrink-0" title="เลือกโปรแกรมสำหรับสแกนข้อความ">
                <span className="text-[8px] font-bold text-slate-500 uppercase tracking-wider font-pixel">OCR:</span>
                <select
                  value={ocrEngine}
                  onChange={(e) => onChangeOcrEngine(e.target.value)}
                  className="bg-zinc-900 border border-zinc-800 text-slate-200 text-[9px] rounded py-0.5 px-1 max-w-[130px] truncate focus:outline-none focus:border-yellow-500 cursor-pointer"
                >
                  <optgroup label="⚡ Local Fast GPU / ONNX">
                    {(() => {
                      const stV5 = getEngineStatus('ppocrv5') ?? getEngineStatus('rapidocr') ?? { available: true };
                      return (
                        <option value="ppocrv5" disabled={!stV5.available} title={stV5.reason || 'RapidOCR Engine (GPU DirectML / PP-OCRv5 Korean/English/Chinese)'}>
                          ⚡ RapidOCR (GPU / PP-OCRv5){!stV5.available ? ` (${stV5.reason || 'Disabled'})` : ''}
                        </option>
                      );
                    })()}
                  </optgroup>
                  <optgroup label="AI Cloud & PyTorch VLM Services">
                    {(() => {
                      const stGem = getEngineStatus('gemini');
                      const stGlm = getEngineStatus('glm');
                      const stDs = getEngineStatus('deepseek');
                      return (
                        <>
                          <option value="gemini" disabled={!stGem.available} title={stGem.reason || 'DOBKLE OCR (Gemini 3.6 Flash)'}>
                            ✨ DOBKLE OCR{!stGem.available ? ` (${stGem.reason || 'Disabled'})` : ''}
                          </option>
                          <option value="glm" disabled={!stGlm.available} title={stGlm.reason || 'GLM-OCR Local PyTorch VLM Server (Port 2322)'}>
                            🧠 GLM-OCR{!stGlm.available ? ` (${stGlm.reason || 'Offline'})` : ''}
                          </option>
                          <option value="deepseek" disabled={!stDs.available} title={stDs.reason || 'DeepSeek-OCR PyTorch VLM Server (Port 2322)'}>
                            🐋 DeepSeek-OCR{!stDs.available ? ` (${stDs.reason || 'Offline'})` : ''}
                          </option>
                        </>
                      );
                    })()}
                  </optgroup>
                </select>
                {currentEngineStatus && !currentEngineStatus.available && (
                  <span className="text-amber-400 text-[10px] flex items-center gap-1 font-sans" title={currentEngineStatus.reason || 'Engine offline or missing API key'}>
                    ⚠️ <span className="hidden xl:inline">{currentEngineStatus.reason || 'Offline / Key Missing'}</span>
                  </span>
                )}
              </div>
            )}

            {onToggleAiOcrCorrection && (
              <label className="flex items-center gap-1.5 cursor-pointer select-none hover:text-slate-100 transition-colors" title="ตรวจสะกดคำผิดปกติของ OCR ด้วยโมเดล AI">
                <input
                  type="checkbox"
                  checked={aiOcrCorrection}
                  onChange={(e) => onToggleAiOcrCorrection(e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
                />
                <span className="text-[11px]">AI spellcheck</span>
              </label>
            )}

            {onToggleLiveMaskOverlay && (
              <label className="flex items-center gap-1.5 cursor-pointer select-none hover:text-slate-100 transition-colors" title="แสดงแผ่นสีแดงโปร่งแสงคลุมทับจุดที่จะทำการลบข้อความ">
                <input
                  type="checkbox"
                  checked={liveMaskOverlay}
                  onChange={(e) => onToggleLiveMaskOverlay(e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
                />
                <span className="text-yellow-400 font-bold text-[11px]">Live Mask</span>
              </label>
            )}

            {onToggleProjectSetting && (
              <>
                <div className="h-4 w-px bg-zinc-800 mx-0.5" />
                <div className="grid grid-cols-3 xl:grid-cols-6 gap-x-3 gap-y-0.5 text-[10px]">
                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="หมุนทิศทางข้อความที่ตรวจจับได้จากแนวตั้งเป็นแนวนอนโดยอัตโนมัติ">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.vertical_to_horizontal ?? false}
                      onChange={(e) => onToggleProjectSetting('vertical_to_horizontal', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Vert to Horiz</span>
                  </label>

                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="ลบอักษรเสียงอ่านขนาดเล็ก (ฟุริกานะ) เหนือคันจิภาษาญี่ปุ่น">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.strip_furigana ?? false}
                      onChange={(e) => onToggleProjectSetting('strip_furigana', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Strip furigana</span>
                  </label>

                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="แปลงเครื่องหมายวรรคตอนปกติให้เป็นแบบความกว้างเต็มตามมาตรฐานภาษาจีน">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.use_chinese_punctuation ?? false}
                      onChange={(e) => onToggleProjectSetting('use_chinese_punctuation', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Chinese punct</span>
                  </label>

                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="ลบการเว้นวรรคและช่องว่างทั้งหมดระหว่างคำ เหมาะสำหรับ CJK">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.remove_spaces ?? true}
                      onChange={(e) => onToggleProjectSetting('remove_spaces', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Remove spaces</span>
                  </label>

                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="สแกนข้อความในหน้ากระดาษทันทีโดยอัตโนมัติเมื่อทำการอัปโหลดรูปภาพใหม่">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.auto_ocr ?? true}
                      onChange={(e) => onToggleProjectSetting('auto_ocr', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Auto OCR</span>
                  </label>

                  <label className="flex items-center gap-1 cursor-pointer select-none hover:text-yellow-400 transition-colors" title="ลบการขึ้นบรรทัดใหม่ทั้งหมดในกล่องข้อความ ช่วยจัดย่อหน้า">
                    <input
                      type="checkbox"
                      checked={activeProjectSettings.auto_remove_line_breaks ?? true}
                      onChange={(e) => onToggleProjectSetting('auto_remove_line_breaks', e.target.checked)}
                      className="w-3 h-3 rounded border-zinc-800 bg-zinc-900 text-yellow-500 accent-yellow-500 cursor-pointer"
                    />
                    <span>Auto line breaks</span>
                  </label>
                </div>
              </>
            )}
          </>
        )}

        {workspaceMode === 'typeset' && (
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-yellow-400 font-pixel font-bold uppercase tracking-wider">B+ Typeset</span>
            {decisionCounts?.with_text && (
              <span className="flex items-center gap-1 text-[9px] font-pixel bg-zinc-900 border border-zinc-800/80 px-2 py-0.5 rounded-sm">
                <span className="text-emerald-400" title="AUTO_APPLIED">OK {decisionCounts.AUTO_APPLIED || 0}</span>
                <span className="text-sky-400" title="DEFAULTED">DEF {decisionCounts.DEFAULTED || 0}</span>
                <span className="text-amber-400" title="NEEDS_REVIEW">REV {decisionCounts.NEEDS_REVIEW || 0}</span>
              </span>
            )}
            {onRunAutoStylePage && (
              <button
                type="button"
                disabled={!activePage || isProcessing}
                onClick={() => onRunAutoStylePage(true)}
                className="rounded border border-yellow-500/40 bg-yellow-500/15 px-2.5 py-1 text-[9px] font-bold text-yellow-300 hover:bg-yellow-500/25 font-pixel disabled:opacity-40 cursor-pointer shadow-sm"
                title="Style Judge ทั้งหน้า + recompute layout"
              >
                ⚡ STYLE JUDGE PAGE
              </button>
            )}
            {onToggleReviewQueueFilter && (
              <button
                type="button"
                disabled={!activePage}
                onClick={() => onToggleReviewQueueFilter()}
                className={`rounded border px-2.5 py-1 text-[9px] font-bold font-pixel cursor-pointer ${
                  layerDecisionFilter === 'NEEDS_REVIEW'
                    ? 'border-amber-500/50 bg-amber-500/20 text-amber-200'
                    : 'border-zinc-700 bg-zinc-900 text-slate-300 hover:border-amber-500/40 hover:text-amber-300'
                }`}
                title="Review Queue — แสดงเฉพาะกล่อง NEEDS_REVIEW"
              >
                REVIEW QUEUE
              </button>
            )}
            
            {/* Tools Dropdown */}
            <div className="relative" ref={toolsDropdownRef}>
              <button
                type="button"
                onClick={() => setShowToolsDropdown(!showToolsDropdown)}
                className="rounded border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-900 hover:border-yellow-500/30 px-2.5 py-1 text-[9px] font-bold text-slate-300 hover:text-yellow-400 font-pixel cursor-pointer flex items-center gap-1.5 transition-colors"
                title="เครื่องมือทำความสะอาด และคำสั่งเพิ่มเติม"
              >
                🛠️ TOOLS <span className="text-[7px]">▼</span>
              </button>
              {showToolsDropdown && (
                <div className="absolute left-0 mt-1.5 w-44 bg-zinc-950 border border-zinc-800/80 rounded shadow-2xl py-1 z-40 flex flex-col font-sans select-none animate-fade-in">
                  {onUndoAutoStylePage && (
                    <button
                      type="button"
                      disabled={!activePage || isProcessing || !hasAutoStyleSnapshot}
                      onClick={() => { onUndoAutoStylePage(); setShowToolsDropdown(false); }}
                      className="px-3 py-1.5 text-[10px] font-semibold text-slate-300 hover:bg-zinc-900 hover:text-sky-300 text-left disabled:opacity-40 disabled:pointer-events-none"
                    >
                      ↩️ Undo Auto Style
                    </button>
                  )}
                  {onRunSuggestOnly && (
                    <button
                      type="button"
                      disabled={!activePage || isProcessing}
                      onClick={() => { onRunSuggestOnly(); setShowToolsDropdown(false); }}
                      className="px-3 py-1.5 text-[10px] font-semibold text-slate-300 hover:bg-zinc-900 hover:text-amber-400 text-left disabled:opacity-40"
                    >
                      💡 Suggest Only (แนะนำสไตล์)
                    </button>
                  )}
                  {onRecomputeSmartBalloons && (
                    <button
                      type="button"
                      disabled={isProcessing}
                      onClick={() => { onRecomputeSmartBalloons(); setShowToolsDropdown(false); }}
                      className="px-3 py-1.5 text-[10px] font-semibold text-yellow-300 hover:bg-yellow-500/10 hover:text-yellow-200 text-left font-bold"
                    >
                      🎈 ✨ Recompute Smart Balloons
                    </button>
                  )}
                  {onReorganizePageText && (
                    <button
                      type="button"
                      disabled={!activePage || isProcessing}
                      onClick={() => { onReorganizePageText(); setShowToolsDropdown(false); }}
                      className="px-3 py-1.5 text-[10px] font-semibold text-slate-300 hover:bg-zinc-900 hover:text-emerald-400 text-left disabled:opacity-40"
                    >
                      🔄 Recompute Layout
                    </button>
                  )}
                  <div className="h-px bg-zinc-900 my-1" />
                  {onClearTranslationData && (
                    <>
                      <button 
                        type="button" 
                        onClick={() => { onClearTranslationData('layers'); setShowToolsDropdown(false); }} 
                        className="px-3 py-1.5 text-[10px] font-semibold text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 text-left"
                      >
                        🧹 Clear Selected Layer
                      </button>
                      <button 
                        type="button" 
                        onClick={() => { onClearTranslationData('page'); setShowToolsDropdown(false); }} 
                        className="px-3 py-1.5 text-[10px] font-semibold text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 text-left"
                      >
                        🗑️ Clear Current Page
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step buttons when onRunStep is provided */}
        {onRunStep && (
          <div className="flex items-center gap-2 shrink-0 pl-2 border-l border-zinc-900">
            <button
              disabled={isProcessing}
              onClick={() => onRunStep('auto')}
              className="px-3 py-1 bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white font-bold rounded shadow-[0_0_10px_rgba(249,115,22,0.15)] hover:shadow-[0_0_15px_rgba(249,115,22,0.3)] transition-all flex items-center gap-1.5 text-[10.5px] cursor-pointer"
              title="รันสแกนคำและลบตัวอักษรเดิมหน้านี้ครบวงจร"
            >
              <span>⚡</span>
              <span>Auto-Run Page</span>
            </button>

            {onRecomputeSmartBalloons && (
              <button
                disabled={isProcessing}
                onClick={onRecomputeSmartBalloons}
                className="px-2.5 py-1 bg-yellow-500/15 hover:bg-yellow-500/25 border border-yellow-500/40 text-yellow-300 font-bold rounded flex items-center gap-1 text-[10.5px] cursor-pointer transition-colors"
                title="คำนวณทรงและพิกเซลจริง Smart Balloon ทั้งโปรเจกต์"
              >
                <span>🎈</span>
                <span>Smart Balloon</span>
              </button>
            )}

            {/* Individual Steps Dropdown */}
            <div className="relative" ref={stepsDropdownRef}>
              <button
                type="button"
                onClick={() => setShowStepsDropdown(!showStepsDropdown)}
                className="rounded border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-900 hover:border-yellow-500/30 px-2.5 py-1 text-[9px] font-bold text-slate-300 hover:text-amber-400 cursor-pointer flex items-center gap-1.5 transition-colors"
                title="สั่งรันกระบวนการแยกทีละขั้นตอน"
              >
                <span>🛠️ Manual Steps</span>
                <span className="text-[7px]">▼</span>
              </button>
              {showStepsDropdown && (
                <div className="absolute left-0 mt-1.5 w-44 bg-zinc-950 border border-zinc-800/80 rounded shadow-2xl py-1 z-40 flex flex-col font-sans select-none animate-fade-in">
                  <button
                    disabled={isProcessing}
                    onClick={() => { onRunStep('detect'); setShowStepsDropdown(false); }}
                    className="px-3 py-1.5 text-[10px] font-semibold text-slate-300 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                  >
                    <span>🎈</span>
                    <span>1. Detect Balloons</span>
                  </button>
                  <button
                    disabled={isProcessing}
                    onClick={() => { onRunStep('ocr'); setShowStepsDropdown(false); }}
                    className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                  >
                    <span>📖</span>
                    <span>2. Run OCR Scan</span>
                  </button>
                  <button
                    disabled={isProcessing}
                    onClick={() => { onRunStep('inpaint'); setShowStepsDropdown(false); }}
                    className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                  >
                    <span>🧹</span>
                    <span>3. Inpaint Background</span>
                  </button>
                  <button
                    disabled={isProcessing}
                    onClick={() => { onRunStep('font_judge'); setShowStepsDropdown(false); }}
                    className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                  >
                    <span>✒️</span>
                    <span>5. Run AI Font Judge</span>
                  </button>
                  <button
                    disabled={isProcessing}
                    onClick={() => { onRunStep('render'); setShowStepsDropdown(false); }}
                    className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                  >
                    <span>🔤</span>
                    <span>5. Typeset Layout</span>
                  </button>
                  {onReorderBlocks && (
                    <>
                      <div className="h-px bg-zinc-900 my-1" />
                      <button
                        disabled={isProcessing}
                        onClick={() => { onReorderBlocks('rtl'); setShowStepsDropdown(false); }}
                        className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 hover:bg-zinc-900 hover:text-yellow-400 text-left disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
                      >
                        <span>🔄</span>
                        <span>Sort Layers RTL</span>
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Right side Status & Action controls */}
      <div className="flex items-center gap-2 shrink-0">
        {onOpenDiagnostics && (
          <button
            type="button"
            onClick={onOpenDiagnostics}
            className="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-slate-300 border border-zinc-800 rounded text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer"
            title="Backend Server Status - Diagnostics"
          >
            <span
              className={`w-2 h-2 rounded-full ${
                backendStatus === 'online'
                  ? 'bg-emerald-500 animate-pulse'
                  : backendStatus === 'degraded'
                  ? 'bg-amber-500 animate-pulse'
                  : 'bg-rose-500'
              }`}
            />
            <span className="capitalize font-semibold text-[10px]">
              {backendStatus}
            </span>
            {latencyMs !== undefined && latencyMs >= 0 && (
              <span className="text-[10px] text-slate-400 font-mono">
                ({latencyMs}ms)
              </span>
            )}
          </button>
        )}

        {pageCount > 1 && onOpenBatchModal && (
          <button
            onClick={onOpenBatchModal}
            className="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-slate-300 border border-zinc-800 rounded text-xs font-medium transition-all flex items-center gap-1"
          >
            <span>📚</span>
            <span>Batch ({pageCount})</span>
          </button>
        )}

        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="p-1 bg-zinc-900 hover:bg-zinc-800 text-slate-300 border border-zinc-800 rounded transition-all cursor-pointer"
            title="Open Global Settings"
          >
            <span>⚙️</span>
          </button>
        )}

        {onExport && (
          <button
            onClick={onExport}
            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded shadow-sm transition-all flex items-center gap-1 text-xs cursor-pointer"
          >
            <span>📥</span>
            <span>Export</span>
          </button>
        )}
      </div>
    </div>
  );
};
