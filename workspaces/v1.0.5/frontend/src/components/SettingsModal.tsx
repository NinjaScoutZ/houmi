import React, { useState, useEffect } from 'react';
import { useProjectStore } from '../stores/projectStore';
import { ColorField } from './ColorField';
import { DEFAULT_TEXT_TEMPLATES, type TextTemplate } from '../utils/textTemplates';
import { apiFetch } from '../api/runtime';

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Optional extended props from App state when available
  stylePresets?: Record<string, TextTemplate>;
  onSaveTemplates?: (presets: Record<string, TextTemplate>) => void;
  systemFonts?: string[];
  keyBindings?: Record<string, string>;
  onUpdateKeyBinding?: (action: string, key: string) => void;
  onResetKeyBindings?: () => void;
  ocrEngineStatuses?: Record<string, { available: boolean; reason?: string } | boolean>;
}

type SettingsCategory =
  | 'ai_detection'
  | 'engine_health'
  | 'typography'
  | 'templates'
  | 'pipeline'
  | 'performance'
  | 'workspace_dirs'
  | 'keyboard_shortcuts';

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  stylePresets: externalStylePresets,
  onSaveTemplates,
  systemFonts: _systemFonts = [],
  keyBindings: _keyBindings = {},
  onUpdateKeyBinding: _onUpdateKeyBinding,
  onResetKeyBindings: _onResetKeyBindings,
  ocrEngineStatuses,
}) => {
  const activeProject = useProjectStore((state) => state.activeProject);
  const updateProjectSettings = useProjectStore((state) => state.updateProjectSettings);

  const [fetchedEngineStatuses, setFetchedEngineStatuses] = useState<Record<string, { available: boolean; reason?: string }>>({});
  const [healthReport, setHealthReport] = useState<any>(null);
  const [hardwareReport, setHardwareReport] = useState<any>(null);
  const [isOptimizing, setIsOptimizing] = useState(false);

  const handleAutoOptimize = async () => {
    setIsOptimizing(true);
    try {
      const res = await apiFetch('/api/diagnostics/auto-optimize', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.hardware_report) {
          setHardwareReport(data.hardware_report);
        }
        alert(`⚡ ${data.message || 'Auto-Optimize Successful!'}`);
      }
    } catch (err) {
      console.error('Auto-Optimize error:', err);
      alert('เกิดข้อผิดพลาดในการ Auto-Optimize');
    } finally {
      setIsOptimizing(false);
    }
  };
  const [isAuditingEngine, setIsAuditingEngine] = useState(false);
  const [quotaStatus, setQuotaStatus] = useState<any>(null);
  const [checkingQuota, setCheckingQuota] = useState(false);

  const fetchQuotaStatus = () => {
    apiFetch('/api/system/ai-quota-status')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setQuotaStatus(data);
      })
      .catch(() => {});
  };

  const handleCheckQuota = async () => {
    setCheckingQuota(true);
    try {
      const res = await apiFetch('/api/system/ai-quota-status/check', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setQuotaStatus(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setCheckingQuota(false);
    }
  };

  const handleAgyLogin = async () => {
    try {
      await apiFetch('/api/system/agy-login', { method: 'POST' });
    } catch (err) {
      console.error(err);
    }
  };

  const runEngineHealthAudit = async () => {
    setIsAuditingEngine(true);
    try {
      const [healthRes, hwRes] = await Promise.all([
        apiFetch('/api/diagnostics/health'),
        apiFetch('/api/diagnostics/hardware'),
      ]);
      const healthData = healthRes.ok ? await healthRes.json() : null;
      const hwData = hwRes.ok ? await hwRes.json() : null;
      setHealthReport(healthData);
      setHardwareReport(hwData);
    } catch (err) {
      console.error('Engine diagnostic audit error:', err);
    } finally {
      setIsAuditingEngine(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      runEngineHealthAudit();
      fetchQuotaStatus();
      apiFetch('/api/pipeline/ocr/engines')
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && Array.isArray(data.engines)) {
            const map: Record<string, { available: boolean; reason?: string }> = {};
            data.engines.forEach((eng: any) => {
              map[eng.id] = {
                available: eng.status === 'available' || eng.available === true,
                reason: eng.reason || undefined,
              };
            });
            if (map.paddleocr) map.paddle_ocr = map.paddleocr;
            setFetchedEngineStatuses(map);
          }
        })
        .catch(() => {});
    }
  }, [isOpen]);

  const getEngineStatus = (engineId: string): { available: boolean; reason?: string } => {
    const merged = { ...fetchedEngineStatuses, ...(ocrEngineStatuses || {}) };
    const status = merged[engineId];
    if (typeof status === 'boolean') {
      return { available: status, reason: status ? undefined : 'Engine currently unavailable' };
    }
    if (status && typeof status === 'object') {
      return { available: status.available ?? true, reason: status.reason };
    }
    return { available: true };
  };

  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('ai_detection');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>('bubble');

  const [localStylePresets, setLocalStylePresets] = useState<Record<string, TextTemplate>>(() =>
    externalStylePresets || DEFAULT_TEXT_TEMPLATES
  );
  const [templateDirty, setTemplateDirty] = useState(false);

  if (!isOpen) return null;

  const settings = activeProject?.settings || {};
  const currentGpuProvider = settings.execution_provider || settings.gpu_execution_provider || 'CUDA';
  const currentEngine = settings.ocr_engine || settings.ocr_model || 'glm';

  const currentEngineStatus = getEngineStatus(currentEngine);
  const currentInpaintEngine =
    settings.inpaint_engine ||
    settings.active_inpaint_engine ||
    (settings.default_image_inpaint_method === 'Telea' ? 'telea' : 'lama_onnx');
  const currentInpaintStrategy = settings.inpaint_strategy || 'region';
  const currentBatchSize = settings.batch_size ?? 1;
  const currentProfile = settings.performance_profile || 'balanced';
  const customWidth = settings.performance_custom?.preview_width || 1200;
  const autoOcr = settings.auto_ocr ?? true;
  const autoInpaint = settings.auto_inpaint ?? true;
  const autoTranslate = settings.auto_translate ?? false;
  const globalMinFontSize = settings.min_font_size ?? 12;
  const globalMaxFontSize = settings.max_font_size ?? 150;
  const inpaintContextPadding = settings.inpaint_context_padding ?? 96;
  const maskDilationKernel = settings.mask_dilation_kernel ?? 3;
  const maskMagneticLineFill = settings.mask_magnetic_line_fill ?? false;
  const maskGenMethod = settings.mask_gen_method || settings.default_mask_gen_method || 'hybrid';

  const handleUpdateSetting = (updates: Record<string, any>) => {
    Object.entries(updates).forEach(([k, v]) => {
      try {
        localStorage.setItem(`houmi_${k}`, typeof v === 'object' ? JSON.stringify(v) : String(v));
      } catch {}
    });
    if (activeProject) {
      updateProjectSettings(activeProject.id, {
        ...settings,
        ...updates,
      });
    }
  };

  const currentPresets = externalStylePresets || localStylePresets;
  const selectedTemplate = currentPresets[selectedTemplateKey] || Object.values(currentPresets)[0];
  const selectedTemplateFont = selectedTemplate?.font_stack?.[0] || 'FC Sukhumvit';

  const updateTemplateDraft = (patch: Partial<TextTemplate>) => {
    const updated = {
      ...currentPresets,
      [selectedTemplateKey]: {
        ...selectedTemplate,
        ...patch,
      },
    };
    setLocalStylePresets(updated);
    setTemplateDirty(true);
  };

  const handleDeleteTemplate = (keyToDelete: string) => {
    const updated = { ...currentPresets };
    delete updated[keyToDelete];
    setLocalStylePresets(updated);
    setTemplateDirty(true);
    if (onSaveTemplates) {
      onSaveTemplates(updated);
    }
    const remainingKeys = Object.keys(updated);
    if (remainingKeys.length > 0) {
      setSelectedTemplateKey(remainingKeys[0]);
    }
  };

  const handleSaveTemplates = () => {
    if (onSaveTemplates) {
      onSaveTemplates(localStylePresets);
    }
    setTemplateDirty(false);
  };

  const isVisible = (cat: SettingsCategory, title: string) => {
    if (searchQuery.trim()) {
      return title.toLowerCase().includes(searchQuery.toLowerCase());
    }
    return activeCategory === cat;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-sans text-slate-200">
      <div className="w-full max-w-5xl h-[88vh] bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950/80">
          <div className="flex items-center gap-2">
            <span className="text-base">⚙️</span>
            <h3 className="text-sm font-bold text-yellow-400 uppercase tracking-wider font-pixel">
              Global Settings {activeProject ? `(${activeProject.name})` : ''}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xs font-bold border border-zinc-800 px-3 py-1 rounded bg-zinc-900 transition-colors"
          >
            Done (✕)
          </button>
        </div>

        {/* Body Split */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Category Sidebar */}
          <div className="w-56 border-r border-zinc-800 bg-zinc-950/60 p-3 space-y-1 select-none shrink-0 overflow-y-auto">
            <div className="relative mb-3">
              <input
                type="text"
                placeholder="Search settings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-7 pr-3 py-1.5 text-[11px] rounded bg-zinc-900 border border-zinc-800 text-white focus:outline-none focus:border-yellow-500"
              />
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-[10px]">🔍</span>
            </div>

            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block px-2 mb-1">Categories</span>

            {[
              { id: 'ai_detection', icon: '🧠', label: 'AI Detection & Scan' },
              { id: 'engine_health', icon: '🩺', label: 'Engine Health & Audit' },
              { id: 'typography', icon: '📝', label: 'Typography & Style' },
              { id: 'templates', icon: '🎨', label: 'Role / Font Templates' },
              { id: 'pipeline', icon: '🧼', label: 'Cleanup Pipeline' },
              { id: 'performance', icon: '⚡', label: 'Performance & Hardware' },
              { id: 'workspace_dirs', icon: '📂', label: 'Directories' },
              { id: 'keyboard_shortcuts', icon: '⌨️', label: 'Keyboard Shortcuts' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setSearchQuery('');
                  setActiveCategory(item.id as SettingsCategory);
                }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-left rounded text-[11px] font-medium transition-colors ${
                  activeCategory === item.id && !searchQuery
                    ? 'bg-yellow-500/15 text-yellow-300 border border-yellow-500/30 font-bold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900'
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          {/* Right Main Content Form */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs bg-zinc-950/30">
            {/* Category 1: AI Detection & Scan */}
            {isVisible('ai_detection', 'AI Detection Balloon Scan YOLO OCR Engine Models') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] border-b border-zinc-800 pb-2">
                  🧠 AI Detection & Scan Options
                </h4>

                <div className="space-y-3">
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">GPU Execution Provider</label>
                    <select
                      value={currentGpuProvider}
                      onChange={(e) => handleUpdateSetting({ gpu_execution_provider: e.target.value, execution_provider: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500"
                      aria-label="GPU Execution Provider"
                    >
                      <option value="CUDA">CUDA (NVIDIA High Performance)</option>
                      <option value="DirectML">DirectML (Windows DirectX/AMD/Intel)</option>
                      <option value="CPU">CPU Fallback</option>
                    </select>
                  </div>

                  {/* Smart Balloon V15 Engine Control Card */}
                  <div className="p-3.5 rounded-lg bg-gradient-to-b from-amber-500/15 to-amber-950/20 border border-amber-500/40 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-base">🎈</span>
                          <label className="text-amber-200 font-bold text-sm tracking-wide">
                            Smart Balloon V15 (Adaptive 4-Archetype Engine)
                          </label>
                          <span className={`px-2 py-0.2 rounded text-[9.5px] font-pixel font-bold border ${
                            Boolean(settings.enable_smart_balloon)
                              ? 'bg-amber-400/20 text-amber-300 border-amber-400/30'
                              : 'bg-zinc-800 text-zinc-500 border-zinc-700'
                          }`}>
                            {Boolean(settings.enable_smart_balloon) ? 'ACTIVE' : 'OFF'}
                          </span>
                        </div>
                        <p className="text-xs text-amber-300/80">
                          สกัดขอบบอลลูนดิบ 100% คงลวดลายขนฟู/มุมแหลมคม และแยกบอลลูนติดกันด้วย Dynamic Waist Healing
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={Boolean(settings.enable_smart_balloon)}
                        className="w-5 h-5 accent-yellow-500 rounded cursor-pointer"
                        onChange={(e) => {
                          const val = e.target.checked;
                          handleUpdateSetting({ enable_smart_balloon: val });
                          try {
                            localStorage.setItem('houmi_g_enable_smart_balloon', JSON.stringify(val));
                            localStorage.setItem('houmi_setting_enable_smart_balloon', JSON.stringify(val));
                          } catch {}
                        }}
                        aria-label="Smart Balloon V15 Auto-Resize"
                      />
                    </div>

                    {Boolean(settings.enable_smart_balloon) && (
                      <div className="space-y-2.5 pt-2.5 border-t border-amber-500/20">
                        {/* Inset Margin Slider */}
                        <div className="flex items-center justify-between gap-3 text-[11px]">
                          <div>
                            <span className="font-semibold text-slate-200">📐 Safe Text Inset Margin:</span>
                            <span className="ml-1.5 font-mono font-bold text-amber-300">
                              {Math.round(((settings.smart_balloon_inset_ratio as number) ?? 0.10) * 100)}%
                            </span>
                            <span className="text-[10px] text-slate-400 block">
                              ระยะปลอดภัยเว้นขอบเข้าหาจุดกึ่งกลาง ไม่ให้ตัวอักษรชนขอบเส้นหมึกดำ
                            </span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className="text-[10px] text-slate-500 font-mono">5%</span>
                            <input
                              type="range"
                              min="5"
                              max="25"
                              step="1"
                              value={Math.round(((settings.smart_balloon_inset_ratio as number) ?? 0.10) * 100)}
                              onChange={(e) =>
                                handleUpdateSetting({ smart_balloon_inset_ratio: Number(e.target.value) / 100 })
                              }
                              className="w-28 accent-yellow-500 cursor-pointer"
                              aria-label="Safe Text Inset Margin"
                            />
                            <span className="text-[10px] text-slate-500 font-mono">25%</span>
                          </div>
                        </div>

                        {/* Supported Archetype Badges */}
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          <span className="text-[10px] text-slate-400 font-semibold mr-1">โหมดรองรับ:</span>
                          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                            🟣 Spiky/Fuzzy (ขนฟู)
                          </span>
                          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                            🟢 Angular (มุมแหลม)
                          </span>
                          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                            🟦 Rectangular (กล่องสี่เหลี่ยม)
                          </span>
                          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            🟠 Smooth Oval (วงรีมาตรฐาน)
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-zinc-800/80">
                    <div>
                      <label className="block text-slate-200 font-semibold text-sm">🧭 Contour-aware Typesetting (ทดลอง)</label>
                      <p className="text-xs text-slate-400">
                        ใช้ mask จริงคุมความกว้างแต่ละบรรทัด; ถ้า mask ไม่พร้อมจะกลับไปใช้การคำนวณเดิม
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={Boolean(settings.enable_contour_layout ?? false)}
                      onChange={(e) => handleUpdateSetting({ enable_contour_layout: e.target.checked })}
                      className="w-4 h-4 accent-cyan-500 rounded cursor-pointer"
                      aria-label="Contour-aware Typesetting"
                    />
                  </div>


                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Active OCR Model</label>
                    <select
                      value={currentEngine}
                      onChange={(e) => handleUpdateSetting({ ocr_model: e.target.value, ocr_engine: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500"
                      aria-label="Active OCR Model"
                    >
                      <optgroup label="⚡ Local ONNX Hardware Acceleration (DirectML / CUDA GPU)">
                        {[
                          { id: 'rapidocr', label: '⚡ RapidOCR (PP-OCRv6 Multilingual 18.7k SOTA 🌟)' },
                          { id: 'ppocrv5', label: '⚡ RapidOCR (PP-OCRv5 Chinese/Korean/English/Thai)' },
                        ].map((eng) => {
                          const st = getEngineStatus(eng.id) ?? getEngineStatus('ppocrv5') ?? getEngineStatus('paddleocr') ?? { available: true };
                          return (
                            <option key={eng.id} value={eng.id} disabled={!st.available} title={st.reason || eng.label}>
                              {eng.label}{!st.available ? ` (${st.reason || 'Disabled'})` : ''}
                            </option>
                          );
                        })}
                      </optgroup>
                      <optgroup label="AI Cloud & PyTorch VLM Services">
                        {[
                          { id: 'gemini', label: '✨ DOBKLE OCR (Gemini 3.6 Flash)' },
                          { id: 'glm', label: '🧠 GLM-OCR (PyTorch VLM Server)' },
                          { id: 'deepseek', label: '🐋 DeepSeek-OCR (PyTorch VLM Server)' },
                        ].map((eng) => {
                          const st = getEngineStatus(eng.id);
                          return (
                            <option key={eng.id} value={eng.id} disabled={!st.available} title={st.reason || eng.label}>
                              {eng.label}{!st.available ? ` (${st.reason || 'Disabled'})` : ''}
                            </option>
                          );
                        })}
                      </optgroup>
                    </select>
                    {!currentEngineStatus.available && (
                      <div className="mt-1.5 text-[10px] text-amber-400 flex items-center gap-1 font-sans" title={currentEngineStatus.reason}>
                        ⚠️ <span>Selected OCR engine is currently unavailable ({currentEngineStatus.reason || 'Offline / Key Missing'}).</span>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Batch Size</label>
                    <select
                      value={currentBatchSize}
                      onChange={(e) => handleUpdateSetting({ batch_size: Number(e.target.value) })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500"
                      aria-label="Batch Size"
                    >
                      <option value={1}>1 page per batch</option>
                      <option value={2}>2 pages per batch</option>
                      <option value={4}>4 pages per batch</option>
                      <option value={8}>8 pages per batch</option>
                    </select>
                  </div>

                  {/* AGY CLI Auth & Quota Cooldown Card */}
                  <div className="col-span-2 mt-2 p-3.5 bg-zinc-900/90 rounded-lg border border-zinc-800 space-y-3">
                    <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-base">✨</span>
                        <div>
                          <h5 className="font-bold text-yellow-400 text-xs font-pixel uppercase tracking-wider">
                            AGY / Gemini AI CLI Status & Auth
                          </h5>
                          <p className="text-[10px] text-slate-400">
                            จัดการการเชื่อมต่อบัญชี AGY CLI และตรวจสอบโควต้า / คูลดาวน์การใช้งาน AI
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleAgyLogin}
                          className="px-2.5 py-1 text-[10px] font-bold rounded bg-yellow-500 hover:bg-yellow-400 text-black transition-colors flex items-center gap-1 cursor-pointer"
                          title="เปิดหน้าต่าง Terminal เพื่อเข้าสู่ระบบบัญชี AGY CLI"
                        >
                          🔑 Login AGY CLI
                        </button>
                        <button
                          type="button"
                          onClick={handleCheckQuota}
                          disabled={checkingQuota}
                          className="px-2.5 py-1 text-[10px] font-bold rounded bg-zinc-800 hover:bg-zinc-700 text-slate-200 border border-zinc-700 transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
                          title="ตรวจสอบสถานะโควต้าและคูลดาวน์ปัจจุบัน"
                        >
                          {checkingQuota ? '⌛ Checking...' : '🔍 Check Quota & Cooldown'}
                        </button>
                      </div>
                    </div>

                    {quotaStatus && (
                      <div className="space-y-1.5 text-[11px] font-sans">
                        {quotaStatus.quota_exceeded ? (
                          <div className="p-2.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 space-y-1">
                            <div className="flex items-center gap-1.5 font-bold text-rose-400">
                              <span>⚠️</span>
                              <span>Individual Quota Limit Reached (โควต้า AI ชั่วคราวเต็มแล้ว)</span>
                            </div>
                            <div className="text-[10px] text-slate-300 pl-5">
                              {quotaStatus.reason || 'Individual quota reached. Please wait for reset or upgrade.'}
                            </div>
                            {quotaStatus.cooldown_reset && (
                              <div className="text-[10px] font-mono text-yellow-400 font-bold pl-5">
                                ⏳ Reset Cooldown: Resets in {quotaStatus.cooldown_reset}
                              </div>
                            )}
                            <div className="text-[9px] text-slate-400 pl-5 pt-0.5">
                              ⚡ ระบบได้สลับไปใช้ local ONNX (PP-OCRv5) สำหรับการอ่านอักษรให้อัตโนมัติ เพื่อให้งานไม่สะดุด
                            </div>
                          </div>
                        ) : (
                          <div className="p-2.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span>🟢</span>
                              <span className="font-bold">AGY / Gemini AI CLI Active & Ready</span>
                            </div>
                            <span className="text-[10px] text-slate-400">
                              {quotaStatus.last_checked_at ? `Checked ${new Date(quotaStatus.last_checked_at * 1000).toLocaleTimeString()}` : 'Ready'}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Category: Engine Health & Diagnostics */}
            {isVisible('engine_health', 'Engine Health Diagnostics Check Status Models Error Missing Audit') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <span>🩺</span> System Engine Health & File Audit
                  </h4>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        apiFetch('/api/diagnostics/crashes/latest')
                          .then((res) => res.json())
                          .then((data) => {
                            const text = data.content || JSON.stringify(data, null, 2);
                            alert(`🚨 HOUMI CRASH REPORT LOG:\n\n${text.slice(0, 1500)}`);
                          })
                          .catch(() => alert('No crash logs recorded yet. System running smoothly!'));
                      }}
                      className="px-2.5 py-1 text-[10px] font-bold rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition-colors"
                      title="View recorded crash logs and stack traces"
                    >
                      🚨 Crash Logs
                    </button>
                    <button
                      type="button"
                      onClick={() => apiFetch('/api/diagnostics/show-console')}
                      className="px-2.5 py-1 text-[10px] font-bold rounded bg-zinc-800 hover:bg-zinc-700 text-slate-300 border border-zinc-700 transition-colors"
                      title="Allocates CMD console window for live python backend logs"
                    >
                      💻 Live CMD Console
                    </button>
                    <button
                      type="button"
                      onClick={runEngineHealthAudit}
                      disabled={isAuditingEngine}
                      className="px-3 py-1 text-[11px] font-bold rounded bg-yellow-500 hover:bg-yellow-400 text-zinc-950 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {isAuditingEngine ? '⌛ Auditing...' : '🔍 Check All Engines'}
                    </button>
                  </div>
                </div>

                {hardwareReport && (
                  <div className="space-y-3 p-3.5 rounded-lg bg-zinc-900 border border-zinc-800 text-[11px]">
                    {/* Hardware Specs Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-300 font-sans">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-mono">CPU:</span>
                        <span className="font-semibold text-slate-200">{hardwareReport.cpu_name || 'Detecting...'}</span>
                        <span className="text-[10px] text-amber-400 font-mono">({hardwareReport.cpu_cores} Cores)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-mono">RAM:</span>
                        <span className="font-semibold text-slate-200">{hardwareReport.ram_total_gb} GB</span>
                        <span className="text-[10px] text-slate-400 font-mono">(Avail: {hardwareReport.ram_available_gb} GB)</span>
                      </div>
                      <div className="flex items-center gap-1.5 sm:col-span-2">
                        <span className="text-slate-500 font-mono">GPU:</span>
                        <span className="font-semibold text-amber-300">{hardwareReport.gpu_name || 'No dedicated GPU detected'}</span>
                        {hardwareReport.gpu_vram_gb && (
                          <span className="text-[10px] text-amber-400 font-mono">({hardwareReport.gpu_vram_gb} GB VRAM)</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 sm:col-span-2 pt-1 border-t border-zinc-800/80">
                        <span className="text-slate-500 font-mono">Active Provider:</span>
                        <span className="font-bold text-yellow-400">{hardwareReport.acceleration_type}</span>
                      </div>
                    </div>

                    {/* Status & Auto-Optimize Action */}
                    <div className="p-2.5 rounded bg-zinc-950 border border-zinc-850 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 text-[11px]">
                          {hardwareReport.is_optimized ? (
                            <span className="text-emerald-400 font-bold flex items-center gap-1">
                              ✅ Hardware Optimized ({hardwareReport.optimal_provider} Active, {hardwareReport.optimal_thread_count} Threads)
                            </span>
                          ) : (
                            <span className="text-amber-400 font-bold flex items-center gap-1">
                              ⚠️ ตรวจพบว่าระบบยังไม่ได้ปรับแต่งค่าสำหรับ GPU ({hardwareReport.optimal_provider} Ready)
                            </span>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={handleAutoOptimize}
                          disabled={isOptimizing}
                          className="shrink-0 px-3 py-1.5 rounded font-bold text-[11px] bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-zinc-950 shadow-md shadow-amber-500/10 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                        >
                          {isOptimizing ? '⚡กำลังปรับแต่ง...' : '⚡ Auto-Optimize (1-Click)'}
                        </button>
                      </div>
                      <div className="text-[10px] text-slate-400">{hardwareReport.notice}</div>
                    </div>

                    {/* Optimization Suggestions & Driver Downloads */}
                    {hardwareReport.optimization_suggestions && hardwareReport.optimization_suggestions.length > 0 && (
                      <div className="space-y-2 pt-2 border-t border-zinc-800">
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-pixel flex items-center gap-1.5">
                          <span>💡</span> Driver & Performance Recommendations
                        </div>
                        {hardwareReport.optimization_suggestions.map((sugg: any, idx: number) => (
                          <div key={idx} className="p-2.5 rounded bg-zinc-950 border border-zinc-850 flex items-center justify-between text-[11px] gap-2">
                            <div className="space-y-0.5">
                              <div className="font-bold text-slate-200 flex items-center gap-1.5">
                                <span>{sugg.priority === 'high' ? '🚨' : '🟢'}</span>
                                {sugg.title}
                              </div>
                              <div className="text-[10px] text-slate-400">{sugg.description}</div>
                            </div>
                            {sugg.action_url && (
                              <a
                                href={sugg.action_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="shrink-0 px-2.5 py-1 text-[10px] font-bold rounded bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition-colors flex items-center gap-1"
                              >
                                {sugg.action_label || 'ดาวน์โหลด'} ↗
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* 1. Manga UNet++ Mask Engine */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">1. Manga UNet++ Mask Engine</span>
                      {healthReport?.manga_unet_mask?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">🟢 HEALTHY</span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">🔴 MISSING / ERROR</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">{healthReport?.manga_unet_mask?.message || 'Manga UNet++ ONNX text mask segmentation model'}</div>
                  </div>

                  {/* 2. GPU Inpaint Server Status */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">2. GPU Inpaint Server</span>
                      {healthReport?.checks?.inpaint?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          🟢 {healthReport?.checks?.inpaint?.server_type === 'custom_gpu' ? 'CUSTOM GPU' : 'LOCAL GPU'} ({healthReport?.checks?.inpaint?.latency_ms}ms)
                        </span>
                      ) : healthReport?.checks?.inpaint?.status === 'fallback' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
                          ⚠️ ONNX FALLBACK
                        </span>
                      ) : healthReport?.checks?.inpaint?.status === 'degraded' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-orange-500/20 text-orange-400 border border-orange-500/30">
                          🔶 TELEA ONLY
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">🔴 ERROR</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {healthReport?.checks?.inpaint?.message || 'GPU Inpainting Server (PyTorch CUDA / ONNX DirectML)'}
                    </div>
                    {healthReport?.checks?.inpaint?.server_type && (
                      <div className="text-[9px] text-slate-500 italic">
                        Mode: {healthReport?.checks?.inpaint?.server_type}
                      </div>
                    )}
                  </div>

                  {/* 3. YOLO Balloon Detector */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">3. YOLO Balloon Detector</span>
                      {healthReport?.checks?.yolo?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          🟢 HEALTHY ({healthReport?.checks?.yolo?.latency_ms}ms)
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">🔴 MISSING</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">{healthReport?.checks?.yolo?.message || 'YOLOv8 Speech Balloon Detector Model'}</div>
                  </div>

                  {/* 4. OCR Subprocess Engine */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">4. Managed OCR Subprocess</span>
                      {healthReport?.checks?.ocr?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">🟢 ACTIVE</span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">🔴 UNRESPONSIVE</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">{healthReport?.checks?.ocr?.message || 'PaddleOCR / PyTorch Managed Subprocess Service'}</div>
                  </div>

                  {/* 5. PSD CLI Tool */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">5. PSD CLI Export Tool</span>
                      {healthReport?.checks?.psd?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">🟢 READY</span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">⚠️ MISSING</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">{healthReport?.checks?.psd?.message || 'Photoshop PSD Export Engine Tool'}</div>
                  </div>

                  {/* 6. SQLite Database */}
                  <div className="p-3 rounded bg-zinc-900/90 border border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">6. SQLite Database</span>
                      {healthReport?.checks?.database?.status === 'ok' ? (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          🟢 CONNECTED ({healthReport?.checks?.database?.latency_ms}ms)
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">🔴 ERROR</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">{healthReport?.checks?.database?.message || 'Database WAL Journal & Schema State'}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Category 2: Typography & Style */}
            {isVisible('typography', 'Typography Style Min Max Font Size Line Height Letter Spacing Default Template') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] border-b border-zinc-800 pb-2">
                  📝 Typography & Global Fallback Settings
                </h4>

                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-slate-400 font-semibold mb-1">Default Import Template</label>
                    <select
                      value={settings.default_text_template_id || 'bubble'}
                      onChange={(e) => handleUpdateSetting({ default_text_template_id: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500"
                    >
                      {Object.entries(currentPresets).map(([key, template]) => (
                        <option key={key} value={key}>
                          {template.name} · {template.font_stack[0]} ({template.font_size}px)
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">
                      Global Fallback Min Font Size (px)
                    </label>
                    <input
                      type="number"
                      min="6"
                      max="100"
                      value={globalMinFontSize}
                      onChange={(e) => handleUpdateSetting({ min_font_size: Number(e.target.value) || 12 })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500 font-mono"
                    />
                    <span className="text-[10px] text-slate-500 block mt-1">
                      Fallback lower limit when auto-resizing text inside balloons.
                    </span>
                  </div>

                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">
                      Global Fallback Max Font Size (px)
                    </label>
                    <input
                      type="number"
                      min="20"
                      max="300"
                      value={globalMaxFontSize}
                      onChange={(e) => handleUpdateSetting({ max_font_size: Number(e.target.value) || 150 })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500 font-mono"
                    />
                    <span className="text-[10px] text-slate-500 block mt-1">
                      Fallback upper limit when auto-resizing text inside balloons.
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Category 3: Font Templates */}
            {isVisible('templates', 'Role Font Templates Preset Styles Color Stroke Glow Shadow') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px]">
                    🎨 Role / Font Templates Manager
                  </h4>
                  {templateDirty && (
                    <button
                      type="button"
                      onClick={handleSaveTemplates}
                      className="px-3 py-1 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded text-xs transition-colors"
                    >
                      Save Templates
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-[200px_1fr] gap-4">
                  {/* Template List */}
                  <div className="space-y-1 max-h-[300px] overflow-y-auto pr-1">
                    {Object.entries(currentPresets).map(([key, template]) => (
                      <div key={key} className="group relative flex items-center">
                        <button
                          type="button"
                          onClick={() => setSelectedTemplateKey(key)}
                          className={`w-full text-left p-2 rounded border transition-colors pr-7 ${
                            selectedTemplateKey === key
                              ? 'border-yellow-500 bg-yellow-500/10 text-yellow-300 font-bold'
                              : 'border-zinc-800 bg-zinc-900 text-slate-300 hover:border-zinc-700'
                          }`}
                        >
                          <div className="text-xs truncate">{template.name}</div>
                          <div className="text-[9px] text-slate-500 truncate">
                            {template.font_stack[0]} · {template.font_size}px
                          </div>
                        </button>
                        <button
                          type="button"
                          title={`ลบถาวร ${template.name}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`คุณแน่ใจหรือไม่ว่าต้องการลบ Template "${template.name}" นี้ถาวร?`)) {
                              handleDeleteTemplate(key);
                            }
                          }}
                          className="absolute right-1 text-[10px] p-1 text-red-400 hover:text-red-300 hover:bg-red-950/60 rounded transition-opacity"
                        >
                          🗑️
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Template Editor */}
                  {selectedTemplate && (
                    <div className="space-y-3 bg-zinc-950 p-3 rounded border border-zinc-800">
                      <div className="flex items-center justify-between pb-2 border-b border-zinc-850">
                        <span className="text-xs font-bold text-slate-200">แก้ไขสไตล์: {selectedTemplate.name}</span>
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`ลบ Template "${selectedTemplate.name}" ถาวร?`)) {
                              handleDeleteTemplate(selectedTemplateKey);
                            }
                          }}
                          className="px-2.5 py-1 bg-red-900/60 hover:bg-red-800 border border-red-700/50 text-red-200 font-bold rounded text-[10px] transition-colors flex items-center gap-1"
                        >
                          <span>🗑️</span> ลบ Template นี้ถาวร
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-1">Template Name</label>
                          <input
                            type="text"
                            value={selectedTemplate.name}
                            onChange={(e) => updateTemplateDraft({ name: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-1">Font Stack</label>
                          <input
                            type="text"
                            value={selectedTemplateFont}
                            onChange={(e) => updateTemplateDraft({ font_stack: [e.target.value] })}
                            className="w-full bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                          />
                        </div>
                        <div className="col-span-2 flex items-center justify-between rounded border border-yellow-500/20 bg-yellow-500/[0.04] p-2 mb-1">
                          <div>
                            <span className="block text-[11px] font-bold text-yellow-400">✨ Auto Size Font (ขยาย/ย่อฟอนต์ตามกล่อง)</span>
                            <span className="block text-[9px] text-slate-400">เมื่อเปิดใช้งาน ระบบจะคำนวณปรับขนาดฟอนต์ให้พอดีกับกล่องข้อความอัตโนมัติ (ปิดการตั้งค่าขนาดตายตัว)</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={Boolean(selectedTemplate.auto_font_size || selectedTemplate.font_size === 0)}
                            onChange={(e) => {
                              const isAuto = e.target.checked;
                              updateTemplateDraft({
                                auto_font_size: isAuto,
                                font_size: isAuto ? 0 : (selectedTemplate.font_size || 52),
                              });
                            }}
                            className="h-3.5 w-3.5 accent-yellow-500 cursor-pointer"
                          />
                        </div>

                        {Boolean(selectedTemplate.auto_font_size || selectedTemplate.font_size === 0) ? (
                          <div className="col-span-2 p-2.5 bg-yellow-500/10 border border-yellow-500/30 rounded text-xs font-semibold text-yellow-400">
                            ⚡ Auto Sizing Enabled — Fixed font size options are locked (System dynamically calculates text scaling inside block bounds).
                          </div>
                        ) : (
                          <>
                            <div>
                              <label className="block text-[10px] text-slate-400 mb-1">Default Size (px)</label>
                              <input
                                type="number"
                                value={selectedTemplate.font_size}
                                onChange={(e) => updateTemplateDraft({ font_size: Number(e.target.value) })}
                                className="w-full bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[10px] text-slate-400 mb-1">Template Min / Max Size</label>
                              <div className="flex gap-1">
                                <input
                                  type="number"
                                  placeholder="Min"
                                  value={selectedTemplate.min_font_size}
                                  onChange={(e) => updateTemplateDraft({ min_font_size: Number(e.target.value) })}
                                  className="w-1/2 bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                                />
                                <input
                                  type="number"
                                  placeholder="Max"
                                  value={selectedTemplate.max_font_size}
                                  onChange={(e) => updateTemplateDraft({ max_font_size: Number(e.target.value) })}
                                  className="w-1/2 bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                                />
                              </div>
                            </div>
                          </>
                        )}
                        <div>
                          <label className="block text-[10px] font-bold text-yellow-400 mb-1">✨ Anti-Alias Mode (การลดรอยหยัก)</label>
                          <select
                            value={selectedTemplate.anti_alias || 'sharp'}
                            onChange={(e) => updateTemplateDraft({ anti_alias: e.target.value as any })}
                            className="w-full bg-zinc-900 border border-zinc-800 rounded p-1.5 text-xs text-white"
                          >
                            <option value="sharp">Sharp (ค่าเริ่มต้น - แหลมคม)</option>
                            <option value="smooth">Smooth (สมูท)</option>
                            <option value="crisp">Crisp (คมชัด)</option>
                            <option value="strong">Strong (เน้นคม)</option>
                            <option value="none">None (Smooth Off)</option>
                          </select>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-zinc-800">
                        <ColorField
                          label="Text Fill Color"
                          value={selectedTemplate.color_hex}
                          onChange={(color) => updateTemplateDraft({ color_hex: color })}
                          compact
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Category 4: Cleanup Pipeline */}
            {isVisible('pipeline', 'Cleanup Pipeline Inpaint Engine Context Padding Telea LaMa Manga Cleaner Mask Engine') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900 font-sans">
                <div className="border-b border-zinc-800 pb-2">
                  <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <span>🧼</span> Cleanup Pipeline & Neural Eraser Settings
                  </h4>
                  <span className="text-[10px] text-slate-400 block mt-0.5">
                    ตั้งค่าโมเดลลบตัวหนังสือ โมเดลสร้าง Mask และการปรับแต่งขอบขนานสำหรับคลีนฉากภาพ
                  </span>
                </div>

                {/* Section 1: Core AI Engine Selection */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Card 1: Default Mask Detection Engine */}
                  <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 space-y-2">
                    <label className="block text-slate-200 font-bold text-xs flex items-center gap-1">
                      <span>🎭</span> Default Mask Engine (โมเดลสร้าง/ตรวจจับ Mask)
                    </label>
                    <select
                      value={maskGenMethod || 'hybrid'}
                      onChange={(e) => {
                        const val = e.target.value;
                        handleUpdateSetting({
                          mask_gen_method: val,
                          default_mask_gen_method: val,
                        });
                      }}
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-yellow-500 font-sans cursor-pointer"
                    >
                      <option value="hybrid">Manga UNet++ (Pixel Neural Mask - แนะนำสำหรับมังงะ/มันฮวา)</option>
                      <option value="sam">Meta SAM 2.1 Segmenter (Segment Anything ONNX - เหมาะกับ SFX)</option>
                      <option value="contour">Adaptive Morphology & Contours (โหมดมังงะขาวดำดั้งเดิม - ไวมาก)</option>
                      <option value="imagetrans">ImageTrans Otsu Binarization (ไบนารีแยกกลุ่มตัวอักษร)</option>
                      <option value="balloon">Full Bounding Box Mask (ล้างเต็มกรอบสี่เหลี่ยม)</option>
                    </select>
                    <span className="text-[10px] text-slate-400 block">
                      อัลกอริทึมตรวจจับและแยกพิกเซลตัวอักษร: Manga UNet++ เทรนด้วยฟอนต์การ์ตูน แม่นยำสูง ไม่กินเส้นขอบบอลลูน
                    </span>
                  </div>

                  {/* Card 2: Default Image Inpainting Model */}
                  <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 space-y-2">
                    <label className="block text-slate-200 font-bold text-xs flex items-center gap-1">
                      <span>🧼</span> Default Inpainter Engine (โมเดล AI ลบข้อความและเติมฉากหลัง)
                    </label>
                    <select
                      value={currentInpaintEngine}
                      onChange={(e) => {
                        const val = e.target.value;
                        const isTelea = val === 'telea' || val === 'Telea';
                        const isMat = val === 'mat_onnx' || val === 'mat';
                        handleUpdateSetting({
                          inpaint_engine: val,
                          active_inpaint_engine: val,
                          default_image_inpaint_method: isTelea ? 'Telea' : (isMat ? 'MAT' : 'LamaInpaint'),
                          force_lama_inpaint: !isTelea,
                        });
                      }}
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-yellow-500 font-sans cursor-pointer"
                    >
                      <option value="lama_manga">LaMa-Manga (FFC-ResNet GPU - แนะนำ SOTA 198MB)</option>
                      <option value="lama_onnx">Big-LaMa Standard (ONNX 208MB)</option>
                      <option value="mat_onnx">MAT Inpainter (Mask-Aware Transformer ONNX)</option>
                      <option value="telea">OpenCV Telea (Fast Interpolation CPU - พรีวิวเร็ว &lt;5ms)</option>
                    </select>
                    <span className="text-[10px] text-slate-400 block">
                      โมเดล AI ลบตัวหนังสือ: LaMa-Manga เทรนด้วย Anime & Manga กว่า 300,000 ภาพ คมชัดทั้งมังงะและเว็บตูนสี
                    </span>

                    {/* Inpaint Strategy Selection */}
                    <div className="pt-3 mt-3 border-t border-zinc-800 space-y-2">
                      <label className="block text-slate-200 font-bold text-xs flex items-center gap-1">
                        <span>⚙️</span> Inpaint Strategy (กลยุทธ์การส่งรูปไปคลีน)
                      </label>
                      <select
                        value={currentInpaintStrategy}
                        onChange={(e) => handleUpdateSetting({ inpaint_strategy: e.target.value })}
                        className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-yellow-500 font-sans cursor-pointer"
                      >
                        <option value="region">🎯 Region-Based (เร็ว - รวมบอลลูนใกล้กัน GPU)</option>
                        <option value="per_block">🔷 Per-Block (เสถียร - ทีละบอลลูน CPU/GPU)</option>
                        <option value="parallel">⚡ Parallel (เร็วมาก - หลายบอลลูนพร้อมกัน GPU)</option>
                      </select>
                      <div className="text-[10px] text-slate-400 space-y-1">
                        <p><strong className="text-cyan-400">Region-Based:</strong> รวม regions ใกล้กันเป็นก้อนเดียว → เร็วสำหรับ GPU</p>
                        <p><strong className="text-green-400">Per-Block:</strong> ส่งทีละ text block แยกกัน → เสถียรสำหรับทุกคน (แนะนำสำหรับ CPU)</p>
                        <p><strong className="text-yellow-400">Parallel:</strong> ส่งหลาย regions พร้อมกัน → เร็วมากสำหรับ GPU multi-core</p>
                      </div>
                    </div>

                    {/* Quick Inpaint Server Folder / Executable Picker */}
                    <div className="pt-2 mt-2 border-t border-zinc-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold text-amber-300 flex items-center gap-1">
                          🖥️ โฟลเดอร์เซิร์ฟเวอร์ Inpaint แยก (Inpaint Server Path)
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="เช่น C:\inpaint_server หรือ ImageTrans\plugins\Lamal"
                          value={settings.inpaint_server_path || ''}
                          onChange={(e) => handleUpdateSetting({ inpaint_server_path: e.target.value })}
                          className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-yellow-500"
                        />
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              const res = await fetch(`/api/utils/browse-folder?default_directory=${encodeURIComponent(settings.inpaint_server_path || '')}`, { method: 'POST' });
                              if (res.ok) {
                                const data = await res.json();
                                if (data.success && data.path) {
                                  handleUpdateSetting({ inpaint_server_path: data.path });
                                  alert(`✅ เลือกโฟลเดอร์เซิร์ฟเวอร์เรียบร้อย:\n${data.path}`);
                                }
                              }
                            } catch {
                              alert('❌ ไม่สามารถเปิดหน้าต่างเลือกโฟลเดอร์ได้');
                            }
                          }}
                          className="px-3 py-1.5 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-300 border border-yellow-500/40 rounded text-xs font-bold transition cursor-pointer flex items-center gap-1 shrink-0"
                        >
                          📁 เลือกโฟลเดอร์...
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Section 2: Fine-Tuning & Mask Expansion Kernel */}
                <div className="p-3 bg-zinc-900/60 rounded border border-zinc-800 space-y-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-slate-300 font-semibold text-xs">🔍 Mask Expansion Dilation (ขยายขอบมาสก์เก็บรอยหมึก)</label>
                      <span className="text-xs font-mono text-yellow-400 font-bold">{maskDilationKernel} px</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="0"
                        max="56"
                        value={maskDilationKernel}
                        onChange={(e) => {
                          const val = Math.max(0, Math.min(56, Number(e.target.value) || 0));
                          handleUpdateSetting({ mask_dilation_kernel: val });
                        }}
                        className="flex-1 accent-yellow-500 cursor-pointer"
                      />
                      <input
                        type="number"
                        min="0"
                        max="56"
                        value={maskDilationKernel}
                        onChange={(e) => {
                          const val = Math.max(0, Math.min(56, Number(e.target.value) || 0));
                          handleUpdateSetting({ mask_dilation_kernel: val });
                        }}
                        className="w-16 bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-slate-200 text-center font-mono focus:outline-none focus:border-yellow-500"
                      />
                    </div>
                    <span className="text-[10px] text-slate-400 block mt-1">
                      ขยายขอบมาสก์ 0 ถึง 56px เพื่อคลุมขอบหมึกฟุ้ง (Anti-aliasing) ของตัวอักษรให้สะอาดหมดจด (แนะนำ 2 - 4px)
                    </span>
                  </div>

                  {/* Magnetic Line Mask Toggle */}
                  <div className="pt-2 border-t border-zinc-800/80">
                    <label className="flex items-center gap-2.5 cursor-pointer text-slate-200 text-xs font-semibold">
                      <input
                        type="checkbox"
                        checked={maskMagneticLineFill}
                        onChange={(e) => handleUpdateSetting({ mask_magnetic_line_fill: e.target.checked })}
                        className="w-4 h-4 rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500 cursor-pointer"
                      />
                      <span className="flex items-center gap-1">
                        <span>🧲</span>
                        <span>Magnetic Line Mask (มาสก์แม่เหล็กเชื่อมเต็มบรรทัด - ไม่แหว่งกลาง)</span>
                      </span>
                    </label>
                    <span className="text-[10px] text-slate-400 block mt-1 pl-6.5">
                      เชื่อมช่องว่างระหว่างคำในแต่ละบรรทัดเข้าด้วยกันเป็นแถบสี่เหลี่ยมต่อเนื่อง ลบตัวหนังสือทั้งแถวเนียนสนิท ไม่แหว่งกลาง และไม่กินขอบบอลลูน
                    </span>
                  </div>

                  <div>
                    <label className="block text-slate-300 font-semibold text-xs mb-1">📐 Inpaint Context Padding (ระยะขอบภาพอ้างอิงรอบข้อความ: px)</label>
                    <input
                      type="number"
                      min="0"
                      max="512"
                      value={inpaintContextPadding}
                      onChange={(e) => handleUpdateSetting({ inpaint_context_padding: Number(e.target.value) || 0 })}
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500 font-mono text-xs"
                    />
                    <span className="text-[10px] text-slate-400 block mt-1">
                      ระยะขอบภาพรอบตัวหนังสือที่ส่งให้ AI ใช้สังเกตทิศทางลายเส้นและโครงสร้างฉากหลังเพื่อวาดต่อ (แนะนำ 96px)
                    </span>
                  </div>
                </div>

                {/* Section 3: Batch Actions & Automation Checkboxes */}
                <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                  <div className="space-y-1.5">
                    <label className="flex items-center gap-2 cursor-pointer text-slate-300 text-xs">
                      <input
                        type="checkbox"
                        checked={autoOcr}
                        onChange={(e) => handleUpdateSetting({ auto_ocr: e.target.checked })}
                        className="rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500"
                      />
                      <span>Auto OCR after balloon detection</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer text-slate-300 text-xs">
                      <input
                        type="checkbox"
                        checked={autoInpaint}
                        onChange={(e) => handleUpdateSetting({ auto_inpaint: e.target.checked })}
                        className="rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500"
                      />
                      <span>Auto Inpaint text background during OCR scan</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer text-slate-300 text-xs">
                      <input
                        type="checkbox"
                        checked={autoTranslate}
                        onChange={(e) => handleUpdateSetting({ auto_translate: e.target.checked })}
                        className="rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500"
                      />
                      <span>Auto Translate text blocks after OCR</span>
                    </label>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      if (activeProject?.id) {
                        apiFetch(`/api/pipeline/inpaint-batch?project_id=${activeProject.id}`, { method: 'POST' })
                          .then(() => alert('🚀 เริ่มต้นลบภาพและสั่งคลีนใหม่ทุกหน้าในโปรเจกต์เรียบร้อยแล้ว!'))
                          .catch((err) => alert(`Failed to trigger re-clean: ${err}`));
                      }
                    }}
                    className="px-4 py-2 text-xs font-bold rounded bg-yellow-500 hover:bg-yellow-400 text-zinc-950 transition-colors shrink-0 flex items-center gap-1.5 shadow-md"
                  >
                    <span>🧹</span> สั่งคลีนรูปภาพใหม่ทั้งหมดทุกหน้า (Re-clean All Pages Now)
                  </button>
                </div>
              </div>
            )}

            {/* Category 5: Performance */}
            {isVisible('performance', 'Performance Profile Preview Width Hardware Workers Auto Optimize GPU CPU Parallel Inpaint') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] border-b border-zinc-800 pb-2">
                  ⚡ Performance & Hardware
                </h4>

                {/* Hardware Auto-Optimize Section */}
                <div className="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 p-4 rounded-lg border border-yellow-500/30 space-y-3">
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">🚀</span>
                    <div className="flex-1 space-y-2">
                      <h5 className="font-bold text-yellow-300 text-xs">Hardware Auto-Optimization</h5>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        Automatically detect your GPU (NVIDIA/AMD/Intel) and CPU cores, then apply optimal settings for Parallel Inpainting, AI Detection, and OCR performance.
                      </p>

                      <button
                        type="button"
                        onClick={handleAutoOptimize}
                        disabled={isOptimizing}
                        className="w-full bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-400 hover:to-orange-400 disabled:from-zinc-700 disabled:to-zinc-600 text-black font-bold py-2.5 px-4 rounded-lg text-xs uppercase tracking-wider transition-all shadow-lg hover:shadow-yellow-500/30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {isOptimizing ? (
                          <>
                            <span className="inline-block w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin"></span>
                            <span>Optimizing...</span>
                          </>
                        ) : (
                          <>
                            <span>⚡</span>
                            <span>Auto-Optimize Hardware</span>
                          </>
                        )}
                      </button>

                      {hardwareReport && (
                        <div className="mt-3 p-3 bg-zinc-900/80 rounded border border-zinc-800 space-y-2 text-[10px]">
                          <div className="flex justify-between">
                            <span className="text-slate-400">Execution Provider:</span>
                            <span className="text-yellow-300 font-bold">{hardwareReport.optimal_provider || hardwareReport.execution_provider || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-400">CPU Cores:</span>
                            <span className="text-white font-mono">{hardwareReport.cpu_cores || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-400">Optimal Threads:</span>
                            <span className="text-white font-mono">{hardwareReport.optimal_thread_count || 'N/A'}</span>
                          </div>
                          {hardwareReport.gpu_name && (
                            <div className="flex justify-between">
                              <span className="text-slate-400">GPU Detected:</span>
                              <span className="text-green-400 font-semibold text-[10px]">{hardwareReport.gpu_name}</span>
                            </div>
                          )}
                          {hardwareReport.acceleration_type && (
                            <div className="flex justify-between">
                              <span className="text-slate-400">Acceleration:</span>
                              <span className="text-cyan-400 font-semibold">{hardwareReport.acceleration_type}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Canvas Performance Profile */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Canvas Performance Profile</label>
                    <select
                      value={currentProfile}
                      onChange={(e) => handleUpdateSetting({ performance_profile: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-yellow-500"
                    >
                      <option value="balanced">Balanced (1200px Preview)</option>
                      <option value="quality">High Quality (1800px Preview)</option>
                      <option value="performance">Fast Performance (800px Preview)</option>
                      <option value="custom">Custom Width</option>
                    </select>
                  </div>

                  {currentProfile === 'custom' && (
                    <div>
                      <label className="block text-slate-400 font-semibold mb-1">
                        Custom Preview Width ({customWidth}px)
                      </label>
                      <input
                        type="range"
                        min="600"
                        max="2400"
                        step="100"
                        value={customWidth}
                        onChange={(e) =>
                          handleUpdateSetting({
                            performance_custom: {
                              ...settings.performance_custom,
                              preview_width: Number(e.target.value),
                            },
                          })
                        }
                        className="w-full accent-yellow-500"
                      />
                    </div>
                  )}
                </div>

                {/* External GPU Inpaint Server Folder / Executable Selection */}
                <div className="p-3.5 bg-gradient-to-br from-zinc-900/90 via-zinc-900/60 to-zinc-900/90 rounded-lg border border-zinc-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="block text-slate-200 font-bold text-xs flex items-center gap-1.5">
                      <span>🖥️</span> โฟลเดอร์เซิร์ฟเวอร์ GPU Inpaint แยกต่างหาก (Inpaint Server Path)
                    </label>
                    <span className="text-[10px] text-amber-400 font-mono bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                      PyTorch CUDA / LaMa Daemon
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    หากคุณมีโฟลเดอร์เซิร์ฟเวอร์ GPU แยก เช่น <code className="text-yellow-300 bg-zinc-950 px-1 py-0.5 rounded">inpaint_server</code> หรือ <code className="text-yellow-300 bg-zinc-950 px-1 py-0.5 rounded">ImageTrans\plugins\Lamal</code> สามารถคลิกปุ่มด้านล่างเพื่อเลือกโฟลเดอร์หรือไฟล์โปรแกรมเซิร์ฟเวอร์ได้ทันที
                  </p>

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="เช่น C:\inpaint_server หรือ C:\Users\...\Desktop\ImageTrans\plugins\Lamal"
                      value={settings.inpaint_server_path || ''}
                      onChange={(e) => handleUpdateSetting({ inpaint_server_path: e.target.value })}
                      className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-yellow-500 shadow-inner"
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await fetch(`/api/utils/browse-folder?default_directory=${encodeURIComponent(settings.inpaint_server_path || '')}`, { method: 'POST' });
                          if (res.ok) {
                            const data = await res.json();
                            if (data.success && data.path) {
                              handleUpdateSetting({ inpaint_server_path: data.path });
                              alert(`✅ เลือกโฟลเดอร์เซิร์ฟเวอร์เรียบร้อย:\n${data.path}`);
                            }
                          }
                        } catch {
                          alert('❌ ไม่สามารถเปิดหน้าต่างเลือกโฟลเดอร์ได้');
                        }
                      }}
                      className="px-3.5 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-300 border border-yellow-500/40 rounded text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shrink-0 shadow"
                    >
                      📁 เลือกโฟลเดอร์...
                    </button>
                  </div>

                  {/* Port and Test connection */}
                  <div className="flex items-center justify-between pt-1.5 border-t border-zinc-800/80">
                    <div className="text-[11px] text-slate-400 flex items-center gap-2">
                      <span className="font-semibold text-slate-300">Custom Port / URL:</span>
                      <input
                        type="text"
                        placeholder="http://127.0.0.1:2328"
                        value={settings.custom_inpaint_url || ''}
                        onChange={(e) => handleUpdateSetting({ custom_inpaint_url: e.target.value })}
                        className="w-44 bg-zinc-950 border border-zinc-700 rounded px-2.5 py-1 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-yellow-500"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await fetch('/api/diagnostics/test-inpaint-server', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              url: settings.custom_inpaint_url || 'http://127.0.0.1:2328/inpaint',
                              server_path: settings.inpaint_server_path || ''
                            })
                          });
                          const data = await res.json();
                          if (data.success || data.status === 'connected' || data.status === 'ok') {
                            alert(`✅ เชื่อมต่อเซิร์ฟเวอร์ GPU สำเร็จ!\n${data.message || 'Ready'}`);
                          } else {
                            alert(`⚠️ ${data.message || 'เซิร์ฟเวอร์ยังไม่พร้อม'}\n(ระบบจะสลับใช้ Built-in ONNX สำรองอัตโนมัติ)`);
                          }
                        } catch (err: any) {
                          alert(`❌ เชื่อมต่อไม่สำเร็จ: ${err.message}`);
                        }
                      }}
                      className="px-3.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-slate-200 rounded text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 shadow"
                    >
                      ⚡ ทดสอบการเชื่อมต่อ & สถานะ
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Category 6: Workspace & Storage Directories */}
            {isVisible('workspace_dirs', 'Directories Workspace Storage Projects Path Local Folder Database') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] border-b border-zinc-800 pb-2">
                  📂 Workspace & Storage Directories
                </h4>

                <div className="space-y-4">
                  {activeProject && (
                    <div className="p-3 bg-zinc-900/80 rounded border border-zinc-800 space-y-1">
                      <span className="text-[10px] text-yellow-400 font-bold uppercase tracking-wider">Active Project Source Folder</span>
                      <div className="font-mono text-slate-200 text-[11px] break-all bg-zinc-950 p-2 rounded border border-zinc-900">
                        {activeProject.settings?.local_folder || 'Managed Internal Project Workspace'}
                      </div>
                    </div>
                  )}

                  <div className="space-y-3">
                    <div>
                      <label className="block text-slate-400 font-semibold mb-1">Local Data & Database Storage Path</label>
                      <input
                        type="text"
                        readOnly
                        value="App Directory / data (SQLite database, cache & project thumbnails)"
                        className="w-full bg-zinc-900/50 border border-zinc-800 rounded px-3 py-2 text-slate-400 font-mono text-[11px] select-all cursor-text"
                      />
                    </div>

                    <div>
                      <label className="block text-slate-400 font-semibold mb-1">Export & Output Directory</label>
                      <input
                        type="text"
                        readOnly
                        value={activeProject ? `data/projects/${activeProject.id}/exports` : 'data/exports'}
                        className="w-full bg-zinc-900/50 border border-zinc-800 rounded px-3 py-2 text-slate-400 font-mono text-[11px] select-all cursor-text"
                      />
                      <span className="text-[10px] text-slate-500 block mt-1">
                        Exported PSD files, high-res clean images, and translation JSON/ZIP manifests are saved here.
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Category 7: Keyboard Shortcuts */}
            {isVisible('keyboard_shortcuts', 'Keyboard Shortcuts Navigation Hotkeys Keys Controls Cheatsheet') && (
              <div className="space-y-4 bg-zinc-900/30 p-4 rounded-lg border border-zinc-900">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-[11px] border-b border-zinc-800 pb-2">
                  ⌨️ Keyboard Shortcuts & Controls
                </h4>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    {
                      category: 'Canvas & Navigation',
                      shortcuts: [
                        { keys: ['Space', 'Drag'], description: 'Pan / Scroll Workspace' },
                        { keys: ['Ctrl', 'Wheel'], description: 'Zoom In / Out' },
                        { keys: ['Double Click'], description: 'Activate Text Editing' },
                        { keys: ['Right Click'], description: 'Quick Block Actions Menu' },
                      ],
                    },
                    {
                      category: 'Block Editing',
                      shortcuts: [
                        { keys: ['Delete'], description: 'Delete Selected Text Block' },
                        { keys: ['Ctrl', 'Z'], description: 'Undo Last Action' },
                        { keys: ['Ctrl', 'Y'], description: 'Redo Action' },
                        { keys: ['Esc'], description: 'Deselect / Close Modals' },
                      ],
                    },
                    {
                      category: 'Pipeline Operations',
                      shortcuts: [
                        { keys: ['Shift', 'D'], description: 'Detect Speech Balloons' },
                        { keys: ['Shift', 'O'], description: 'Run OCR Text Recognition' },
                        { keys: ['Shift', 'I'], description: 'Clean Background (Inpaint)' },
                        { keys: ['Shift', 'T'], description: 'Auto Typeset Selection' },
                      ],
                    },
                    {
                      category: 'Layer & Nudging',
                      shortcuts: [
                        { keys: ['Arrow Keys'], description: 'Nudge Block Position (1px)' },
                        { keys: ['Shift', 'Arrows'], description: 'Nudge Block Position (10px)' },
                        { keys: ['Ctrl', 'A'], description: 'Select All Blocks on Page' },
                      ],
                    },
                  ].map((group) => (
                    <div key={group.category} className="space-y-2 bg-zinc-950/60 p-3 rounded border border-zinc-800/80">
                      <h5 className="text-[11px] font-bold text-yellow-400 border-b border-zinc-800/60 pb-1">
                        {group.category}
                      </h5>
                      <div className="space-y-1.5">
                        {group.shortcuts.map((sc, idx) => (
                          <div key={idx} className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-300">{sc.description}</span>
                            <div className="flex items-center gap-1">
                              {sc.keys.map((k, kIdx) => (
                                <kbd
                                  key={kIdx}
                                  className="px-1.5 py-0.5 text-[9px] font-mono font-semibold text-slate-200 bg-zinc-800 border border-zinc-700/70 rounded shadow-xs"
                                >
                                  {k}
                                </kbd>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
