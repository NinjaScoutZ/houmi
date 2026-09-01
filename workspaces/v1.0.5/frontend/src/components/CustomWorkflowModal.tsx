import React, { useState, useEffect } from 'react';
import { 
  X, Play, RotateCcw, Trash2, ArrowUp, ArrowDown, Plus, Minus, 
  Settings, Check, Sparkles, Layers, Sliders, Zap 
} from 'lucide-react';

export interface WorkflowStepDef {
  id: string;
  name: string;
  nameTh: string;
  icon: string;
  desc: string;
  defaultParams?: Record<string, any>;
}

export const AVAILABLE_WORKFLOW_STEPS: WorkflowStepDef[] = [
  {
    id: 'detect',
    name: 'Text detection',
    nameTh: 'ตรวจจับบอลลูนข้อความ',
    icon: '🎈',
    desc: 'สแกนหากล่องข้อความและบอลลูนด้วย AI Detector',
    defaultParams: { min_confidence: 0.25, balloon_model: 'default' }
  },
  {
    id: 'sort',
    name: 'Sort reading order',
    nameTh: 'จัดลำดับการอ่าน',
    icon: '🔢',
    desc: 'เรียงลำดับกล่องข้อความตามทิศทางการอ่านมังงะ/เว็บตูน (Y, X)',
  },
  {
    id: 'ocr',
    name: 'Text recognition (OCR)',
    nameTh: 'อ่านตัวอักษร (OCR)',
    icon: '📖',
    desc: 'สแกนข้อความด้วย RapidOCR / Gemini / VLM',
    defaultParams: { backend: 'rapidocr' }
  },
  {
    id: 'filter_empty',
    name: 'Remove empty text areas',
    nameTh: 'ลบกล่องที่ไม่มีตัวอักษร',
    icon: '✂️',
    desc: 'ตัดกล่องที่ OCR ไม่พบตัวอักษร หรือมีแต่ขยะภาพออกอัตโนมัติ',
  },
  {
    id: 'merge_expand',
    name: 'Merge & expand areas',
    nameTh: 'รวมบรรทัด & ขยายขอบเซฟตี้',
    icon: '↔️',
    desc: 'รวมกล่องที่อยู่ใกล้กัน และขยายขอบเซฟตี้ +10px ไม่ให้ตัวอักษรขาด',
  },
  {
    id: 'mask',
    name: 'Generate text mask',
    nameTh: 'สร้าง Mask ตัวหนังสือ',
    icon: '🎭',
    desc: 'สร้างมาสก์ครอบเฉพาะลายเส้นตัวอักษรเตรียมคลีนภาพ',
  },
  {
    id: 'inpaint',
    name: 'Inpainting / Clean background',
    nameTh: 'ลบข้อความพื้นหลัง (Clean)',
    icon: '🧹',
    desc: 'ลบตัวอักษรเดิมด้วย Solid Fill 1ms และ AI LaMa',
    defaultParams: { method: 'auto' }
  },
  {
    id: 'font_judge',
    name: 'AI Font Judge',
    nameTh: 'ตัดสินสไตล์ฟอนต์ (AI Font)',
    icon: '✨',
    desc: 'วิเคราะห์อารมณ์และจับคู่ฟอนต์การ์ตูนให้เหมาะสมอัตโนมัติ',
  },
  {
    id: 'typeset',
    name: 'Smart Typesetting & Wrap',
    nameTh: 'จัดหน้า & ตัดคำไทย',
    icon: '📐',
    desc: 'ตัดคำไทยและคำนวณขนาดตัวอักษรให้พอดีกับบอลลูน',
  }
];

export const WORKFLOW_PRESETS: { id: string; name: string; icon: string; steps: string[] }[] = [
  {
    id: 'manga_std',
    name: 'Manga Standard (แนะนำ)',
    icon: '⚡',
    steps: ['detect', 'sort', 'ocr', 'filter_empty', 'inpaint', 'font_judge']
  },
  {
    id: 'full_auto',
    name: 'Full Automation (ครบวงจร)',
    icon: '🚀',
    steps: ['detect', 'sort', 'ocr', 'filter_empty', 'merge_expand', 'mask', 'inpaint', 'font_judge', 'typeset']
  },
  {
    id: 'ocr_transcribe',
    name: 'OCR & Transcribe Only',
    icon: '📝',
    steps: ['detect', 'sort', 'ocr', 'filter_empty']
  },
  {
    id: 'clean_only',
    name: 'Clean & Inpaint Only',
    icon: '🧹',
    steps: ['detect', 'mask', 'inpaint']
  }
];

const LOCAL_STORAGE_WORKFLOW_KEY = 'houmi_custom_workflow_config_v1';

export interface CustomWorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRunWorkflow: (steps: string[], scope: 'current' | 'all', params: Record<string, any>) => void;
  activeProject: any;
  activePage: any;
  isProcessing: boolean;
  ocrEngine?: string;
  onChangeOcrEngine?: (engine: string) => void;
  ocrEngineStatuses?: Record<string, any>;
}

export const CustomWorkflowModal: React.FC<CustomWorkflowModalProps> = ({
  isOpen,
  onClose,
  onRunWorkflow,
  activeProject,
  activePage,
  isProcessing,
  ocrEngine = 'rapidocr',
  onChangeOcrEngine,
  ocrEngineStatuses,
}) => {
  const [activeStepIds, setActiveStepIds] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_WORKFLOW_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed.steps) && parsed.steps.length > 0) {
          return parsed.steps;
        }
      }
    } catch {}
    return WORKFLOW_PRESETS[0].steps;
  });

  const [workflowParams, setWorkflowParams] = useState<Record<string, any>>(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_WORKFLOW_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.params && typeof parsed.params === 'object') {
          return parsed.params;
        }
      }
    } catch {}
    return {
      ocr_backend: ocrEngine || 'rapidocr',
      min_confidence: 0.25,
      inpaint_method: 'auto',
    };
  });

  const [selectedAvailableId, setSelectedAvailableId] = useState<string>(AVAILABLE_WORKFLOW_STEPS[0].id);
  const [selectedActiveIndex, setSelectedActiveIndex] = useState<number | null>(0);
  const [scope, setScope] = useState<'current' | 'all'>('all');
  const [selectedPresetId, setSelectedPresetId] = useState<string>('manga_std');

  useEffect(() => {
    if (ocrEngine) {
      setWorkflowParams(prev => ({ ...prev, ocr_backend: ocrEngine }));
    }
  }, [ocrEngine]);

  useEffect(() => {
    try {
      localStorage.setItem(LOCAL_STORAGE_WORKFLOW_KEY, JSON.stringify({
        steps: activeStepIds,
        params: workflowParams,
        scope,
        presetId: selectedPresetId,
      }));
    } catch (e) {
      console.warn('Failed to save custom workflow config:', e);
    }
  }, [activeStepIds, workflowParams, scope, selectedPresetId]);

  if (!isOpen) return null;

  const handleAddStep = (stepIdToAdd?: string) => {
    const id = stepIdToAdd || selectedAvailableId;
    if (!id) return;
    setActiveStepIds(prev => [...prev, id]);
    setSelectedActiveIndex(activeStepIds.length);
  };

  const handleRemoveStep = () => {
    if (selectedActiveIndex === null || selectedActiveIndex < 0 || selectedActiveIndex >= activeStepIds.length) return;
    setActiveStepIds(prev => prev.filter((_, idx) => idx !== selectedActiveIndex));
    setSelectedActiveIndex(prev => {
      if (prev === null) return null;
      if (prev >= activeStepIds.length - 1) return Math.max(0, activeStepIds.length - 2);
      return prev;
    });
  };

  const handleMoveUp = () => {
    if (selectedActiveIndex === null || selectedActiveIndex <= 0) return;
    const idx = selectedActiveIndex;
    setActiveStepIds(prev => {
      const next = [...prev];
      const temp = next[idx - 1];
      next[idx - 1] = next[idx];
      next[idx] = temp;
      return next;
    });
    setSelectedActiveIndex(idx - 1);
  };

  const handleMoveDown = () => {
    if (selectedActiveIndex === null || selectedActiveIndex >= activeStepIds.length - 1) return;
    const idx = selectedActiveIndex;
    setActiveStepIds(prev => {
      const next = [...prev];
      const temp = next[idx + 1];
      next[idx + 1] = next[idx];
      next[idx] = temp;
      return next;
    });
    setSelectedActiveIndex(idx + 1);
  };

  const handleClear = () => {
    setActiveStepIds([]);
    setSelectedActiveIndex(null);
  };

  const handleApplyPreset = (preset: typeof WORKFLOW_PRESETS[0]) => {
    setActiveStepIds([...preset.steps]);
    setSelectedPresetId(preset.id);
    setSelectedActiveIndex(0);
  };

  const handleRun = () => {
    if (activeStepIds.length === 0) return;
    if (workflowParams.ocr_backend && onChangeOcrEngine && workflowParams.ocr_backend !== ocrEngine) {
      onChangeOcrEngine(workflowParams.ocr_backend);
    }
    onRunWorkflow(activeStepIds, scope, workflowParams);
    onClose();
  };

  const activeStepDetails = selectedActiveIndex !== null && selectedActiveIndex >= 0 && selectedActiveIndex < activeStepIds.length
    ? AVAILABLE_WORKFLOW_STEPS.find(s => s.id === activeStepIds[selectedActiveIndex])
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in font-sans">
      <div className="w-full max-w-2xl bg-zinc-950 border border-zinc-800/90 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-slide-up text-slate-200">
        
        {/* Header Bar */}
        <div className="px-5 py-3.5 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between shrink-0 font-pixel">
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <Sliders size={16} />
            </span>
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                Custom Workflow Manager
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-amber-400 border border-zinc-700">
                  {activeStepIds.length} Steps
                </span>
              </h3>
              <p className="text-[10px] text-slate-400 font-sans mt-0.5">
                ปรับแต่งและเรียงลำดับขั้นตอนการประมวลผล Pipeline ตามที่ต้องการ (ระบบจะจดจำค่าไว้อัตโนมัติ)
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            title="ปิด (Close)"
          >
            <X size={18} />
          </button>
        </div>

        {/* Quick Presets Bar */}
        <div className="px-5 py-2.5 bg-zinc-900/40 border-b border-zinc-900 flex items-center gap-2 overflow-x-auto text-xs shrink-0">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-pixel shrink-0 flex items-center gap-1">
            <Zap size={11} className="text-yellow-400" /> Presets:
          </span>
          {WORKFLOW_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handleApplyPreset(preset)}
              className={`px-2.5 py-1 rounded-lg font-pixel text-[10.5px] font-bold transition-all shrink-0 cursor-pointer flex items-center gap-1.5 ${
                selectedPresetId === preset.id
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-sm shadow-amber-500/10'
                  : 'bg-zinc-900/80 hover:bg-zinc-800 text-slate-300 border border-zinc-800 hover:border-zinc-700'
              }`}
            >
              <span>{preset.icon}</span>
              <span>{preset.name}</span>
            </button>
          ))}
        </div>

        {/* Main 3-Column Box */}
        <div className="p-5 grid grid-cols-1 md:grid-cols-[1fr_80px_1fr] gap-3 flex-1 overflow-hidden min-h-0">
          
          {/* Left Column: Available Steps List */}
          <div className="flex flex-col border border-zinc-800 bg-zinc-900/40 rounded-xl overflow-hidden min-h-0">
            <div className="px-3 py-2 bg-zinc-900/80 border-b border-zinc-800 text-[10px] font-bold text-slate-400 uppercase tracking-wider font-pixel flex items-center justify-between">
              <span>📋 Available Steps (ขั้นตอนที่เลือกได้)</span>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-1 custom-scrollbar">
              {AVAILABLE_WORKFLOW_STEPS.map((step) => {
                const isSelected = selectedAvailableId === step.id;
                return (
                  <div
                    key={step.id}
                    onClick={() => setSelectedAvailableId(step.id)}
                    onDoubleClick={() => handleAddStep(step.id)}
                    className={`px-3 py-2 rounded-lg text-xs transition-all cursor-pointer select-none flex flex-col gap-0.5 ${
                      isSelected
                        ? 'bg-cyan-500/15 border border-cyan-500/50 text-cyan-200'
                        : 'bg-zinc-900/60 hover:bg-zinc-800/80 text-slate-300 border border-transparent hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center justify-between font-bold">
                      <span className="flex items-center gap-1.5">
                        <span>{step.icon}</span>
                        <span>{step.name}</span>
                      </span>
                      <span className="text-[9.5px] text-slate-400 font-normal font-sans">
                        {step.nameTh}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Center Action Buttons */}
          <div className="flex md:flex-col items-center justify-center gap-2 shrink-0 py-2">
            <button
              type="button"
              onClick={() => handleAddStep()}
              className="w-full py-2 px-3 bg-zinc-800 hover:bg-amber-500/20 hover:border-amber-500/50 border border-zinc-700 text-slate-200 hover:text-amber-300 rounded-lg text-xs font-bold font-pixel transition-all flex items-center justify-center gap-1 cursor-pointer shadow-sm"
              title="Add to Workflow"
            >
              <Plus size={13} />
              <span>Add</span>
            </button>
            <button
              type="button"
              disabled={selectedActiveIndex === null || activeStepIds.length === 0}
              onClick={handleRemoveStep}
              className="w-full py-2 px-3 bg-zinc-800 hover:bg-rose-500/20 hover:border-rose-500/50 border border-zinc-700 text-slate-200 hover:text-rose-300 rounded-lg text-xs font-bold font-pixel transition-all flex items-center justify-center gap-1 cursor-pointer disabled:opacity-30 disabled:pointer-events-none"
              title="Remove from Workflow"
            >
              <Minus size={13} />
              <span>Remove</span>
            </button>
            <div className="h-px bg-zinc-800 w-full my-1 hidden md:block" />
            <button
              type="button"
              disabled={selectedActiveIndex === null || selectedActiveIndex <= 0}
              onClick={handleMoveUp}
              className="w-full py-1.5 px-3 bg-zinc-850 hover:bg-zinc-700 border border-zinc-700 text-slate-300 rounded-lg text-xs font-bold font-pixel transition-all flex items-center justify-center gap-1 cursor-pointer disabled:opacity-30 disabled:pointer-events-none"
              title="Move Up"
            >
              <ArrowUp size={13} />
              <span>Up</span>
            </button>
            <button
              type="button"
              disabled={selectedActiveIndex === null || selectedActiveIndex >= activeStepIds.length - 1}
              onClick={handleMoveDown}
              className="w-full py-1.5 px-3 bg-zinc-850 hover:bg-zinc-700 border border-zinc-700 text-slate-300 rounded-lg text-xs font-bold font-pixel transition-all flex items-center justify-center gap-1 cursor-pointer disabled:opacity-30 disabled:pointer-events-none"
              title="Move Down"
            >
              <ArrowDown size={13} />
              <span>Down</span>
            </button>
            <button
              type="button"
              disabled={activeStepIds.length === 0}
              onClick={handleClear}
              className="w-full py-1.5 px-3 bg-zinc-900 hover:bg-rose-500/15 border border-zinc-800 hover:border-rose-500/40 text-slate-400 hover:text-rose-300 rounded-lg text-xs font-bold font-pixel transition-all flex items-center justify-center gap-1 cursor-pointer disabled:opacity-30 disabled:pointer-events-none mt-1"
              title="Clear All Steps"
            >
              <Trash2 size={12} />
              <span>Clear</span>
            </button>
          </div>

          {/* Right Column: Active Workflow Sequence */}
          <div className="flex flex-col border border-zinc-800 bg-zinc-900/40 rounded-xl overflow-hidden min-h-0">
            <div className="px-3 py-2 bg-zinc-900/80 border-b border-zinc-800 text-[10px] font-bold text-amber-400 uppercase tracking-wider font-pixel flex items-center justify-between">
              <span>⚡ Active Workflow Sequence (ลำดับที่ทำงานจริง)</span>
              <span className="font-mono text-[9px] text-slate-400">เรียง 1 ➔ N</span>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 custom-scrollbar">
              {activeStepIds.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center p-6 text-slate-500 text-xs italic font-pixel text-center">
                  <span>ยังไม่มีขั้นตอนใน Workflow</span>
                  <span className="text-[10px] text-slate-600 mt-1">กดปุ่ม Add หรือเลือก Preset ด้านบน</span>
                </div>
              ) : (
                activeStepIds.map((stepId, idx) => {
                  const stepDef = AVAILABLE_WORKFLOW_STEPS.find(s => s.id === stepId) || {
                    id: stepId,
                    name: stepId,
                    nameTh: '',
                    icon: '⚙️',
                    desc: ''
                  };
                  const isSelected = selectedActiveIndex === idx;
                  return (
                    <div
                      key={`${stepId}-${idx}`}
                      onClick={() => setSelectedActiveIndex(idx)}
                      className={`px-3 py-2 rounded-lg text-xs transition-all cursor-pointer select-none flex items-center justify-between ${
                        isSelected
                          ? 'bg-amber-500/20 border border-amber-500/60 text-amber-200 shadow-sm shadow-amber-500/10'
                          : 'bg-zinc-900/80 hover:bg-zinc-850 text-slate-200 border border-zinc-800 hover:border-zinc-700'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded bg-zinc-950 border border-zinc-700 font-mono text-[10px] font-bold flex items-center justify-center text-amber-400">
                          {idx + 1}
                        </span>
                        <span className="text-sm">{stepDef.icon}</span>
                        <div className="flex flex-col">
                          <span className="font-bold font-pixel text-[11px]">{stepDef.name}</span>
                          <span className="text-[9.5px] text-slate-400 font-sans">{stepDef.nameTh}</span>
                        </div>
                      </div>
                      <span className="text-[9px] font-mono text-slate-500 uppercase">
                        step {idx + 1}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Dynamic Parameter Configuration Panel (Params click to set) */}
        <div className="px-5 py-3 bg-zinc-900/60 border-t border-zinc-850 flex flex-col gap-2 shrink-0">
          <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-wider font-pixel">
            <span className="flex items-center gap-1.5 text-slate-300">
              <Settings size={12} className="text-yellow-400" />
              <span>Params (คลิกสเต็ปด้านบนเพื่อตั้งค่าเฉพาะ):</span>
              <span className="text-amber-400 font-mono">
                {activeStepDetails ? activeStepDetails.name : 'All Steps'}
              </span>
            </span>
          </div>

          <div className="p-3 bg-zinc-950 border border-zinc-800/90 rounded-xl grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            {/* OCR Engine Parameter */}
            <div>
              <label className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-1 font-pixel">
                📖 OCR Engine
              </label>
              <select
                value={workflowParams.ocr_backend || 'rapidocr'}
                onChange={(e) => setWorkflowParams(prev => ({ ...prev, ocr_backend: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value="rapidocr">⚡ RapidOCR (DirectML GPU / PP-OCRv6 SOTA)</option>
                <option value="gemini">🌟 DOBKLE OCR (Gemini 3.6 Flash)</option>
                <option value="glm">🤖 GLM-OCR (VLM)</option>
                <option value="rapidocr">🐋 RapidOCR-OCR (VLM)</option>
                <option value="paddleocr">📦 PaddleOCR (Local ONNX)</option>
              </select>
            </div>

            {/* Balloon Model Parameter */}
            <div>
              <label className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-1 font-pixel">
                🎯 Balloon Model
              </label>
              <select
                value={workflowParams.balloon_model || 'Chinese Webtoon (SQ)'}
                onChange={(e) => setWorkflowParams(prev => ({ ...prev, balloon_model: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value="Chinese Webtoon (SQ)">🇨🇳 Chinese Webtoon (SQ) [ม่านฮวาจีน]</option>
                <option value="Comic-Translate (8k Multi-Style)">🎨 Comic-Translate 8k [ฟูลขอบเขตลูกโป่ง]</option>
                <option value="Manga Panel & Text (YOLO26n)">⚡ Manga Panel & Text [YOLO26n]</option>
                <option value="RF-DETR (Transformer)">🤖 RF-DETR [Transformer]</option>
                <option value="Japanese Manga & CG (YOLO11s)">🇯🇵 Japanese Manga [YOLO11s]</option>
                <option value="Korean Webtoon (YOLOv8)">🇰🇷 Korean Webtoon (SAO Default)</option>
              </select>
            </div>

            {/* Balloon Detect Confidence Slider */}
            <div>
              <div className="flex justify-between items-center mb-1 text-[9.5px] font-bold font-pixel">
                <span className="text-slate-400 uppercase tracking-wider">🎈 Confidence</span>
                <span className="font-mono text-yellow-400">{Math.round((workflowParams.min_confidence ?? 0.25) * 100)}%</span>
              </div>
              <input
                type="range"
                min="0.1"
                max="0.9"
                step="0.05"
                value={workflowParams.min_confidence ?? 0.25}
                onChange={(e) => setWorkflowParams(prev => ({ ...prev, min_confidence: parseFloat(e.target.value) }))}
                className="w-full accent-yellow-500 cursor-pointer"
              />
            </div>

            {/* Clean Method Parameter */}
            <div>
              <label className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-1 font-pixel">
                🧹 Clean / Inpaint Method
              </label>
              <select
                value={workflowParams.inpaint_method || 'auto'}
                onChange={(e) => setWorkflowParams(prev => ({ ...prev, inpaint_method: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value="auto">⚡ Two-Tier (Solid Fill + LaMa)</option>
                <option value="lama_only">🎨 Force AI LaMa (ทุกกล่อง)</option>
                <option value="solid_only">⬜ Solid Fill Only (เร็วสุด)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Footer Actions: Scope Switcher + Run Button */}
        <div className="px-5 py-3.5 bg-zinc-900/90 border-t border-zinc-800 flex items-center justify-between shrink-0 font-pixel gap-3">
          {/* Scope Radio Selector */}
          <div className="flex items-center bg-zinc-950 border border-zinc-800 rounded-lg p-0.5 gap-0.5">
            <button
              type="button"
              onClick={() => setScope('current')}
              className={`px-3 py-1.5 rounded-md text-[10px] font-bold transition-colors cursor-pointer ${
                scope === 'current'
                  ? 'bg-amber-500 text-black shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              📄 หน้าปัจจุบัน {activePage ? `(#${activePage.page_number})` : ''}
            </button>
            <button
              type="button"
              onClick={() => setScope('all')}
              className={`px-3 py-1.5 rounded-md text-[10px] font-bold transition-colors cursor-pointer ${
                scope === 'all'
                  ? 'bg-amber-500 text-black shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              📚 ทั้งโปรเจกต์ {activeProject?.pages?.length ? `(${activeProject.pages.length} หน้า)` : ''}
            </button>
          </div>

          {/* Right Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-slate-300 rounded-xl text-xs font-bold transition-colors cursor-pointer"
            >
              ยกเลิก
            </button>
            <button
              type="button"
              disabled={isProcessing || activeStepIds.length === 0}
              onClick={handleRun}
              className="px-5 py-2 bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-black font-extrabold rounded-xl text-xs shadow-lg shadow-amber-500/20 hover:shadow-amber-500/35 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
            >
              <Play size={14} fill="currentColor" />
              <span>🚀 Start Workflow ({activeStepIds.length} Steps)</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
