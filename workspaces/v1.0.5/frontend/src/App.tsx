import { useEffect, useState, useRef } from 'react';
import {
  useProjectStore,
  flushPendingBlockUpdates,
  discardPendingBlockUpdates,
  type CanvasRenderCapture,
  type TextBlock,
} from './stores/projectStore';
import { useShallow } from 'zustand/react/shallow';
import Canvas, { matchBinding } from './components/Canvas';
import { MaskEditorModal } from './components/MaskEditorModal';
import { PipelineControlsPanel } from './components/PipelineControlsPanel';
import { AIProviderSettingsModal, AIProviderSettingsPanel } from './components/AIProviderSettingsModal';
import { TypesettingRulesSettingsPanel } from './components/TypesettingRulesSettingsPanel';
import { ChangelogModal } from './components/ChangelogModal';
import { ConfirmModal } from './components/ConfirmModal';
import { OversizeWarningModal } from './components/OversizeWarningModal';
import { SmartStitchModal } from './components/SmartStitchModal';
import { HOUMI_VERSION, HOUMI_VERSION_LABEL } from './version';
import { ColorField } from './components/ColorField';
import { ExportYoloDatasetModal } from './components/ExportYoloDatasetModal';
import { useWebSocket } from './hooks/useWebSocket';
import { HotkeyModal } from './components/HotkeyModal';
import { ProjectPresetModal } from './components/ProjectPresetModal';
import { CustomWorkflowModal } from './components/CustomWorkflowModal';
import { BatchProgressModal } from './components/BatchProgressModal';
import { DobkleOcrProgressModal, type DobkleProgressData } from './components/DobkleOcrProgressModal';
import { DevMapDashboard } from './components/dev_map/DevMapDashboard';
import {
  CLIENT_PROFILES_STORAGE_KEY,
  ACTIVE_CLIENT_PROFILE_STORAGE_KEY,
  createClientProjectProfile,
  loadClientProjectProfiles,
  serializeClientProjectProfiles,
  clientProfileToProjectSettings,
  exportSingleClientProfileToJson,
  exportClientProfilesToJson,
  importClientProfilesFromJson,
  type ClientProjectProfile,
} from './utils/clientProfiles';
import {
  DEFAULT_TEXT_TEMPLATES,
  buildTemplateReapplicationUpdates,
  normalizeTextTemplates,
  resolveBlockTemplateRole,
  resolveGlobalTextTemplates,
  templateBlockFields,
  type TextTemplate,
  type WorkspaceMode,
} from './utils/textTemplates';
import { apiFetch } from './api/runtime';
import { isAutoFontSizeEnabled } from './utils/fontSizing';
import {
  CURRENT_LAYOUT_ENGINE_VERSION,
  isValidCanonicalSpec,
  runStyleJudge,
  recordTypesettingFeedback,
} from './utils/typesetting';
import {
  resolveDecisionBadge,
  countDecisions,
  filterBlocksByDecision,
  type LayerDecisionFilter,
} from './utils/decisionStatus';
import {
  captureAutoStyleSnapshot,
  snapshotToBulkUpdates,
  type AutoStyleSnapshot,
} from './utils/autoStyleSnapshot';
import { stripSemanticTranslationTags } from './utils/canvasView';
import { 
  FolderOpen, FolderPlus, Folder, FileText, Image as ImageIcon, 
  ChevronRight, ChevronLeft, UploadCloud,
  Sparkles, Cpu, Activity, Clock, Trash2, Paintbrush, RefreshCw, Palette, Type as TypeIcon, Copy,
  ChevronDown, Layers, Sliders, History, Settings, MoreHorizontal, AlignLeft, AlignCenter, AlignRight, X,
  Pipette, Wand2, Minus, Plus, Clipboard, Scissors, ArrowUpDown, Crosshair, Bug
} from 'lucide-react';

import { AboutModal } from './components/AboutModal';
import { UpdateModal } from './components/UpdateModal';
import { UpdateSuccessModal } from './components/UpdateSuccessModal';
import { FontSelector } from './components/FontSelector';
import { isFontAvailable, injectFontStylesheet } from './utils/fontLoader';
import { DebugConsoleDrawer } from './components/DebugConsoleDrawer';
import { useDebugStore } from './stores/debugStore';
import { logAction } from './utils/actionLogger';

interface TrainStatus {
  is_training: boolean;
  epoch_current: number;
  epoch_total: number;
  loss_current: number;
  eta_seconds: number;
  log: string[];
}

interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

interface LayerContextMenuState {
  blockId: string;
  x: number;
  y: number;
}

type PerformanceProfile = 'eco' | 'balanced' | 'performance' | 'custom';
interface PerformanceCustomSettings {
  preview_width: number;
  typesetting_candidates: number;
  ocr_workers: number;
  prefer_gpu: boolean;
}

const PERFORMANCE_PROFILE_INFO: Record<Exclude<PerformanceProfile, 'custom'>, {
  label: string; description: string; preview: string; workers: number;
}> = {
  eco: { label: 'Eco', description: 'ประหยัด RAM และรักษาความลื่นบนเครื่องสเปกต่ำ', preview: '800px', workers: 1 },
  balanced: { label: 'Balanced', description: 'สมดุลระหว่างความลื่นและความเร็ว เหมาะกับเครื่องทั่วไป', preview: '1200px', workers: 2 },
  performance: { label: 'Performance', description: 'ใช้ CPU/GPU และ Preview คุณภาพสูงสำหรับเครื่องแรง', preview: '1800px', workers: 4 },
};

const getStoredSetting = (key: string, defaultValue: any) => {
  try {
    const val = localStorage.getItem(`houmi_g_${key}`);
    if (val !== null) return JSON.parse(val);
  } catch (e) {
    console.error(e);
  }
  return defaultValue;
};

const cloneTextTemplates = (templates: Record<string, TextTemplate>) => (
  normalizeTextTemplates(JSON.parse(JSON.stringify(templates)))
);

const colorWithOpacity = (hex: string, opacity: number) => {
  const normalized = /^#[0-9a-f]{6}$/i.test(hex) ? hex.slice(1) : 'ffffff';
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${Math.max(0, Math.min(1, opacity))})`;
};

const setStoredSetting = (key: string, value: any) => {
  try {
    localStorage.setItem(`houmi_g_${key}`, JSON.stringify(value));
  } catch (e) {
    console.error(e);
  }
};

const getStoredTranslationLayoutLock = () => {
  const policyVersion = Number(getStoredSetting('translation_layout_policy_version', 0));
  if (policyVersion < 2) {
    setStoredSetting('translation_layout_policy_version', 2);
    setStoredSetting('lock_translation_to_detected_box', false);
    return false;
  }
  return Boolean(getStoredSetting('lock_translation_to_detected_box', false));
};

interface BlockTextEditorProps {
  block: TextBlock;
  onBlockChange: (blockId: string, fields: Partial<TextBlock>) => void;
}

const BlockTextEditor: React.FC<BlockTextEditorProps> = ({ block, onBlockChange }) => {
  const [sourceText, setSourceText] = useState(block.source_text);
  const [translation, setTranslation] = useState(() => stripSemanticTranslationTags(block.translation));
  const timerRef = useRef<any>(null);
  
  const sourceTextRef = useRef(sourceText);
  const translationRef = useRef(translation);
  const blockIdRef = useRef(block.id);
  
  // Track latest block prop synchronously during render.
  // This ref is always up-to-date BEFORE any effects or event handlers fire,
  // so blur/unmount handlers can distinguish user edits from external updates (OCR).
  const blockPropRef = useRef(block);
  blockPropRef.current = block;

  // Sync refs with state
  useEffect(() => {
    sourceTextRef.current = sourceText;
  }, [sourceText]);

  useEffect(() => {
    translationRef.current = translation;
  }, [translation]);

  // Sync state when block changes
  useEffect(() => {
    if (blockIdRef.current !== block.id) {
      // Switching to a different block — save old block's local changes first
      if (timerRef.current) clearTimeout(timerRef.current);
      onBlockChange(blockIdRef.current, { 
        source_text: sourceTextRef.current, 
        translation: translationRef.current 
      });

      blockIdRef.current = block.id;
      setSourceText(block.source_text);
      setTranslation(stripSemanticTranslationTags(block.translation));
      sourceTextRef.current = block.source_text;
      translationRef.current = stripSemanticTranslationTags(block.translation);
    } else {
      // Same block — external data changed (e.g. OCR re-run updated source_text)
      // Cancel any pending debounce timer to prevent saving stale text back
      if (timerRef.current) clearTimeout(timerRef.current);
      
      if (block.source_text !== sourceTextRef.current && !document.activeElement?.classList.contains('source-input')) {
        setSourceText(block.source_text);
        sourceTextRef.current = block.source_text;
      }
      if (block.translation !== translationRef.current && !document.activeElement?.classList.contains('translation-input')) {
        const cleanedTranslation = stripSemanticTranslationTags(block.translation);
        setTranslation(cleanedTranslation);
        translationRef.current = cleanedTranslation;
      }
    }
  }, [block.id, block.source_text, block.translation, onBlockChange]);

  // Save on unmount — but ONLY if user has local changes that differ from the prop
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      const latestProp = blockPropRef.current;
      const hasLocalChanges = 
        sourceTextRef.current !== latestProp.source_text || 
        translationRef.current !== latestProp.translation;
      if (hasLocalChanges) {
        onBlockChange(blockIdRef.current, { 
          source_text: sourceTextRef.current, 
          translation: translationRef.current 
        });
      }
    };
  }, [onBlockChange]);

  const handleSourceChange = (val: string) => {
    setSourceText(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onBlockChange(blockIdRef.current, { source_text: val });
    }, 250);
  };

  const handleTranslationChange = (val: string) => {
    setTranslation(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onBlockChange(blockIdRef.current, { translation: val });
    }, 250);
  };

  const handleBlur = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    // Only save if user has local edits that differ from the latest prop.
    // This prevents overwriting external updates (like OCR results).
    const latestProp = blockPropRef.current;
    const hasLocalChanges = 
      sourceTextRef.current !== latestProp.source_text || 
      translationRef.current !== latestProp.translation;
    if (hasLocalChanges) {
      onBlockChange(blockIdRef.current, { 
        source_text: sourceTextRef.current, 
        translation: translationRef.current 
      });
    }
  };

  return (
    <>
      {/* Source Field */}
      <div>
        <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Source Text</label>
        <textarea 
          value={sourceText}
          onChange={(e) => handleSourceChange(e.target.value)}
          onBlur={handleBlur}
          className="source-input w-full p-2.5 text-xs text-slate-300 focus:outline-none input-glass resize-none h-14 font-sans"
        />
      </div>

      {/* Translation Field */}
      <div>
        <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Translation</label>
        <textarea 
          value={translation}
          onChange={(e) => handleTranslationChange(e.target.value)}
          onBlur={handleBlur}
          className="translation-input w-full p-2.5 text-xs text-white focus:outline-none input-glass resize-none h-16 font-sans"
          placeholder="พิมพ์คำแปลที่นี่…"
        />
      </div>
    </>
  );
};

interface RotationControlProps {
  value: number;
  mixed: boolean;
  onCommit: (value: number) => void;
}

const RotationControl: React.FC<RotationControlProps> = ({ value, mixed, onCommit }) => {
  const [draft, setDraft] = useState(value);
  const [hasMoved, setHasMoved] = useState(false);
  const committedRef = useRef(value);
  const hasCommittedRef = useRef(false);
  const hasMovedRef = useRef(false);

  const commit = (next: number) => {
    if (mixed && !hasMovedRef.current) return;
    if (next === committedRef.current && (!mixed || hasCommittedRef.current)) return;
    committedRef.current = next;
    hasCommittedRef.current = true;
    onCommit(next);
  };

  return (
    <div className="text-[8px] font-bold uppercase tracking-wider text-slate-500">
      <div className="flex items-center justify-between">
        <span>Rotation</span>
        <button
          type="button"
          onClick={() => {
            setDraft(0);
            setHasMoved(true);
            hasMovedRef.current = true;
            commit(0);
          }}
          className="text-[8px] text-slate-500 hover:text-yellow-300"
        >
          Reset
        </button>
      </div>
      <div className="mt-1 flex items-center gap-2 border border-zinc-800 bg-zinc-950 px-2 py-1.5">
        <input
          type="range"
          min="-180"
          max="180"
          step="1"
          value={draft}
          onChange={(event) => {
            setDraft(Number(event.target.value));
            setHasMoved(true);
            hasMovedRef.current = true;
          }}
          onPointerUp={(event) => commit(Number(event.currentTarget.value))}
          onPointerCancel={(event) => commit(Number(event.currentTarget.value))}
          onKeyUp={(event) => commit(Number(event.currentTarget.value))}
          onBlur={(event) => commit(Number(event.currentTarget.value))}
          className="min-w-0 flex-1 cursor-ew-resize accent-yellow-500"
          aria-label="Rotation"
        />
        <output className="w-11 text-right font-mono text-[10px] text-slate-200">
          {mixed && !hasMoved ? 'Mixed' : `${Math.round(draft)}°`}
        </output>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const {
    projects, activeProject, activePage, selectedBlock, selectedBlocks, statusMessage, isProcessing, isSavingBlocks,
    fetchProjects, createProject, selectProject, uploadPage, selectPage,
    updateBlock, updateBlocksBulk, deleteBlocks, setStatus,
    browseFolderProject, updateProjectSettings, undo, redo, mergeBlocks,
    defaultLoadProjectPath, defaultSaveOcrPath, setDefaultLoadProjectPath, setDefaultSaveOcrPath,
    oversizeWarningData, setOversizeWarningData, smartSplitAndOpen
  } = useProjectStore(useShallow((state) => ({
    projects: state.projects,
    activeProject: state.activeProject,
    activePage: state.activePage,
    selectedBlock: state.selectedBlock,
    selectedBlocks: state.selectedBlocks,
    statusMessage: state.statusMessage,
    isProcessing: state.isProcessing,
    isSavingBlocks: state.isSavingBlocks,
    fetchProjects: state.fetchProjects,
    createProject: state.createProject,
    selectProject: state.selectProject,
    uploadPage: state.uploadPage,
    selectPage: state.selectPage,
    updateBlock: state.updateBlock,
    updateBlocksBulk: state.updateBlocksBulk,
    deleteBlocks: state.deleteBlocks,
    setStatus: state.setStatus,
    browseFolderProject: state.browseFolderProject,
    updateProjectSettings: state.updateProjectSettings,
    undo: state.undo,
    redo: state.redo,
    mergeBlocks: state.mergeBlocks,
    defaultLoadProjectPath: state.defaultLoadProjectPath,
    defaultSaveOcrPath: state.defaultSaveOcrPath,
    setDefaultLoadProjectPath: state.setDefaultLoadProjectPath,
    setDefaultSaveOcrPath: state.setDefaultSaveOcrPath,
    oversizeWarningData: state.oversizeWarningData,
    setOversizeWarningData: state.setOversizeWarningData,
    smartSplitAndOpen: state.smartSplitAndOpen,
  })));

  const [isSplittingOversize, setIsSplittingOversize] = useState(false);
  const [showSmartStitchModal, setShowSmartStitchModal] = useState(false);

  // Menu dropdowns states
  const [showMenuFile, setShowMenuFile] = useState(false);
  const [showMenuEdit, setShowMenuEdit] = useState(false);
  const [showMenuNav, setShowMenuNav] = useState(false);
  const [showMenuProj, setShowMenuProj] = useState(false);
  const [showMenuTools, setShowMenuTools] = useState(false);
  const [showMenuAbout, setShowMenuAbout] = useState(false);
  const [showMenuExport, setShowMenuExport] = useState(false);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const currentUser = { username: 'admin', role: 'admin', status: 'active' };

  // Auto Update State & Check
  const [updateManifest, setUpdateManifest] = useState<any>(null);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);
  const [justUpdatedVersion, setJustUpdatedVersion] = useState<string | null>(null);
  const [justUpdatedNotes, setJustUpdatedNotes] = useState<string>('');
  const [isUpdateSuccessModalOpen, setIsUpdateSuccessModalOpen] = useState<boolean>(false);

  useEffect(() => {
    // 1. Check if user just reloaded after an update
    const v = localStorage.getItem('houmi_just_updated_version');
    const n = localStorage.getItem('houmi_just_updated_notes');
    if (v) {
      setJustUpdatedVersion(v);
      setJustUpdatedNotes(n || '');
      setIsUpdateSuccessModalOpen(true);
    }

    // 2. Check for available patch updates
    fetch('/api/system/check-update')
      .then((res) => res.json())
      .then((data) => {
        if (data && data.update_available) {
          setUpdateManifest(data);
        }
      })
      .catch(() => {});
  }, []);

  const handleCloseUpdateSuccessModal = () => {
    localStorage.removeItem('houmi_just_updated_version');
    localStorage.removeItem('houmi_just_updated_notes');
    setIsUpdateSuccessModalOpen(false);
  };

  // Sub-Toolbar setting states
  const [ocrEngine, setOcrEngine] = useState(() => getStoredSetting('ocr_engine', 'ppocrv5'));
  const [vlmInstalled, setVlmInstalled] = useState(false);

  useEffect(() => {
    fetch('/api/vlm-server/status')
      .then((res) => res.json())
      .then((data) => {
        if (data && typeof data.installed === 'boolean') {
          setVlmInstalled(data.installed);
        }
      })
      .catch(() => {});
  }, [ocrEngine]);

  useEffect(() => {
    if (activeProject) {
      if (activeProject.source_lang) {
        setSourceLang(activeProject.source_lang);
        localStorage.setItem('houmi_source_lang', activeProject.source_lang);
      }
      const pSettings = activeProject.settings || {};
      if (pSettings.ocr_engine) {
        setOcrEngine(pSettings.ocr_engine);
        localStorage.setItem('houmi_ocr_engine', pSettings.ocr_engine);
      }
      if (pSettings.client_profile_id) {
        setSelectedClientId(pSettings.client_profile_id);
        localStorage.setItem(ACTIVE_CLIENT_PROFILE_STORAGE_KEY, pSettings.client_profile_id);
        localStorage.setItem('houmi_active_client_profile_id', pSettings.client_profile_id);
      }
      if (typeof pSettings.ai_ocr_correction === 'boolean') {
        setAiOcrCorrection(pSettings.ai_ocr_correction);
      }
    }
  }, [activeProject?.id, activeProject?.source_lang, activeProject?.settings?.ocr_engine, activeProject?.settings?.ai_ocr_correction, activeProject?.settings?.client_profile_id]);

  const [aiOcrCorrection, setAiOcrCorrection] = useState(() => getStoredSetting('ai_ocr_correction', false));
  const [liveMaskOverlay, setLiveMaskOverlay] = useState(() => getStoredSetting('live_mask_overlay', false));

  // Client Profiles & Project Preset Modal states
  const [clientProfiles, setClientProfiles] = useState<ClientProjectProfile[]>(() => {
    return loadClientProjectProfiles(localStorage.getItem(CLIENT_PROFILES_STORAGE_KEY));
  });
  const [selectedClientId, setSelectedClientId] = useState<string>(() => {
    const saved = localStorage.getItem(ACTIVE_CLIENT_PROFILE_STORAGE_KEY) || localStorage.getItem('houmi_active_client_profile_id');
    const profiles = loadClientProjectProfiles(localStorage.getItem(CLIENT_PROFILES_STORAGE_KEY));
    if (saved && profiles.some(p => p.id === saved)) return saved;
    return profiles[0]?.id || '';
  });
  const [showProjectPresetModal, setShowProjectPresetModal] = useState<boolean>(false);
  const [newClientNameInput, setNewClientNameInput] = useState<string>('');
  const [isCreatingNewClient, setIsCreatingNewClient] = useState<boolean>(false);
  const [isAddingClientModalOpen, setIsAddingClientModalOpen] = useState(false);
  const [newClientProfileName, setNewClientProfileName] = useState('');
  const [newClientProfileDesc, setNewClientProfileDesc] = useState('');
  const [isRenamingClientModalOpen, setIsRenamingClientModalOpen] = useState(false);
  const [renameClientProfileName, setRenameClientProfileName] = useState('');
  const [renameClientProfileDesc, setRenameClientProfileDesc] = useState('');
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  const [roleSearchQuery, setRoleSearchQuery] = useState('');
  const [isCustomWorkflowModalOpen, setIsCustomWorkflowModalOpen] = useState<boolean>(false);
  const [isPageWorkflowRunning, setIsPageWorkflowRunning] = useState<boolean>(false);
  const [missingFonts, setMissingFonts] = useState<string[]>([]);
  const [isDownloadingFonts, setIsDownloadingFonts] = useState<boolean>(false);
  const [isFontBannerDismissed, setIsFontBannerDismissed] = useState<boolean>(false);
  const [dobkleProgress, setDobkleProgress] = useState<DobkleProgressData | null>(null);
  const [isDobkleModalOpen, setIsDobkleModalOpen] = useState<boolean>(false);

  useEffect(() => {
    const checkEssentialFonts = async () => {
      try {
        const res = await apiFetch('/api/fonts/check-essential');
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.missing_fonts) && data.missing_fonts.length > 0) {
            setMissingFonts(data.missing_fonts);
          } else {
            setMissingFonts([]);
          }
        }
      } catch (err) {
        console.warn('Failed to check essential fonts:', err);
      }
    };
    checkEssentialFonts();
  }, []);

  const handleDownloadEssentialFonts = async () => {
    setIsDownloadingFonts(true);
    showToast('กำลังดาวน์โหลดและติดตั้งชุดฟอนต์มาตรฐาน...', 'info');
    try {
      const res = await apiFetch('/api/fonts/download-essential-bundle', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        injectFontStylesheet();
        setMissingFonts([]);
        showToast('✅ ดาวน์โหลดและติดตั้งฟอนต์มาตรฐานเรียบร้อยแล้ว!', 'success');
      } else {
        showToast(data.message || 'ไม่สามารถดาวน์โหลดฟอนต์ได้', 'error');
      }
    } catch (err: any) {
      showToast('เกิดข้อผิดพลาดในการดาวน์โหลดฟอนต์: ' + err.message, 'error');
    } finally {
      setIsDownloadingFonts(false);
    }
  };

  const workflowCancelledRef = useRef<boolean>(false);
  const workflowAbortControllerRef = useRef<AbortController | null>(null);
  const clientProfileImportFileRef = useRef<HTMLInputElement>(null);

  const handleRunCustomWorkflow = async (steps: string[], scope: 'current' | 'all', params: Record<string, any>) => {
    if (!activeProject) return;

    if (params.ocr_backend && params.ocr_backend !== ocrEngine) {
      setOcrEngine(params.ocr_backend);
    }

    if (scope === 'all') {
      await runBatchPipeline(steps.join(','));
    } else if (activePage) {
      workflowCancelledRef.current = false;
      const controller = new AbortController();
      workflowAbortControllerRef.current = controller;
      setIsPageWorkflowRunning(true);
      showToast(`กำลังเริ่มรัน Custom Workflow (${steps.length} ขั้นตอน)...`, 'info');
      try {
        for (const step of steps) {
          if (workflowCancelledRef.current || controller.signal.aborted) {
            showToast('Workflow ถูกยกเลิกแล้ว', 'info');
            break;
          }
          if (step === 'filter_empty' || step === 'merge_expand') continue;
          await runPipelineStep(step as any);
          if (workflowCancelledRef.current || controller.signal.aborted) {
            showToast('Workflow ถูกยกเลิกแล้ว', 'info');
            break;
          }
        }
        if (!workflowCancelledRef.current && !controller.signal.aborted) {
          showToast('Custom Workflow สำหรับหน้านี้เสร็จสมบูรณ์แล้ว! 🎉', 'success');
        }
      } catch (err: any) {
        if (!workflowCancelledRef.current) {
          showToast(`Workflow error: ${err.message}`, 'error');
        }
      } finally {
        setIsPageWorkflowRunning(false);
        setStatus('Ready');
      }
    }
  };

  // Style Presets states
  const [showPresetsModal, setShowPresetsModal] = useState(false);
  const [showMultiPageStyleModal, setShowMultiPageStyleModal] = useState(false);
  const [multiPageSelectedIds, setMultiPageSelectedIds] = useState<Set<string>>(new Set());
  const [multiPageSearch, setMultiPageSearch] = useState('');
  const [multiPageFilter, setMultiPageFilter] = useState('all');
  const [multiPageTemplateKey, setMultiPageTemplateKey] = useState('');
  const [multiPageFontFamily, setMultiPageFontFamily] = useState('');
  const [multiPageFontSize, setMultiPageFontSize] = useState('');
  const [multiPageColor, setMultiPageColor] = useState('');
  const [multiPageBold, setMultiPageBold] = useState<'keep' | 'on' | 'off'>('keep');
  const [multiPageItalic, setMultiPageItalic] = useState<'keep' | 'on' | 'off'>('keep');
  const [newPresetName, setNewPresetName] = useState('');
  const [stylePresets, setStylePresets] = useState<Record<string, TextTemplate>>(() => {
    try {
      const saved = localStorage.getItem('houmi_style_presets');
      return normalizeTextTemplates(saved ? JSON.parse(saved) : DEFAULT_TEXT_TEMPLATES);
    } catch {
      return DEFAULT_TEXT_TEMPLATES;
    }
  });
  const [selectedTemplateKey, setSelectedTemplateKey] = useState('bubble');
  const [templateLayerStyleTab, setTemplateLayerStyleTab] = useState<'type' | 'fill' | 'stroke' | 'glow' | 'shadow'>('type');
  const templateDraftBaselineRef = useRef<Record<string, TextTemplate> | null>(null);
  const [templateSettingsDirty, setTemplateSettingsDirty] = useState(false);
  const layerSelectionAnchorRef = useRef<string | null>(null);
  const layerCardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    layerSelectionAnchorRef.current = null;
    layerCardRefs.current = {};
  }, [activePage?.id]);

  // Auto-scroll Layers & Text Review list when a balloon/block is selected
  useEffect(() => {
    const targetId = selectedBlock?.id || (selectedBlocks.length > 0 ? selectedBlocks[selectedBlocks.length - 1].id : null);
    if (!targetId) return;

    const frameId = requestAnimationFrame(() => {
      const targetEl = layerCardRefs.current[targetId];
      if (targetEl) {
        targetEl.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'nearest',
        });
      }
    });
    return () => cancelAnimationFrame(frameId);
  }, [selectedBlock?.id, selectedBlocks]);

  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('ocr');
  const [reviewPanelView, setReviewPanelView] = useState<'review' | 'pipeline'>('pipeline');
  const [showFloatingLetteringBar, setShowFloatingLetteringBar] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('houmi_show_floating_lettering_bar');
      return saved !== 'false';
    } catch {
      return true;
    }
  });
  const [showMenuView, setShowMenuView] = useState(false);
  const [isFormattingWidgetOpen, setIsFormattingWidgetOpen] = useState(() => {
    try {
      return localStorage.getItem('houmi_formatting_widget_open') === 'true';
    } catch {
      return false;
    }
  });
  const [isFormattingWidgetMinimized, setIsFormattingWidgetMinimized] = useState(false);
  const [formattingWidgetPos, setFormattingWidgetPos] = useState<{ x: number; y: number }>(() => {
    try {
      const saved = localStorage.getItem('houmi_formatting_widget_coords');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
          return {
            x: Math.min(Math.max(10, parsed.x), window.innerWidth - 340),
            y: Math.min(Math.max(50, parsed.y), window.innerHeight - 80),
          };
        }
      }
    } catch {}
    return { x: Math.max(20, window.innerWidth - 380), y: 70 };
  });
  const [isStyleTemplatesExpanded, setIsStyleTemplatesExpanded] = useState(true);
  const [isCustomStyleExpanded, setIsCustomStyleExpanded] = useState(true);
  const isDraggingWidgetRef = useRef(false);
  const dragStartOffsetRef = useRef({ x: 0, y: 0 });

  const handleWidgetPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('button') || (e.target as HTMLElement).closest('input')) return;
    isDraggingWidgetRef.current = true;
    dragStartOffsetRef.current = {
      x: e.clientX - formattingWidgetPos.x,
      y: e.clientY - formattingWidgetPos.y,
    };
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {}
  };

  const handleWidgetPointerMove = (e: React.PointerEvent) => {
    if (!isDraggingWidgetRef.current) return;
    const newX = Math.max(10, Math.min(window.innerWidth - 120, e.clientX - dragStartOffsetRef.current.x));
    const newY = Math.max(40, Math.min(window.innerHeight - 60, e.clientY - dragStartOffsetRef.current.y));
    setFormattingWidgetPos({ x: newX, y: newY });
  };

  const handleWidgetPointerUp = (e: React.PointerEvent) => {
    if (isDraggingWidgetRef.current) {
      isDraggingWidgetRef.current = false;
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}
      try {
        localStorage.setItem('houmi_formatting_widget_coords', JSON.stringify(formattingWidgetPos));
      } catch {}
    }
  };
  const [isStyleAlignExpanded, setIsStyleAlignExpanded] = useState(false);
  const [showAIProviderSettingsModal, setShowAIProviderSettingsModal] = useState(false);
  const [showChangelogModal, setShowChangelogModal] = useState(false);
  const [globalConfirm, setGlobalConfirm] = useState<{
    isOpen: boolean;
    title?: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    type?: 'warning' | 'danger' | 'info';
    onConfirm: () => void;
  }>({ isOpen: false, message: '', onConfirm: () => {} });

  const showConfirmDialog = (
    message: string,
    onConfirm: () => void,
    title = 'ยืนยันการดำเนินการ',
    options?: { confirmText?: string; cancelText?: string; type?: 'warning' | 'danger' | 'info' }
  ) => {
    setGlobalConfirm({
      isOpen: true,
      title,
      message,
      confirmText: options?.confirmText,
      cancelText: options?.cancelText,
      type: options?.type || (message.includes('ลบ') || title.includes('ลบ') ? 'danger' : 'warning'),
      onConfirm,
    });
  };

  useEffect(() => {
    const lastSeen = localStorage.getItem('houmi_last_seen_changelog_version');
    if (lastSeen !== HOUMI_VERSION) {
      setShowChangelogModal(true);
      localStorage.setItem('houmi_last_seen_changelog_version', HOUMI_VERSION);
    }
  }, []);

  const handleSetReviewPanelView = (view: 'review' | 'pipeline') => {
    setReviewPanelView(view);
    localStorage.setItem('houmi_review_panel_view', view);
  };

  const closeAllMenus = () => {
    setShowMenuFile(false);
    setShowMenuEdit(false);
    setShowMenuView(false);
    setShowMenuNav(false);
    setShowMenuProj(false);
    setShowMenuTools(false);
    setShowMenuAbout(false);
    setShowMenuExport(false);
  };

  const persistTemplates = async (templates: Record<string, TextTemplate>) => {
    setStylePresets(templates);
    localStorage.setItem('houmi_style_presets', JSON.stringify(templates));

    setClientProfiles(prevProfiles => {
      const updated = prevProfiles.map(p => {
        if (p.id === selectedClientId) {
          return {
            ...p,
            text_templates: normalizeTextTemplates(JSON.parse(JSON.stringify(templates))),
            updated_at: new Date().toISOString(),
          };
        }
        return p;
      });
      localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
      return updated;
    });

    if (activeProject) {
      await updateProjectSettings(activeProject.id, {
        ...(activeProject.settings || {}),
        text_templates: templates,
      });
    }
  };

  const savePreset = async (name: string, style: TextTemplate) => {
    const updated = { ...stylePresets, [name]: style };
    await persistTemplates(updated);
  };

  const deletePreset = async (name: string) => {
    const updated = { ...stylePresets };
    delete updated[name];
    await persistTemplates(updated);
  };

  useEffect(() => {
    if (!activeProject) return;
    // Font Templates live under Global Settings, so the local global copy is
    // authoritative across projects and app restarts. Only use a project's
    // templates to seed a first-time installation.
    let savedTemplates: unknown = null;
    try {
      const saved = localStorage.getItem('houmi_style_presets');
      savedTemplates = saved ? JSON.parse(saved) : null;
    } catch {
      savedTemplates = null;
    }
    const templates = resolveGlobalTextTemplates(savedTemplates, activeProject.settings?.text_templates);
    localStorage.setItem('houmi_style_presets', JSON.stringify(templates));
    setStylePresets(templates);
    setSelectedTemplateKey(current => templates[current] ? current : Object.keys(templates)[0]);
  }, [activeProject?.id]);

  const layoutRecomputeRef = useRef(new Set<string>());
  const invalidLayoutSignature = activePage?.text_blocks
    .filter(block => Boolean(block.translation) && !isValidCanonicalSpec(block.extra_metadata?.typesetting_spec))
    .map(block => block.id)
    .sort()
    .join('|') || '';

  const refreshPagePreservingSelection = async (pageId: string) => {
    const response = await fetch(`/api/pages/${pageId}`);
    if (!response.ok) throw new Error(`Page refresh failed (${response.status})`);
    const freshPage = await response.json();
    const state = useProjectStore.getState();
    const selectedIds = state.selectedBlocks.map(block => block.id);
    const primaryId = state.selectedBlock?.id;
    const selectedBlocksFresh = selectedIds
      .map(id => freshPage.text_blocks.find((block: TextBlock) => block.id === id))
      .filter(Boolean) as TextBlock[];
    const primaryFresh = primaryId
      ? freshPage.text_blocks.find((block: TextBlock) => block.id === primaryId) || null
      : selectedBlocksFresh.at(-1) || null;
    const project = state.activeProject;
    useProjectStore.setState({
      activePage: freshPage,
      activeProject: project
        ? { ...project, pages: project.pages.map(page => page.id === pageId ? freshPage : page) }
        : null,
      selectedBlock: primaryFresh,
      selectedBlocks: selectedBlocksFresh,
    });
  };

  useEffect(() => {
    if (!activePage || !invalidLayoutSignature || isSavingBlocks) return;
    const recomputeKey = `${activePage.id}:${CURRENT_LAYOUT_ENGINE_VERSION}:${invalidLayoutSignature}`;
    if (layoutRecomputeRef.current.has(recomputeKey)) return;
    layoutRecomputeRef.current.add(recomputeKey);

    void fetch(`/api/typesetting/recompute/page/${activePage.id}`, { method: 'POST' })
      .then(response => {
        if (!response.ok) throw new Error(`Typesetting refresh failed (${response.status})`);
        return refreshPagePreservingSelection(activePage.id);
      })
      .catch(error => {
        layoutRecomputeRef.current.delete(recomputeKey);
        console.error(error);
      });
  }, [activePage?.id, invalidLayoutSignature, isSavingBlocks]);

  useEffect(() => {
    localStorage.setItem('houmi_workspace_mode', workspaceMode);
    if (workspaceMode === 'ocr') setStyleSettingsOpen(false);
    if (workspaceMode === 'typeset') {
      setStyleSettingsOpen(true);
      setTypesetInspectorCollapsed(window.innerWidth < 1320);
    }
  }, [workspaceMode]);

  useEffect(() => {
    const handleWindowClick = () => {
      closeAllMenus();
      setLayerContextMenu(null);
    };
    window.addEventListener('click', handleWindowClick);
    return () => window.removeEventListener('click', handleWindowClick);
  }, []);


  const [newProjName, setNewProjName] = useState('');
  const [selectedBlockForMaskEdit, setSelectedBlockForMaskEdit] = useState<string | null>(null);
  const [typesetInspectorTab, setTypesetInspectorTab] = useState<'character' | 'templates'>('character');
  const [typesetInspectorCollapsed, setTypesetInspectorCollapsed] = useState(() => window.innerWidth < 1320);
  const compactInspectorViewportRef = useRef(window.innerWidth < 1320);
  const [layerContextMenu, setLayerContextMenu] = useState<LayerContextMenuState | null>(null);
  const [showNewProjModal, setShowNewProjModal] = useState(false);
  const [showGlobalSettingsModal, setShowGlobalSettingsModal] = useState(false);
  const [settingsGlobalCategory, setSettingsGlobalCategory] = useState<'ai_provider' | 'workspace_dirs' | 'keyboard_shortcuts' | 'appearance' | 'ai_detection' | 'typography' | 'templates' | 'typesetting_rules' | 'pipeline' | 'performance'>('ai_detection');
  const [settingsGlobalSearch, setSettingsGlobalSearch] = useState('');
  const [activeBindingAction, setActiveBindingAction] = useState<string | null>(null);
  const [hardwareReport, setHardwareReport] = useState<any>(null);
  const [isOptimizingHardware, setIsOptimizingHardware] = useState(false);

  useEffect(() => {
    if (showGlobalSettingsModal) {
      apiFetch('/api/diagnostics/hardware')
        .then(res => res.ok ? res.json() : null)
        .then(data => { if (data) setHardwareReport(data); })
        .catch(() => {});
    }
  }, [showGlobalSettingsModal]);

  const handleAutoOptimizeHardware = async () => {
    setIsOptimizingHardware(true);
    try {
      const res = await apiFetch('/api/diagnostics/auto-optimize', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.hardware_report) {
          setHardwareReport(data.hardware_report);
        }
        showToast(`⚡ ${data.message || 'Auto-Optimize Hardware สำเร็จ!'}`, 'success');
      } else {
        showToast('เกิดข้อผิดพลาดในการ Auto-Optimize Hardware', 'error');
      }
    } catch (err) {
      console.error('Auto-Optimize error:', err);
      showToast('เกิดข้อผิดพลาดในการ Auto-Optimize Hardware', 'error');
    } finally {
      setIsOptimizingHardware(false);
    }
  };

  const [gpuInpaintUrl, setGpuInpaintUrl] = useState<string>(() => {
    return localStorage.getItem('houmi_gpu_inpaint_url') || 'http://127.0.0.1:2328/inpaint';
  });
  const [inpaintServerFolderPath, setInpaintServerFolderPath] = useState<string>(() => {
    return localStorage.getItem('houmi_inpaint_server_path') || '';
  });
  const [isTestingInpaintServer, setIsTestingInpaintServer] = useState(false);
  const [inpaintServerTestResult, setInpaintServerTestResult] = useState<any>(null);

  const handleTestInpaintServer = async () => {
    setIsTestingInpaintServer(true);
    setInpaintServerTestResult(null);
    try {
      const res = await apiFetch('/api/diagnostics/test-inpaint-server', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: gpuInpaintUrl, server_path: inpaintServerFolderPath })
      });
      const data = await res.json();
      setInpaintServerTestResult(data);
      if (data.success || data.status === 'connected' || data.status === 'ok') {
        localStorage.setItem('houmi_gpu_inpaint_url', gpuInpaintUrl);
        if (inpaintServerFolderPath) {
          localStorage.setItem('houmi_inpaint_server_path', inpaintServerFolderPath);
        }
        showToast(`✅ ${data.message}`, 'success');
      } else {
        showToast(`⚠️ ${data.message}`, 'error');
      }
    } catch (err: any) {
      const msg = `ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ (${err?.message || err})`;
      setInpaintServerTestResult({ success: false, message: msg });
      showToast(`⚠️ ${msg}`, 'error');
    } finally {
      setIsTestingInpaintServer(false);
    }
  };


  const keyBindings = useProjectStore((s) => s.keyBindings);
  const setKeyBinding = useProjectStore((s) => s.setKeyBinding);
  const resetKeyBindings = useProjectStore((s) => s.resetKeyBindings);

  const autoSaveTimeoutRef = useRef<any>(null);
  const lastSettingsSyncSignatureRef = useRef('');

  const openTemplateSettings = () => {
    templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
    setTemplateSettingsDirty(false);
    setSettingsGlobalCategory('templates');
    setShowGlobalSettingsModal(true);
    setShowPresetsModal(false);
  };

  const closeGlobalSettings = () => {
    if (templateSettingsDirty && templateDraftBaselineRef.current) {
      const discard = window.confirm('Discard unsaved Font Template changes?');
      if (!discard) return;
      setStylePresets(templateDraftBaselineRef.current);
    }
    templateDraftBaselineRef.current = null;
    setTemplateSettingsDirty(false);
    setShowGlobalSettingsModal(false);
    setActiveBindingAction(null);
  };

  const saveTemplateDraft = async () => {
    await persistTemplates(stylePresets);
    templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
    setTemplateSettingsDirty(false);

    if (activeProject) {
      const updates = buildTemplateReapplicationUpdates(activeProject, stylePresets);
      if (updates.length > 0) {
        await updateBlocksBulk(updates);
      }
    }

    showToast('บันทึก Font Templates และอัปเดตโปรไฟล์แล้ว ✨', 'success');
  };

  const activeClientProfile = clientProfiles.find(p => p.id === selectedClientId) || clientProfiles[0];

  const handleSelectClientProfile = (profileId: string) => {
    const target = clientProfiles.find(p => p.id === profileId);
    if (!target) return;
    setSelectedClientId(profileId);
    const cloned = normalizeTextTemplates(JSON.parse(JSON.stringify(target.text_templates)));
    setStylePresets(cloned);
    templateDraftBaselineRef.current = cloneTextTemplates(cloned);
    setSelectedTemplateKey(Object.keys(cloned)[0] || 'bubble');
    setTemplateSettingsDirty(false);
    showToast(`สลับใช้งานโปรไฟล์: ${target.name}`, 'info');
  };

  const handleAddNewClientProfile = (name: string, desc = '') => {
    const trimmed = name.trim();
    if (!trimmed) {
      showToast('กรุณากรอกชื่อโปรไฟล์ลูกค้า', 'error');
      return;
    }
    const newProfile = createClientProjectProfile(trimmed, stylePresets, {
      description: desc.trim(),
      default_font_family: selectedTemplateKey && stylePresets[selectedTemplateKey]?.font_stack?.[0] ? stylePresets[selectedTemplateKey].font_stack[0] : 'TH Sarabun New'
    });
    const updated = [...clientProfiles, newProfile];
    setClientProfiles(updated);
    localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
    setSelectedClientId(newProfile.id);
    setStylePresets(normalizeTextTemplates(JSON.parse(JSON.stringify(newProfile.text_templates))));
    templateDraftBaselineRef.current = cloneTextTemplates(newProfile.text_templates);
    setSelectedTemplateKey(Object.keys(newProfile.text_templates)[0] || 'bubble');
    setTemplateSettingsDirty(false);
    setIsAddingClientModalOpen(false);
    setNewClientProfileName('');
    setNewClientProfileDesc('');
    showToast(`สร้างโปรไฟล์ลูกค้า "${trimmed}" เรียบร้อยแล้ว 🎉`, 'success');
  };

  const handleRenameClientProfile = (name: string, desc = '') => {
    const trimmed = name.trim();
    if (!trimmed) {
      showToast('กรุณากรอกชื่อโปรไฟล์ลูกค้า', 'error');
      return;
    }
    const updated = clientProfiles.map(p => {
      if (p.id === selectedClientId) {
        return {
          ...p,
          name: trimmed,
          description: desc.trim(),
          updated_at: new Date().toISOString(),
        };
      }
      return p;
    });
    setClientProfiles(updated);
    localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
    setIsRenamingClientModalOpen(false);
    showToast(`เปลี่ยนชื่อโปรไฟล์เป็น "${trimmed}" เรียบร้อย`, 'success');
  };

  const handleDuplicateClientProfile = () => {
    const current = clientProfiles.find(p => p.id === selectedClientId) || clientProfiles[0];
    if (!current) return;
    const copyName = `${current.name} (สำเนา)`;
    const newProfile = createClientProjectProfile(copyName, stylePresets, {
      description: current.description || '',
      default_font_family: current.default_font_family || 'TH Sarabun New'
    });
    const updated = [...clientProfiles, newProfile];
    setClientProfiles(updated);
    localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
    setSelectedClientId(newProfile.id);
    setStylePresets(normalizeTextTemplates(JSON.parse(JSON.stringify(newProfile.text_templates))));
    templateDraftBaselineRef.current = cloneTextTemplates(newProfile.text_templates);
    setTemplateSettingsDirty(false);
    showToast(`คัดลอกโปรไฟล์ "${copyName}" เรียบร้อย ✨`, 'success');
  };

  const handleDeleteClientProfile = () => {
    if (clientProfiles.length <= 1) {
      showToast('ไม่สามารถลบได้ เนื่องจากต้องมีโปรไฟล์อย่างน้อย 1 รายการ', 'info');
      return;
    }
    const current = clientProfiles.find(p => p.id === selectedClientId);
    if (!current) return;
    if (!window.confirm(`คุณแน่ใจหรือไม่ว่าต้องการลบโปรไฟล์ลูกค้า "${current.name}"?`)) return;

    const updated = clientProfiles.filter(p => p.id !== selectedClientId);
    setClientProfiles(updated);
    localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
    const nextActive = updated[0];
    setSelectedClientId(nextActive.id);
    setStylePresets(normalizeTextTemplates(JSON.parse(JSON.stringify(nextActive.text_templates))));
    templateDraftBaselineRef.current = cloneTextTemplates(nextActive.text_templates);
    setSelectedTemplateKey(Object.keys(nextActive.text_templates)[0] || 'bubble');
    setTemplateSettingsDirty(false);
    showToast(`ลบโปรไฟล์ "${current.name}" เรียบร้อย`, 'info');
  };

  const handleApplyProfileToCurrentProject = async () => {
    const current = clientProfiles.find(p => p.id === selectedClientId);
    if (!current || !activeProject) {
      showToast('กรุณาเปิดโปรเจกต์มังงะก่อนใช้งาน', 'info');
      return;
    }
    await persistTemplates(stylePresets);
    const updates = buildTemplateReapplicationUpdates(activeProject, stylePresets);
    if (updates.length > 0) {
      await updateBlocksBulk(updates);
    }
    showToast(`นำโปรไฟล์ "${current.name}" ไปปรับใช้กับโปรเจกต์ปัจจุบัน (${updates.length} บล็อก) แล้ว! ⚡`, 'success');
  };

  const handleExportCurrentProfile = () => {
    const current = clientProfiles.find(p => p.id === selectedClientId);
    if (!current) return;
    const profileToExport: ClientProjectProfile = {
      ...current,
      text_templates: normalizeTextTemplates(JSON.parse(JSON.stringify(stylePresets))),
      updated_at: new Date().toISOString()
    };
    exportSingleClientProfileToJson(profileToExport);
    showToast(`ส่งออกและบันทึกโปรไฟล์ "${current.name}" เรียบร้อย (.json)`, 'success');
  };

  const handleExportAllProfiles = () => {
    const updatedProfiles = clientProfiles.map(p => {
      if (p.id === selectedClientId) {
        return {
          ...p,
          text_templates: normalizeTextTemplates(JSON.parse(JSON.stringify(stylePresets))),
          updated_at: new Date().toISOString()
        };
      }
      return p;
    });
    exportClientProfilesToJson(updatedProfiles);
    showToast('ส่งออกและบันทึกโปรไฟล์ลูกค้าทั้งหมดเรียบร้อย (.json)', 'success');
  };

  const handleImportClientProfiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const text = event.target?.result as string;
        const { profiles: updated, importedCount } = importClientProfilesFromJson(text, clientProfiles);
        setClientProfiles(updated);
        localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
        if (updated.length) {
          const newest = updated[updated.length - 1];
          setSelectedClientId(newest.id);
          setStylePresets(normalizeTextTemplates(JSON.parse(JSON.stringify(newest.text_templates))));
          templateDraftBaselineRef.current = cloneTextTemplates(newest.text_templates);
          setSelectedTemplateKey(Object.keys(newest.text_templates)[0] || 'bubble');
          setTemplateSettingsDirty(false);
        }
        showToast(`นำเข้าโปรไฟล์สำเร็จ ${importedCount} รายการ 🎉`, 'success');
      } catch (err: any) {
        showToast(`นำเข้าไม่สำเร็จ: ${err.message}`, 'error');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const discardTemplateDraft = () => {
    if (!templateDraftBaselineRef.current) return;
    setStylePresets(templateDraftBaselineRef.current);
    setSelectedTemplateKey(current => (
      templateDraftBaselineRef.current?.[current]
        ? current
        : Object.keys(templateDraftBaselineRef.current || {})[0] || 'bubble'
    ));
    setTemplateSettingsDirty(false);
  };

  const importTemplateFileRef = useRef<HTMLInputElement>(null);

  const handleExportTemplates = () => {
    try {
      const jsonString = JSON.stringify(stylePresets, null, 2);
      const blob = new Blob([jsonString], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const downloadAnchor = document.createElement('a');
      downloadAnchor.href = url;
      downloadAnchor.download = `houmi_font_templates_${Date.now()}.json`;
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      document.body.removeChild(downloadAnchor);
      URL.revokeObjectURL(url);
      showToast('ส่งออก Font Templates เรียบร้อยแล้ว (Export JSON Success)', 'success');
    } catch (err: any) {
      showToast(`ส่งออกไม่สำเร็จ: ${err.message}`, 'error');
    }
  };

  const handleImportTemplates = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);
        if (typeof parsed === 'object' && parsed !== null) {
          if (!templateDraftBaselineRef.current) {
            templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
          }
          setStylePresets(current => ({ ...current, ...parsed }));
          setTemplateSettingsDirty(true);
          showToast('นำเข้า Font Templates สำเร็จแล้ว! กด Save Templates เพื่อบันทึก', 'success');
        } else {
          showToast('รูปแบบไฟล์ JSON ไม่ถูกต้อง', 'error');
        }
      } catch (err: any) {
        showToast(`ไม่สามารถอ่านไฟล์ JSON: ${err.message}`, 'error');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  useEffect(() => {
    const handleResize = () => {
      const isCompact = window.innerWidth < 1320;
      if (isCompact && !compactInspectorViewportRef.current) {
        setTypesetInspectorCollapsed(true);
      }
      compactInspectorViewportRef.current = isCompact;
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (
      showGlobalSettingsModal
      && settingsGlobalCategory === 'templates'
      && !templateDraftBaselineRef.current
    ) {
      templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
    }
  }, [settingsGlobalCategory, showGlobalSettingsModal, stylePresets]);

  const updateGlobalSetting = (key: string, value: any) => {
    // 1. Save to localStorage
    setStoredSetting(key, value);

    // 2. Update React state
    if (key === 'ocr_engine') setOcrEngine(value);
    else if (key === 'ai_ocr_correction') setAiOcrCorrection(value);
    else if (key === 'live_mask_overlay') setLiveMaskOverlay(value);
    else if (key === 'source_lang') setSourceLang(value);
    else if (key === 'mask_dilation_kernel') setSettingsMaskDilationKernel(value);
    else if (key === 'mask_magnetic_line_fill') setSettingsMaskMagneticLineFill(value);
    else if (key === 'process_by_text_areas') setSettingsProcessByTextAreas(value);
    else if (key === 'cleanup_mask_strategy') setSettingsCleanupMaskStrategy(value);
    else if (key === 'force_lama_inpaint') setSettingsForceLamaInpaint(value);
    else if (key === 'cleanup_pipeline_profile') setSettingsCleanupPipelineProfile(value);
    else if (key === 'vertical_to_horizontal') setSettingsVerticalToHorizontal(value);
    else if (key === 'strip_furigana') setSettingsStripFurigana(value);
    else if (key === 'use_chinese_punctuation') setSettingsUseChinesePunctuation(value);
    else if (key === 'remove_spaces') setSettingsRemoveSpaces(value);
    else if (key === 'auto_ocr') setSettingsAutoOcr(value);
    else if (key === 'auto_remove_line_breaks') setSettingsAutoRemoveLineBreaks(value);
    else if (key === 'default_txt_mode') setSettingsDefaultTxtMode(value);
    else if (key === 'read_subfolders') setSettingsReadSubfolders(value);
    else if (key === 'intermediate_results_folder') setSettingsIntermediateResultsFolder(value);
    else if (key === 'right_to_left_reading_order') setSettingsRightToLeftReadingOrder(value);
    else if (key === 'auto_font_resize') setSettingsAutoFontResize(value);
    else if (key === 'default_font_family') setSettingsDefaultFontFamily(value);
    else if (key === 'default_text_template_id') setSettingsDefaultTextTemplateId(value);
    else if (key === 'lock_translation_to_detected_box') setSettingsLockTranslationToDetectedBox(value);
    else if (key === 'match_source_font_size') setSettingsMatchSourceFontSize(value);
    else if (key === 'source_font_scale') setSettingsSourceFontScale(value);
    else if (key === 'max_font_size') setSettingsMaxFontSize(value);
    else if (key === 'min_font_size') setSettingsMinFontSize(value);
    else if (key === 'binary_threshold') setSettingsBinaryThreshold(value);
    else if (key === 'auto_compute_threshold') setSettingsAutoComputeThreshold(value);
    else if (key === 'auto_select_threshold_fewer') setSettingsAutoSelectThresholdFewer(value);
    else if (key === 'pixels_to_expand_around_textbox') setSettingsPixelsToExpandAroundTextbox(value);
    else if (key === 'expand_after_balloon_detection') setSettingsExpandAfterBalloonDetection(value);
    else if (key === 'convert_vertical_area') setSettingsConvertVerticalArea(value);
    else if (key === 'avoid_breaking_words') setSettingsAvoidBreakingWords(value);
    else if (key === 'restrain_areas_within_image') setSettingsRestrainAreasWithinImage(value);
    else if (key === 'infer_text_direction') setSettingsInferTextDirection(value);
    else if (key === 'use_bridge_language') setSettingsUseBridgeLanguage(value);
    else if (key === 'bridge_language') setSettingsBridgeLanguage(value);
    else if (key === 'enable_rich_text') setSettingsEnableRichText(value);
    else if (key === 'enable_cjk_vertical_text_engine') setSettingsEnableCjkVerticalTextEngine(value);
    else if (key === 'sort_criteria') setSettingsSortCriteria(value);
    else if (key === 'sort_based_on_panels') setSettingsSortBasedOnPanels(value);
    else if (key === 'when_generating_mask_check_separation') setSettingsWhenGeneratingMaskCheckSeparation(value);
    else if (key === 'consider_fg_bg_depth') setSettingsConsiderFgBgDepth(value);
    else if (key === 'default_textbox_width') setSettingsDefaultTextboxWidth(value);
    else if (key === 'default_textbox_height') setSettingsDefaultTextboxHeight(value);
    else if (key === 'accurate_text_erase_mode') setSettingsAccurateTextEraseMode(value);
    else if (key === 'default_mask_gen_method') setSettingsDefaultMaskGenMethod(value);
    else if (key === 'default_image_inpaint_method') setSettingsDefaultImageInpaintMethod(value);
    else if (key === 'inpaint_engine') setSettingsInpaintEngine(value);
    else if (key === 'inpaint_strategy') setSettingsInpaintStrategy(value);
    else if (key === 'image_inpainting_radius') setSettingsImageInpaintingRadius(value);
    else if (key === 'inpaint_context_padding') setSettingsInpaintContextPadding(value);
    else if (key === 'mask_radius_imprecise') setSettingsMaskRadiusImprecise(value);
    else if (key === 'pixels_to_expand_text_areas') setSettingsPixelsToExpandTextAreas(value);
    else if (key === 'gaussian_blur_times') setSettingsGaussianBlurTimes(value);
    else if (key === 'mask_feathering_sigma') setSettingsMaskFeatheringSigma(value);
    else if (key === 'inpainting_max_width') setSettingsInpaintingMaxWidth(value);
    else if (key === 'sliding_window_overlap') setSettingsSlidingWindowOverlap(value);
    else if (key === 'generate_text_mask_ocr') setSettingsGenerateTextMaskOcr(value);
    else if (key === 'enable_sliding_windows') setSettingsEnableSlidingWindows(value);
    else if (key === 'multiply_alpha_channel') setSettingsMultiplyAlphaChannel(value);
    else if (key === 'ocr_for_mask_gen') setSettingsOcrForMaskGen(value);
    else if (key === 'enable_smart_balloon') setSettingsEnableSmartBalloon(value);
    else if (key === 'balloon_model') setSettingsBalloonModel(value);
    else if (key === 'scale_image_before_detection') setSettingsScaleImageBeforeDetection(value);
    else if (key === 'scale_image_size') setSettingsScaleImageSize(value);
    else if (key === 'use_fixed_image_ratio') setSettingsUseFixedImageRatio(value);
    else if (key === 'fixed_image_ratio') setSettingsFixedImageRatio(value);
    else if (key === 'height_to_width_ratio_dividing') setSettingsHeightToWidthRatioDividing(value);
    else if (key === 'use_model_params_first') setSettingsUseModelParamsFirst(value);
    else if (key === 'store_detected_class_font_style') setSettingsStoreDetectedClassFontStyle(value);
    else if (key === 'expand_small_images') setSettingsExpandSmallImages(value);
    else if (key === 'performance_profile') setSettingsPerformanceProfile(value);
    else if (key === 'performance_custom') setSettingsPerformanceCustom(value);

    // 3. Debounced sync to active project settings database on the backend
    const currentProject = useProjectStore.getState().activeProject;
    if (currentProject) {
      const updatedSettings = {
        ...(currentProject.settings || {}),
        text_templates: stylePresets,
        [key]: value,
      };
      
      // Optimistic state update in store
      useProjectStore.setState({
        activeProject: { ...currentProject, settings: updatedSettings }
      });

      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
      }

      autoSaveTimeoutRef.current = setTimeout(async () => {
        try {
          await updateProjectSettings(currentProject.id, updatedSettings);
        } catch (err) {
          console.error("Auto-save sync failed:", err);
        }
      }, 500);
    }
  };

  const applyCleanupPipelineProfile = (profile: 'smart_lama' | 'fast_preview') => {
    const values = profile === 'smart_lama'
      ? {
          cleanup_pipeline_profile: 'smart_lama',
          cleanup_mask_strategy: 'smart',
          process_by_text_areas: true,
          force_lama_inpaint: true,
          default_image_inpaint_method: 'LamaInpaint',
          inpaint_context_padding: 96,
        }
      : {
          cleanup_pipeline_profile: 'fast_preview',
          cleanup_mask_strategy: 'smart',
          process_by_text_areas: true,
          force_lama_inpaint: false,
          default_image_inpaint_method: 'Telea',
          inpaint_context_padding: 64,
        };

    Object.entries(values).forEach(([key, value]) => updateGlobalSetting(key, value));
    showToast(
      profile === 'smart_lama'
        ? 'ใช้ Smart Clean: Smart Mask + LaMa แล้ว'
        : 'ใช้ Fast Preview: Smart Mask + Telea แล้ว',
      'success',
    );
  };

  // Keyboard shortcut binding capture hook
  useEffect(() => {
    if (!activeBindingAction) return;

    const handleKeyCapture = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;

      const keys: string[] = [];
      if (e.ctrlKey || e.metaKey) keys.push('Ctrl');
      if (e.shiftKey) keys.push('Shift');
      if (e.altKey) keys.push('Alt');

      let keyLabel = e.key;
      if (keyLabel === ' ') keyLabel = 'Space';
      if (keyLabel.length === 1) keyLabel = keyLabel.toUpperCase();
      keys.push(keyLabel);

      const formatted = keys.join('+');
      const [action, slotText] = activeBindingAction.split(':');
      const slot = Math.max(0, Math.min(2, Number(slotText) || 0));
      const alternatives = (keyBindings[action] || '').split('|').map(value => value.trim()).filter(Boolean);
      alternatives[slot] = formatted;
      setKeyBinding(action, alternatives.filter(Boolean).slice(0, 3).join(' | '));
      setActiveBindingAction(null);
      showToast(`ผูกปุ่มลัดใหม่: ${formatted}`, 'success');
    };

    window.addEventListener('keydown', handleKeyCapture, true);
    return () => {
      window.removeEventListener('keydown', handleKeyCapture, true);
    };
  }, [activeBindingAction, keyBindings]);

  // Auto-collapse / restore sidebars on screen resize for responsive workspace
  useEffect(() => {
    let lastWidth = window.innerWidth;
    const handleScreenResize = () => {
      const currentWidth = window.innerWidth;
      if (currentWidth < 1280 && lastWidth >= 1280) {
        setLeftSidebarOpen(false);
      } else if (currentWidth >= 1280 && lastWidth < 1280) {
        setLeftSidebarOpen(true);
      }
      if (currentWidth < 1024 && lastWidth >= 1024) {
        setRightSidebarOpen(false);
      } else if (currentWidth >= 1024 && lastWidth < 1024) {
        setRightSidebarOpen(true);
      }
      lastWidth = currentWidth;
    };
    handleScreenResize();
    window.addEventListener('resize', handleScreenResize);
    return () => {
      window.removeEventListener('resize', handleScreenResize);
    };
  }, []);

  const [showExportTxtModal, setShowExportTxtModal] = useState(false);
  const [showPsdExportModal, setShowPsdExportModal] = useState(false);
  const [psdTextMode, setPsdTextMode] = useState<'paragraph' | 'point' | 'jsx'>('paragraph');
  const [layerStrokeModalBlockId, setLayerStrokeModalBlockId] = useState<string | null>(null);
  const [showExportYoloModal, setShowExportYoloModal] = useState(false);
  const [showHotkeyModal, setShowHotkeyModal] = useState(false);
  const [showDevStudioModal, setShowDevStudioModal] = useState(false);
  const [devStudioInitialTab, setDevStudioInitialTab] = useState<'dev_map' | 'dev_notes'>('dev_map');

  useEffect(() => {
    const handleGlobalHotkey = (e: KeyboardEvent) => {
      // Toggle Action Debug Console Matrix (Ctrl+Shift+D or F12)
      if ((e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) || e.key === 'F12') {
        e.preventDefault();
        useDebugStore.getState().toggleDrawer();
        logAction('HOTKEY', 'Toggle Action Debug Console', { key: e.key });
        return;
      }

      if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const target = e.target as HTMLElement;
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA' && !target.isContentEditable) {
          e.preventDefault();
          setShowHotkeyModal((prev) => !prev);
        }
      }
    };
    window.addEventListener('keydown', handleGlobalHotkey);
    return () => window.removeEventListener('keydown', handleGlobalHotkey);
  }, []);
  
  // Settings states
  const [settingsMaskDilationKernel, setSettingsMaskDilationKernel] = useState(() => getStoredSetting('mask_dilation_kernel', 3));
  const [settingsMaskMagneticLineFill, setSettingsMaskMagneticLineFill] = useState(() => getStoredSetting('mask_magnetic_line_fill', false));
  const [settingsProcessByTextAreas, setSettingsProcessByTextAreas] = useState(() => getStoredSetting('process_by_text_areas', true));
  const [settingsCleanupMaskStrategy, setSettingsCleanupMaskStrategy] = useState(() => getStoredSetting('cleanup_mask_strategy', 'smart'));
  const [settingsForceLamaInpaint, setSettingsForceLamaInpaint] = useState(() => getStoredSetting('force_lama_inpaint', true));
  const [settingsCleanupPipelineProfile, setSettingsCleanupPipelineProfile] = useState(() => getStoredSetting('cleanup_pipeline_profile', 'smart_lama'));
  // Removed unused activeSettingsTab to avoid TS compile error
  const [settingsVerticalToHorizontal, setSettingsVerticalToHorizontal] = useState(() => getStoredSetting('vertical_to_horizontal', false));
  const [settingsStripFurigana, setSettingsStripFurigana] = useState(() => getStoredSetting('strip_furigana', false));
  const [settingsUseChinesePunctuation, setSettingsUseChinesePunctuation] = useState(() => getStoredSetting('use_chinese_punctuation', false));
  const [settingsRemoveSpaces, setSettingsRemoveSpaces] = useState(() => getStoredSetting('remove_spaces', true));
  const [settingsAutoOcr, setSettingsAutoOcr] = useState(() => getStoredSetting('auto_ocr', true));
  const [settingsAutoRemoveLineBreaks, setSettingsAutoRemoveLineBreaks] = useState(() => getStoredSetting('auto_remove_line_breaks', true));
  const [settingsDefaultTxtMode, setSettingsDefaultTxtMode] = useState(() => getStoredSetting('default_txt_mode', 'both'));

  // General tab options
  const [settingsReadSubfolders, setSettingsReadSubfolders] = useState(() => getStoredSetting('read_subfolders', false));
  const [settingsIntermediateResultsFolder, setSettingsIntermediateResultsFolder] = useState(() => getStoredSetting('intermediate_results_folder', 'intermediateResults'));
  const [settingsRightToLeftReadingOrder, setSettingsRightToLeftReadingOrder] = useState(() => getStoredSetting('right_to_left_reading_order', false));
  const [settingsPerformanceProfile, setSettingsPerformanceProfile] = useState<PerformanceProfile>(() => getStoredSetting('performance_profile', 'balanced'));
  const [settingsPerformanceCustom, setSettingsPerformanceCustom] = useState<PerformanceCustomSettings>(() => getStoredSetting('performance_custom', {
    preview_width: 1200,
    typesetting_candidates: 40,
    ocr_workers: 2,
    prefer_gpu: true,
  }));
  const [settingsAutoFontResize, setSettingsAutoFontResize] = useState(() => getStoredSetting('auto_font_resize', true));
  const [settingsDefaultFontFamily, setSettingsDefaultFontFamily] = useState(() => getStoredSetting('default_font_family', 'Tahoma'));
  const [settingsDefaultTextTemplateId, setSettingsDefaultTextTemplateId] = useState(() => getStoredSetting('default_text_template_id', 'bubble'));
  const [settingsLockTranslationToDetectedBox, setSettingsLockTranslationToDetectedBox] = useState(getStoredTranslationLayoutLock);
  const [settingsMatchSourceFontSize, setSettingsMatchSourceFontSize] = useState(() => getStoredSetting('match_source_font_size', true));
  const [settingsSourceFontScale, setSettingsSourceFontScale] = useState(() => getStoredSetting('source_font_scale', 1.10));
  const [settingsMaxFontSize, setSettingsMaxFontSize] = useState(() => getStoredSetting('max_font_size', 152));
  const [settingsMinFontSize, setSettingsMinFontSize] = useState(() => getStoredSetting('min_font_size', 44));
  const [settingsBinaryThreshold, setSettingsBinaryThreshold] = useState(() => getStoredSetting('binary_threshold', 200));
  const [settingsAutoComputeThreshold, setSettingsAutoComputeThreshold] = useState(() => getStoredSetting('auto_compute_threshold', true));
  const [settingsAutoSelectThresholdFewer, setSettingsAutoSelectThresholdFewer] = useState(() => getStoredSetting('auto_select_threshold_fewer', true));
  const [settingsPixelsToExpandAroundTextbox, setSettingsPixelsToExpandAroundTextbox] = useState(() => getStoredSetting('pixels_to_expand_around_textbox', 5));
  const [settingsExpandAfterBalloonDetection, setSettingsExpandAfterBalloonDetection] = useState(() => getStoredSetting('expand_after_balloon_detection', true));
  const [settingsConvertVerticalArea, setSettingsConvertVerticalArea] = useState(() => getStoredSetting('convert_vertical_area', false));
  const [settingsAvoidBreakingWords, setSettingsAvoidBreakingWords] = useState(() => getStoredSetting('avoid_breaking_words', false));
  const [settingsRestrainAreasWithinImage, setSettingsRestrainAreasWithinImage] = useState(() => getStoredSetting('restrain_areas_within_image', false));
  const [settingsInferTextDirection, setSettingsInferTextDirection] = useState(() => getStoredSetting('infer_text_direction', true));
  const [settingsUseBridgeLanguage, setSettingsUseBridgeLanguage] = useState(() => getStoredSetting('use_bridge_language', false));
  const [settingsBridgeLanguage, setSettingsBridgeLanguage] = useState(() => getStoredSetting('bridge_language', 'en'));
  const [settingsEnableRichText, setSettingsEnableRichText] = useState(() => getStoredSetting('enable_rich_text', false));
  const [settingsEnableCjkVerticalTextEngine, setSettingsEnableCjkVerticalTextEngine] = useState(() => getStoredSetting('enable_cjk_vertical_text_engine', true));
  const [settingsSortCriteria, setSettingsSortCriteria] = useState(() => getStoredSetting('sort_criteria', 'Distance to the origin'));
  const [settingsSortBasedOnPanels, setSettingsSortBasedOnPanels] = useState(() => getStoredSetting('sort_based_on_panels', true));
  const [settingsWhenGeneratingMaskCheckSeparation, setSettingsWhenGeneratingMaskCheckSeparation] = useState(() => getStoredSetting('when_generating_mask_check_separation', true));
  const [settingsConsiderFgBgDepth, setSettingsConsiderFgBgDepth] = useState(() => getStoredSetting('consider_fg_bg_depth', false));
  const [settingsDefaultTextboxWidth, setSettingsDefaultTextboxWidth] = useState(() => getStoredSetting('default_textbox_width', 100));
  const [settingsDefaultTextboxHeight, setSettingsDefaultTextboxHeight] = useState(() => getStoredSetting('default_textbox_height', 50));

  // Text Removal tab options
  const [settingsAccurateTextEraseMode, setSettingsAccurateTextEraseMode] = useState(() => getStoredSetting('accurate_text_erase_mode', 'Image inpainting'));
  const [settingsDefaultMaskGenMethod, setSettingsDefaultMaskGenMethod] = useState(() => getStoredSetting('default_mask_gen_method', 'Built-in binary generator'));
  const [settingsDefaultImageInpaintMethod, setSettingsDefaultImageInpaintMethod] = useState(() => getStoredSetting('default_image_inpaint_method', 'LamaInpaint'));
  const [settingsInpaintEngine, setSettingsInpaintEngine] = useState(() => getStoredSetting('inpaint_engine', 'lama_manga'));
  const [settingsInpaintStrategy, setSettingsInpaintStrategy] = useState(() => getStoredSetting('inpaint_strategy', 'cluster'));
  const [settingsImageInpaintingRadius, setSettingsImageInpaintingRadius] = useState(() => getStoredSetting('image_inpainting_radius', 3));
  const [settingsInpaintContextPadding, setSettingsInpaintContextPadding] = useState(() => getStoredSetting('inpaint_context_padding', 96));
  const [settingsMaskRadiusImprecise, setSettingsMaskRadiusImprecise] = useState(() => getStoredSetting('mask_radius_imprecise', 0));
  const [settingsPixelsToExpandTextAreas, setSettingsPixelsToExpandTextAreas] = useState(() => getStoredSetting('pixels_to_expand_text_areas', 5));
  const [settingsGaussianBlurTimes, setSettingsGaussianBlurTimes] = useState(() => getStoredSetting('gaussian_blur_times', 1));
  const [settingsMaskFeatheringSigma, setSettingsMaskFeatheringSigma] = useState(() => getStoredSetting('mask_feathering_sigma', 0));
  const [settingsInpaintingMaxWidth, setSettingsInpaintingMaxWidth] = useState(() => getStoredSetting('inpainting_max_width', 2048));
  const [settingsSlidingWindowOverlap, setSettingsSlidingWindowOverlap] = useState(() => getStoredSetting('sliding_window_overlap', 5));
  const [settingsGenerateTextMaskOcr, setSettingsGenerateTextMaskOcr] = useState(() => getStoredSetting('generate_text_mask_ocr', true));
  const [settingsEnableSlidingWindows, setSettingsEnableSlidingWindows] = useState(() => getStoredSetting('enable_sliding_windows', false));
  const [settingsMultiplyAlphaChannel, setSettingsMultiplyAlphaChannel] = useState(() => getStoredSetting('multiply_alpha_channel', false));
  const [settingsOcrForMaskGen, setSettingsOcrForMaskGen] = useState(() => getStoredSetting('ocr_for_mask_gen', '{"engine":"paddleocr","lang":"ch"}'));

  // Balloon Detection tab options
  const [settingsEnableSmartBalloon, setSettingsEnableSmartBalloon] = useState(() => getStoredSetting('enable_smart_balloon', false));
  const [settingsBalloonModel, setSettingsBalloonModel] = useState(() => getStoredSetting('balloon_model', 'เวอร์ชั่นเบต้าเทสแอลฟ่าโอเมก้าแห่ง SAO'));
  const [settingsScaleImageBeforeDetection, setSettingsScaleImageBeforeDetection] = useState(() => getStoredSetting('scale_image_before_detection', true));
  const [settingsScaleImageSize, setSettingsScaleImageSize] = useState(() => getStoredSetting('scale_image_size', 1024));
  const [settingsUseFixedImageRatio, setSettingsUseFixedImageRatio] = useState(() => getStoredSetting('use_fixed_image_ratio', false));
  const [settingsFixedImageRatio, setSettingsFixedImageRatio] = useState(() => getStoredSetting('fixed_image_ratio', '1x1'));
  const [settingsHeightToWidthRatioDividing, setSettingsHeightToWidthRatioDividing] = useState(() => getStoredSetting('height_to_width_ratio_dividing', 4));
  const [settingsUseModelParamsFirst, setSettingsUseModelParamsFirst] = useState(() => getStoredSetting('use_model_params_first', true));
  const [settingsStoreDetectedClassFontStyle, setSettingsStoreDetectedClassFontStyle] = useState(() => getStoredSetting('store_detected_class_font_style', false));
  const [settingsExpandSmallImages, setSettingsExpandSmallImages] = useState(() => getStoredSetting('expand_small_images', true));
  
  const [sourceLang, setSourceLang] = useState(() => getStoredSetting('source_lang', 'ko'));
  const [targetLang, setTargetLang] = useState('th');

  const handleToggleProjectSetting = (key: string, val: any) => {
    updateGlobalSetting(key, val);
    if (activeProject) {
      const currentSettings = activeProject.settings || {};
      const updatedSettings = { ...currentSettings, [key]: val };
      const updatedProj = { ...activeProject, settings: updatedSettings };
      useProjectStore.setState({ activeProject: updatedProj });
      fetch(`/api/projects/${activeProject.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: updatedSettings }),
      }).catch(err => console.error(`Failed to persist project setting ${key}:`, err));
    }
  };
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);
  const [isDraggingOverPages, setIsDraggingOverPages] = useState(false);

  // Collapsible Accordion States
  const [layersOpen, setLayersOpen] = useState(true);
  const [layerDecisionFilter, setLayerDecisionFilter] = useState<LayerDecisionFilter>('all');
  const [autoStyleSnapshot, setAutoStyleSnapshot] = useState<AutoStyleSnapshot | null>(null);
  const [trainingOpen, setTrainingOpen] = useState(false);
  const [styleSettingsOpen, setStyleSettingsOpen] = useState(true);
  const useDockedTypographyControls = false;

  // New features states
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.1);
  const [batchProgress, setBatchProgress] = useState<any>(null);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const pendingExactRenderAfterBatchRef = useRef(false);
  const [inpaintPreviewImage, setInpaintPreviewImage] = useState<string | null>(null);
  const [cleanPreviewRevision, setCleanPreviewRevision] = useState(0);
  // Removed unused shortcutSearch to avoid TS compile error

  // System font list for font picker
  const [systemFonts, setSystemFonts] = useState<string[]>([]);
  const [systemFontDetails, setSystemFontDetails] = useState<Record<string, string[]>>({});
  const [systemFontFamilies, setSystemFontFamilies] = useState<Record<string, any>>({});

  const reloadFonts = async (rescan = false): Promise<void> => {
    try {
      const endpoint = rescan ? '/api/fonts/rescan' : '/api/fonts/list';
      const method = rescan ? 'POST' : 'GET';
      const res = await fetch(endpoint, { method });
      const data = await res.json();
      setSystemFonts(data.fonts || []);
      setSystemFontDetails(data.details || {});
      setSystemFontFamilies(data.families || {});
      injectFontStylesheet(true);
      if (rescan) {
        showToast(`🔄 รีเฟรชและโหลดข้อมูลฟอนต์ ${data.count || data.fonts?.length || 0} รายการเรียบร้อยแล้ว`, 'success');
      }
    } catch {
      setSystemFonts(['NotoSansThai', 'Tahoma', 'Arial', 'Calibri']);
      setSystemFontDetails({
        'NotoSansThai': ['regular', 'bold'],
        'Tahoma': ['regular', 'bold'],
        'Arial': ['regular', 'bold', 'italic', 'bold_italic'],
        'Calibri': ['regular', 'bold', 'italic', 'bold_italic']
      });
    }
  };

  useEffect(() => {
    void reloadFonts();
  }, []);

  // Import preview modal state
  const [showImportPreview, setShowImportPreview] = useState(false);
  const [importPreviewData, setImportPreviewData] = useState<any>(null);
  const [importPreviewFile, setImportPreviewFile] = useState<File | null>(null);
  const [excludedLines, setExcludedLines] = useState<Set<number>>(new Set());

  // Automatically initialize excludedLines when preview data is loaded
  useEffect(() => {
    if (importPreviewData?.preview_records) {
      const initialExcludes = new Set<number>();
      importPreviewData.preview_records.forEach((rec: any) => {
        // Exclude errors and skips by default
        if (rec.status === 'error' || rec.status === 'skip') {
          initialExcludes.add(rec.line_number);
        }
      });
      setExcludedLines(initialExcludes);
    }
  }, [importPreviewData]);

  // Debounced/Immediate Block Update with Multi-Selection support
  const handleBlockChange = async (fields: Partial<TextBlock>) => {
    const targets = selectedBlocks.length > 0
      ? selectedBlocks
      : selectedBlock ? [selectedBlock] : [];
    await Promise.all(targets.map((block) => {
      const payload: Partial<TextBlock> = { ...fields };
      const invalidatesLayout = ['translation', 'font_size', 'font_family', 'bold', 'italic', 'text_align', 'text_direction', 'balloon_type', 'rotation_deg', 'color_hex']
        .some((key) => key in fields);
      if (invalidatesLayout) {
        const { typesetting_spec: _staleSpec, ...freshMetadata } = block.extra_metadata || {};
        payload.extra_metadata = {
          ...freshMetadata,
          ...(typeof fields.font_size === 'number'
            ? { manual_font_size: fields.font_size, font_size_mode: 'manual' }
            : {}),
          ...('translation' in fields
            ? {
                line_break_source: 'manual_hard',
                ai_preferred_lines: null,
                ai_layout_hint: null,
                ai_layout_text: null,
              }
            : {}),
        };
      }
      return updateBlock(block.id, payload);
    }));
  };

  const handleBlockMetadataChange = async (metadataPatch: Record<string, unknown>) => {
    const targets = selectedBlocks.length > 0
      ? selectedBlocks
      : selectedBlock ? [selectedBlock] : [];
    await Promise.all(targets.map((block) => {
      const { typesetting_spec: _staleSpec, ...freshMetadata } = block.extra_metadata || {};
      return updateBlock(block.id, {
        extra_metadata: { ...freshMetadata, ...metadataPatch },
      });
    }));
  };

  const applyTextTemplate = async (template: TextTemplate) => {
    const targets = selectedBlocks.length > 0
      ? selectedBlocks
      : selectedBlock ? [selectedBlock] : [];
    if (targets.length === 0) {
      showToast('เลือก Layer อย่างน้อยหนึ่งรายการก่อนใช้ Template', 'info');
      return;
    }
    // Auto-feedback: if user picks a different template than the system's
    // suggested_template_id, treat as system_wrong; pure preference only when
    // there was no system suggestion (or user re-picks same as suggestion after edit).
    for (const block of targets) {
      const prevTemplate = (block.extra_metadata?.text_template_id
        || (block.extra_metadata?.typesetting_spec as { template_id?: string } | undefined)?.template_id
        || '') as string;
      const suggested = (
        (block.extra_metadata?.suggested_template_id as string | undefined)
        || (block.extra_metadata?.typesetting_spec as { metrics?: { style_descriptor?: { suggested_template?: string } } } | undefined)
          ?.metrics?.style_descriptor?.suggested_template
        || ''
      );
      if (template.id && template.id !== prevTemplate) {
        const reason =
          suggested && template.id !== suggested
            ? 'system_wrong'
            : 'user_preference';
        const specLines = (block.extra_metadata?.typesetting_spec as { explicit_lines?: string[] } | undefined)?.explicit_lines;
        const suggestedLines = (block.extra_metadata?.suggested_explicit_lines as string[] | undefined) || specLines;
        const liveText = (block.translation || '').trim();
        const finalLines = liveText ? liveText.split(/\r?\n/) : specLines;
        void recordTypesettingFeedback({
          block_id: block.id,
          change_reason: reason,
          suggested_template: suggested || prevTemplate || undefined,
          selected_template: template.id,
          suggested_lines: suggestedLines,
          final_lines: finalLines,
        }).catch(() => { /* non-blocking */ });
      }
    }
    await updateBlocksBulk(targets.map((block) => ({
      blockId: block.id,
      data: templateBlockFields(template, {
        ...(block.extra_metadata || {}),
        source_font_size: block.extra_metadata?.source_font_size ?? block.font_size,
      }),
    })));
    showToast(`ใช้ Template “${template.name}” กับ ${targets.length} Layer แล้ว`, 'success');
  };

  const openMultiPageStyleEditor = () => {
    const current = selectedBlocks.map(block => block.id);
    setMultiPageSelectedIds(new Set(current));
    setMultiPageSearch('');
    setMultiPageFilter('all');
    setShowMultiPageStyleModal(true);
  };

  const applyMultiPageStyle = async () => {
    if (!activeProject || multiPageSelectedIds.size === 0) {
      showToast('เลือก Layer ข้ามหน้าอย่างน้อยหนึ่งรายการก่อน', 'info');
      return;
    }
    const targets = activeProject.pages.flatMap(page => page.text_blocks)
      .filter(block => multiPageSelectedIds.has(block.id));
    const template = multiPageTemplateKey ? stylePresets[multiPageTemplateKey] : undefined;
    const parsedSize = Number(multiPageFontSize);
    const updates = targets.map(block => {
      const { typesetting_spec: _staleSpec, ...metadata } = block.extra_metadata || {};
      const data: Partial<TextBlock> = template
        ? templateBlockFields(template, {
            ...metadata,
            source_font_size: metadata.source_font_size ?? block.font_size,
          })
        : { extra_metadata: metadata };
      if (multiPageFontFamily) data.font_family = multiPageFontFamily;
      if (Number.isFinite(parsedSize) && parsedSize > 0) {
        data.font_size = parsedSize;
        data.extra_metadata = { ...(data.extra_metadata || metadata), manual_font_size: parsedSize, font_size_mode: 'manual' };
      }
      if (/^#[0-9a-f]{6}$/i.test(multiPageColor)) data.color_hex = multiPageColor;
      if (multiPageBold !== 'keep') data.bold = multiPageBold === 'on';
      if (multiPageItalic !== 'keep') data.italic = multiPageItalic === 'on';
      return { blockId: block.id, data };
    });
    await updateBlocksBulk(updates);
    showToast(`อัปเดต Font/Style ข้ามหน้า ${updates.length} Layer แล้ว`, 'success');
    setShowMultiPageStyleModal(false);
  };

  const templateFromBlock = (name: string, block: TextBlock): TextTemplate => {
    const metadata = block.extra_metadata || {};
    const padding = metadata.padding || {};
    return {
      id: `custom-${Date.now()}`,
      name,
      // AI brace label; empty until user sets it — template id is still the semantic role
      semantic_tag: String(metadata.semantic_role_label || name || ''),
      font_stack: [(
        Array.isArray(metadata.font_stack) && metadata.font_stack.length > 0
          ? metadata.font_stack[0]
          : block.font_family
      )],
      font_size: block.font_size,
      min_font_size: Number(metadata.min_font_size ?? activeProject?.settings?.min_font_size ?? 24),
      max_font_size: Number(metadata.max_font_size ?? activeProject?.settings?.max_font_size ?? 152),
      color_hex: block.color_hex,
      stroke_color: String(metadata.stroke_color ?? '#ffffff'),
      stroke_width: Number(metadata.stroke_width ?? 0),
      bold: block.bold,
      italic: block.italic,
      text_align: block.text_align,
      text_direction: block.text_direction,
      balloon_type: block.balloon_type,
      line_height_ratio: Number(metadata.line_height_ratio ?? 1.2),
      letter_spacing: Number(metadata.letter_spacing ?? 0),
      padding: {
        top: Number(padding.top ?? 0), right: Number(padding.right ?? 0),
        bottom: Number(padding.bottom ?? 0), left: Number(padding.left ?? 0),
      },
    };
  };

  const getCommonValue = <K extends keyof TextBlock>(key: K): TextBlock[K] | undefined | '' => {
    if (selectedBlocks.length === 0) return undefined;
    const firstVal = selectedBlocks[0][key];
    const allSame = selectedBlocks.every(b => b[key] === firstVal);
    return allSame ? firstVal : '';
  };

  const handleLayerSelection = (block: TextBlock, event: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => {
    const ordered = [...(activePage?.text_blocks || [])].sort((a, b) => a.block_index - b.block_index);
    if (event.shiftKey && ordered.length > 0) {
      const anchorId = layerSelectionAnchorRef.current || selectedBlock?.id || block.id;
      const anchorIndex = Math.max(0, ordered.findIndex((item) => item.id === anchorId));
      const targetIndex = ordered.findIndex((item) => item.id === block.id);
      const range = ordered.slice(Math.min(anchorIndex, targetIndex), Math.max(anchorIndex, targetIndex) + 1);
      const next = event.ctrlKey || event.metaKey
        ? [...new Map([...selectedBlocks, ...range].map((item) => [item.id, item])).values()]
        : range;
      useProjectStore.setState({ selectedBlocks: next, selectedBlock: block });
      return;
    }
    layerSelectionAnchorRef.current = block.id;
    if (event.ctrlKey || event.metaKey) {
      const selected = selectedBlocks.some((item) => item.id === block.id);
      const next = selected
        ? selectedBlocks.filter((item) => item.id !== block.id)
        : [...selectedBlocks, block];
      useProjectStore.setState({ selectedBlocks: next, selectedBlock: next.at(-1) || null });
      return;
    }
    useProjectStore.setState({ selectedBlocks: [block], selectedBlock: block });
  };

  const hasEyeDropper = typeof window !== 'undefined' && 'EyeDropper' in window;

  const handleEyedropperClick = async () => {
    if (!hasEyeDropper) {
      showToast("Your browser does not support the EyeDropper API", "info");
      return;
    }
    try {
      // @ts-ignore
      const eyeDropper = new window.EyeDropper();
      const result = await eyeDropper.open();
      if (result && result.sRGBHex) {
        handleBlockChange({ color_hex: result.sRGBHex });
        showToast(`Sampled color: ${result.sRGBHex}`, 'success');
      }
    } catch (err) {
      console.warn("Eyedropper cancelled or failed:", err);
    }
  };

  // Connect WebSocket
  const { isConnected, lastMessage } = useWebSocket(activeProject?.id || null);
  const lastProcessedWSMessageRef = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const txtFileInputRef = useRef<HTMLInputElement>(null);
  const psdFileInputRef = useRef<HTMLInputElement>(null);


  // Training state
  const [trainStatus, setTrainStatus] = useState<TrainStatus>({
    is_training: false,
    epoch_current: 0,
    epoch_total: 10,
    loss_current: 0.0,
    eta_seconds: 0,
    log: []
  });

  // Toast notifications state
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Diagnostics states
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [diagnosticsHealth, setDiagnosticsHealth] = useState<any>(null);
  const [e2eReport, setE2eReport] = useState<any>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [activeReportTab, setActiveReportTab] = useState('05_after_detect');

  const fetchDiagnostics = async () => {
    setDiagnosticsLoading(true);
    try {
      const [hRes, rRes] = await Promise.all([
        fetch('/api/diagnostics/health'),
        fetch('/api/diagnostics/e2e-report')
      ]);
      if (hRes.ok) {
        setDiagnosticsHealth(await hRes.json());
      } else {
        setDiagnosticsHealth(null);
      }
      if (rRes.ok) {
        setE2eReport(await rRes.json());
      } else {
        setE2eReport(null);
      }
    } catch (err) {
      console.error("Failed to fetch diagnostics:", err);
      setDiagnosticsHealth(null);
      setE2eReport(null);
    } finally {
      setDiagnosticsLoading(false);
    }
  };

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  };

  // Startup Model & Asset Integrity Check
  const [missingModelsWarning, setMissingModelsWarning] = useState<string[] | null>(null);

  useEffect(() => {
    fetch('/api/diagnostics/models-audit')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && data.missing_critical_count > 0) {
          setMissingModelsWarning(data.missing_critical_names);
          showToast(`⚠️ ตรวจพบโมเดล AI ขาดหายไป ${data.missing_critical_count} ตัว (${data.missing_critical_names.join(', ')})`, 'error');
        }
      })
      .catch(() => {});
  }, []);

  const waitForCanvasRenderCapture = async (pageId: string): Promise<CanvasRenderCapture> => {
    const deadline = Date.now() + 45_000;
    while (Date.now() < deadline) {
      const state = useProjectStore.getState();
      if (state.canvasRenderPageId === pageId && state.getCanvasRenderCapture) {
        const capture = await state.getCanvasRenderCapture(true);
        if (capture?.pageId === pageId) return capture;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 80));
    }
    throw new Error(`Canvas render timed out for page ${pageId}`);
  };

  const responseError = async (response: Response): Promise<string> => {
    try {
      const payload = await response.json();
      return String(payload.detail || payload.message || `HTTP ${response.status}`);
    } catch {
      return `HTTP ${response.status}`;
    }
  };

  const captureAndUploadExactPage = async (pageId: string): Promise<string> => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await flushPendingBlockUpdates();
      const readyPage = useProjectStore.getState().activePage;
      if (!readyPage || readyPage.id !== pageId) {
        throw new Error(`Page ${pageId} is not active in the canvas`);
      }
      const backgroundKind = readyPage.inpainted_image_path ? 'clean' : 'source';
      const contractResponse = await fetch(
        `/api/pages/${pageId}/render-contract?background_kind=${backgroundKind}`,
      );
      if (!contractResponse.ok) throw new Error(await responseError(contractResponse));
      const contract = await contractResponse.json();

      const capture = await waitForCanvasRenderCapture(pageId);
      const form = new FormData();
      form.append('file', capture.blob, `${String(readyPage.page_number).padStart(2, '0')}_text.png`);
      form.append('revision', String(contract.revision));
      form.append('background_kind', backgroundKind);
      const uploadResponse = await fetch(`/api/pages/${pageId}/rendered-overlay`, {
        method: 'PUT',
        body: form,
      });
      if (uploadResponse.ok) {
        const result = await uploadResponse.json();
        return String(result.path || '');
      }
      if (uploadResponse.status === 409 && attempt === 0) {
        await selectPage(pageId);
        continue;
      }
      throw new Error(await responseError(uploadResponse));
    }
    throw new Error(`Exact render failed for page ${pageId}`);
  };

  const renderAllPagesExact = async (): Promise<string[]> => {
    const state = useProjectStore.getState();
    const project = state.activeProject;
    if (!project) throw new Error('No project is open');
    const pages = [...project.pages].sort((a, b) => a.page_number - b.page_number);
    if (pages.length === 0) throw new Error('Project has no pages');
    const originalPageId = state.activePage?.id || pages[0].id;
    const paths: string[] = [];

    try {
      for (let index = 0; index < pages.length; index += 1) {
        const page = pages[index];
        setBatchProgress({
          status: 'running',
          progress: index / pages.length,
          current_page: index + 1,
          total_pages: pages.length,
          step: 'exact-render',
          error: null,
        });
        setStatus(`Exact Render: page ${index + 1}/${pages.length}…`, true);
        if (useProjectStore.getState().activePage?.id !== page.id) {
          await selectPage(page.id);
        }
        paths.push(await captureAndUploadExactPage(page.id));
      }
      setBatchProgress({
        status: 'success',
        progress: 1,
        current_page: pages.length,
        total_pages: pages.length,
        step: 'exact-render',
        error: null,
      });
      return paths;
    } finally {
      // Refresh and restore the page that was open before the serial capture.
      await selectPage(originalPageId);
      setStatus('Exact render ready', false);
    }
  };

  // Load projects list on mount and auto-select active project
  useEffect(() => {
    const initProjects = async () => {
      await fetchProjects();
      const store = useProjectStore.getState();
      if (!store.activeProject && store.projects && store.projects.length > 0) {
        const lastId = localStorage.getItem('houmi_last_project_id');
        const target = (lastId ? store.projects.find(p => p.id === lastId) : null) ||
                       store.projects.find(p => ['352', '196', '14', '115', '43', '137', '138'].includes(p.name)) ||
                       store.projects[0];
        if (target) {
          await store.selectProject(target.id);
        }
      }
    };
    void initProjects();
  }, []);

  // Sync active project settings to match global settings on load
  useEffect(() => {
    if (activeProject) {
      const syncActiveProjectSettings = async () => {
        const updatedSettings = {
          ...(activeProject.settings || {}),
          mask_dilation_kernel: settingsMaskDilationKernel,
          process_by_text_areas: settingsProcessByTextAreas,
          cleanup_mask_strategy: settingsCleanupMaskStrategy,
          force_lama_inpaint: settingsForceLamaInpaint,
          cleanup_pipeline_profile: settingsCleanupPipelineProfile,
          vertical_to_horizontal: settingsVerticalToHorizontal,
          strip_furigana: settingsStripFurigana,
          use_chinese_punctuation: settingsUseChinesePunctuation,
          remove_spaces: settingsRemoveSpaces,
          auto_ocr: settingsAutoOcr,
          auto_remove_line_breaks: settingsAutoRemoveLineBreaks,
          default_txt_mode: settingsDefaultTxtMode,
          read_subfolders: settingsReadSubfolders,
          intermediate_results_folder: settingsIntermediateResultsFolder,
          right_to_left_reading_order: settingsRightToLeftReadingOrder,
          performance_profile: settingsPerformanceProfile,
          performance_custom: settingsPerformanceCustom,
          auto_font_resize: settingsAutoFontResize,
          default_font_family: settingsDefaultFontFamily,
          default_text_template_id: settingsDefaultTextTemplateId,
          text_templates: stylePresets,
          lock_translation_to_detected_box: settingsLockTranslationToDetectedBox,
          match_source_font_size: settingsMatchSourceFontSize,
          source_font_scale: settingsSourceFontScale,
          max_font_size: settingsMaxFontSize,
          min_font_size: settingsMinFontSize,
          binary_threshold: settingsBinaryThreshold,
          auto_compute_threshold: settingsAutoComputeThreshold,
          auto_select_threshold_fewer: settingsAutoSelectThresholdFewer,
          pixels_to_expand_around_textbox: settingsPixelsToExpandAroundTextbox,
          expand_after_balloon_detection: settingsExpandAfterBalloonDetection,
          convert_vertical_area: settingsConvertVerticalArea,
          avoid_breaking_words: settingsAvoidBreakingWords,
          restrain_areas_within_image: settingsRestrainAreasWithinImage,
          infer_text_direction: settingsInferTextDirection,
          use_bridge_language: settingsUseBridgeLanguage,
          bridge_language: settingsBridgeLanguage,
          enable_rich_text: settingsEnableRichText,
          enable_cjk_vertical_text_engine: settingsEnableCjkVerticalTextEngine,
          sort_criteria: settingsSortCriteria,
          sort_based_on_panels: settingsSortBasedOnPanels,
          when_generating_mask_check_separation: settingsWhenGeneratingMaskCheckSeparation,
          consider_fg_bg_depth: settingsConsiderFgBgDepth,
          default_textbox_width: settingsDefaultTextboxWidth,
          default_textbox_height: settingsDefaultTextboxHeight,
          accurate_text_erase_mode: settingsAccurateTextEraseMode,
          default_mask_gen_method: settingsDefaultMaskGenMethod,
          default_image_inpaint_method: settingsDefaultImageInpaintMethod,
          image_inpainting_radius: settingsImageInpaintingRadius,
          inpaint_context_padding: settingsInpaintContextPadding,
          mask_radius_imprecise: settingsMaskRadiusImprecise,
          pixels_to_expand_text_areas: settingsPixelsToExpandTextAreas,
          gaussian_blur_times: settingsGaussianBlurTimes,
          mask_feathering_sigma: settingsMaskFeatheringSigma,
          inpainting_max_width: settingsInpaintingMaxWidth,
          sliding_window_overlap: settingsSlidingWindowOverlap,
          generate_text_mask_ocr: settingsGenerateTextMaskOcr,
          enable_sliding_windows: settingsEnableSlidingWindows,
          multiply_alpha_channel: settingsMultiplyAlphaChannel,
          ocr_for_mask_gen: settingsOcrForMaskGen,
          balloon_model: settingsBalloonModel,
          scale_image_before_detection: settingsScaleImageBeforeDetection,
          scale_image_size: settingsScaleImageSize,
          use_fixed_image_ratio: settingsUseFixedImageRatio,
          fixed_image_ratio: settingsFixedImageRatio,
          height_to_width_ratio_dividing: settingsHeightToWidthRatioDividing,
          use_model_params_first: settingsUseModelParamsFirst,
          store_detected_class_font_style: settingsStoreDetectedClassFontStyle,
          expand_small_images: settingsExpandSmallImages,
        };
        
        let hasDiff = false;
        for (const [k, v] of Object.entries(updatedSettings)) {
          const currentValue = activeProject.settings?.[k];
          const isEqual = typeof v === 'object' && v !== null
            ? JSON.stringify(currentValue) === JSON.stringify(v)
            : currentValue === v;
          if (!isEqual) {
            hasDiff = true;
            break;
          }
        }
        
        if (hasDiff) {
          const signature = JSON.stringify(updatedSettings);
          if (lastSettingsSyncSignatureRef.current === signature) return;
          lastSettingsSyncSignatureRef.current = signature;
          useProjectStore.setState({
            activeProject: { ...activeProject, settings: updatedSettings }
          });
          try {
            await updateProjectSettings(activeProject.id, updatedSettings);
          } catch (err) {
            lastSettingsSyncSignatureRef.current = '';
            console.error("Failed to sync global settings to project:", err);
          }
        }
      };
      
      syncActiveProjectSettings();
    }
  }, [activeProject?.id]);

  // Keep the active workspace inspector visible after a canvas selection.
  useEffect(() => {
    if (selectedBlock) {
      setRightSidebarOpen(true);
    }
  }, [selectedBlock]);

  // Keyboard listener for Navigation and Export keys
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || (activeEl as HTMLElement).isContentEditable);
      
      if (isInput) return;

      if (matchBinding(keyBindings.exportOcrTxt, e)) {
        e.preventDefault();
        if (activeProject) {
          handleExport('txt', 'ocr');
        }
      }
      if (matchBinding(keyBindings.prevPage, e)) {
        e.preventDefault();
        selectPrevPage();
      }
      if (matchBinding(keyBindings.nextPage, e)) {
        e.preventDefault();
        selectNextPage();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeProject, activePage]);

  // Handle WebSocket messages
  useEffect(() => {
    if (!lastMessage || lastProcessedWSMessageRef.current === lastMessage) return;
    lastProcessedWSMessageRef.current = lastMessage;

    if (lastMessage.type === 'dobkle_ocr_progress') {
      const dData = lastMessage as unknown as DobkleProgressData;
      setDobkleProgress(dData);
      setIsDobkleModalOpen(true);
      if (dData.phase === 'completed') {
        setTimeout(() => {
          setIsDobkleModalOpen(false);
          setDobkleProgress(null);
        }, 3500);
      }
    }

    if (lastMessage.type === 'batch_progress') {
      const { status, progress, current_page, total_pages, error, step } = lastMessage;
      const normalizedStatus = String(status || '').toLowerCase();
      setBatchProgress({ status, progress, current_page, total_pages, error });

      if (normalizedStatus === 'running') {
        setIsBatchRunning(true);
        const pct = Math.round((progress || 0) * 100);
        setStatus(`Batch Pipeline (${current_page}/${total_pages}): ${(step || '').toUpperCase()} — ${pct}%…`, false);
      } else if (normalizedStatus === 'success') {
        if (pendingExactRenderAfterBatchRef.current && activeProject) {
          pendingExactRenderAfterBatchRef.current = false;
          const projectId = activeProject.id;
          void (async () => {
            try {
              setIsBatchRunning(true);
              setCleanPreviewRevision(Date.now());
              await selectProject(projectId);
              await renderAllPagesExact();
              showToast('Batch processing and Exact Render completed!', 'success');
            } catch (error: any) {
              setBatchProgress((current: any) => ({
                ...(current || {}),
                status: 'failed',
                error: error.message,
              }));
              showToast(`Exact Render failed: ${error.message}`, 'error');
            } finally {
              setIsBatchRunning(false);
              setStatus('Ready', false);
            }
          })();
          return;
        }
        setIsBatchRunning(false);
        setStatus('Batch processing completed successfully!', false);
        setCleanPreviewRevision(Date.now());
        showToast('Batch processing completed successfully!', 'success');
        if (activeProject) {
          selectProject(activeProject.id);
        }
        setTimeout(() => setBatchProgress(null), 3000);
      } else if (normalizedStatus === 'failed') {
        setIsBatchRunning(false);
        setStatus(`Batch processing failed: ${error}`, false);
        showToast(`Batch processing failed: ${error}`, 'error');
        setTimeout(() => setBatchProgress(null), 3000);
      } else if (normalizedStatus === 'cancelled') {
        setIsBatchRunning(false);
        setStatus('Ready', false);
        setBatchProgress(null);
        showToast('Batch workflow cancelled', 'info');
      }
    } else if (lastMessage.type === 'page_progress') {
      const { status, step, error } = lastMessage;
      const normalizedStatus = String(status || '').toLowerCase();
      if (normalizedStatus === 'running') {
        setStatus(`Running Auto Pipeline: ${step.toUpperCase()}…`, true);
      } else if (normalizedStatus === 'success') {
        setStatus('Auto Pipeline completed successfully!', false);
        setCleanPreviewRevision(Date.now());
        showToast('Auto Pipeline completed successfully!', 'success');
        if (activePage) {
          selectPage(activePage.id);
        }
      } else if (normalizedStatus === 'error' || normalizedStatus === 'failed') {
        setStatus(`Auto Pipeline failed: ${error}`, false);
        showToast(`Auto Pipeline failed: ${error}`, 'error');
      } else if (normalizedStatus === 'cancelled') {
        setStatus('Auto Pipeline cancelled', false);
        showToast('Auto Pipeline cancelled', 'info');
      }
    } else if (lastMessage.type === 'mask_progress') {
      const { status, page_id, error } = lastMessage;
      if (status === 'running') {
        setStatus('กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…', true);
      } else if (status === 'success') {
        setStatus('คลีนภาพเฉพาะบริเวณเสร็จสมบูรณ์เรียบร้อย', false);
        setCleanPreviewRevision(Date.now());
        showToast('อัปเดตภาพ Clean ล่าสุดเรียบร้อยแล้ว (Reclean Success)', 'success');
        if (activePage?.id === page_id) {
          selectPage(page_id);
        }
      } else if (status === 'error') {
        setStatus(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, false);
        showToast(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, 'error');
      }
    } else if (lastMessage.type === 'train_status') {
      setTrainStatus(lastMessage.status);
    }
  }, [lastMessage, activeProject, activePage]);

  // Handle Project Creation
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;
    try {
      let chosenProfile = clientProfiles.find(p => p.id === selectedClientId) || clientProfiles[0];
      if (isCreatingNewClient && newClientNameInput.trim()) {
        const newProf = createClientProjectProfile(newClientNameInput.trim());
        const updatedProfiles = [...clientProfiles, newProf];
        setClientProfiles(updatedProfiles);
        localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updatedProfiles));
        chosenProfile = newProf;
        setSelectedClientId(newProf.id);
      }
      const clientSettings = chosenProfile ? clientProfileToProjectSettings(chosenProfile) : {};
      const proj = await createProject(newProjName, sourceLang, targetLang, clientSettings);
      showToast(`สร้างโปรเจกต์ "${proj.name}" สำหรับลูกค้า ${chosenProfile?.name || 'ทั่วไป'} สำเร็จ!`, 'success');
      setNewProjName('');
      setShowNewProjModal(false);
      setIsCreatingNewClient(false);
      setNewClientNameInput('');
      await selectProject(proj.id);
    } catch (err: any) {
      console.error(err);
      showToast(`Failed to create project: ${err.message}`, 'error');
    }
  };

  const handleSaveProjectPreset = async (
    newSourceLang: string,
    chosenProfile: ClientProjectProfile,
    newOcrEngine?: string,
    newBalloonModel?: string
  ) => {
    if (!activeProject) return;
    try {
      const clientSettings = clientProfileToProjectSettings(chosenProfile);
      const mergedSettings = {
        ...(activeProject.settings || {}),
        ...clientSettings,
        source_lang: newSourceLang,
        ...(newOcrEngine ? { ocr_engine: newOcrEngine } : {}),
        ...(newBalloonModel ? { balloon_model: newBalloonModel } : {}),
      };
      const updatedProj = { ...activeProject, source_lang: newSourceLang, settings: mergedSettings };
      useProjectStore.setState({ activeProject: updatedProj });
      setSourceLang(newSourceLang);
      localStorage.setItem('houmi_source_lang', newSourceLang);
      localStorage.setItem(ACTIVE_CLIENT_PROFILE_STORAGE_KEY, chosenProfile.id);
      localStorage.setItem('houmi_active_client_profile_id', chosenProfile.id);
      setSelectedClientId(chosenProfile.id);

      if (newOcrEngine) {
        setOcrEngine(newOcrEngine);
        updateGlobalSetting('ocr_engine', newOcrEngine);
        localStorage.setItem('houmi_ocr_engine', newOcrEngine);
      }

      await fetch(`/api/projects/${activeProject.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: mergedSettings, source_lang: newSourceLang }),
      });
      showToast(`ตั้งค่าภาษา (${newSourceLang}) และโปรไฟล์ลูกค้า "${chosenProfile.name}" เป็นค่ามาตรฐานถาวรเรียบร้อยแล้ว!`, 'success');
    } catch (err: any) {
      console.error('Failed to update project preset:', err);
      showToast('ไม่สามารถอัปเดตตั้งค่าโปรเจกต์ได้: ' + err.message, 'error');
    }
  };

  // Unused handleSelectFolder and handleSaveSettings removed to prevent compilation errors

  // Handle Page Upload
  const handlePageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!activeProject || !e.target.files || e.target.files.length === 0) return;
    
    const files = Array.from(e.target.files).sort((a, b) => a.name.localeCompare(b.name));
    
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const pageNum = (activeProject.pages?.length || 0) + i + 1;
        await uploadPage(activeProject.id, pageNum, file);
      }
      showToast(`Successfully uploaded ${files.length} page(s)!`, 'success');
      
      // Auto OCR trigger if enabled
      if (activeProject?.settings?.auto_ocr ?? true) {
        showToast("เริ่มต้นตรวจจับและ OCR อัตโนมัติ...", "info");
        await runPipelineStep('detect');
        await runPipelineStep('ocr');
      }
    } catch (err: any) {
      showToast(`Upload failed: ${err.message}`, 'error');
    }
  };

  // Handle user-translated TXT import — 2-phase: preview → confirm → import
  const handleImportTxt = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!activeProject || !e.target.files || e.target.files.length === 0) return;
    
    const file = e.target.files[0];
    setStatus("กำลังตรวจสอบไฟล์คำแปล...", true);
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetch(`/api/import/txt/preview?project_id=${activeProject.id}`, {
        method: "POST",
        body: formData,
      });
      
      if (!res.ok) {
        throw new Error(`Preview failed with status ${res.status}`);
      }
      
      const data = await res.json();
      setImportPreviewData(data);
      setImportPreviewFile(file);
      setShowImportPreview(true);
    } catch (err: any) {
      showToast(`ตรวจสอบไฟล์ล้มเหลว: ${err.message}`, 'error');
    } finally {
      setStatus("", false);
      e.target.value = "";
    }
  };

  const handleConfirmImport = async () => {
    if (!activeProject || !importPreviewFile) return;

    setShowImportPreview(false);
    setStatus("กำลังนำเข้าคำแปล...", true);

    const formData = new FormData();
    formData.append("file", importPreviewFile);

    const excludeParam = Array.from(excludedLines).join(',');
    try {
      const res = await fetch(`/api/import/txt?project_id=${activeProject.id}&exclude_lines=${excludeParam}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Import failed with status ${res.status}`);
      }

      const data = await res.json();
      if (data.success) {
        const skipped = data.skipped_empty_count ? `, ข้าม ${data.skipped_empty_count} ว่าง` : '';
        const unmatched = data.skipped_unmatched_count
          ? `, ข้าม ${data.skipped_unmatched_count} ไม่ตรงกัน`
          : '';
        showToast(`นำเข้า ${data.updated_count} บล็อกสำเร็จ${skipped}${unmatched}`, 'success');

        const currentActivePageId = activePage?.id;
        await selectProject(activeProject.id);
        if (currentActivePageId) {
          await selectPage(currentActivePageId);
        }
      } else {
        const errorMsg = data.errors && data.errors.length > 0
          ? data.errors.slice(0, 3).join("; ") + (data.errors.length > 3 ? '...' : '')
          : "Unknown validation error";
        showToast(`นำเข้าล้มเหลว: ${errorMsg}`, 'error');
      }
    } catch (err: any) {
      showToast(`นำเข้าล้มเหลว: ${err.message}`, 'error');
    } finally {
      setStatus("", false);
      setImportPreviewFile(null);
      setImportPreviewData(null);
    }
  };

  const handleImportPsd = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!activeProject || !activePage || !e.target.files || e.target.files.length === 0) return;
    
    const file = e.target.files[0];
    setStatus("Importing PSD translation...", true);
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetch(`/api/import/psd?page_id=${activePage.id}`, {
        method: "POST",
        body: formData,
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: `Import failed: ${res.statusText}` }));
        throw new Error(errorData.detail || `Import failed with status ${res.status}`);
      }
      
      const data = await res.json();
      if (data.success && data.updated_blocks) {
        showToast(`Successfully imported ${data.updated_blocks.length} text layer(s) from PSD!`, 'success');
        
        const currentActivePageId = activePage.id;
        await selectProject(activeProject.id);
        if (currentActivePageId) {
          await selectPage(currentActivePageId);
        }
      } else {
        const errorMsg = data.errors && data.errors.length > 0 
          ? data.errors.join("; ")
          : "Unknown validation error";
        showToast(`Import failed: ${errorMsg}`, 'error');
      }
    } catch (err: any) {
      showToast(`Import failed: ${err.message}`, 'error');
    } finally {
      setStatus("", false);
      e.target.value = "";
    }
  };

  // handleBlockChange has been moved to top-level helpers definition block for hoisting safety

  // Trigger Pipeline API calls
  const runPipelineStep = async (step: 'detect' | 'ocr' | 'sort' | 'mask' | 'inpaint' | 'font_judge' | 'render' | 'auto', blockIds?: string[]): Promise<boolean> => {
    const targetPage = useProjectStore.getState().activePage || activePage;
    if (!targetPage) return false;
    
    // Discard any pending debounced updates so stale values don't overwrite fresh pipeline results
    discardPendingBlockUpdates();
    useProjectStore.setState({ undoStack: [], redoStack: [] });

    const storeState = useProjectStore.getState();
    const targetedBlockIds = blockIds && blockIds.length > 0
      ? blockIds
      : (storeState.selectedBlocks.length > 0
          ? storeState.selectedBlocks.map(b => b.id)
          : (storeState.selectedBlock ? [storeState.selectedBlock.id] : []));
    const isTargetedOcr = step === 'ocr' && targetedBlockIds.length > 0;

    // Only full-page operations show the full blocking canvas overlay
    setStatus(`Running Pipeline: ${step.toUpperCase()}…`, !isTargetedOcr);
    
    try {
      if (step === 'render') {
        await captureAndUploadExactPage(targetPage.id);
        await selectPage(targetPage.id);
        setStatus('Exact Preview Render completed successfully!', false);
        showToast('Render ตรงกับ Preview แล้ว (Fabric Exact)', 'success');
        return true;
      }

      if (step === 'inpaint' || step === 'auto') {
        const getMask = useProjectStore.getState().getCanvasMaskBlob;
        if (getMask) {
          try {
            const maskData = await Promise.race([
              getMask(),
              new Promise<null>((resolve) => setTimeout(() => resolve(null), 2000)),
            ]);
            if (maskData) {
              await useProjectStore.getState().uploadPageMask(targetPage.id, maskData);
            }
          } catch (maskErr) {
            console.warn('Canvas mask pre-upload skipped:', maskErr);
          }
        }
      }

      let url = `/api/pipeline/${step}?page_id=${targetPage.id}`;
      let options: RequestInit = {
        method: 'POST'
      };

      if (step === 'sort') {
        url = `/api/pipeline/sort?page_id=${targetPage.id}`;
      } else if (step === 'ocr') {
        if (targetedBlockIds.length > 0) {
          url += `&block_ids=${targetedBlockIds.join(',')}`;
        }
        url += `&backend=${ocrEngine}`;
        const currentLang = activeProject?.source_lang || sourceLang || 'zh';
        url += `&source_lang=${encodeURIComponent(currentLang)}`;
      } else if (step === 'detect') {
        url += `&backend=${ocrEngine}`;
        const currentModel = activeProject?.settings?.balloon_model || settingsBalloonModel;
        if (currentModel) {
          url += `&balloon_model=${encodeURIComponent(currentModel)}`;
        }
      } else if (step === 'font_judge') {
        url = `/api/pipeline/font_judge?page_id=${targetPage.id}`;
      } else if (step === 'typeset') {
        url = `/api/pipeline/typeset?page_id=${targetPage.id}`;
      } else if (step === 'auto') {
        const targetProj = useProjectStore.getState().activeProject || activeProject;
        const currentLang = targetProj?.source_lang || sourceLang || 'zh';
        const currentModel = targetProj?.settings?.balloon_model || settingsBalloonModel;
        url = `/api/pipeline/auto/background?page_id=${targetPage.id}&project_id=${targetProj?.id}&backend=${ocrEngine}&source_lang=${encodeURIComponent(currentLang)}&balloon_model=${encodeURIComponent(currentModel || '')}`;
      }
      if (step === 'detect' || step === 'auto') {
        url += `&min_confidence=${confidenceThreshold}`;
      }

      const res = await apiFetch(url, options);
      if (!res.ok) throw new Error(`Pipeline step ${step} failed`);
      const resultData = await res.json().catch(() => ({}));
      
      if (step === 'auto') {
        // The background task has started. We will rely on WebSocket 'page_progress' 
        // to show status and eventually refresh the page.
        return true;
      }

      if (isTargetedOcr) {
        // Targeted OCR: lightweight refresh that preserves current block selection and updates text
        const pageRes = await apiFetch(`/api/pages/${targetPage.id}`);
        if (pageRes.ok) {
          const freshPage = await pageRes.json();
          const store = useProjectStore.getState();
          const activeProj = store.activeProject;
          const updatedPages = activeProj ? activeProj.pages.map(p => p.id === freshPage.id ? freshPage : p) : [];
          
          const currentSelectedId = store.selectedBlock?.id;
          const freshSelectedBlock = currentSelectedId 
            ? freshPage.text_blocks.find((b: any) => b.id === currentSelectedId) || null
            : null;
          const freshSelectedBlocks = store.selectedBlocks
            .map((sb: any) => freshPage.text_blocks.find((b: any) => b.id === sb.id))
            .filter(Boolean);

          useProjectStore.setState({
            activePage: freshPage,
            activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
            selectedBlock: freshSelectedBlock,
            selectedBlocks: freshSelectedBlocks
          });
        }
        discardPendingBlockUpdates();
      } else {
        // Full-page operations (detect, inpaint, render, or full-page OCR)
        const currentSelectedId = useProjectStore.getState().selectedBlock?.id;
        await selectPage(targetPage.id);
        if (currentSelectedId) {
          const state = useProjectStore.getState();
          const restoredBlock = state.activePage?.text_blocks.find(b => b.id === currentSelectedId);
          if (restoredBlock) {
            useProjectStore.setState({ selectedBlock: restoredBlock, selectedBlocks: [restoredBlock] });
          }
        }
        discardPendingBlockUpdates();
      }

      if (step === 'inpaint') {
        setCleanPreviewRevision(Date.now());
      }

      if (step === 'detect') {
        const count = Number(resultData.detected_blocks_count || 0);
        showToast(`Detect สำเร็จ: ตรวจพบบอลลูน/กล่องข้อความ ${count} จุด`, 'info');
      }

      setStatus(`Pipeline step ${step} completed successfully!`, false);
      showToast(`Pipeline step ${step.toUpperCase()} completed successfully!`, 'success');
      return true;

    } catch (err: any) {
      setStatus(`Pipeline Error: ${err.message}`, false);
      showToast(`Pipeline Error: ${err.message}`, 'error');
      return false;
    }
  };

  const handleRunInpaintPreview = async () => {
    if (!activePage) return;
    await flushPendingBlockUpdates();
    const getMask = useProjectStore.getState().getCanvasMaskBlob;
    if (getMask) {
      const maskData = await getMask();
      if (maskData) {
        await useProjectStore.getState().uploadPageMask(activePage.id, maskData);
      }
    }
    
    setStatus("Generating Inpaint Preview...", true);
    try {
      const res = await apiFetch(`/api/pipeline/inpaint-preview?page_id=${activePage.id}`);
      if (!res.ok) throw new Error("Failed to generate inpaint preview");
      const data = await res.json();
      if (data.status === "success" && data.image) {
        setInpaintPreviewImage(data.image);
        showToast("Inpaint preview generated successfully!", "success");
      } else {
        throw new Error(data.detail || "Invalid inpaint preview response");
      }
    } catch (err: any) {
      showToast(`Inpaint preview error: ${err.message}`, "error");
    } finally {
      setStatus("Ready", false);
    }
  };

  const refreshActivePage = async () => {
    if (!activePage) return;
    await flushPendingBlockUpdates();
    await selectPage(activePage.id);
    showToast(`รีเฟรชหน้า ${activePage.page_number} แล้ว`, 'success');
  };

  const resetMasksAndClean = async (scope: 'page' | 'project') => {
    if (!activePage || !activeProject) return;
    const label = scope === 'page' ? `หน้า ${activePage.page_number}` : 'ทุกหน้าในโปรเจกต์';
    if (!window.confirm(`ลบมาสก์ที่แก้เองและผลคลีนเดิมของ ${label} แล้วคลีนใหม่หรือไม่?`)) return;
    const query = scope === 'page' ? `page_id=${activePage.id}` : `project_id=${activeProject.id}`;
    const response = await apiFetch(`/api/pipeline/masks?${query}`, { method: 'DELETE' });
    if (!response.ok) {
      showToast('ล้างมาสก์ไม่สำเร็จ', 'error');
      return;
    }
    if (scope === 'page') {
      setStatus('กำลังคลีนหน้าปัจจุบันด้วย Mask ใหม่...', true);
      const cleanResponse = await apiFetch(`/api/pipeline/inpaint?page_id=${activePage.id}`, { method: 'POST' });
      if (!cleanResponse.ok) {
        setStatus('Clean failed', false);
        showToast('คลีนหน้าใหม่ไม่สำเร็จ', 'error');
        return;
      }
      await selectPage(activePage.id);
      setCleanPreviewRevision(Date.now());
      setStatus('Ready', false);
      showToast('ล้าง Mask และคลีนหน้าปัจจุบันใหม่แล้ว', 'success');
    } else await runBatchPipeline('inpaint');
  };

  const reorganizePageText = async () => {
    if (!activePage) return;
    setStatus('กำลังตรวจ Balloon และจัด Text ใหม่...', true);
    try {
      const response = await fetch(`/api/typesetting/recompute/page/${activePage.id}`, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await selectPage(activePage.id);
      showToast('จัดกรอบและขนาด Text ใหม่จาก Balloon แล้ว', 'success');
    } catch (error: any) {
      showToast(`จัด Text ใหม่ไม่สำเร็จ: ${error.message}`, 'error');
    } finally {
      setStatus('Ready', false);
    }
  };

  const runAutoStylePage = async (applyTemplate = false) => {
    if (!activePage) return;
    // Gate 2 not certified: default and primary button are suggest-only.
    // Batch auto-apply is blocked until calibrated confidence exists.
    if (applyTemplate) {
      showToast(
        'Auto-apply ถูกปิดชั่วคราวจนกว่า Gate 2 (calibrated confidence) จะผ่าน — ใช้ Suggest Only',
        'info',
      );
      applyTemplate = false;
    }
    setStatus('Style Judge: วิเคราะห์สไตล์ทั้งหน้า (suggest-only)...', true);
    try {
      // Snapshot for Undo Auto Style (if apply is later re-enabled)
      const snap = captureAutoStyleSnapshot(activePage.id, activePage.text_blocks || []);
      setAutoStyleSnapshot(snap);

      const result = await runStyleJudge({
        page_id: activePage.id,
        apply_template: false,
        confidence_auto_threshold: 0.90,
        recompute_layout: true,
      });
      await refreshPagePreservingSelection(activePage.id);
      const applied = (result.results || []).filter(
        (r: any) => r?.style?.applied,
      ).length;
      const review = (result.results || []).filter(
        (r: any) => r?.typesetting_spec?.decision_status === 'NEEDS_REVIEW',
      ).length;
      if (review > 0) setLayerDecisionFilter('NEEDS_REVIEW');
      showToast(
        `Style Judge (suggest-only) ${result.count} กล่อง · auto-apply ${applied} · review ${review}${review > 0 ? ' · เปิด Review Queue' : ''}`,
        review > 0 ? 'info' : 'success',
      );
    } catch (error: any) {
      showToast(`Style Judge ล้มเหลว: ${error.message}`, 'error');
    } finally {
      setStatus('Ready', false);
    }
  };

  const undoAutoStylePage = async () => {
    if (!activePage || !autoStyleSnapshot || autoStyleSnapshot.pageId !== activePage.id) {
      showToast('ไม่มี snapshot สำหรับ Undo Auto Style บนหน้านี้', 'info');
      return;
    }
    setStatus('Undo Auto Style...', true);
    try {
      const store = useProjectStore.getState();
      await store.updateBlocksBulk(snapshotToBulkUpdates(autoStyleSnapshot));
      await refreshPagePreservingSelection(activePage.id);
      setAutoStyleSnapshot(null);
      setLayerDecisionFilter('all');
      showToast('Undo Auto Style แล้ว — คืนค่าก่อนรัน Style Judge', 'success');
    } catch (error: any) {
      showToast(`Undo ไม่สำเร็จ: ${error.message}`, 'error');
    } finally {
      setStatus('Ready', false);
    }
  };

  const submitDecisionFeedback = async (
    changeReason: 'accepted' | 'system_wrong' | 'user_preference',
  ) => {
    if (!selectedBlock) return;
    const spec = selectedBlock.extra_metadata?.typesetting_spec as
      | {
          template_id?: string;
          explicit_lines?: string[];
          decision_status?: string;
          revision?: number;
          font_fingerprint?: string;
          metrics?: { style_descriptor?: { suggested_template?: string } };
        }
      | undefined;
    const meta = selectedBlock.extra_metadata || {};
    // suggested = what the system proposed; final = what is on the block now
    const suggestedLines =
      (meta.suggested_explicit_lines as string[] | undefined)
      || spec?.explicit_lines
      || undefined;
    // Live canvas/editor text when available (translation may differ after user edit)
    const liveText = (selectedBlock.translation || '').trim();
    const finalLines = liveText
      ? liveText.split(/\r?\n/)
      : (spec?.explicit_lines || suggestedLines);
    try {
      await recordTypesettingFeedback({
        block_id: selectedBlock.id,
        change_reason: changeReason,
        suggested_template:
          (meta.suggested_template_id as string | undefined)
          || spec?.metrics?.style_descriptor?.suggested_template
          || spec?.template_id,
        selected_template:
          (meta.text_template_id as string | undefined)
          || spec?.template_id,
        suggested_lines: suggestedLines,
        final_lines: finalLines,
      });
      const labels = {
        accepted: 'บันทึกว่ายอมรับ suggestion แล้ว',
        system_wrong: 'บันทึกว่าเป็นความผิดของระบบ',
        user_preference: 'บันทึกว่าเปลี่ยนตามความชอบ',
      } as const;
      showToast(labels[changeReason], 'success');
    } catch (error: any) {
      showToast(`บันทึก feedback ไม่สำเร็จ: ${error.message}`, 'error');
    }
  };
  void submitDecisionFeedback;

  const clearTranslationData = async (scope: 'layers' | 'page' | 'project') => {
    if (!activePage || !activeProject) return;
    const blockIds = selectedBlocks.length > 0 ? selectedBlocks.map(block => block.id) : selectedBlock ? [selectedBlock.id] : [];
    if (scope === 'layers' && blockIds.length === 0) {
      showToast('เลือก Layer ที่ต้องการล้างก่อน', 'info');
      return;
    }
    const label = scope === 'layers' ? `${blockIds.length} Layer` : scope === 'page' ? `หน้า ${activePage.page_number}` : 'ทั้งโปรเจกต์';
    if (!window.confirm(`ลบคำแปลและ Typesetting เก่าของ ${label} เพื่อ Import ใหม่หรือไม่? ข้อความต้นฉบับจะยังอยู่`)) return;
    const response = await fetch('/api/translations/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope, block_ids: blockIds, page_id: activePage.id, project_id: activeProject.id }),
    });
    if (!response.ok) {
      showToast('ล้างข้อมูลคำแปลไม่สำเร็จ', 'error');
      return;
    }
    const data = await response.json();
    await selectProject(activeProject.id);
    await selectPage(activePage.id);
    showToast(`ล้างคำแปลและ Layout เก่า ${data.cleared_blocks} Layer แล้ว`, 'success');
  };

  // Trigger Batch processing on all pages of project
  const runBatchPipeline = async (steps: string) => {
    if (!activeProject) return;
    const requestedSteps = steps.split(',').map((step) => step.trim().toLowerCase()).filter(Boolean);
    const needsExactRender = requestedSteps.includes('render');
    const backendSteps = requestedSteps.filter((step) => step !== 'render');
    setIsBatchRunning(true);
    setBatchProgress({
      status: 'running',
      progress: 0,
      current_page: 0,
      total_pages: 0,
      error: null
    });
    
    showToast(`Started batch pipeline (${steps.toUpperCase()})...`, 'info');
    try {
      if (needsExactRender && backendSteps.length === 0) {
        await renderAllPagesExact();
        setIsBatchRunning(false);
        showToast('Exact Render completed for every page!', 'success');
        setTimeout(() => setBatchProgress(null), 5000);
        return;
      }

      pendingExactRenderAfterBatchRef.current = needsExactRender;
      const serverSteps = backendSteps.join(',');
      const currentLang = activeProject?.source_lang || sourceLang || 'zh';
      const currentModel = activeProject?.settings?.balloon_model || settingsBalloonModel;
      const res = await apiFetch(`/api/pipeline/batch?project_id=${activeProject.id}&min_confidence=${confidenceThreshold}&steps=${serverSteps}&backend=${ocrEngine}&source_lang=${encodeURIComponent(currentLang)}&balloon_model=${encodeURIComponent(currentModel || '')}`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error("Failed to start batch pipeline");
    } catch (err: any) {
      pendingExactRenderAfterBatchRef.current = false;
      showToast(`Batch error: ${err.message}`, 'error');
      setIsBatchRunning(false);
      setBatchProgress(null);
    }
  };

  const cancelBatchWorkflow = async () => {
    const prjId = activeProject?.id;
    const pageId = activePage?.id;

    // Immediately abort any running frontend workflow loops
    workflowCancelledRef.current = true;
    if (workflowAbortControllerRef.current) {
      try {
        workflowAbortControllerRef.current.abort();
      } catch {}
    }

    // Immediately unblock the UI & clear progress indicators
    setIsBatchRunning(false);
    setIsPageWorkflowRunning(false);
    setBatchProgress(null);
    setStatus('Ready', false);
    useProjectStore.setState({ isProcessing: false, statusMessage: 'Ready' });

    try {
      const cancelRequests = [];
      if (prjId) {
        cancelRequests.push(apiFetch(`/api/pipeline/batch/cancel?project_id=${prjId}`, { method: 'POST' }));
      }
      if (pageId) {
        cancelRequests.push(apiFetch(`/api/pipeline/auto/cancel?page_id=${pageId}`, { method: 'POST' }));
      }

      await Promise.all(cancelRequests);
      showToast('Workflow cancelled successfully', 'info');
    } catch (error) {
      console.error('Failed to cancel workflow on backend:', error);
    }
  };

  // Trigger Model Training
  const handleStartTraining = async () => {
    setStatus('Starting training…', true);
    try {
      const res = await apiFetch('/api/pipeline/train', { method: 'POST' });
      if (!res.ok) throw new Error("Failed to start training");
      
      setTrainStatus(prev => ({ ...prev, is_training: true }));
      setStatus('Model training initiated in background.', false);
      showToast('Model training initiated in background.', 'success');
    } catch (err: any) {
      setStatus(`Training Error: ${err.message}`, false);
      showToast(`Training Error: ${err.message}`, 'error');
    }
  };

  const triggerBasicDownload = (blob: Blob, filename: string, format: string) => {
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    setTimeout(() => {
      window.URL.revokeObjectURL(downloadUrl);
    }, 1000);
    
    setStatus(`Exported ${format.toUpperCase()} successfully!`, false);
    showToast(`Exported ${format.toUpperCase()} successfully!`, 'success');
  };

  // Export exchange text, editable PSD, or finished raster images.
  const handleExport = async (
    format: 'txt' | 'psd' | 'psd-zip' | 'png' | 'jpeg' | 'jsx' | 'jsx-run' | 'jsx-page-run' | 'jsx-page-dl' | 'jsx-project-run' | 'jsx-project-zip',
    txtMode?: 'ocr' | 'translation' | 'both' | 'ai_layout'
  ) => {
    if (!activeProject) return;
    
    if (format === 'jsx-run' || format === 'jsx-page-run' || format === 'jsx-project-run') {
      try {
        setStatus("Executing ExtendScript in Photoshop...", true);
        showToast("🚀 สั่งรัน ExtendScript เปิด Photoshop ทันที...", "info");
        const query = (format === 'jsx-project-run' || !activePage)
          ? `project_id=${activeProject.id}`
          : `page_id=${activePage.id}`;
        const res = await fetch(`/api/export/open-in-photoshop?${query}&text_mode=${psdTextMode}`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to run Photoshop via ExtendScript");
        showToast(`✅ ${data.message || 'เปิดใน Photoshop สำเร็จ!'}`, "success");
        setStatus("Photoshop JSX execution complete", false);
      } catch (err: any) {
        console.error("Failed to run Photoshop via ExtendScript:", err);
        showToast(`❌ ${err.message || 'เปิด Photoshop ไม่สำเร็จ'}`, "error");
        setStatus("Photoshop JSX execution failed", false);
      }
      return;
    }

    setStatus(`Exporting ${format.toUpperCase()}…`, true);
    
    try {
      if (format === 'psd') {
        if (!activePage) throw new Error('Please select a page to export PSD');
        await captureAndUploadExactPage(activePage.id);
      } else if (format === 'psd-zip' || format === 'png' || format === 'jpeg') {
        setIsBatchRunning(true);
        try {
          await renderAllPagesExact();
        } finally {
          setIsBatchRunning(false);
        }
      }

      let url = "";
      let filename = "";
      let isPost = false;
      
      if (format === 'psd') {
        if (!activePage) {
          setStatus("Please select a page to export PSD", false);
          showToast("Please select a page to export PSD", "info");
          return;
        }
        url = `/api/export/psd?page_id=${activePage.id}&text_mode=${psdTextMode}`;
        filename = `page_${String(activePage?.page_number).padStart(3, '0')}.psd`;
        isPost = true;
      } else if (format === 'jsx' || format === 'jsx-page-dl') {
        if (!activePage) {
          setStatus("Please select a page to export JSX script", false);
          showToast("Please select a page to export JSX script", "info");
          return;
        }
        url = `/api/export/page/${activePage.id}/jsx?text_mode=${psdTextMode}`;
        filename = `page_${String(activePage?.page_number).padStart(3, '0')}.jsx`;
        isPost = false;
      } else if (format === 'jsx-project-zip') {
        url = `/api/projects/${activeProject.id}/export/jsx-zip?text_mode=${psdTextMode}`;
        filename = `${activeProject.name}_jsx_scripts.zip`;
        isPost = false;
      } else if (format === 'txt') {
        const mode = txtMode || 'both';
        url = `/api/export/txt?project_id=${activeProject.id}&mode=${mode}`;
        filename = `${activeProject.name}_export_${mode}.txt`;
        isPost = true;
      } else if (format === 'png' || format === 'jpeg') {
        url = `/api/projects/${activeProject.id}/export/images?format=${format}`;
        filename = '';
        isPost = true;
      } else if (format === 'psd-zip') {
        url = `/api/projects/${activeProject.id}/export/psd-zip?text_mode=${psdTextMode}`;
        filename = `${activeProject.name}_psd.zip`;
      }

      const res = await fetch(url, { method: isPost ? 'POST' : 'GET' });
      if (!res.ok) throw new Error("Export request failed");

      if (format === 'png' || format === 'jpeg') {
        const result = await res.json();
        const count = Array.isArray(result.paths) ? result.paths.length : 0;
        const folder = count > 0 ? String(result.paths[0]).replace(/[\\/][^\\/]+$/, '') : activeProject.name;
        setStatus(`Exported ${count} ${format.toUpperCase()} page(s) to ${folder}`, false);
        showToast(`Saved ${count} page(s) to: ${folder}`, 'success');
        return;
      }

      const encodedServerExportPath = res.headers.get('X-Houmi-Export-Path');
      // TXT is a hand-off file and must always reach the native/browser Save
      // As dialog. Other server-rendered artefacts can keep their project path.
      if (encodedServerExportPath && format !== 'txt') {
        const serverExportPath = decodeURIComponent(encodedServerExportPath);
        setStatus(`Exported successfully to: ${serverExportPath}`, false);
        showToast(`Saved to: ${serverExportPath}`, 'success');
        return;
      }
      
      const blob = await res.blob();
      
      if ((window as any).pywebview?.api?.save_file_b64) {
        const reader = new FileReader();
        reader.onloadend = async () => {
          const base64data = (reader.result as string).split(',')[1];
          const saveRes = await (window as any).pywebview.api.save_file_b64(base64data, filename, defaultSaveOcrPath);
          if (saveRes && saveRes.success) {
            setStatus(`Exported successfully to: ${saveRes.path}`, false);
            showToast(`Saved to: ${saveRes.path}`, 'success');
          } else if (saveRes && saveRes.cancelled) {
            setStatus("Export cancelled", false);
          } else {
            const errMsg = saveRes?.error || "Unknown error";
            setStatus(`Export failed: ${errMsg}`, false);
            showToast(`Export failed: ${errMsg}`, 'error');
          }
        };
        reader.readAsDataURL(blob);
      } else if ((window as any).showSaveFilePicker) {
        // Modern Browser Save File Dialog (File System Access API)
        try {
          // Determine MIME type and accept parameters based on format
          let acceptTypes: Record<string, string[]> = {};
          let description = "";
          if (format === 'txt') {
            acceptTypes = { 'text/plain': ['.txt'] };
            description = "Text Files";
          } else if (format === 'psd') {
            acceptTypes = { 'image/vnd.adobe.photoshop': ['.psd'] };
            description = "Photoshop Files";
          } else if (format === 'psd-zip') {
            acceptTypes = { 'application/zip': ['.zip'] };
            description = "ZIP Archives";
          }
          
          const handle = await (window as any).showSaveFilePicker({
            suggestedName: filename,
            types: [{
              description: description || `${format.toUpperCase()} Files`,
              accept: acceptTypes
            }]
          });
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          setStatus(`Exported ${format.toUpperCase()} successfully!`, false);
          showToast(`Exported ${format.toUpperCase()} successfully!`, 'success');
        } catch (err: any) {
          if (err.name === 'AbortError') {
            setStatus("Export cancelled", false);
          } else {
            console.warn("showSaveFilePicker failed, falling back to basic download:", err);
            triggerBasicDownload(blob, filename, format);
          }
        }
      } else {
        triggerBasicDownload(blob, filename, format);
      }
    } catch (err: any) {
      setStatus(`Export Error: ${err.message}`, false);
      showToast(`Export Error: ${err.message}`, 'error');
    }
  };


  // Format seconds to readable timer
  const formatTime = (secs: number) => {
    if (secs <= 0) return "Estimating…";
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}m ${s}s`;
  };

  const selectPrevPage = () => {
    if (!activeProject || !activePage) return;
    const idx = activeProject.pages.findIndex(p => p.id === activePage.id);
    if (idx > 0) {
      selectPage(activeProject.pages[idx - 1].id);
    }
  };

  const selectNextPage = () => {
    if (!activeProject || !activePage) return;
    const idx = activeProject.pages.findIndex(p => p.id === activePage.id);
    if (idx >= 0 && idx < activeProject.pages.length - 1) {
      selectPage(activeProject.pages[idx + 1].id);
    }
  };

  const isMulti = selectedBlocks.length > 1;
  const commonFontFamily = getCommonValue('font_family') as string || '';
  const effectiveFontSize = (block: TextBlock) => {
    // When auto-fit is active the frontend Canvas autoFit is the authority –
    // it writes the fitted result into block.font_size.  The typesetting_spec
    // may still contain a stale value from an earlier backend response, so we
    // must NOT read spec.font_size in auto mode.
    const isAuto = isAutoFontSizeEnabled(block);
    if (isAuto) {
      return Number(block.font_size || 18);
    }
    // Manual mode: prefer manual_font_size, then spec, then block.font_size
    const manual = block.extra_metadata?.manual_font_size;
    if (manual != null && Number.isFinite(Number(manual)) && Number(manual) > 0) {
      return Number(manual);
    }
    const spec = block.extra_metadata?.typesetting_spec;
    if (spec?.font_size) {
      return spec.font_size;
    }
    return Number(block.font_size || 18);
  };
  const fontSizeTargets = selectedBlocks.length > 0
    ? selectedBlocks
    : selectedBlock ? [selectedBlock] : [];
  const selectedFontSizes = fontSizeTargets.map(effectiveFontSize);
  const commonFontSize = selectedFontSizes.length > 0 && selectedFontSizes.every(size => size === selectedFontSizes[0])
    ? selectedFontSizes[0]
    : '';
  const isAutoFontSize = fontSizeTargets.length > 0
    && fontSizeTargets.every(isAutoFontSizeEnabled);
  const commonColorHex = getCommonValue('color_hex') as string || '';
  const commonTextAlign = getCommonValue('text_align') as string || '';
  const commonBold = getCommonValue('bold') as boolean | '';
  const commonItalic = getCommonValue('italic') as boolean | '';
  const commonTextDirection = getCommonValue('text_direction') as string || '';
  const commonBalloonType = getCommonValue('balloon_type') as string || '';
  const commonFontStyle = (() => {
    if (isMulti && (commonBold === '' || commonItalic === '')) return '';
    const bold = isMulti ? commonBold === true : Boolean(selectedBlock?.bold);
    const italic = isMulti ? commonItalic === true : Boolean(selectedBlock?.italic);
    if (bold && italic) return 'bold_italic';
    if (bold) return 'bold';
    if (italic) return 'italic';
    return 'regular';
  })();
  const metadataTargets = selectedBlocks.length > 0
    ? selectedBlocks
    : selectedBlock ? [selectedBlock] : [];
  const commonMetadataNumber = (reader: (block: TextBlock) => number) => {
    const values = metadataTargets.map(reader);
    return values.length > 0 && values.every(value => value === values[0]) ? values[0] : '';
  };
  const commonLeading = commonMetadataNumber(block => Number(block.extra_metadata?.line_height_ratio ?? 1.2));
  const commonTracking = commonMetadataNumber(block => Number(block.extra_metadata?.tracking ?? block.extra_metadata?.letter_spacing ?? 0));
  const commonRotation = getCommonValue('rotation_deg');
  const rotationMixed = isMulti && commonRotation === '';
  const rotationValue = Number(rotationMixed ? 0 : (commonRotation ?? selectedBlock?.rotation_deg ?? 0));
  const inspectorFontValue = isMulti ? commonFontFamily : selectedBlock?.font_family || '';
  const inspectorFontOptions = Array.from(new Set([inspectorFontValue, ...systemFonts].filter(Boolean)));

  return (
    <div className="flex flex-col h-screen w-screen bg-[#09090b] text-slate-100 overflow-hidden font-sans relative">
      <AboutModal
        isOpen={showAboutModal}
        onClose={() => setShowAboutModal(false)}
        onOpenLoginModal={() => {}}
        onOpenChangelog={() => setShowChangelogModal(true)}
        userInfo={{
          username: currentUser?.username || 'admin',
          role: currentUser?.role || 'admin',
          status: currentUser?.status || 'active',
          expiresInDays: 365,
          mode: 'local'
        }}
      />

      <ChangelogModal
        isOpen={showChangelogModal}
        onClose={() => setShowChangelogModal(false)}
      />

      <ConfirmModal
        isOpen={globalConfirm.isOpen}
        title={globalConfirm.title}
        message={globalConfirm.message}
        confirmText={globalConfirm.confirmText}
        cancelText={globalConfirm.cancelText}
        type={globalConfirm.type}
        onConfirm={globalConfirm.onConfirm}
        onClose={() => setGlobalConfirm(prev => ({ ...prev, isOpen: false }))}
      />

      <OversizeWarningModal
        isOpen={!!oversizeWarningData}
        folderPath={oversizeWarningData?.folderPath || ''}
        scanReport={oversizeWarningData?.scanReport || null}
        isProcessing={isSplittingOversize}
        onReject={() => {
          setOversizeWarningData(null);
          setStatus('Ready', false);
        }}
        onConfirmSplit={async (options) => {
          if (!oversizeWarningData) return;
          setIsSplittingOversize(true);
          try {
            await smartSplitAndOpen(oversizeWarningData.folderPath, options);
            showToast('✂️ แบ่งภาพและเปิดโปรเจกต์สำเร็จเรียบร้อย', 'success');
          } catch (err: any) {
            console.error('Error splitting webtoon:', err);
            showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
            setStatus(err.message || 'Ready', false);
          } finally {
            setIsSplittingOversize(false);
            setOversizeWarningData(null);
          }
        }}
        onProceedAnyway={async () => {
          if (!oversizeWarningData) return;
          const targetFolder = oversizeWarningData.folderPath;
          setOversizeWarningData(null);
          try {
            await browseFolderProject(undefined, targetFolder, { allow_oversize: true });
          } catch (err: any) {
            showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
            setStatus('Ready', false);
          }
        }}
      />

      <SmartStitchModal
        isOpen={showSmartStitchModal}
        initialFolderPath={activeProject?.settings?.local_folder || defaultLoadProjectPath || ''}
        isProcessing={isProcessing}
        onClose={() => setShowSmartStitchModal(false)}
        onExecuteSplit={async ({ folderPath, splitHeight, enforceWidth, backupOriginal }) => {
          try {
            const res = await fetch('/api/projects/smart-split', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                folder_path: folderPath,
                project_id: activeProject?.id || null,
                split_height: splitHeight,
                enforce_width: enforceWidth,
                backup_original: backupOriginal,
              }),
            });
            if (!res.ok) {
              const err = await res.json().catch(() => ({ detail: 'Failed to split folder' }));
              throw new Error(err.detail || 'Failed to split folder');
            }
            const result = await res.json();
            showToast(`✂️ ตัดแบ่งภาพสำเร็จ ${result.output_images_count || 0} ไฟล์`, 'success');
            
            // Reload projects and refresh current project pages
            await useProjectStore.getState().fetchProjects();
            if (activeProject) {
              await selectProject(activeProject.id);
              const storePages = useProjectStore.getState().activeProject?.pages;
              if (storePages && storePages.length > 0) {
                await selectPage(storePages[0].id);
              }
            }
            return {
              success: true,
              message: `ตัดแบ่งภาพสำเร็จเรียบร้อย (${result.output_images_count || 0} ไฟล์)`,
              output_images_count: result.output_images_count,
            };
          } catch (err: any) {
            console.error('Smart Split execute error:', err);
            showToast(`Smart Split ล้มเหลว: ${err.message}`, 'error');
            return {
              success: false,
              message: err.message,
            };
          }
        }}
        onExecuteStitch={async ({ folderPath, targetHeight, enforceWidth, backupOriginal }) => {
          try {
            const res = await fetch('/api/projects/smart-stitch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                folder_path: folderPath,
                project_id: activeProject?.id || null,
                target_height: targetHeight,
                enforce_width: enforceWidth,
                backup_original: backupOriginal,
              }),
            });
            if (!res.ok) {
              const err = await res.json().catch(() => ({ detail: 'Failed to stitch folder' }));
              throw new Error(err.detail || 'Failed to stitch folder');
            }
            const result = await res.json();
            showToast(`🪡 ต่อภาพสำเร็จ ${result.output_images_count || 0} ไฟล์`, 'success');
            
            // Reload projects and refresh current project pages
            await useProjectStore.getState().fetchProjects();
            if (activeProject) {
              await selectProject(activeProject.id);
              const storePages = useProjectStore.getState().activeProject?.pages;
              if (storePages && storePages.length > 0) {
                await selectPage(storePages[0].id);
              }
            }
            return {
              success: true,
              message: `ต่อภาพสำเร็จเรียบร้อย (${result.output_images_count || 0} ไฟล์)`,
              output_images_count: result.output_images_count,
            };
          } catch (err: any) {
            console.error('Smart Stitch execute error:', err);
            showToast(`Smart Stitch ล้มเหลว: ${err.message}`, 'error');
            return {
              success: false,
              message: err.message,
            };
          }
        }}
        onBrowseFolder={async () => {
          try {
            const defaultPath = defaultLoadProjectPath || localStorage.getItem('houmi_last_load_project_path') || '';
            const res = await fetch(`/api/projects/browse-folder?default_load_path=${encodeURIComponent(defaultPath)}`, {
              method: 'POST',
            });
            if (res.ok) {
              const data = await res.json();
              if (data.folder_path) {
                return data.folder_path;
              }
            }
          } catch (err) {
            console.warn('Browse folder failed:', err);
          }
          return null;
        }}
      />
      {/* Background Ambient Cosmic Spotlights */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-yellow-500/[0.035] rounded-full filter blur-[120px] pointer-events-none z-0" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-amber-600/[0.025] rounded-full filter blur-[120px] pointer-events-none z-0" />
      <nav 
        className="w-full bg-zinc-950/75 backdrop-blur-md border-b border-zinc-900/60 text-slate-300 text-xs font-medium select-none z-30 shrink-0 relative flex items-center justify-between px-5 h-10 shadow-lg pywebview-drag window-drag-region cursor-move"
        style={{ WebkitAppRegion: 'drag' } as any}
        onMouseDown={(e) => {
          if (e.button === 0) {
            (window as any).pywebview?.api?.start_window_drag?.();
          }
        }}
      >
        <div className="flex items-center gap-1 pywebview-no-drag window-no-drag-region" style={{ WebkitAppRegion: 'no-drag' } as any}>
          {/* Logo / Brand */}
          <div className="flex items-center gap-1.5 mr-4 font-bold text-amber-400 uppercase tracking-widest font-pixel">
            <Sparkles size={13} className="text-yellow-500 animate-pulse" />
            <span>Houmi Studio</span>
          </div>

          {/* Menus */}
          {/* File Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuFile(!showMenuFile);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuFile ? 'bg-zinc-900 text-white' : ''}`}
            >
              File
            </button>
            {showMenuFile && (
              <div 
                className="absolute left-0 mt-1.5 w-60 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={async () => {
                    closeAllMenus();
                    try {
                      const defaultPath = defaultLoadProjectPath || localStorage.getItem('houmi_last_load_project_path') || '';
                      const newProj = await browseFolderProject(defaultPath);
                      if (newProj) {
                        showToast(`Imported project "${newProj.name}"`, 'success');
                        if (newProj.settings?.local_folder) {
                          localStorage.setItem('houmi_last_load_project_path', newProj.settings.local_folder);
                        }
                      }
                    } catch (err: any) {
                      showToast(`Import failed: ${err.message}`, 'error');
                    }
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center gap-2 cursor-pointer"
                >
                  📁 Browse Project Folder...
                </button>
                <div className="relative group">
                  <span className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between gap-2 cursor-pointer">
                    <span className="flex items-center gap-2">📂 Open Recent Project</span>
                    <span className="text-[10px] text-slate-500">▶</span>
                  </span>
                  <div className="absolute left-full top-0 ml-1.5 w-52 glass-panel p-1.5 hidden group-hover:flex flex-col gap-1 rounded-md shadow-2xl">
                    {projects
                      .slice()
                      .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
                      .slice(0, 10)
                      .map((p) => (
                        <button
                          key={p.id}
                          onClick={() => {
                            closeAllMenus();
                            selectProject(p.id);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition truncate cursor-pointer"
                        >
                          {p.name}
                        </button>
                      ))}
                    {projects.length === 0 && (
                      <span className="px-3 py-2 text-slate-500 italic text-[11px]">No projects</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => {
                    closeAllMenus();
                    showToast("Project saved locally", "success");
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span className="flex items-center gap-2">💾 Save</span>
                  <span className="text-[10px] text-slate-500 font-mono">Ctrl+S</span>
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    fileInputRef.current?.click();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center gap-2 cursor-pointer"
                >
                  📥 Import Pages...
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    txtFileInputRef.current?.click();
                  }}
                  disabled={!activeProject}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2 cursor-pointer"
                >
                  📝 Import Translated TXT...
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    psdFileInputRef.current?.click();
                  }}
                  disabled={!activeProject || !activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2 cursor-pointer"
                >
                  📷 Import Page (PSD)...
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <div className="relative group">
                  <span className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between gap-2 cursor-pointer">
                    <span className="flex items-center gap-2">📤 Export Options</span>
                    <span className="text-[10px] text-slate-500">▶</span>
                  </span>
                  <div className="absolute left-full top-0 ml-1.5 w-52 glass-panel p-1.5 hidden group-hover:flex flex-col gap-1 rounded-md shadow-2xl">
                    <button
                      onClick={() => { closeAllMenus(); handleExport('png'); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                    >
                      Export PNG (Finished Project)
                    </button>
                    <button
                      onClick={() => { closeAllMenus(); handleExport('jpeg'); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                    >
                      Export JPEG (Finished Project)
                    </button>
                    <button
                      onClick={() => { closeAllMenus(); setShowPsdExportModal(true); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex justify-between items-center"
                    >
                      <span>Export PSD (Photoshop)</span>
                      <span className="text-[9px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">.psd</span>
                    </button>
                    <button
                      onClick={() => { closeAllMenus(); setShowExportTxtModal(true); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                    >
                      TXT Exchange (OCR / Translated)
                    </button>
                    <button
                      onClick={() => { closeAllMenus(); handleExport('txt', 'ocr'); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex justify-between items-center text-[11px]"
                      title="ส่งออกข้อความสแกนภาษาต้นทาง (OCR Text) เป็นไฟล์ TXT (Ctrl+Shift+S)"
                    >
                      <span>Export OCR (TXT)</span>
                      <span className="text-[8px] text-slate-500 font-mono">Ctrl+Shift+S</span>
                    </button>
                    <button
                      onClick={() => { closeAllMenus(); setShowExportYoloModal(true); }}
                      className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer text-[11px]"
                      title="ส่งออกรูปภาพและพิกัดกรอบสำหรับฝึกสอน YOLO"
                    >
                      Export YOLO Dataset
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowPsdExportModal(true);
                  }}
                  disabled={!activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  ⚡ Generate editable PSD files
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowSmartStitchModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-amber-500/15 hover:text-amber-300 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer text-amber-400 font-medium"
                  title="ตัดแบ่งและปรับขนาดภาพเว็บตูนขนาดยาวอัตโนมัติตามร่องขาว/ดำ (Smart Stitch)"
                >
                  <span className="flex items-center gap-2">✂️ Smart Stitch & Split...</span>
                  <span className="text-[9px] font-mono text-amber-400/80 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">Webtoon</span>
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    useProjectStore.setState({ activeProject: null, activePage: null });
                  }}
                  className="w-full text-left px-3 py-2 text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 rounded-md transition-all spring-transition cursor-pointer"
                >
                  ❌ Close Project
                </button>
              </div>
            )}
          </div>

          {/* Edit Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuEdit(!showMenuEdit);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuEdit ? 'bg-zinc-900 text-white' : ''}`}
            >
              Edit
            </button>
            {showMenuEdit && (
              <div 
                className="absolute left-0 mt-1.5 w-60 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => {
                    closeAllMenus();
                    undo();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span>Undo</span>
                  <span className="text-[10px] text-slate-500 font-mono">Ctrl+Z</span>
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    redo();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span>Redo</span>
                  <span className="text-[10px] text-slate-500 font-mono">Ctrl+Y</span>
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    if (activePage && selectedBlocks.length > 1) {
                      mergeBlocks(activePage.id, selectedBlocks.map(b => b.id));
                      showToast("Merged selected blocks", "success");
                    } else {
                      showToast("Please select at least 2 blocks to merge", "info");
                    }
                  }}
                  disabled={selectedBlocks.length <= 1}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  ⛓️ Merge selected text blocks
                </button>
                <button
                  onClick={async () => {
                    closeAllMenus();
                    if (selectedBlocks.length > 0) {
                      await deleteBlocks(selectedBlocks.map(b => b.id));
                      showToast(`ลบกล่องข้อความที่เลือก ${selectedBlocks.length} กล่องสำเร็จ!`, 'success');
                    } else if (selectedBlock) {
                      await deleteBlocks([selectedBlock.id]);
                      showToast("ลบกล่องข้อความสำเร็จ!", "success");
                    }
                  }}
                  disabled={selectedBlocks.length === 0 && !selectedBlock}
                  className="w-full text-left px-3 py-2 hover:bg-rose-500/10 hover:text-rose-450 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none text-red-400 cursor-pointer"
                >
                  🗑️ Delete selected block{selectedBlocks.length > 1 ? 's' : ''}
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowGlobalSettingsModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span className="flex items-center gap-2">⚙️ Preferences & Settings...</span>
                  <span className="text-[10px] text-slate-500 font-mono">Ctrl+,</span>
                </button>
              </div>
            )}
          </div>

          {/* View Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuView(!showMenuView);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuView ? 'bg-zinc-900 text-white' : ''}`}
            >
              View
            </button>
            {showMenuView && (
              <div 
                className="absolute left-0 mt-1.5 w-64 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    const next = !showFloatingLetteringBar;
                    setShowFloatingLetteringBar(next);
                    try { localStorage.setItem('houmi_show_floating_lettering_bar', String(next)); } catch {}
                    showToast(next ? 'เปิดแถบเครื่องมือลอยแล้ว (Floating Bar: ON)' : 'ซ่อนแถบเครื่องมือลอยแล้ว (Floating Bar: OFF)', 'info');
                    closeAllMenus();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span>🎛️ แถบเครื่องมือลอยเหนือบล็อก (Floating Toolbar)</span>
                  <span className="text-[11px] font-bold text-amber-400">{showFloatingLetteringBar ? '✓' : ''}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsFormattingWidgetOpen(!isFormattingWidgetOpen);
                    closeAllMenus();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span>🎨 หน้าต่าง Text & Formatting (Flyout)</span>
                  <span className="text-[11px] font-bold text-amber-400">{isFormattingWidgetOpen ? '✓' : ''}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRightSidebarOpen(!rightSidebarOpen);
                    closeAllMenus();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center justify-between cursor-pointer"
                >
                  <span>📑 หน้าต่างขวา (Right Inspector)</span>
                  <span className="text-[11px] font-bold text-amber-400">{rightSidebarOpen ? '✓' : ''}</span>
                </button>
              </div>
            )}
          </div>

          {/* Navigation Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuNav(!showMenuNav);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuNav ? 'bg-zinc-900 text-white' : ''}`}
            >
              Navigation
            </button>
            {showMenuNav && (
              <div 
                className="absolute left-0 mt-1.5 w-60 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => {
                    closeAllMenus();
                    selectPrevPage();
                  }}
                  disabled={!activeProject || !activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none flex items-center justify-between cursor-pointer"
                >
                  <span>Previous Page</span>
                  <span className="text-[10px] text-slate-500 font-mono">PageUp</span>
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    selectNextPage();
                  }}
                  disabled={!activeProject || !activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none flex items-center justify-between cursor-pointer"
                >
                  <span>Next Page</span>
                  <span className="text-[10px] text-slate-500 font-mono">PageDown</span>
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    showToast("Use Ctrl + Scroll to Zoom", "info");
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                >
                  🔎 Zoom In / Out
                </button>
              </div>
            )}
          </div>

          {/* Project Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuProj(!showMenuProj);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuProj ? 'bg-zinc-900 text-white' : ''}`}
            >
              Project
            </button>
            {showMenuProj && (
              <div 
                className="absolute left-0 mt-1.5 w-60 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    closeAllMenus();
                    setShowProjectPresetModal(true);
                  }}
                  disabled={!activeProject}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-amber-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none cursor-pointer font-bold text-amber-400"
                >
                  👤 ตั้งค่าภาษา & โปรไฟล์ลูกค้า (Preset)...
                </button>
                <button
                  type="button"
                  onClick={() => {
                    closeAllMenus();
                    setShowGlobalSettingsModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                >
                  ⚙️ Settings (ตั้งค่าระบบ)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    closeAllMenus();
                    showToast("Cloud Hub: เชื่อมต่อเซิร์ฟเวอร์เรียบร้อย (houmi.click)", "info");
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-sky-500/10 hover:text-sky-300 rounded-md transition-all spring-transition cursor-pointer flex items-center gap-2 text-sky-400 font-medium"
                >
                  <span>☁️ Cloud Hub (Sync & Backup)...</span>
                </button>
                <div className="h-px bg-zinc-900 my-1" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    openTemplateSettings();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer"
                >
                  🎨 Manage Style Presets...
                </button>
              </div>
            )}
          </div>

          {/* Tools Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuTools(!showMenuTools);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuTools ? 'bg-zinc-900 text-white' : ''}`}
            >
              Tools
            </button>
            {showMenuTools && (
              <div 
                className="absolute left-0 mt-1.5 w-60 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => {
                    closeAllMenus();
                    runPipelineStep('auto');
                  }}
                  disabled={!activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  ⚡ Run Pipeline (Auto Flow)
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setWorkspaceMode('ocr');
                    setReviewPanelView('pipeline');
                  }}
                  disabled={!activeProject}
                  className={`w-full text-left px-3 py-2 rounded-md transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer flex items-center justify-between ${
                    workspaceMode === 'ocr' ? 'bg-yellow-500/15 text-yellow-400 font-bold' : 'hover:bg-yellow-500/10 hover:text-yellow-400'
                  }`}
                >
                  <span>🧰 Mode: OCR Pipeline</span>
                  {workspaceMode === 'ocr' && <span className="text-[10px] text-yellow-400">✓</span>}
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setWorkspaceMode('typeset');
                  }}
                  disabled={!activeProject}
                  className={`w-full text-left px-3 py-2 rounded-md transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer flex items-center justify-between ${
                    workspaceMode === 'typeset' ? 'bg-yellow-500/15 text-yellow-400 font-bold' : 'hover:bg-yellow-500/10 hover:text-yellow-400'
                  }`}
                >
                  <span>🎨 Mode: Typesetting & Inspector</span>
                  {workspaceMode === 'typeset' && <span className="text-[10px] text-yellow-400">✓</span>}
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    handleStartTraining();
                  }}
                  disabled={!activeProject}
                  className="w-full text-left px-2.5 py-1.5 hover:bg-zinc-900 hover:text-yellow-400 rounded-sm transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  🎯 Calibrate Balloon Detector
                </button>
                <div className="h-px bg-zinc-900 my-0.5" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    void runAutoStylePage(true);
                  }}
                  disabled={!activePage || isProcessing}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 cursor-pointer"
                >
                  ⚡ Style Judge (AI Style Alignment)
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    void reorganizePageText();
                  }}
                  disabled={!activePage || isProcessing}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 cursor-pointer"
                >
                  📐 Recompute Typesetting Layout
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setLayerDecisionFilter((f) => (f === 'NEEDS_REVIEW' ? 'all' : 'NEEDS_REVIEW'));
                  }}
                  disabled={!activePage}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition disabled:opacity-40 cursor-pointer"
                >
                  🔍 Review Queue (NEEDS_REVIEW Filter)
                </button>
                <div className="h-px bg-zinc-900 my-0.5" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    useDebugStore.getState().openDrawer();
                    logAction('UI_INTERACTION', 'Open Action Debug Console from Tools Menu');
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex items-center justify-between text-yellow-400 font-bold"
                >
                  <span className="flex items-center gap-1.5">
                    <Bug size={13} className="text-yellow-500" /> Action Debug Console
                  </span>
                  <span className="text-[9px] font-mono text-zinc-500">Ctrl+Shift+D</span>
                </button>
              </div>
            )}
          </div>

          {/* Help Menu */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeAllMenus();
                setShowMenuAbout(!showMenuAbout);
              }}
              className={`px-3 py-1 hover:bg-zinc-900 hover:text-white rounded-md cursor-pointer transition-all spring-transition ${showMenuAbout ? 'bg-zinc-900 text-white' : ''}`}
            >
              Help
            </button>
            {showMenuAbout && (
              <div 
                className="absolute left-0 mt-1.5 w-64 glass-panel p-1.5 z-40 flex flex-col gap-1 animate-fade-in"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowAboutModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex items-center gap-2 font-bold text-yellow-400"
                >
                  ℹ️ About Houmi Studio & Patch...
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowAboutModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-amber-500/10 hover:text-amber-300 rounded-md transition-all spring-transition cursor-pointer flex items-center justify-between font-bold text-amber-400"
                >
                  <span className="flex items-center gap-2">🔑 Register License Key...</span>
                  <span className="text-[9px] font-mono text-amber-400 bg-amber-500/20 px-1.5 py-0.5 rounded border border-amber-500/30">PRO</span>
                </button>
                <div className="h-px bg-zinc-900 my-0.5" />
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowChangelogModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center gap-2 cursor-pointer"
                >
                  🚀 Version Changelog & What's New
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowHotkeyModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex items-center justify-between"
                >
                  <span>⌨️ Keyboard Shortcuts</span>
                  <span className="text-[10px] text-slate-500 font-mono">?</span>
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowDiagnostics(true);
                    fetchDiagnostics();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition cursor-pointer flex items-center gap-2"
                >
                  🏥 System Diagnostics & Audits
                </button>
                <button
                  onClick={() => {
                    closeAllMenus();
                    setShowDevStudioModal(true);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-yellow-500/10 hover:text-yellow-400 rounded-md transition-all spring-transition flex items-center gap-2 cursor-pointer text-slate-400"
                >
                  🗺️ Architecture & Node Map
                </button>
              </div>
            )}
          </div>
        </div>

        {activeProject && (
          <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-md border border-zinc-800/80 bg-zinc-950/90 px-3 py-1 shadow-inner">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[9.5px] font-pixel font-bold uppercase tracking-wider text-amber-400">
              HOUMI UNIFIED WORKSPACE
            </span>
          </div>
        )}

        {/* Right side Actions & Tools - Minimalist Desktop HIG Layout */}
        <div className="flex items-center text-xs text-slate-300 gap-2 font-medium relative pywebview-no-drag window-no-drag-region" style={{ WebkitAppRegion: 'no-drag' } as any}>
          <input 
            type="file" 
            multiple 
            accept="image/*" 
            ref={fileInputRef} 
            onChange={handlePageUpload} 
            className="hidden" 
          />
          <input 
            type="file" 
            accept=".txt,.tsv" 
            ref={txtFileInputRef} 
            onChange={handleImportTxt} 
            className="hidden" 
          />
          <input 
            type="file" 
            accept=".psd" 
            ref={psdFileInputRef} 
            onChange={handleImportPsd} 
            className="hidden" 
          />

          {/* Minimalist System Status Badge */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-zinc-900/90 border border-zinc-800 shadow-inner">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[9.5px] font-mono font-bold uppercase text-emerald-400 tracking-wider">LOCAL</span>
            <span className="text-zinc-700 text-[9px]">•</span>
            <button
              type="button"
              onClick={() => setShowAboutModal(true)}
              className="text-[9.5px] font-mono font-bold text-amber-400/90 hover:text-amber-300 transition-colors cursor-pointer"
              title="License: PRO (4d) - Click to manage"
            >
              PRO (4d)
            </button>
          </div>

          {/* Minimalist Quick Settings Icon */}
          <button
            type="button"
            onClick={() => setShowGlobalSettingsModal(true)}
            className="p-1.5 rounded-md hover:bg-zinc-800/70 text-zinc-400 hover:text-amber-400 transition-all cursor-pointer"
            title="Preferences & Settings (Ctrl+,)"
          >
            <Settings size={14} className="hover:rotate-45 transition-transform duration-300" />
          </button>
        </div>
      </nav>



      {/* MISSING ESSENTIAL FONTS WARNING BANNER */}
      {missingFonts.length > 0 && !isFontBannerDismissed && (
        <div className="w-full bg-gradient-to-r from-amber-950/90 via-amber-900/80 to-zinc-950 border-b border-amber-500/50 text-amber-100 px-5 py-2 text-xs flex items-center justify-between z-40 animate-fade-in shadow-lg shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-base">⚠️</span>
            <div>
              <span className="font-bold text-amber-300 font-pixel tracking-wide">ตรวจพบฟอนต์มาตรฐานที่ยังไม่ได้ติดตั้ง:</span>{' '}
              <span className="font-mono bg-black/50 px-2 py-0.5 rounded border border-amber-500/30 text-amber-400 font-bold">
                {missingFonts.join(', ')}
              </span>{' '}
              <span className="text-slate-400 text-[11px]">(กำลังใช้ฟอนต์สำรองชั่วคราว)</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadEssentialFonts}
              disabled={isDownloadingFonts}
              className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-yellow-500 text-black font-extrabold hover:brightness-110 text-[11px] shadow-lg shadow-amber-500/20 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50 active:scale-95"
            >
              {isDownloadingFonts ? '⏳ กำลังดาวน์โหลด...' : '📥 ดาวน์โหลดและติดตั้งฟอนต์อัตโนมัติ'}
            </button>
            <button
              onClick={() => setIsFontBannerDismissed(true)}
              className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition cursor-pointer"
              title="ซ่อนการแจ้งเตือน"
            >
              <X size={15} />
            </button>
          </div>
        </div>
      )}

      {/* MISSING AI MODELS STARTUP WARNING BANNER */}
      {missingModelsWarning && missingModelsWarning.length > 0 && (
        <div className="w-full bg-gradient-to-r from-rose-950/95 via-rose-900/90 to-rose-950/95 border-b border-rose-600/60 text-rose-100 px-5 py-2 text-xs flex items-center justify-between z-40 animate-fade-in shadow-lg shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-base animate-pulse">🚨</span>
            <div>
              <span className="font-bold text-rose-300">แจ้งเตือนโมเดล AI ขาดหายไป ({missingModelsWarning.length} ตัว):</span>{' '}
              <span className="text-rose-200">
                ตรวจพบไฟล์โมเดลไม่ครบในเครื่อง ({missingModelsWarning.join(', ')}) ระบบจะทำงานในโหมดฉุกเฉิน
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowGlobalSettingsModal(true);
                setSettingsGlobalCategory('performance');
              }}
              className="px-3 py-1 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded text-[11px] transition-colors cursor-pointer shadow flex items-center gap-1"
            >
              🔍 ตรวจสอบโมเดล & วิธีแก้ไข ↗
            </button>
            <button
              onClick={() => setMissingModelsWarning(null)}
              className="px-2 py-1 text-rose-400 hover:text-white text-xs cursor-pointer"
              title="ปิดการแจ้งเตือนนี้"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* MAIN CONTAINER */}
      <div className="flex flex-1 gap-4 p-4 pt-2 overflow-hidden z-10 relative pywebview-no-drag">
        {/* 2. LEFT SIDEBAR (Page List navigator) */}
        <aside 
          className={`transition-[width,opacity] duration-200 flex flex-col overflow-hidden border-r border-zinc-900/60 bg-zinc-950/95 animate-slide-up ${
            activeProject && leftSidebarOpen ? 'w-72 opacity-100' : 'w-0 opacity-0 border-none'
          } ${
            isDraggingOverPages 
              ? 'border-2 border-dashed border-yellow-500/60 shadow-[0_0_15px_rgba(234,179,8,0.15)] bg-yellow-500/[0.02]' 
              : 'border-zinc-900/50'
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            if (activeProject) {
              setIsDraggingOverPages(true);
            }
          }}
          onDragLeave={() => {
            setIsDraggingOverPages(false);
          }}
          onDrop={async (e) => {
            e.preventDefault();
            setIsDraggingOverPages(false);
            if (!activeProject) return;
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              const files = Array.from(e.dataTransfer.files)
                .filter(file => file.type.startsWith('image/'))
                .sort((a, b) => a.name.localeCompare(b.name));
              
              if (files.length === 0) return;
              
              setStatus(`Uploading ${files.length} dropped pages...`, true);
              try {
                for (let i = 0; i < files.length; i++) {
                  const file = files[i];
                  const pageNum = (activeProject.pages?.length || 0) + i + 1;
                  await uploadPage(activeProject.id, pageNum, file);
                }
                showToast(`Successfully uploaded ${files.length} page(s) via drag-and-drop!`, 'success');
                
                // Auto OCR trigger if enabled
                if (activeProject?.settings?.auto_ocr ?? true) {
                  showToast("เริ่มต้นตรวจจับและ OCR อัตโนมัติ...", "info");
                  await runPipelineStep('detect');
                  await runPipelineStep('ocr');
                }
              } catch (err: any) {
                showToast(`Upload failed: ${err.message}`, 'error');
              } finally {
                setStatus('Ready', false);
              }
            }
          }}
        >
          {/* Page Navigator */}
          <div className="flex-1 flex flex-col p-4.5 overflow-hidden">
            <div className="flex items-center justify-between mb-3.5 border-b border-zinc-900 pb-2">
              <h3 className="text-[10px] font-bold text-yellow-400 uppercase tracking-widest flex items-center gap-1.5 font-pixel">
                <ImageIcon size={12} /> Page List
              </h3>
              
              {activeProject && (
                <label className={`flex items-center gap-1.5 text-[9px] font-bold transition-all font-pixel ${
                  isProcessing 
                    ? 'text-slate-600 cursor-not-allowed' 
                    : 'cursor-pointer text-yellow-500 hover:text-yellow-400 hover-zoom'
                }`}>
                  <UploadCloud size={14} /> Add Pages
                  {!isProcessing && (
                    <input 
                      type="file" 
                      multiple 
                      accept="image/*" 
                      onChange={handlePageUpload} 
                      className="hidden" 
                    />
                  )}
                </label>
              )}
            </div>
 
            {!activeProject ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-zinc-900/10 rounded-sm border border-zinc-850">
                <FolderOpen size={32} className="text-slate-800 mb-2" />
                <p className="text-xs text-slate-500 font-medium">Please select or create a project to start translating.</p>
              </div>
            ) : !activeProject.pages || activeProject.pages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-850 rounded-sm bg-zinc-900/10">
                <UploadCloud size={32} className="text-zinc-800 mb-2" />
                <p className="text-xs text-slate-500 font-medium">No pages added. Upload image files above.</p>
              </div>
            ) : (
              <div className="page-list-scroll flex-1 overflow-y-auto pr-1 flex flex-col gap-2.5">
                {activeProject.pages.map((p) => {
                  const previewUrl = `/static/projects/${p.project_id}/${p.id}/thumbnail.jpg`;
                  const isActive = activePage?.id === p.id;
                  return (
                    <div
                      key={p.id}
                      className={`group relative flex items-center gap-3.5 p-2.5 rounded-md border sidebar-page-card ${
                        isActive
                          ? 'active-page-card'
                          : 'bg-zinc-950/35 border-zinc-900/80'
                      }`}
                    >
                      <button
                        onClick={() => selectPage(p.id)}
                        className="flex flex-1 items-center gap-3.5 text-left focus:outline-none min-w-0 cursor-pointer"
                      >
                        <div className="w-12 h-16 rounded-sm overflow-hidden bg-slate-950 flex-shrink-0 border border-zinc-850 shadow-md">
                          <img 
                            src={previewUrl} 
                            alt={`Page ${p.page_number}`} 
                            width={48}
                            height={64}
                            loading="lazy"
                            decoding="async"
                            className="w-full h-full object-cover" 
                            onError={(e) => { e.currentTarget.style.display = 'none'; }}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-slate-200">Page {p.page_number}</p>
                          <p className="text-[10px] text-slate-500 truncate mt-0.5">{p.name || 'Image File'}</p>
                          <span className={`inline-block text-[9px] px-2 py-0.5 rounded-md mt-2.5 font-bold uppercase tracking-wider ${
                            p.status === 'processed' ? 'badge-active' : 'badge-pending'
                          }`}>
                            {p.status}
                          </span>
                        </div>
                      </button>
 
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          showConfirmDialog(
                            `คุณแน่ใจหรือไม่ที่จะลบ "หน้า ${p.page_number}"?\nรูปภาพนี้จะถูกลบอย่างถาวร!`,
                            async () => {
                              try {
                                const store = useProjectStore.getState();
                                await store.deletePage(p.id);
                                showToast(`ลบหน้า ${p.page_number} สำเร็จ!`, 'success');
                              } catch (err: any) {
                                showToast(`ลบล้มเหลว: ${err.message}`, 'error');
                              }
                            },
                            `ยืนยันการลบหน้า ${p.page_number}`
                          );
                        }}
                        disabled={isProcessing}
                        className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 focus:opacity-100 p-1.5 text-slate-500 hover:text-rose-400 transition-all rounded bg-slate-950/80 border border-white/5 hover:border-rose-900/30"
                        title="ลบหน้านี้"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
        {/* 3. MIDDLE CANVAS WORKSPACE (Floating with backdrop glow) */}
        <main className="flex-1 border border-zinc-900 bg-zinc-950/25 backdrop-blur-sm overflow-hidden flex flex-col shadow-2xl relative select-none animate-fade-in">
          {/* Ambient Glow behind Canvas */}
          <div className="cosmic-glow top-[10%] left-[10%]" />
          
          {!activeProject ? (
            <div className="flex-1 flex flex-col items-center justify-start text-slate-400 p-6 lg:p-10 z-10 font-sans max-w-5xl mx-auto w-full select-none overflow-y-auto relative custom-scrollbar">
              <button
                type="button"
                onClick={() => setShowGlobalSettingsModal(true)}
                className="absolute top-4 right-4 p-2.5 rounded-lg border border-zinc-800 bg-zinc-950/60 text-slate-400 hover:text-amber-400 hover:border-yellow-500/30 transition-all duration-300 hover:scale-105 cursor-pointer shadow-lg group z-20"
                title="Global Settings (ตั้งค่าระบบ)"
              >
                <Settings size={18} className="group-hover:rotate-45 transition-transform duration-500" />
              </button>

              {/* Logo / Header */}
              <div className="flex flex-col items-center text-center mt-2 mb-8 shrink-0">
                <div className="relative mb-4">
                  <div className="absolute inset-0 rounded-2xl bg-amber-500/15 blur-xl animate-pulse" />
                  <div className="w-14 h-14 rounded-2xl bg-[#121218] border-2 border-amber-500/40 flex items-center justify-center relative z-10 shadow-2xl shadow-amber-500/20">
                    <Sparkles size={28} className="text-amber-400" />
                  </div>
                </div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono font-bold tracking-wider uppercase">
                    ⚡ HOUMI TRANSLATION STUDIO
                  </span>
                </div>
                <h1 className="text-xl lg:text-2xl font-black tracking-tight text-white mb-1.5">
                  ยินดีต้อนรับสู่ <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-amber-300 to-yellow-200">Houmi Studio</span>
                </h1>
                <p className="text-xs text-slate-400 max-w-lg leading-relaxed font-sans">
                  ระบบ AI จัดหน้าและแปลภาษามังงะ/เว็บตูนระดับมืออาชีพ รองรับการคลีนภาพ ตรวจจับบอลลูน และฟอนต์อักษรครบวงจร
                </p>
              </div>

              {/* 3 Action Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 w-full max-w-4xl mb-6 shrink-0">
                {/* 1. Open Local Folder */}
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const defaultPath = defaultLoadProjectPath || localStorage.getItem('houmi_last_load_project_path') || '';
                      const newProj = await browseFolderProject(defaultPath);
                      if (newProj) {
                        showToast(`นำเข้าโปรเจกต์ "${newProj.name}" สำเร็จ`, 'success');
                        await selectProject(newProj.id);
                        if (newProj.settings?.local_folder) {
                          localStorage.setItem('houmi_last_load_project_path', newProj.settings.local_folder);
                        }
                      }
                    } catch (e: any) {
                      showToast(`เปิดโฟลเดอร์ล้มเหลว: ${e.message}`, 'error');
                    }
                  }}
                  className="flex flex-col items-center text-center p-5 rounded-2xl border border-[#242436] bg-[#12121a]/80 hover:bg-[#181824] hover:border-amber-500/60 transition-all duration-300 shadow-xl cursor-pointer group hover:scale-[1.02] active:scale-[0.99] relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 px-2 py-0.5 bg-amber-500/10 border-b border-l border-amber-500/20 text-[8.5px] font-mono font-bold text-amber-400 rounded-bl-lg">
                    LOCAL FOLDER
                  </div>
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 group-hover:scale-110 group-hover:bg-amber-500/20 transition-all duration-300 mb-2.5 shadow-md shadow-amber-500/10">
                    <FolderOpen size={24} className="text-amber-400" />
                  </div>
                  <h3 className="text-xs font-bold text-slate-100 group-hover:text-amber-300 transition-colors">
                    เปิดโฟลเดอร์โปรเจกต์
                  </h3>
                  <p className="text-[10px] text-slate-400 mt-1 leading-relaxed font-sans">
                    เลือกโฟลเดอร์รูปภาพมังงะในเครื่องเพื่อเริ่มต้นทำงาน
                  </p>
                  <span className="mt-3 text-[9.5px] font-bold text-amber-400 group-hover:underline flex items-center gap-1 font-mono">
                    BROWSE FOLDER ➔
                  </span>
                </button>

                {/* 2. Create Blank Project */}
                <button
                  type="button"
                  onClick={() => setShowNewProjModal(true)}
                  className="flex flex-col items-center text-center p-5 rounded-2xl border border-[#242436] bg-[#12121a]/80 hover:bg-[#181824] hover:border-cyan-500/60 transition-all duration-300 shadow-xl cursor-pointer group hover:scale-[1.02] active:scale-[0.99] relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 px-2 py-0.5 bg-cyan-500/10 border-b border-l border-cyan-500/20 text-[8.5px] font-mono font-bold text-cyan-400 rounded-bl-lg">
                    BLANK PROJECT
                  </div>
                  <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 group-hover:scale-110 group-hover:bg-cyan-500/20 transition-all duration-300 mb-2.5 shadow-md shadow-cyan-500/10">
                    <FolderPlus size={24} className="text-cyan-400" />
                  </div>
                  <h3 className="text-xs font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">
                    สร้างโปรเจกต์ใหม่
                  </h3>
                  <p className="text-[10px] text-slate-400 mt-1 leading-relaxed font-sans">
                    ตั้งค่าพื้นที่ทำงานว่าง กำหนดภาษาต้นทางและปลายทาง
                  </p>
                  <span className="mt-3 text-[9.5px] font-bold text-cyan-400 group-hover:underline flex items-center gap-1 font-mono">
                    NEW WORKSPACE ➔
                  </span>
                </button>

                {/* 3. Smart Stitch (Webtoon) */}
                <button
                  type="button"
                  onClick={() => setShowSmartStitchModal(true)}
                  className="flex flex-col items-center text-center p-5 rounded-2xl border border-[#242436] bg-[#12121a]/80 hover:bg-[#181824] hover:border-purple-500/60 transition-all duration-300 shadow-xl cursor-pointer group hover:scale-[1.02] active:scale-[0.99] relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 px-2 py-0.5 bg-purple-500/10 border-b border-l border-purple-500/20 text-[8.5px] font-mono font-bold text-purple-400 rounded-bl-lg">
                    AI WEBTOON
                  </div>
                  <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/30 group-hover:scale-110 group-hover:bg-purple-500/20 transition-all duration-300 mb-2.5 shadow-md shadow-purple-500/10">
                    <Scissors size={24} className="text-purple-400" />
                  </div>
                  <h3 className="text-xs font-bold text-slate-100 group-hover:text-purple-300 transition-colors">
                    Smart Stitch (ตัดต่อเว็บตูน)
                  </h3>
                  <p className="text-[10px] text-slate-400 mt-1 leading-relaxed font-sans">
                    ตัดแบ่งภาพเว็บตูนขนาดยาว (Long-strip) ด้วย AI
                  </p>
                  <span className="mt-3 text-[9.5px] font-bold text-purple-400 group-hover:underline flex items-center gap-1 font-mono">
                    OPEN SMART STITCH ➔
                  </span>
                </button>
              </div>

              {/* Recent Projects Section */}
              <div className="w-full max-w-4xl flex flex-col gap-2.5 pt-1 animate-slide-up shrink-0">
                <div className="flex items-center justify-between border-b border-[#242436] pb-2">
                  <div className="flex items-center gap-2">
                    <Folder size={14} className="text-amber-400" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                      โปรเจกต์ล่าสุด (Recent Projects)
                    </h4>
                    <span className="text-[10px] font-mono font-bold bg-[#181824] text-amber-300 px-2 py-0.5 rounded-full border border-amber-500/20">
                      {projects?.length || 0}
                    </span>
                  </div>
                  {projects && projects.length > 0 && (
                    <button
                      type="button"
                      onClick={() => void fetchProjects()}
                      className="text-[10px] text-slate-400 hover:text-amber-400 flex items-center gap-1 cursor-pointer font-mono"
                    >
                      <RefreshCw size={10} /> รีเฟรช
                    </button>
                  )}
                </div>

                {projects && projects.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 pb-4">
                    {projects.map((p) => (
                      <div
                        key={p.id}
                        onClick={() => void selectProject(p.id)}
                        className="p-3 rounded-xl border border-[#20202e] bg-[#121218] hover:border-amber-500/50 hover:bg-[#161622] transition-all cursor-pointer group flex flex-col justify-between gap-2 shadow-sm"
                      >
                        <div className="flex items-start gap-2.5">
                          <div className="p-2 rounded-lg bg-[#181824] border border-[#262638] group-hover:border-amber-500/40 transition-colors shrink-0">
                            <Folder size={16} className="text-amber-400" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <h5 className="text-xs font-bold text-slate-100 group-hover:text-amber-300 truncate">
                              {p.name}
                            </h5>
                            <p className="text-[10px] text-slate-500 truncate mt-0.5 font-mono">
                              {p.settings?.local_folder || 'Local Project'}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[9px] font-mono text-slate-400">
                          <span className="bg-[#1a1a24] px-1.5 py-0.5 rounded text-amber-400/90 font-semibold">
                            {p.pages?.length || 0} หน้า (Pages)
                          </span>
                          <span className="text-slate-500">
                            {p.source_lang?.toUpperCase() || 'JA'} ➔ {p.target_lang?.toUpperCase() || 'TH'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 text-center rounded-xl border border-dashed border-[#242436] bg-[#101016]/50">
                    <p className="text-xs text-slate-400">ยังไม่มีประวัติโปรเจกต์ในเครื่อง</p>
                    <p className="text-[10px] text-slate-500 mt-1">เริ่มต้นด้วยการเปิดโฟลเดอร์หรือสร้างโปรเจกต์ใหม่ด้านบน</p>
                  </div>
                )}
              </div>
            </div>
          ) : activePage ? (
            <Canvas 
              onOpenMaskEditor={(blockId: string) => setSelectedBlockForMaskEdit(blockId)} 
              onRunOCR={(blockIds) => runPipelineStep('ocr', blockIds)}
              onRunInpaintPreview={handleRunInpaintPreview}
              onEnsureInpainted={() => runPipelineStep('inpaint')}
              onRefreshPage={refreshActivePage}
              onRefitPageText={reorganizePageText}
              onResetPageMasks={() => resetMasksAndClean('page')}
              onResetProjectMasks={() => resetMasksAndClean('project')}
              liveMaskOverlay={liveMaskOverlay}
              cleanPreviewRevision={cleanPreviewRevision}
              showBottomPageNavigator={!leftSidebarOpen}
              showFloatingLetteringBar={showFloatingLetteringBar}
              onCloseFloatingLetteringBar={() => {
                setShowFloatingLetteringBar(false);
                try { localStorage.setItem('houmi_show_floating_lettering_bar', 'false'); } catch {}
                showToast('ซ่อนแถบเครื่องมือลอยแล้ว (เปิดใหม่ได้ที่เมนู View หรือปุ่ม 🎛️ Toolbar)', 'info');
              }}
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 p-8 z-10 font-sans">
              <div className="w-16 h-16 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-4 pulse shadow-lg shadow-yellow-500/5">
                <ImageIcon size={28} className="text-yellow-500" />
              </div>
              <p className="text-sm font-extrabold text-slate-300 font-pixel">Select a page to open the Canvas Workspace</p>
              <p className="text-xs text-slate-500 mt-1 max-w-xs text-center font-sans">Double click any box on the canvas to activate editing and start typing translations.</p>
            </div>
          )}

          {/* Smooth premium loading overlay */}
          {isProcessing && (
            <div role="status" aria-live="polite" className="absolute inset-0 bg-[#09090b]/80 backdrop-blur-md flex flex-col items-center justify-center gap-3.5 z-30 transition-all duration-300">
              <div className="relative flex items-center justify-center w-14 h-14">
                <div className="absolute w-full h-full rounded-full border-4 border-yellow-500/20 border-t-yellow-500 animate-spin" />
                <div className="absolute w-9 h-9 rounded-full border-4 border-yellow-500/20 border-b-yellow-500 animate-spin-reverse" />
              </div>
              <div className="flex flex-col items-center gap-1.5 text-center font-sans">
                <p className="text-sm font-extrabold text-yellow-400 tracking-wide animate-pulse font-pixel">{statusMessage}</p>
                <span className="text-[10px] text-slate-500 font-extrabold tracking-wider uppercase animate-pulse font-pixel">Running backend process...</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  cancelBatchWorkflow();
                  useProjectStore.setState({ isProcessing: false, statusMessage: 'Ready' });
                }}
                className="mt-2 px-3.5 py-1 text-[10px] font-bold text-rose-300 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 rounded-lg transition-colors cursor-pointer shadow-lg active:scale-95"
              >
                ✕ ปิดหน้าต่างนี้ (Dismiss / Cancel)
              </button>
            </div>
          )}
        </main>

        {workspaceMode === 'typeset' && (
          <aside
            className={`fixed top-[136px] z-40 max-h-[calc(100vh-164px)] overflow-hidden border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur-md transition-[width] duration-200 ${
              typesetInspectorCollapsed
                ? 'w-10'
                : 'w-[clamp(244px,18vw,292px)] max-[760px]:w-[220px]'
            }`}
            style={{ right: rightSidebarOpen ? 332 : 12 }}
            aria-label="Typesetting inspector"
          >
            <button
              type="button"
              onClick={() => setTypesetInspectorCollapsed(value => !value)}
              className={`flex h-10 w-full items-center border-b border-zinc-800 bg-zinc-900/95 font-pixel text-[9px] font-bold uppercase tracking-wider text-slate-200 hover:text-yellow-300 ${typesetInspectorCollapsed ? 'justify-center px-0' : 'justify-between px-3'}`}
              aria-expanded={!typesetInspectorCollapsed}
              title={typesetInspectorCollapsed ? 'Open Typography Controls' : 'Collapse Typography Controls'}
            >
              {!typesetInspectorCollapsed && <span>Text & Formatting</span>}
              {typesetInspectorCollapsed ? <TypeIcon size={14} /> : <ChevronDown size={13} />}
            </button>
            {!typesetInspectorCollapsed && (
              <>
                <div className="grid grid-cols-2 border-b border-zinc-800 bg-zinc-950 p-1">
                  <button type="button" onClick={() => setTypesetInspectorTab('character')} className={`flex items-center justify-center gap-1.5 px-2 py-2 text-[9px] font-bold uppercase tracking-wider ${typesetInspectorTab === 'character' ? 'bg-yellow-500 text-black' : 'text-slate-500 hover:bg-zinc-900 hover:text-slate-200'}`}>
                    <TypeIcon size={12} /> Text Style
                  </button>
                  <button type="button" onClick={() => setTypesetInspectorTab('templates')} className={`flex items-center justify-center gap-1.5 px-2 py-2 text-[9px] font-bold uppercase tracking-wider ${typesetInspectorTab === 'templates' ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-500 hover:bg-zinc-900 hover:text-slate-200'}`}>
                    <Palette size={12} /> Templates
                  </button>
                </div>

                {typesetInspectorTab === 'character' && (
                  <div className="max-h-[calc(100vh-252px)] overflow-y-auto p-3.5 space-y-3 font-sans">
                    {!selectedBlock ? (
                      <p className="text-xs text-slate-500 text-center py-4">เลือก Text Layer เพื่อปรับแต่ง Font, สี และระยะบรรทัด</p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {isMulti && (
                          <div className="border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 rounded-md text-[10px] font-bold text-amber-300 flex items-center gap-1.5">
                            <span>✏️</span> Editing {selectedBlocks.length} selected text layers
                          </div>
                        )}

                        {/* Font Family Dropdown with Visual Font Explorer */}
                        <div>
                          <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                            Font Family
                          </label>
                          <FontSelector
                            value={inspectorFontValue}
                            availableFonts={inspectorFontOptions}
                            availableFamilies={systemFontFamilies}
                            onFontUploaded={reloadFonts}
                            onRescanFonts={reloadFonts}
                            onChange={(font) => void handleBlockChange({ font_family: font })}
                            className="w-full"
                          />
                        </div>

                        {/* Font Size & Auto Size Pill */}
                        <div className="grid grid-cols-2 gap-2.5 items-end">
                          <div>
                            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                              Font Size (pt)
                            </label>
                            <input
                              type="number"
                              min="6"
                              max="150"
                              step="0.5"
                              value={
                                isMulti
                                  ? commonFontSize
                                  : effectiveFontSize(selectedBlock)
                                  ? Math.round(Number(effectiveFontSize(selectedBlock)) * 10) / 10
                                  : 18
                              }
                              placeholder={isMulti ? 'Mixed' : ''}
                              onChange={(e) => void handleBlockChange({ font_size: Number(e.target.value) || 12 })}
                              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-2 text-xs text-amber-400 font-mono focus:outline-none font-bold transition-colors"
                            />
                          </div>

                          {/* Auto Size Pill Button */}
                          <button
                            type="button"
                            onClick={() => void handleBlockMetadataChange({ manual_font_size: null, font_size_mode: 'auto' })}
                            className={`w-full py-2 px-2.5 rounded-lg border text-[10px] font-bold tracking-wide transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                              isAutoFontSize
                                ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-300 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                                : 'border-zinc-800 bg-zinc-900 text-slate-400 hover:text-amber-300 hover:border-amber-500/40'
                            }`}
                            title="Auto fit font size to balloon bounds"
                          >
                            <Sparkles size={11} className={isAutoFontSize ? 'text-emerald-400 animate-pulse' : ''} />
                            <span>{isAutoFontSize ? 'Auto-Fit Active' : 'Auto-Fit Balloon'}</span>
                          </button>
                        </div>

                        {/* Font Style & Alignment Bar */}
                        <div className="grid grid-cols-2 gap-2.5">
                          <div>
                            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                              Style
                            </label>
                            <select
                              value={commonFontStyle}
                              onChange={(e) => {
                                const style = e.target.value;
                                void handleBlockChange({
                                  bold: style === 'bold' || style === 'bold_italic',
                                  italic: style === 'italic' || style === 'bold_italic',
                                });
                              }}
                              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-2 text-xs text-slate-200 focus:outline-none transition-colors"
                            >
                              {isMulti && commonFontStyle === '' && <option value="">Mixed Styles</option>}
                              <option value="regular">Regular</option>
                              <option value="bold">Bold</option>
                              <option value="italic">Italic</option>
                              <option value="bold_italic">Bold Italic</option>
                            </select>
                          </div>

                          <div>
                            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                              Alignment
                            </label>
                            <div className="grid grid-cols-3 border border-zinc-800 bg-zinc-950 rounded-lg p-0.5">
                              {(['left', 'center', 'right'] as const).map((align) => {
                                const isActive = (isMulti ? commonTextAlign : selectedBlock.text_align) === align;
                                return (
                                  <button
                                    key={align}
                                    type="button"
                                    onClick={() => void handleBlockChange({ text_align: align })}
                                    className={`py-1.5 flex items-center justify-center rounded-md transition-all cursor-pointer ${
                                      isActive
                                        ? 'bg-amber-500 text-black font-bold shadow'
                                        : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-850'
                                    }`}
                                    title={`${align} align`}
                                  >
                                    {align === 'left' && <AlignLeft size={13} />}
                                    {align === 'center' && <AlignCenter size={13} />}
                                    {align === 'right' && <AlignRight size={13} />}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        </div>

                        {/* Fill Color */}
                        <div className="pt-1">
                          <ColorField
                            label="Fill Color"
                            value={isMulti ? commonColorHex || selectedBlock.color_hex : selectedBlock.color_hex}
                            mixed={isMulti && !commonColorHex}
                            onChange={(color_hex) => void handleBlockChange({ color_hex })}
                            compact
                          />
                        </div>

                        {/* Photoshop Character Pair Fields: Leading & Tracking */}
                        <div className="grid grid-cols-2 gap-2.5 pt-1 border-t border-zinc-850/80">
                          <div>
                            <div className="flex items-center gap-1 mb-1">
                              <span className="text-[11px] font-bold text-amber-400 font-serif">A/A</span>
                              <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
                                Leading (Line)
                              </label>
                            </div>
                            <input
                              type="number"
                              min="0.8"
                              max="3"
                              step="0.05"
                              value={commonLeading}
                              placeholder={isMulti && commonLeading === '' ? 'Mixed' : '1.2'}
                              onChange={(e) => void handleBlockMetadataChange({ line_height_ratio: Number(e.target.value) || 1.2 })}
                              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-2 text-xs text-slate-100 font-mono focus:outline-none transition-colors"
                            />
                          </div>

                          <div>
                            <div className="flex items-center gap-1 mb-1">
                              <span className="text-[11px] font-bold text-amber-400 font-mono tracking-tighter">V/A</span>
                              <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
                                Tracking (Spacing)
                              </label>
                            </div>
                            <input
                              type="number"
                              min="-200"
                              max="500"
                              step="10"
                              value={commonTracking}
                              placeholder={isMulti && commonTracking === '' ? 'Mixed' : '0'}
                              onChange={(e) => {
                                const tracking = Number(e.target.value) || 0;
                                void handleBlockMetadataChange({ tracking, letter_spacing: tracking });
                              }}
                              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-2 text-xs text-slate-100 font-mono focus:outline-none transition-colors"
                            />
                          </div>
                        </div>

                        {/* Rotation Slider */}
                        <div className="pt-1">
                          <RotationControl
                            key={metadataTargets.map((block) => `${block.id}:${block.rotation_deg}`).join('|')}
                            value={rotationValue}
                            mixed={rotationMixed}
                            onCommit={(rotation_deg) => void handleBlockChange({ rotation_deg })}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {typesetInspectorTab === 'templates' && <div className="max-h-[calc(100vh-252px)] overflow-y-auto p-3">
              {!selectedBlock ? (
                <p className="text-xs text-slate-500">เลือก Text Layer เพื่อใช้ Role หรือ Font Template</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {(() => {
                    const role = resolveBlockTemplateRole(selectedBlock, stylePresets);
                    return (
                      <div className="border border-cyan-500/25 bg-cyan-500/5 px-2.5 py-2 text-[10px] text-cyan-100">
                        Current: <strong>{role.roleLabel}</strong>
                        <span className="text-slate-500"> · {role.fontLabel}</span>
                      </div>
                    );
                  })()}
                  <div className="grid grid-cols-2 gap-1.5">
                    {Object.entries(stylePresets).map(([key, template]) => {
                      const active = resolveBlockTemplateRole(selectedBlock, stylePresets).templateId;
                      const selected = active === template.id || active === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => void applyTextTemplate(template)}
                          className={`min-w-0 border px-2 py-2 text-left text-[10px] font-bold transition-colors ${
                            selected
                              ? 'border-yellow-500 bg-yellow-500/15 text-yellow-300'
                              : 'border-zinc-800 bg-zinc-900 text-slate-300 hover:border-yellow-500/50 hover:text-yellow-300'
                          }`}
                          title={`${template.font_stack[0]} · ${template.font_size}px`}
                        >
                          <span className="block truncate">{template.semantic_tag || template.name || key}</span>
                          <span className="block truncate pt-0.5 text-[8px] font-normal text-slate-500">{template.font_stack[0]} · {template.font_size}px</span>
                        </button>
                      );
                    })}
                  </div>
                  <button
                    type="button"
                    onClick={openTemplateSettings}
                    className="border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-[9px] font-bold uppercase tracking-wider text-slate-300 hover:border-yellow-500/50 hover:text-yellow-300"
                  >
                    Manage Templates
                  </button>
                </div>
              )}
                </div>}
              </>
            )}
          </aside>
        )}

        {layerContextMenu && (() => {
          const block = activePage?.text_blocks.find(item => item.id === layerContextMenu.blockId);
          if (!block) return null;
          const x = Math.min(layerContextMenu.x, window.innerWidth - 224);
          const y = Math.min(layerContextMenu.y, window.innerHeight - 250);
          const choose = (action: () => void) => {
            action();
            setLayerContextMenu(null);
          };
          return (
            <div className="fixed z-[90] w-56 border border-zinc-700 bg-zinc-950 p-1.5 shadow-2xl" style={{ left: Math.max(8, x), top: Math.max(8, y) }} onClick={(e) => e.stopPropagation()}>
              <div className="border-b border-zinc-800 px-2 py-2">
                <span className="block font-pixel text-[8px] font-bold uppercase tracking-wider text-yellow-300">Text Layer {block.block_index + 1}</span>
                <span className="mt-1 block truncate text-[10px] text-slate-500">{stripSemanticTranslationTags(block.translation || block.source_text || 'Empty layer')}</span>
              </div>
              <span className="block px-2 pb-1 pt-2 text-[7px] font-bold uppercase tracking-wider text-slate-600">Layer settings</span>
              {workspaceMode === 'typeset' && <>
                <button type="button" onClick={() => choose(() => { setTypesetInspectorTab('character'); setTypesetInspectorCollapsed(false); })} className="flex w-full items-center gap-2 px-2 py-2 text-left text-xs text-slate-300 hover:bg-zinc-900 hover:text-yellow-300"><TypeIcon size={13} /> Text Style</button>
                <button type="button" onClick={() => choose(() => { setTypesetInspectorTab('templates'); setTypesetInspectorCollapsed(false); })} className="flex w-full items-center gap-2 px-2 py-2 text-left text-xs text-slate-300 hover:bg-zinc-900 hover:text-cyan-200"><Palette size={13} /> Role / Template</button>
              </>}
              <button type="button" onClick={() => choose(() => setLayerStrokeModalBlockId(block.id))} className="flex w-full items-center gap-2 px-2 py-2 text-left text-xs text-slate-300 hover:bg-zinc-900 hover:text-amber-300"><Palette size={13} /> Layer Stroke & Outline...</button>
              <button type="button" onClick={() => choose(() => setSelectedBlockForMaskEdit(block.id))} className="flex w-full items-center gap-2 px-2 py-2 text-left text-xs text-slate-300 hover:bg-zinc-900 hover:text-cyan-200"><Paintbrush size={13} /> Edit Text Mask</button>
              {workspaceMode === 'typeset' && <>
                <span className="block border-t border-zinc-800 px-2 pb-1 pt-2 text-[7px] font-bold uppercase tracking-wider text-slate-600">Page actions</span>
                <button type="button" onClick={() => choose(() => void reorganizePageText())} className="flex w-full items-center gap-2 px-2 py-2 text-left text-xs text-slate-300 hover:bg-zinc-900 hover:text-yellow-300"><RefreshCw size={13} /> Refit Page Text</button>
              </>}
              <button type="button" onClick={() => choose(() => { if (window.confirm('Delete this text layer?')) void deleteBlocks([block.id]); })} className="mt-1 flex w-full items-center gap-2 border-t border-zinc-800 px-2 py-2 text-left text-xs text-rose-300 hover:bg-rose-500/10"><Trash2 size={13} /> Delete Layer</button>
            </div>
          );
        })()}

        {/* Left Sidebar Toggle Button */}
        <button
          onClick={() => setLeftSidebarOpen(prev => !prev)}
          className="absolute top-1/2 -translate-y-1/2 w-4 h-14 bg-zinc-950 hover:bg-yellow-500 hover:text-black border border-zinc-800 hover:border-amber-400 rounded-r-sm flex items-center justify-center cursor-pointer transition-all duration-300 z-30 shadow-2xl group"
          style={{ left: leftSidebarOpen ? '288px' : '16px' }}
          title={leftSidebarOpen ? "ซ่อนแผงด้านซ้าย" : "แสดงแผงด้านซ้าย"}
        >
          {leftSidebarOpen ? (
            <ChevronLeft size={10} className="text-slate-400 group-hover:text-black transition-colors" />
          ) : (
            <ChevronRight size={10} className="text-slate-400 group-hover:text-black transition-colors" />
          )}
        </button>

        {/* Right Sidebar Toggle Button */}
        <button
          onClick={() => setRightSidebarOpen(prev => !prev)}
          className="absolute top-1/2 -translate-y-1/2 w-4 h-14 bg-zinc-950 hover:bg-yellow-500 hover:text-black border border-zinc-800 hover:border-amber-400 rounded-l-sm flex items-center justify-center cursor-pointer transition-all duration-300 z-30 shadow-2xl group"
          style={{ right: rightSidebarOpen ? '320px' : '16px' }}
          title={rightSidebarOpen ? "ซ่อนแผงด้านขวา" : "แสดงแผงด้านขวา"}
        >
          {rightSidebarOpen ? (
            <ChevronRight size={10} className="text-slate-400 group-hover:text-white transition-colors" />
          ) : (
            <ChevronLeft size={10} className="text-slate-400 group-hover:text-white transition-colors" />
          )}
        </button>

        {/* ================= PHOTOSHOP STYLE VERTICAL ICON RAIL & FLYOUT ================= */}
        <div className="relative z-40 shrink-0 flex">
  {/* ================= PHOTOSHOP STYLE VERTICAL ICON RAIL ================= */}
        <div className="w-9 bg-zinc-950/95 backdrop-blur-xl border-l border-zinc-900 flex flex-col items-center py-2 gap-2 z-30 shrink-0">
          <span 
            onClick={() => setIsFormattingWidgetOpen(!isFormattingWidgetOpen)} 
            className="text-slate-400 hover:text-white text-[11px] font-bold cursor-pointer p-1"
            title="เปิด/ปิด แผงสไตล์ข้อความ Text Formatting"
          >
            {isFormattingWidgetOpen ? '«' : '»'}
          </span>
          <button 
            type="button"
            onClick={() => setIsFormattingWidgetOpen(!isFormattingWidgetOpen)}
            className={`w-7 h-7 rounded-md border font-pixel font-bold text-xs flex items-center justify-center transition-all cursor-pointer ${
              isFormattingWidgetOpen 
                ? 'bg-amber-500/15 border-amber-500 text-amber-400 shadow-sm shadow-amber-500/30' 
                : 'bg-transparent border-transparent text-slate-400 hover:bg-zinc-900 hover:text-white'
            }`}
            title="🎨 Text Formatting (เปิด/ปิดแผงสไตล์)"
          >
            A|
          </button>
          <button 
            type="button"
            onClick={() => showToast('⚡ Pipeline Controls (แผงควบคุม Stage)', 'info')}
            className="w-7 h-7 rounded-md border border-transparent bg-transparent text-slate-400 hover:bg-zinc-900 hover:text-white font-bold text-xs flex items-center justify-center transition-all cursor-pointer"
            title="⚡ Quick Pipeline Status"
          >
            ⚡
          </button>
          <button 
            type="button"
            onClick={() => showToast('📑 Layers & Text Review Stack', 'info')}
            className="w-7 h-7 rounded-md border border-transparent bg-transparent text-slate-400 hover:bg-zinc-900 hover:text-white font-bold text-xs flex items-center justify-center transition-all cursor-pointer"
            title="📑 Layers Stack"
          >
            📑
          </button>
        </div>

  {/* ================= 1. HOUMI "TEXT & FORMATTING" FLYOUT PANEL ================= */}
        {activeProject && isFormattingWidgetOpen && (
          <div
            style={{
              left: `${formattingWidgetPos.x}px`,
              top: `${formattingWidgetPos.y}px`,
            }}
            className={`fixed z-50 flex flex-col overflow-hidden transition-shadow duration-150 animate-fade-in bg-zinc-950/95 backdrop-blur-xl border border-amber-500/35 rounded-xl shadow-[-15px_10px_35px_rgba(0,0,0,0.85)] ${
              isFormattingWidgetMinimized ? 'w-64' : 'w-72 sm:w-80 max-h-[calc(100vh-100px)]'
            }`}
          >
            {/* Draggable Title Bar */}
            <div
              onPointerDown={handleWidgetPointerDown}
              onPointerMove={handleWidgetPointerMove}
              onPointerUp={handleWidgetPointerUp}
              className="px-3 py-2 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between shrink-0 font-pixel cursor-grab active:cursor-grabbing select-none"
              title="คลิกค้างเพื่อลากย้ายตำแหน่งหน้าต่างได้อย่างอิสระ (Drag freely anywhere)"
            >
              <div className="flex items-center gap-1.5 truncate">
                <span className="text-slate-500 hover:text-amber-400 cursor-grab">⠿</span>
                <span className="text-[11px] font-bold text-amber-400 uppercase tracking-widest truncate">
                  🎨 TEXT & FORMATTING ({selectedBlocks.length > 0 ? `#${selectedBlocks[0]?.block_index + 1}` : 'No Block'})
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => setFormattingWidgetPos({ x: 20, y: 70 })}
                  className="p-1 text-slate-400 hover:text-amber-300 hover:bg-zinc-800 rounded transition-colors text-[10px] cursor-pointer"
                  title="ยึดฝั่งซ้าย (Dock Left)"
                >
                  ⇱
                </button>
                <button
                  type="button"
                  onClick={() => setFormattingWidgetPos({ x: Math.max(20, window.innerWidth - 380), y: 70 })}
                  className="p-1 text-slate-400 hover:text-amber-300 hover:bg-zinc-800 rounded transition-colors text-[10px] cursor-pointer"
                  title="ยึดฝั่งขวา (Dock Right)"
                >
                  ⇲
                </button>
                <button
                  type="button"
                  onClick={() => setIsFormattingWidgetMinimized(!isFormattingWidgetMinimized)}
                  className="p-1 text-slate-400 hover:text-amber-300 hover:bg-zinc-800 rounded transition-colors text-[10px] font-bold cursor-pointer"
                  title={isFormattingWidgetMinimized ? 'ขยายหน้าต่าง (Expand)' : 'ย่อขนาด (Minimize)'}
                >
                  {isFormattingWidgetMinimized ? '➕' : '➖'}
                </button>
                <button 
                  type="button"
                  onClick={() => setIsFormattingWidgetOpen(false)} 
                  className="p-1 text-slate-400 hover:text-rose-400 hover:bg-zinc-800 rounded transition-colors text-xs font-bold cursor-pointer" 
                  title="ปิดหน้าต่าง (Close)"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Content Body */}
            {!isFormattingWidgetMinimized && (
            <div className="p-3.5 flex flex-col gap-3 overflow-y-auto font-pixel text-xs">
              {/* 0. QUICK LETTERING ACTIONS ROW */}
              {selectedBlock && (
                <div className="flex items-center justify-between p-1.5 bg-zinc-900/90 border border-zinc-800 rounded-lg text-slate-300">
                  <button
                    type="button"
                    onClick={async () => {
                      if (!activePage || !selectedBlock) return;
                      showToast('✨ กำลังวิเคราะห์สีและเส้นขอบ...', 'info');
                      try {
                        const res = await apiFetch('/api/pipeline/extract-style', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            page_id: activePage.id,
                            bbox: [Math.round(selectedBlock.x), Math.round(selectedBlock.y), Math.round(selectedBlock.width), Math.round(selectedBlock.height)],
                            block_id: selectedBlock.id,
                          }),
                        });
                        if (res.ok) {
                          const data = await res.json();
                          if (data.style) {
                            const updates: Record<string, any> = {
                              color_hex: data.style.text_color || '#000000',
                            };
                            if (data.style.has_stroke && data.style.stroke_color) {
                              updates.stroke_color = data.style.stroke_color;
                              updates.stroke_width = data.style.stroke_width || 2;
                              updates.stroke_enabled = true;
                            }
                            await handleBlockChange(updates);
                            showToast('✨ ปรับสไตล์ตามภาพต้นฉบับสำเร็จ!', 'success');
                          }
                        }
                      } catch {
                        showToast('ไม่สามารถดึงสไตล์จากภาพได้', 'error');
                      }
                    }}
                    className="p-1.5 bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 rounded-md text-[10px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
                    title="✨ AI Auto-Extract Style จากภาพต้นฉบับ"
                  >
                    <Sparkles size={12} />
                    <span>Auto Style</span>
                  </button>

                  <button
                    type="button"
                    onClick={async () => {
                      if (!activePage || !selectedBlock) return;
                      showToast('🎯 กำลังคำนวณและจัดข้อความกึ่งกลางบอลลูน...', 'info');
                      try {
                        const res = await apiFetch(`/api/pipeline/blocks/${selectedBlock.id}/smart-balloon/recompute`, {
                          method: 'POST',
                        });
                        if (res.ok) {
                          const data = await res.json();
                          if (data.smart_x != null && data.smart_width != null) {
                            await useProjectStore.getState().updateBlock(selectedBlock.id, {
                              x: Number(data.smart_x),
                              y: Number(data.smart_y),
                              width: Number(data.smart_width),
                              height: Number(data.smart_height),
                              smart_x: Number(data.smart_x),
                              smart_y: Number(data.smart_y),
                              smart_width: Number(data.smart_width),
                              smart_height: Number(data.smart_height),
                            });
                            showToast('🎯 จัดกึ่งกลางบอลลูนสำเร็จ!', 'success');
                          }
                        }
                      } catch {
                        showToast('ไม่สามารถจัดกึ่งกลางบอลลูนได้', 'error');
                      }
                    }}
                    className="p-1.5 bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 rounded-md text-[10px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
                    title="🎯 คำนวณและจัดข้อความกึ่งกลางบอลลูน (Center in Balloon)"
                  >
                    <Crosshair size={12} />
                    <span>Center</span>
                  </button>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        if (selectedBlock) {
                          useProjectStore.getState().copyBlockStyle(selectedBlock.id);
                          showToast('📋 คัดลอกสไตล์แล้ว', 'info');
                        }
                      }}
                      className="p-1.5 hover:bg-zinc-800 rounded-md text-slate-400 hover:text-white transition-colors cursor-pointer"
                      title="คัดลอกสไตล์ตัวหนังสือ (Copy Style)"
                    >
                      <Copy size={12} />
                    </button>
                    <button
                      type="button"
                      disabled={!useProjectStore.getState().copiedStyle}
                      onClick={async () => {
                        if (selectedBlock) {
                          await useProjectStore.getState().pasteBlockStyle(selectedBlock.id);
                          showToast('📋 นำสไตล์มาใช้สำเร็จ', 'success');
                        }
                      }}
                      className="p-1.5 hover:bg-zinc-800 rounded-md text-slate-400 hover:text-white transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                      title="วางสไตล์ตัวหนังสือ (Paste Style)"
                    >
                      <Clipboard size={12} />
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        if (selectedBlock && activePage) {
                          await useProjectStore.getState().createBlock(activePage.id, {
                            x: selectedBlock.x + 20,
                            y: selectedBlock.y + 20,
                            width: selectedBlock.width,
                            height: selectedBlock.height,
                            source_text: selectedBlock.source_text,
                            translation: selectedBlock.translation,
                            font_family: selectedBlock.font_family,
                            font_size: selectedBlock.font_size,
                            color_hex: selectedBlock.color_hex,
                            bold: selectedBlock.bold,
                            italic: selectedBlock.italic,
                            text_align: selectedBlock.text_align,
                            text_direction: selectedBlock.text_direction,
                          });
                          showToast('📑 โคลนบล็อกข้อความสำเร็จ (Ctrl+D)', 'success');
                        }
                      }}
                      className="p-1.5 hover:bg-zinc-800 rounded-md text-slate-400 hover:text-white transition-colors cursor-pointer"
                      title="ทำสำเนาบล็อก (Duplicate Ctrl+D)"
                    >
                      <Layers size={12} />
                    </button>
                  </div>
                </div>
              )}

              {/* 1. TEMPLATES SECTION */}
              <div>
                <button
                  type="button"
                  onClick={() => setIsStyleTemplatesExpanded(!isStyleTemplatesExpanded)}
                  className="w-full flex items-center justify-between py-1 text-[9.5px] font-bold text-slate-300 uppercase tracking-wider hover:text-amber-300 transition-colors cursor-pointer"
                >
                  <span className="flex items-center gap-1.5">
                    <span>🎨</span>
                    <span>Style Templates</span>
                    <span className="text-slate-500 font-mono text-[9px]">({Object.keys(stylePresets).length})</span>
                  </span>
                  <span className="text-[9px] text-slate-400 font-mono">{isStyleTemplatesExpanded ? '▲ ซ่อน' : '▼ ขยาย'}</span>
                </button>
                
                {isStyleTemplatesExpanded && (
                  <div className="mt-1.5 animate-fade-in">
                    {/* Current Active Template Box */}
                    <div className="bg-cyan-500/10 border border-cyan-500/40 rounded-md px-3 py-2 text-[11px] text-cyan-300 flex items-center justify-between font-bold mb-2">
                      <span className="truncate">
                        Current: {selectedBlock ? resolveBlockTemplateRole(selectedBlock, stylePresets).roleLabel : 'ไม่มีบล็อกที่เลือก'}
                      </span>
                      <span className="shrink-0 ml-1">✓</span>
                    </div>

                    {/* Scrollable Template Grid */}
                    <div className="grid grid-cols-2 gap-1.5 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
                      {Object.entries(stylePresets).map(([key, template]) => {
                        const role = selectedBlock ? resolveBlockTemplateRole(selectedBlock, stylePresets) : null;
                        const isSelected = role && (role.templateId === template.id || role.templateId === key);
                        const fontName = template.font_stack?.[0] || 'Default';
                        const fontMissing = !isFontAvailable(fontName, systemFontFamilies, systemFonts);
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => void applyTextTemplate(template)}
                            className={`p-2 rounded-lg border text-left flex flex-col gap-0.5 transition-all cursor-pointer ${
                              isSelected
                                ? 'border-amber-500 bg-amber-500/15 text-amber-300 shadow-sm shadow-amber-500/20'
                                : 'border-zinc-800 bg-zinc-900/80 text-slate-300 hover:border-zinc-700 hover:bg-zinc-850'
                            }`}
                          >
                            <span className="text-[11px] font-bold text-white truncate" style={{ fontFamily: fontName }}>
                              {template.semantic_tag || template.name || key}
                            </span>
                            <span className="text-[9px] text-slate-400 font-mono truncate flex items-center gap-1">
                              <span className="truncate">{fontName} · {template.font_size}px</span>
                              {fontMissing && (
                                <span className="text-amber-400 font-bold shrink-0" title={`ไม่พบไฟล์ฟอนต์ ${fontName} ในเครื่อง (ใช้ Tahoma ชั่วคราว)`}>
                                  ⚠️
                                </span>
                              )}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              <div className="h-[1px] bg-zinc-800 my-0.5" />

              {/* 2. CUSTOM TEXT STYLE SECTION */}
              <div>
                <button
                  type="button"
                  onClick={() => setIsCustomStyleExpanded(!isCustomStyleExpanded)}
                  className="w-full flex items-center justify-between py-1 text-[9.5px] font-bold text-slate-300 uppercase tracking-wider hover:text-amber-300 transition-colors cursor-pointer"
                >
                  <span className="flex items-center gap-1.5">
                    <span>🔤</span>
                    <span>Custom Text Style</span>
                  </span>
                  <span className="text-[9px] text-slate-400 font-mono">{isCustomStyleExpanded ? '▲ ซ่อน' : '▼ ขยาย'}</span>
                </button>
                
                {isCustomStyleExpanded && (
                  <div className="mt-1.5 flex flex-col gap-2.5 animate-fade-in">
                  {/* Font Family (Full Width Row) */}
                  <div>
                    <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Font Family</span>
                    <FontSelector
                      value={selectedBlock?.font_family || 'TH Sarabun New'}
                      availableFonts={Array.from(new Set([
                        ...(selectedBlock?.font_family ? [selectedBlock.font_family] : []),
                        ...Object.values(stylePresets).map(t => t.font_stack?.[0]).filter(Boolean),
                        ...systemFonts,
                        'TH Sarabun New', 'TH SarabunPSK', 'TF Phethai', 'Tahoma', 'Angsana New', 'FC Sukhumvit', 'Layiji TaMaiTine1', 'Layiji JaRakeFadHang v1.0', 'FC Muffin', 'Itim'
                      ])).filter(Boolean)}
                      availableFamilies={systemFontFamilies}
                      onFontUploaded={reloadFonts}
                      onRescanFonts={reloadFonts}
                      onChange={(font) => {
                        if (selectedBlock) {
                          void handleBlockChange({ font_family: font });
                        }
                      }}
                      className="w-full"
                    />
                  </div>

                  {/* Font Size & Steppers & Auto Fit Row */}
                  <div>
                    <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Font Size (px)</span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          if (selectedBlock) {
                            const newSize = Math.max(8, (selectedBlock.font_size || 50) - 1);
                            void handleBlockChange({ font_size: newSize });
                          }
                        }}
                        disabled={!selectedBlock}
                        className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-slate-300 hover:text-white cursor-pointer transition-colors disabled:opacity-50"
                        title="ลดขนาดฟอนต์ 1pt"
                      >
                        <Minus size={12} />
                      </button>
                      <input 
                        type="number" 
                        value={selectedBlock?.font_size || 50} 
                        onChange={(e) => {
                          if (selectedBlock) {
                            void handleBlockChange({ font_size: parseInt(e.target.value) || 12 });
                          }
                        }}
                        disabled={!selectedBlock}
                        className="flex-1 bg-zinc-900 border border-zinc-800 text-white px-2 py-1.5 rounded-lg text-xs font-mono font-bold outline-none focus:border-amber-500 disabled:opacity-50 text-center"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          if (selectedBlock) {
                            const newSize = Math.min(150, (selectedBlock.font_size || 50) + 1);
                            void handleBlockChange({ font_size: newSize });
                          }
                        }}
                        disabled={!selectedBlock}
                        className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-slate-300 hover:text-white cursor-pointer transition-colors disabled:opacity-50"
                        title="เพิ่มขนาดฟอนต์ 1pt"
                      >
                        <Plus size={12} />
                      </button>
                      <button 
                        type="button"
                        onClick={() => {
                          if (selectedBlock) {
                            const text = selectedBlock.translation || selectedBlock.source_text || '';
                            const area = selectedBlock.width * selectedBlock.height;
                            const charCount = Math.max(1, text.length);
                            const estSize = Math.max(10, Math.min(72, Math.round(Math.sqrt(area / (charCount * 1.6)))));
                            void handleBlockChange({ font_size: estSize });
                            showToast(`⚡ Auto Fit ปรับเป็น ${estSize}px`, 'info');
                          }
                        }}
                        disabled={!selectedBlock}
                        className="px-2.5 py-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-lg text-[10px] font-bold hover:bg-amber-500/30 shrink-0 cursor-pointer disabled:opacity-50 transition-colors flex items-center gap-1"
                        title="Auto Fit Font Size"
                      >
                        <Wand2 size={11} /> <span>Auto</span>
                      </button>
                    </div>
                  </div>

                  {/* Collapsible Font Style & Alignment Disclosure */}
                  <div className="pt-0.5">
                    <button
                      type="button"
                      onClick={() => setIsStyleAlignExpanded(!isStyleAlignExpanded)}
                      className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-zinc-900/70 hover:bg-zinc-850 border border-zinc-800 text-[10px] text-slate-300 transition-colors cursor-pointer"
                    >
                      <span className="flex items-center gap-1.5 font-bold">
                        <span>📐</span>
                        <span>Font Style, Align & Direction</span>
                        {selectedBlock && (selectedBlock.bold || selectedBlock.italic || selectedBlock.text_align !== 'center' || selectedBlock.text_direction === 'vertical') && (
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        )}
                      </span>
                      <span className="text-slate-400 text-[9px] font-mono">{isStyleAlignExpanded ? '▲ ซ่อน' : '▼ ขยาย'}</span>
                    </button>

                    {isStyleAlignExpanded && (
                      <div className="mt-2 p-2.5 bg-zinc-900/40 border border-zinc-800 rounded-lg flex flex-col gap-2 animate-fade-in">
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Font Style</span>
                            <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 gap-0.5">
                              <button 
                                type="button"
                                onClick={() => {
                                  if (selectedBlock) {
                                    void handleBlockChange({ bold: !selectedBlock.bold });
                                  }
                                }}
                                disabled={!selectedBlock}
                                className={`flex-1 h-7 rounded-md font-bold text-xs cursor-pointer transition-colors ${
                                  selectedBlock?.bold ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'
                                }`}
                              >
                                B
                              </button>
                              <button 
                                type="button"
                                onClick={() => {
                                  if (selectedBlock) {
                                    void handleBlockChange({ italic: !selectedBlock.italic });
                                  }
                                }}
                                disabled={!selectedBlock}
                                className={`flex-1 h-7 rounded-md italic font-bold text-xs cursor-pointer transition-colors ${
                                  selectedBlock?.italic ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'
                                }`}
                              >
                                I
                              </button>
                            </div>
                          </div>

                          <div>
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Align</span>
                            <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 gap-0.5">
                              {(['left', 'center', 'right'] as const).map((align) => (
                                <button 
                                  key={align}
                                  type="button"
                                  onClick={() => {
                                    if (selectedBlock) {
                                      void handleBlockChange({ text_align: align });
                                    }
                                  }}
                                  disabled={!selectedBlock}
                                  className={`flex-1 h-7 rounded-md text-[10px] font-bold cursor-pointer transition-colors ${
                                    (selectedBlock?.text_align || 'center') === align ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'
                                  }`}
                                >
                                  {align === 'left' ? '⬅' : align === 'center' ? '↔' : '➡'}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div>
                          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Direction</span>
                          <button
                            type="button"
                            onClick={() => {
                              if (selectedBlock) {
                                const newDir = selectedBlock.text_direction === 'vertical' ? 'horizontal' : 'vertical';
                                void handleBlockChange({ text_direction: newDir });
                              }
                            }}
                            disabled={!selectedBlock}
                            className={`w-full h-7 rounded-md text-[10px] font-bold border transition-colors cursor-pointer flex items-center justify-center gap-1 ${
                              selectedBlock?.text_direction === 'vertical'
                                ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                                : 'bg-zinc-900 border-zinc-800 text-slate-300 hover:text-white'
                            }`}
                          >
                            <span>{selectedBlock?.text_direction === 'vertical' ? '↕ CJK (แนวตั้ง)' : '↔ LTR (แนวนอน)'}</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 3. Text Color & Stroke Color Pair */}
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-zinc-850">
                    <div className="relative">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1">
                          <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider">สีตัวอักษร (Text)</span>
                          {(selectedBlock?.extra_metadata?.color_source === 'ai_vision' || selectedBlock?.extra_metadata?.detected_color_hex) && (
                            <span
                              className="text-[8px] bg-sky-500/20 text-sky-300 px-1 py-0.2 rounded font-bold border border-sky-500/30 cursor-help"
                              title={`🤖 AI Vision ตรวจจับสี ${selectedBlock?.extra_metadata?.detected_color_hex || selectedBlock?.color_hex} จากต้นฉบับ`}
                            >
                              AI
                            </span>
                          )}
                        </div>
                        {(window as any).EyeDropper && (
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                const eyeDropper = new (window as any).EyeDropper();
                                const res = await eyeDropper.open();
                                if (res?.sRGBHex && selectedBlock) {
                                  void handleBlockChange({ color_hex: res.sRGBHex });
                                  showToast(`💧 ดูดสีฟอนต์: ${res.sRGBHex}`, 'info');
                                }
                              } catch {
                                // Cancelled
                              }
                            }}
                            className="p-0.5 text-slate-400 hover:text-amber-300 hover:bg-zinc-800 rounded transition-colors cursor-pointer"
                            title="ดูดสีฟอนต์จากหน้าจอ (Eyedropper)"
                          >
                            <Pipette size={11} />
                          </button>
                        )}
                      </div>
                      <ColorField
                        label=""
                        value={selectedBlock?.color_hex || '#000000'}
                        onChange={(color_hex) => {
                          if (selectedBlock) {
                            void handleBlockChange({ color_hex });
                          }
                        }}
                        compact
                      />
                    </div>
                    <div className="relative">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1">
                          <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider">สีเส้นขอบ (Stroke)</span>
                          {selectedBlock?.extra_metadata?.effect_sources?.stroke === 'ai_vision' && (
                            <span
                              className="text-[8px] bg-sky-500/20 text-sky-300 px-1 py-0.2 rounded font-bold border border-sky-500/30 cursor-help"
                              title="🤖 AI Vision ตรวจจับเส้นขอบจากต้นฉบับ"
                            >
                              AI
                            </span>
                          )}
                        </div>
                        {(window as any).EyeDropper && (
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                const eyeDropper = new (window as any).EyeDropper();
                                const res = await eyeDropper.open();
                                if (res?.sRGBHex && selectedBlock) {
                                  void handleBlockMetadataChange({ stroke_color: res.sRGBHex, stroke_enabled: true });
                                  showToast(`💧 ดูดสีเส้นขอบ: ${res.sRGBHex}`, 'info');
                                }
                              } catch {
                                // Cancelled
                              }
                            }}
                            className="p-0.5 text-slate-400 hover:text-amber-300 hover:bg-zinc-800 rounded transition-colors cursor-pointer"
                            title="ดูดสีเส้นขอบจากหน้าจอ (Eyedropper)"
                          >
                            <Pipette size={11} />
                          </button>
                        )}
                      </div>
                      <ColorField
                        label=""
                        value={String(selectedBlock?.extra_metadata?.stroke_color || '#ffffff')}
                        onChange={(stroke_color) => {
                          if (selectedBlock) {
                            void handleBlockMetadataChange({ stroke_color, stroke_enabled: true });
                          }
                        }}
                        compact
                      />
                    </div>
                  </div>

                  {/* Stroke Size Slider & Full FX Link */}
                  <div className="p-2 bg-zinc-900/60 border border-zinc-800 rounded-lg flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-[9px] font-bold">
                      <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                        <input
                          type="checkbox"
                          checked={Boolean(selectedBlock?.extra_metadata?.stroke_enabled)}
                          onChange={(e) => {
                            if (selectedBlock) {
                              void handleBlockMetadataChange({ stroke_enabled: e.target.checked });
                            }
                          }}
                          className="w-3.5 h-3.5 rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500 cursor-pointer"
                        />
                        <span>เปิดเส้นขอบ (Stroke)</span>
                      </label>
                      <span className="font-mono text-yellow-400 font-bold">
                        {Number(selectedBlock?.extra_metadata?.stroke_width ?? 3)}px
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min="0"
                        max="20"
                        step="0.5"
                        value={Number(selectedBlock?.extra_metadata?.stroke_width ?? 3)}
                        onChange={(e) => {
                          if (selectedBlock) {
                            void handleBlockMetadataChange({ stroke_width: Number(e.target.value), stroke_enabled: true });
                          }
                        }}
                        disabled={!selectedBlock}
                        className="flex-1 accent-yellow-500 cursor-pointer"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          if (selectedBlock) {
                            setLayerStrokeModalBlockId(selectedBlock.id);
                          }
                        }}
                        disabled={!selectedBlock}
                        className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-yellow-500/50 rounded text-[9px] font-bold text-yellow-400 shrink-0 cursor-pointer transition-colors"
                        title="เปิด Photoshop Layer Style แบบเต็ม"
                      >
                        🎨 FX...
                      </button>
                    </div>
                  </div>
                </div>
                )}
              </div>

              {/* Manage Templates Button */}
              <button 
                type="button"
                onClick={() => {
                  setSettingsGlobalCategory('templates');
                  setShowGlobalSettingsModal(true);
                }}
                className="w-full mt-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-slate-200 py-2 rounded-lg font-pixel font-bold text-[10.5px] uppercase tracking-wider transition-colors cursor-pointer"
              >
                MANAGE TEMPLATES
              </button>
            </div>
            )}
          </div>
        )}
        </div>

        {/* 4. RIGHT PANEL (Stacked Dock Layout - Pipeline Controls on top, Layers & Text Review on bottom) */}
        <aside 
          className={`transition-all duration-300 flex flex-col overflow-hidden shadow-2xl border-l border-zinc-900/60 bg-zinc-950/40 backdrop-blur-md animate-slide-up shrink-0 ${
            activeProject && rightSidebarOpen ? 'w-80 opacity-100' : 'w-0 opacity-0 border-none'
          }`}
        >
          {/* Top Panel: Pipeline Controls (Direct 1-Click Action Matrix) */}
          <div className="p-3 border-b border-zinc-900 bg-zinc-950/90 shrink-0">
            <PipelineControlsPanel
              activeProject={activeProject}
              activePage={activePage}
              isProcessing={isProcessing}
              isBatchRunning={isBatchRunning}
              isPageWorkflowRunning={isPageWorkflowRunning}
              trainStatus={trainStatus}
              runBatchPipeline={runBatchPipeline}
              runPipelineStep={runPipelineStep}
              cancelPageWorkflow={cancelBatchWorkflow}
              onOpenAIProviderSettings={() => setShowAIProviderSettingsModal(true)}
              onOpenCustomWorkflowModal={() => setIsCustomWorkflowModalOpen(true)}
            />

            {/* Batch Progress Indicator */}
            {batchProgress && (
              <div role="status" aria-live="polite" className="mt-2.5 p-3 bg-zinc-900 border border-zinc-800 rounded-md flex flex-col gap-2 text-[9px] font-pixel">
                <div className="flex justify-between items-center text-slate-400">
                  <span className="font-bold uppercase tracking-wider text-[8px] text-slate-500">Batch Status:</span>
                  <span className={`font-bold uppercase ${batchProgress.status === 'success' ? 'text-yellow-400' : (batchProgress.status === 'failed' || batchProgress.status === 'cancelled') ? 'text-rose-400' : 'text-yellow-500 animate-pulse'}`}>
                    {batchProgress.status}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-400">
                  <span className="text-slate-500 font-bold uppercase tracking-wider text-[8px]">Progress:</span>
                  <span className="font-bold text-slate-200">Page {batchProgress.current_page} / {batchProgress.total_pages} {batchProgress.step && `[${batchProgress.step.toUpperCase()}]`}</span>
                </div>
                <div className="w-full bg-zinc-950 border border-zinc-850 h-1.5 overflow-hidden rounded-full mt-0.5">
                  <div 
                    className="bg-yellow-400 h-full transition-all duration-300 shadow-[0_0_8px_rgba(234,179,8,0.5)]"
                    style={{ width: `${batchProgress.progress * 100}%` }}
                  />
                </div>
                {batchProgress.error && (
                  <span className="text-rose-400 font-mono text-[8px] truncate mt-1">Error: {batchProgress.error}</span>
                )}
              </div>
            )}
          </div>

          {/* Bottom Panel: Layers & Text Review */}
          <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950 min-h-0">
            <div className="px-3.5 py-2.5 border-b border-zinc-900 bg-zinc-950/90 flex items-center justify-between font-pixel">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <Layers size={13} className="text-yellow-500" />
                📑 Layers & Text Review
              </span>
              <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400">
                {activePage?.text_blocks?.length || 0} Blocks
              </span>
            </div>

            {/* Selected Mask Action Toolbar */}
            {selectedBlocks.length > 0 && (
              <div className="px-3 py-2 bg-zinc-900/60 border-b border-zinc-900 flex items-center justify-between gap-2 font-pixel text-[10px]">
                <span className="text-amber-400 font-bold flex items-center gap-1">
                  Selected ({selectedBlocks.length})
                </span>
                <div className="flex items-center gap-1">
                  {selectedBlocks.length === 1 && (
                    <button
                      type="button"
                      onClick={() => setSelectedBlockForMaskEdit(selectedBlocks[0].id)}
                      className="px-2 py-1 bg-purple-500/20 text-purple-300 border border-purple-500/40 hover:bg-purple-500/30 rounded font-bold transition-all cursor-pointer"
                      title="แก้ไข Mask ส้นข้อความ"
                    >
                      🖌️ Mask Editor
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void deleteBlocks(selectedBlocks.map(b => b.id))}
                    className="px-2 py-1 bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 rounded font-bold transition-all cursor-pointer"
                    title="ลบเลเยอร์"
                  >
                    🗑️ ลบ
                  </button>
                </div>
              </div>
            )}

            {/* Layers List Cards (Matching HTML Mockup layer-card style) */}
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
              {(!activePage?.text_blocks || activePage.text_blocks.length === 0) ? (
                <div className="p-6 text-center text-xs text-slate-500 italic font-pixel">
                  ยังไม่มีข้อมูล Balloon Text Layer
                </div>
              ) : (
                [...activePage.text_blocks].sort((a, b) => a.block_index - b.block_index).map((block) => {
                  const isSelected = selectedBlocks.some(b => b.id === block.id);
                  const role = resolveBlockTemplateRole(block, stylePresets);
                  const displayValue = (typeof block.translation === 'string' && block.translation.trim() !== '')
                    ? block.translation
                    : (block.source_text || '');

                  return (
                    <div
                      key={block.id}
                      ref={(el) => {
                        layerCardRefs.current[block.id] = el;
                      }}
                      id={`layer-card-${block.id}`}
                      onClick={(e) => handleLayerSelection(block, e)}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleLayerSelection(block, e);
                        setLayerContextMenu({
                          x: e.clientX,
                          y: e.clientY,
                          blockId: block.id,
                        });
                      }}
                      className={`p-2.5 rounded-lg border transition-all cursor-pointer font-pixel text-xs ${
                        isSelected
                          ? 'border-amber-500 bg-amber-500/12 shadow-sm shadow-amber-500/20'
                          : 'border-zinc-800 bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 font-mono font-bold text-[10px] border border-amber-500/30">
                            #{block.block_index + 1}
                          </span>
                          <span className="text-[10.5px] font-bold text-slate-300">
                            {role.roleLabel}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleLayerSelection(block, e);
                              setLayerStrokeModalBlockId(block.id);
                            }}
                            className="text-zinc-500 hover:text-yellow-400 p-1 rounded transition-colors cursor-pointer hover:bg-zinc-800"
                            title="เปิดเอฟเฟกต์เฉพาะเลเยอร์ (Photoshop Layer Style: Stroke & Outline)"
                          >
                            <Palette size={12} />
                          </button>

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              const textToCopy = stripSemanticTranslationTags(block.translation || block.source_text || '');
                              if (textToCopy) {
                                navigator.clipboard.writeText(textToCopy);
                                showToast('คัดลอกคำแปลแล้ว! 📋', 'info');
                              }
                            }}
                            className="text-zinc-500 hover:text-amber-300 p-1 rounded transition-colors cursor-pointer hover:bg-zinc-800"
                            title="คัดลอกข้อความ (Copy Text)"
                          >
                            <Copy size={12} />
                          </button>

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              showConfirmDialog(
                                'คุณต้องการลบเลเยอร์ข้อความนี้ใช่หรือไม่?',
                                () => { void deleteBlocks([block.id]); },
                                'ยืนยันการลบเลเยอร์'
                              );
                            }}
                            className="text-zinc-500 hover:text-rose-400 p-1 rounded transition-colors cursor-pointer hover:bg-zinc-800"
                            title="ลบเลเยอร์"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>

                      {/* Dual Slots: 1. Source Text (ต้นฉบับ) & 2. Translation (คำแปล) */}
                      <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                        {/* Slot 1: Source Text / OCR */}
                        <div>
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1 font-sans">
                              <span>🔤</span> ต้นฉบับ (Source / OCR)
                            </span>
                            {block.source_text && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigator.clipboard.writeText(block.source_text);
                                  showToast('คัดลอกข้อความต้นฉบับแล้ว! 📋', 'info');
                                }}
                                className="text-[9px] text-slate-500 hover:text-slate-300 font-sans cursor-pointer"
                                title="คัดลอกข้อความต้นฉบับ"
                              >
                                copy
                              </button>
                            )}
                          </div>
                          <input
                            type="text"
                            value={block.source_text || ''}
                            onChange={(e) => {
                              void updateBlock(block.id, { source_text: e.target.value });
                            }}
                            placeholder="ข้อความต้นฉบับ (OCR)..."
                            className="w-full bg-zinc-950/70 border border-zinc-800/80 hover:border-zinc-700 focus:border-amber-500/70 rounded px-2.5 py-1 text-[11px] text-slate-300 font-sans focus:outline-none select-text"
                          />
                        </div>

                        {/* Slot 2: Translation Text */}
                        <div>
                          <span className="text-[9px] font-bold text-amber-400/90 uppercase tracking-wider block mb-0.5 font-sans flex items-center gap-1">
                            <span>🇹🇭</span> คำแปล (Translation)
                          </span>
                          <textarea
                            rows={Math.max(1, Math.min(6, (block.translation || '').split('\n').length))}
                            value={block.translation || ''}
                            onChange={(e) => {
                              const newText = e.target.value;
                              const { typesetting_spec: _staleSpec, ...freshMetadata } = block.extra_metadata || {};
                              void updateBlock(block.id, {
                                translation: newText,
                                extra_metadata: {
                                  ...freshMetadata,
                                  line_break_source: 'manual_hard',
                                  ai_preferred_lines: null,
                                  ai_layout_hint: null,
                                  ai_layout_text: null,
                                },
                              });
                            }}
                            placeholder="พิมพ์คำแปลใหม่..."
                            className="w-full bg-zinc-950/90 border border-zinc-800/90 hover:border-zinc-700 focus:border-amber-500 rounded-md px-2.5 py-1.5 text-xs text-slate-100 font-sans focus:outline-none resize-y min-h-[34px] leading-relaxed select-text"
                          />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* 5. BOTTOM STATUS BAR */}
      <footer role="status" aria-live="polite" className="flex items-center justify-between px-6 py-2.5 border-t border-zinc-900 bg-zinc-950/50 backdrop-blur-md text-xs text-slate-400 z-10 animate-fade-in font-sans">
        <div className="flex items-center gap-2.5">
          <span className={`w-2.5 h-2.5 rounded-full ${isProcessing ? 'bg-yellow-500 animate-ping' : isConnected ? 'bg-emerald-500 shadow-md shadow-emerald-500/25' : 'bg-rose-500 animate-pulse'}`} />
          <span className="font-semibold text-slate-300">
            Status: {statusMessage} {activeProject && !isConnected && <span className="text-rose-400 ml-1.5 font-bold animate-pulse">(WS Offline, Reconnecting...)</span>}
          </span>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={() => { setShowDiagnostics(true); fetchDiagnostics(); }}
            disabled={isProcessing}
            className="flex items-center gap-1.5 text-[10px] font-extrabold text-slate-500 hover:text-yellow-400 transition-colors uppercase tracking-wider cursor-pointer font-pixel"
            title="Open system diagnostics and Playwright E2E UI verification dashboard"
          >
            <Activity size={12} className="text-emerald-500 animate-pulse animate-fade-in" /> Diagnostics & Health
          </button>
          <span className="text-[10px] text-emerald-400/90 font-semibold tracking-wide font-pixel flex items-center gap-1.5" title="Central License & Update Host: https://houmi.click Connected">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Houmi Studio {HOUMI_VERSION_LABEL} (Online Mode)
          </span>
        </div>
      </footer>

      {/* EXPORT TXT MODAL */}
      {showExportTxtModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="w-96 p-6.5 rounded-2xl border border-white/10 glass-panel-heavy shadow-2xl relative overflow-hidden animate-slide-up">
            {/* Background Spot in Modal */}
            <div className="absolute top-[-30%] left-[-30%] w-[60%] h-[60%] bg-yellow-500/5 rounded-full filter blur-[40px] pointer-events-none" />
            
            <h3 className="text-base font-extrabold text-white mb-4 flex items-center gap-2 z-10 relative">
              <FileText size={20} className="text-yellow-500" /> Export Options (TXT)
            </h3>
            
            <div className="flex flex-col gap-3 z-10 relative">
              <p className="text-xs text-slate-400 font-sans leading-relaxed mb-1.5">
                กรุณาเลือกรูปแบบที่ต้องการส่งออกข้อมูลข้อความของทั้งโปรเจกต์
              </p>

              <button
                onClick={async () => {
                  setShowExportTxtModal(false);
                  await handleExport('txt', 'ai_layout');
                }}
                className="w-full text-left px-4 py-3 rounded-lg border border-cyan-500/30 bg-cyan-500/[0.06] hover:border-cyan-400/60 hover:bg-cyan-500/10 transition-all cursor-pointer group"
                title="ส่งคู่ข้อความพร้อมรูปทรงและจำนวนบรรทัดเป้าหมายสำหรับ AI จัดบรรทัด"
              >
                <h4 className="text-xs font-pixel font-bold text-cyan-300 group-hover:text-cyan-200 transition-colors uppercase tracking-wider">
                  ส่งให้ AI จัดบรรทัด (AI Layout)
                </h4>
                <p className="text-[10px] text-slate-500 font-sans mt-0.5">คำต้นฉบับ + คำแปล + HOUMI_LAYOUT โดยไม่ใส่ Bubble หรือ label เพิ่ม</p>
              </button>
              
              <button
                onClick={async () => {
                  setShowExportTxtModal(false);
                  await handleExport('txt', 'ocr');
                }}
                className="w-full text-left px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-950/40 hover:border-yellow-400/30 hover:bg-zinc-900/45 transition-all cursor-pointer group hover:shadow-[0_2px_15px_rgba(234,179,8,0.04)]"
                title="ส่งออกเฉพาะข้อความที่สแกนได้จากภาพมังงะต้นฉบับ"
              >
                <h4 className="text-xs font-pixel font-bold text-slate-200 group-hover:text-amber-400 transition-colors uppercase tracking-wider">
                  ส่งออกเฉพาะคำต้นฉบับ (OCR Only)
                </h4>
                <p className="text-[10px] text-slate-500 font-sans mt-0.5 font-pixel">ส่งออกเฉพาะข้อความสแกนภาษาต้นทางแยกตามรายหน้า</p>
              </button>

              <button
                onClick={async () => {
                  setShowExportTxtModal(false);
                  await handleExport('txt', 'translation');
                }}
                className="w-full text-left px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-950/40 hover:border-yellow-400/30 hover:bg-zinc-900/45 transition-all cursor-pointer group hover:shadow-[0_2px_15px_rgba(234,179,8,0.04)]"
                title="ส่งออกเฉพาะข้อความคำแปลที่ทำเสร็จแล้ว"
              >
                <h4 className="text-xs font-pixel font-bold text-slate-200 group-hover:text-amber-400 transition-colors uppercase tracking-wider">
                  ส่งออกเฉพาะคำแปลอย่างเดียว (Translation Only)
                </h4>
                <p className="text-[10px] text-slate-500 font-sans mt-0.5 font-pixel">ส่งออกเฉพาะคำแปลภาษาไทยของทุกหน้า</p>
              </button>

              <button
                onClick={async () => {
                  setShowExportTxtModal(false);
                  await handleExport('txt', 'both');
                }}
                className="w-full text-left px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-950/40 hover:border-yellow-400/30 hover:bg-zinc-900/45 transition-all cursor-pointer group hover:shadow-[0_2px_15px_rgba(234,179,8,0.04)]"
                title="ส่งออกคู่กันทั้งคำต้นฉบับและคำแปล"
              >
                <h4 className="text-xs font-pixel font-bold text-slate-200 group-hover:text-amber-400 transition-colors uppercase tracking-wider">
                  ส่งออกทั้งคำต้นฉบับและคำแปล (Both)
                </h4>
                <p className="text-[10px] text-slate-500 font-sans mt-0.5 font-pixel">ส่งออกคู่คำข้อความสแกนคู่กับคำแปลแยกตามบล็อกเพื่อความสะดวกในการตรวจ</p>
              </button>
            </div>
            
            <div className="flex justify-end border-t border-zinc-900/60 pt-4 mt-4 shrink-0 font-pixel">
              <button 
                onClick={() => setShowExportTxtModal(false)}
                className="px-4.5 py-2 text-xs font-bold rounded-md pixel-btn-purple cursor-pointer"
                title="ปิดหน้าต่างส่งออกข้อความนี้"
              >
                ยกเลิก
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EXPORT YOLO MODAL */}
      {showExportYoloModal && (
        <ExportYoloDatasetModal onClose={() => setShowExportYoloModal(false)} />
      )}

      {/* EXPORT PSD SCOPE SELECTION MODAL */}
      {showPsdExportModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl max-w-md w-full p-5 shadow-2xl flex flex-col gap-4 font-sans select-none animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-zinc-900 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-amber-400 text-base">⚡</span>
                <h3 className="text-xs font-bold font-pixel text-slate-200 uppercase tracking-wider">
                  ส่งออกไฟล์ PSD (Photoshop Export)
                </h3>
              </div>
              <button
                onClick={() => setShowPsdExportModal(false)}
                className="text-zinc-500 hover:text-zinc-300 text-xs cursor-pointer"
              >
                ✕
              </button>
            </div>

            <p className="text-[11px] text-zinc-400 leading-relaxed font-pixel">
              กรุณาเลือกขอบเขตและรูปแบบ Text Layer ในการสร้างไฟล์ PSD สำหรับแก้ไขใน Photoshop:
            </p>

            {/* 1. Photoshop Text Layer Mode Selector (Text Engine Mode) */}
            <div className="bg-zinc-900/80 border border-zinc-800 p-3 rounded-lg flex flex-col gap-2 font-pixel">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <TypeIcon size={12} className="text-amber-400" /> รูปแบบ TEXT LAYER ใน PHOTOSHOP (TEXT ENGINE MODE)
              </label>
              <div className="grid grid-cols-3 gap-2 pt-1 font-pixel">
                <button
                  type="button"
                  onClick={() => setPsdTextMode('paragraph')}
                  className={`p-2.5 rounded-md border text-left flex flex-col gap-0.5 transition-all cursor-pointer ${
                    psdTextMode === 'paragraph'
                      ? 'border-amber-500/80 bg-amber-500/10 text-amber-200 shadow-md shadow-amber-500/10 font-bold'
                      : 'border-zinc-800 bg-zinc-950 text-slate-400 hover:text-slate-200 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-1 font-bold text-[11px]">
                    <span className="text-amber-400">📦</span> Paragraph
                  </div>
                  <span className="text-[8.5px] text-slate-400 leading-tight font-sans">
                    (Box Text) ตัดคำบรรทัดอัตโนมัติ (แนะนำสำหรับมังงะ)
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setPsdTextMode('point')}
                  className={`p-2.5 rounded-md border text-left flex flex-col gap-0.5 transition-all cursor-pointer ${
                    psdTextMode === 'point'
                      ? 'border-amber-500/80 bg-amber-500/10 text-amber-200 shadow-md shadow-amber-500/10 font-bold'
                      : 'border-zinc-800 bg-zinc-950 text-slate-400 hover:text-slate-200 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-1 font-bold text-[11px]">
                    <span className="text-amber-400">📍</span> Point Text
                  </div>
                  <span className="text-[8.5px] text-slate-400 leading-tight font-sans">
                    (Single Point) ตัวอักษรจุดเดียว เหมาะสำหรับ SFX
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setPsdTextMode('jsx')}
                  className={`p-2.5 rounded-md border text-left flex flex-col gap-0.5 transition-all cursor-pointer ${
                    psdTextMode === 'jsx'
                      ? 'border-amber-500/80 bg-amber-500/15 text-amber-200 shadow-md shadow-amber-500/20 font-bold'
                      : 'border-zinc-800 bg-zinc-950 text-slate-400 hover:text-slate-200 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold text-[11px]">
                    <span className="flex items-center gap-1 text-amber-300">
                      🚀 ExtendScript (.JSX)
                    </span>
                  </div>
                  <span className="text-[8.5px] text-slate-400 leading-tight font-sans">
                    เปิดและรันสร้าง Text Layer ใน Photoshop โดยตรง
                  </span>
                </button>
              </div>
            </div>

            {/* 2. EXPORT ACTIONS (Combined Single Scope Buttons) */}
            <div className="flex flex-col gap-2.5 font-pixel">
              <button
                type="button"
                onClick={async () => {
                  setShowPsdExportModal(false);
                  if (psdTextMode === 'jsx') {
                    await handleExport('jsx-page-run');
                  } else {
                    await handleExport('psd');
                  }
                }}
                disabled={!activePage}
                className="w-full text-left p-3.5 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 hover:border-amber-500/80 transition-all cursor-pointer group shadow-sm shadow-amber-500/10 disabled:opacity-40 disabled:pointer-events-none"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-amber-300 group-hover:text-amber-200 flex items-center gap-1.5">
                    {psdTextMode === 'jsx' ? '🚀 สั่ง Photoshop หน้านี้ (ExtendScript .JSX)' : '📄 เฉพาะหน้าปัจจุบัน (Current Page Only)'}
                  </h4>
                  <span className="text-[9px] font-mono font-bold text-amber-400 bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/40">
                    {psdTextMode === 'jsx' ? 'JSX RUN' : '.PSD'}
                  </span>
                </div>
                <p className="text-[10px] text-zinc-400 mt-1 font-sans">
                  {psdTextMode === 'jsx' 
                    ? 'ส่งคำสั่งเปิด Photoshop และสร้าง Text Layer เฉพาะหน้าที่เปิดอยู่ทันที' 
                    : `ดาวน์โหลดไฟล์ .psd สำเร็จรูปสำหรับหน้าที่เปิดอยู่ (${psdTextMode === 'paragraph' ? 'Paragraph Text Mode' : 'Point Text Mode'})`
                  }
                </p>
              </button>

              <button
                type="button"
                onClick={async () => {
                  setShowPsdExportModal(false);
                  if (psdTextMode === 'jsx') {
                    await handleExport('jsx-project-run');
                  } else {
                    await handleExport('psd-zip');
                  }
                }}
                disabled={!activeProject}
                className="w-full text-left p-3.5 rounded-lg border border-zinc-800/80 bg-zinc-900/60 hover:bg-amber-500/10 hover:border-amber-500/40 transition-all cursor-pointer group disabled:opacity-40 disabled:pointer-events-none"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-amber-300 group-hover:text-amber-200">
                    {psdTextMode === 'jsx' ? `🚀 สั่ง Photoshop ทั้งโปรเจกต์ (${activeProject?.pages?.length || 0} หน้า)` : `📁 ทั้งโปรเจกต์ (${activeProject?.pages?.length || 0} หน้า)`}
                  </h4>
                  <span className="text-[9px] font-mono text-zinc-500 bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800">
                    {psdTextMode === 'jsx' ? 'BATCH RUN' : '.ZIP'}
                  </span>
                </div>
                <p className="text-[10px] text-zinc-400 mt-1 font-sans">
                  {psdTextMode === 'jsx'
                    ? `ส่งคำสั่งเปิด Photoshop และสร้าง Text Layer รวดเดียวทุกหน้าทั้งโปรเจกต์`
                    : `บีบอัดรวมไฟล์ .psd ของทุกหน้าทั้งโปรเจกต์ลงไฟล์ .zip (${psdTextMode === 'paragraph' ? 'Paragraph Text Mode' : 'Point Text Mode'})`
                  }
                </p>
              </button>
            </div>

            <div className="flex justify-end pt-2 border-t border-zinc-900">
              <button
                type="button"
                onClick={() => setShowPsdExportModal(false)}
                className="px-4 py-1.5 text-xs font-bold rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 cursor-pointer font-pixel"
              >
                ยกเลิก
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PHOTOSHOP LAYER STROKE & OUTLINE MODAL */}
      {layerStrokeModalBlockId && (() => {
        const targetBlock = activePage?.text_blocks.find(b => b.id === layerStrokeModalBlockId);
        if (!targetBlock) return null;
        const metadata = targetBlock.extra_metadata || {};
        const strokeEnabled = Boolean(metadata.stroke_enabled);
        const strokeWidth = Number(metadata.stroke_width ?? 3);
        const strokeColor = String(metadata.stroke_color ?? '#ffffff');

        const applyStrokePatch = (patch: Record<string, any>) => {
          void handleBlockMetadataChange(patch);
        };

        return (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 font-sans animate-fade-in">
            <div className="bg-zinc-950 border border-zinc-800/90 rounded-xl max-w-sm w-full p-5 shadow-2xl flex flex-col gap-4 text-slate-200 animate-slide-up">
              <div className="flex items-center justify-between border-b border-zinc-900 pb-3">
                <div className="flex items-center gap-2">
                  <Palette size={16} className="text-yellow-400" />
                  <h3 className="text-xs font-bold font-pixel uppercase tracking-wider text-slate-100">
                    Photoshop Layer Stroke & Outline
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setLayerStrokeModalBlockId(null)}
                  className="text-slate-500 hover:text-slate-200 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-4">
                <label className="flex items-center justify-between bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800 cursor-pointer">
                  <span className="text-xs font-bold text-slate-300 font-pixel">เปิดใช้งาน Stroke / ขอบอักษร</span>
                  <input
                    type="checkbox"
                    checked={strokeEnabled}
                    onChange={(e) => applyStrokePatch({ stroke_enabled: e.target.checked })}
                    className="w-4 h-4 rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500 cursor-pointer"
                  />
                </label>

                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">ขนาดเส้นขอบ (Stroke Size)</span>
                    <span className="font-mono text-yellow-400 font-bold">{strokeWidth}px</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="30"
                    value={strokeWidth}
                    onChange={(e) => applyStrokePatch({ stroke_width: Number(e.target.value), stroke_enabled: true })}
                    className="w-full accent-yellow-500 cursor-pointer"
                  />
                </div>

                <div className="space-y-2">
                  <ColorField
                    label="สีเส้นขอบ (Stroke Color)"
                    value={strokeColor}
                    onChange={(color) => applyStrokePatch({ stroke_color: color, stroke_enabled: true })}
                  />
                </div>

                {/* Photoshop Anti-Aliasing Mode */}
                <div className="pt-2 border-t border-zinc-800">
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Photoshop Anti-Aliasing
                    </label>
                    <span className="text-[9px] font-mono text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">
                      Default: Sharp
                    </span>
                  </div>
                  <select
                    value={(metadata.anti_alias as string) || 'sharp'}
                    onChange={(e) => applyStrokePatch({ anti_alias: e.target.value })}
                    className="w-full bg-zinc-900 border border-zinc-800 focus:border-yellow-500/60 rounded-lg p-2 text-xs text-slate-200 focus:outline-none font-sans transition-colors cursor-pointer"
                  >
                    <option value="sharp">Sharp (คมชัด - Default แนะนำสำหรับ Photoshop)</option>
                    <option value="crisp">Crisp (ประณีต)</option>
                    <option value="strong">Strong (เข้ม)</option>
                    <option value="smooth">Smooth (นุ่มนวล)</option>
                    <option value="none">None (ปิด Anti-Alias)</option>
                  </select>
                </div>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => setLayerStrokeModalBlockId(null)}
                  className="px-4 py-1.5 bg-yellow-500 hover:bg-yellow-400 text-black text-xs font-bold rounded-lg font-pixel transition-colors"
                >
                  เสร็จสิ้น (Done)
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* HOUMI DEV STUDIO HUB (DEV MAP & DEV NOTES MODAL) */}
      {showDevStudioModal && (
        <DevMapDashboard
          onClose={() => setShowDevStudioModal(false)}
          initialTab={devStudioInitialTab}
        />
      )}

      {/* NEW PROJECT MODAL */}
      {showNewProjModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="w-96 p-6.5 rounded-2xl border border-white/10 glass-panel-heavy shadow-2xl relative overflow-hidden animate-slide-up">
            {/* Background Spot in Modal */}
            <div className="absolute top-[-30%] left-[-30%] w-[60%] h-[60%] bg-yellow-500/5 rounded-full filter blur-[40px] pointer-events-none" />
            
            <h3 className="text-base font-extrabold text-white mb-4.5 flex items-center gap-2 z-10 relative">
              <FolderPlus size={20} className="text-yellow-500" /> Create New Project
            </h3>
            <form onSubmit={handleCreateProject} className="flex flex-col gap-4 z-10 relative">
              <div>
                <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Project Name</label>
                <input 
                  type="text" 
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  placeholder="เช่น มังงะตอนที่ 1"
                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1.5" title="เลือกภาษาของภาพมังงะต้นฉบับ">Source Language</label>
                  <select 
                    id="project-source-lang"
                    value={sourceLang}
                    onChange={(e) => setSourceLang(e.target.value)}
                    className="w-full p-2 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer"
                  >
                    <option value="ja">ภาษาญี่ปุ่น (ja)</option>
                    <option value="zh">ภาษาจีน (zh)</option>
                    <option value="ko">ภาษาเกาหลี (ko)</option>
                    <option value="en">ภาษาอังกฤษ (en)</option>
                    <option value="th">ภาษาไทย (th)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1.5" title="เลือกภาษาเป้าหมายปลายทางสำหรับแปล">Target Language</label>
                  <select 
                    id="project-target-lang"
                    value={targetLang}
                    onChange={(e) => setTargetLang(e.target.value)}
                    className="w-full p-2 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer"
                  >
                    <option value="th">ภาษาไทย (th)</option>
                    <option value="en">ภาษาอังกฤษ (en)</option>
                    <option value="zh">ภาษาจีน (zh)</option>
                    <option value="ko">ภาษาเกาหลี (ko)</option>
                    <option value="ja">ภาษาญี่ปุ่น (ja)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1.5" title="เลือกโปรไฟล์งานลูกค้าสำหรับจัดประเภทฟอนต์">
                  Client Profile (จัดประเภท Font งานลูกค้า)
                </label>
                {!isCreatingNewClient ? (
                  <select
                    value={selectedClientId}
                    onChange={(e) => {
                      if (e.target.value === '__NEW__') {
                        setIsCreatingNewClient(true);
                      } else {
                        setSelectedClientId(e.target.value);
                      }
                    }}
                    className="w-full p-2 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-semibold"
                  >
                    {clientProfiles.map(p => (
                      <option key={p.id} value={p.id}>
                        👤 {p.name} {p.default_font_family ? `(${p.default_font_family})` : ''}
                      </option>
                    ))}
                    <option value="__NEW__">➕ เพิ่มชื่อลูกค้าคนใหม่...</option>
                  </select>
                ) : (
                  <div className="space-y-1.5">
                    <input
                      type="text"
                      value={newClientNameInput}
                      onChange={(e) => setNewClientNameInput(e.target.value)}
                      placeholder="กรอกชื่อลูกค้า เช่น สำนักพิมพ์ A"
                      className="w-full p-2 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                    />
                    <button
                      type="button"
                      onClick={() => setIsCreatingNewClient(false)}
                      className="text-[9px] text-amber-400 hover:underline cursor-pointer"
                    >
                      ← เลือกจากรายชื่อลูกค้าเดิม
                    </button>
                  </div>
                )}
              </div>
              <div className="flex gap-2.5 justify-end mt-3 font-pixel">
                <button 
                  type="button" 
                  onClick={() => setShowNewProjModal(false)}
                  className="px-4.5 py-2.5 text-xs font-bold rounded-md pixel-btn-purple cursor-pointer"
                  title="ปิดหน้าต่างสร้างโปรเจกต์"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  className="px-5 py-2.5 text-xs font-extrabold rounded-md pixel-btn-magenta cursor-pointer"
                  title="สร้างโปรเจกต์ใหม่ด้วยการตั้งค่าเหล่านี้"
                >
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* QUICK PROJECT PRESET SETUP MODAL */}
      <ProjectPresetModal
        isOpen={showProjectPresetModal}
        onClose={() => setShowProjectPresetModal(false)}
        currentSourceLang={activeProject?.source_lang || sourceLang || 'ko'}
        currentClientId={(activeProject?.settings as any)?.client_profile_id || ''}
        currentOcrEngine={ocrEngine || (activeProject?.settings as any)?.ocr_engine || 'ppocrv5'}
        currentBalloonModel={(activeProject?.settings as any)?.balloon_model || 'sao'}
        projectName={activeProject?.name || ''}
        onSavePreset={handleSaveProjectPreset}
      />

      {/* CUSTOM WORKFLOW MANAGER MODAL (ImageTrans Style) */}
      <CustomWorkflowModal
        isOpen={isCustomWorkflowModalOpen}
        onClose={() => setIsCustomWorkflowModalOpen(false)}
        onRunWorkflow={handleRunCustomWorkflow}
        activeProject={activeProject}
        activePage={activePage}
        isProcessing={isProcessing || isBatchRunning}
        ocrEngine={ocrEngine}
        onChangeOcrEngine={setOcrEngine}
      />

      {/* REALTIME DOBKLE OCR PIPELINE MODAL */}
      <DobkleOcrProgressModal
        isOpen={isDobkleModalOpen}
        data={dobkleProgress}
        onClose={() => setIsDobkleModalOpen(false)}
      />

      {/* ANTIGRAVITY FLOATING BATCH PROGRESS HUD (NON-BLOCKING) */}
      <BatchProgressModal
        isOpen={Boolean(batchProgress || isBatchRunning)}
        projectId={activeProject?.id || null}
        progress={batchProgress?.progress || 0}
        currentPage={batchProgress?.current_page || 0}
        totalPages={batchProgress?.total_pages || (activeProject?.pages?.length || 0)}
        currentStep={batchProgress?.step}
        status={batchProgress?.status || (isBatchRunning ? 'running' : 'idle')}
        error={batchProgress?.error}
        onClose={() => {
          setBatchProgress(null);
          setIsBatchRunning(false);
        }}
        onCancel={cancelBatchWorkflow}
      />

      {/* DIAGNOSTICS & SYSTEM HEALTH MODAL */}
      {showDiagnostics && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="w-[85vw] h-[85vh] p-6.5 rounded-2xl border border-white/10 glass-panel-heavy shadow-2xl flex flex-col relative overflow-hidden text-slate-100">
            {/* Background Spot */}
            <div className="absolute top-[-20%] left-[-20%] w-[40%] h-[40%] bg-yellow-500/5 rounded-full filter blur-[60px] pointer-events-none" />
            <div className="absolute bottom-[-20%] right-[-20%] w-[40%] h-[40%] bg-emerald-500/5 rounded-full filter blur-[60px] pointer-events-none" />
            
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4 z-10">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                  <Activity size={18} className="text-white animate-pulse" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-white">System Diagnostics & E2E Verification</h3>
                  <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">ทดสอบและตรวจสอบความถูกต้องหน้าบ้าน-หลังบ้าน</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={fetchDiagnostics}
                  disabled={diagnosticsLoading}
                  className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 transition-all text-slate-300 disabled:opacity-50"
                >
                  Refresh
                </button>
                <button 
                  onClick={() => setShowDiagnostics(false)}
                  className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-slate-950 border border-white/5 text-slate-400 hover:bg-slate-900 hover:text-white transition-all"
                >
                  Close
                </button>
              </div>
            </div>

            {/* Modal Content */}
            {diagnosticsLoading && !diagnosticsHealth ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3">
                <div className="w-10 h-10 rounded-full border-4 border-yellow-500/20 border-t-yellow-500 animate-spin" />
                <p className="text-xs text-slate-400">Loading system status...</p>
              </div>
            ) : (
              <div className="flex-1 flex gap-5 overflow-hidden z-10">
                {/* Left Side: Health Matrix & E2E steps */}
                <div className="w-96 flex flex-col gap-4 overflow-y-auto pr-1">
                  
                  {/* Backend System Health */}
                  <div className="p-4 rounded-xl border border-white/5 bg-slate-950/40 backdrop-blur-md">
                    <h4 className="text-[10px] font-bold text-yellow-500 uppercase tracking-widest mb-3 flex items-center gap-1.5 font-pixel">
                      <Cpu size={12} /> System Health Matrix (หลังบ้าน)
                    </h4>
                    <div className="flex flex-col gap-2.5">
                      {/* Database Status */}
                      <div className="flex items-center justify-between text-xs py-1 border-b border-white/[0.02]">
                        <span className="text-slate-400">SQLite Database</span>
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${diagnosticsHealth?.database?.status === 'ok' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                          <span className="font-bold text-slate-200">{diagnosticsHealth?.database?.status === 'ok' ? 'Connected' : 'Offline'}</span>
                        </div>
                      </div>
                      
                      {/* OCR Server Status */}
                      <div className="flex items-center justify-between text-xs py-1 border-b border-white/[0.02]">
                        <span className="text-slate-400">DeepSeek OCR Subprocess</span>
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${diagnosticsHealth?.ocr_server?.status === 'ok' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                          <span className="font-bold text-slate-200">{diagnosticsHealth?.ocr_server?.status === 'ok' ? 'Online' : 'Offline'}</span>
                        </div>
                      </div>
                      
                      {/* YOLO model Status */}
                      <div className="flex items-center justify-between text-xs py-1 border-b border-white/[0.02]">
                        <span className="text-slate-400">YOLO Balloon ONNX</span>
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${diagnosticsHealth?.yolo_model?.status === 'ok' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                          <span className="font-bold text-slate-200">
                            {diagnosticsHealth?.yolo_model?.status === 'ok' 
                              ? `Ready (${diagnosticsHealth.yolo_model.latency_ms}ms)` 
                              : 'Missing/Error'}
                          </span>
                        </div>
                      </div>
                      
                      {/* PSD CLI Status */}
                      <div className="flex items-center justify-between text-xs py-1">
                        <span className="text-slate-400">Manga PSD CLI Utility</span>
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${diagnosticsHealth?.psd_cli?.status === 'ok' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                          <span className="font-bold text-slate-200">{diagnosticsHealth?.psd_cli?.status === 'ok' ? 'Ready' : 'Missing'}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Playwright E2E Integration Test Results */}
                  <div className="flex-1 p-4 rounded-xl border border-white/5 bg-slate-950/40 backdrop-blur-md flex flex-col overflow-hidden">
                    <h4 className="text-[10px] font-bold text-yellow-500 uppercase tracking-widest mb-3 flex items-center gap-1.5 font-pixel">
                      <Clock size={12} /> Playwright E2E Test Report
                    </h4>
                    
                    {e2eReport ? (
                      <div className="flex-1 flex flex-col gap-3 overflow-y-auto pr-1">
                        <div className="flex items-center justify-between bg-slate-950/60 p-2.5 rounded-lg border border-slate-900">
                          <span className="text-[10px] text-slate-500">สถานะทดสอบรอบล่าสุด:</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold uppercase ${
                            e2eReport.status === 'success' ? 'bg-emerald-950 border border-emerald-500/30 text-emerald-300' : 'bg-rose-950 border border-rose-500/30 text-rose-300'
                          }`}>
                            {e2eReport.status}
                          </span>
                        </div>

                        {e2eReport.timestamp && (
                          <div className="text-[10px] text-slate-500 italic">
                            Run time: {new Date(e2eReport.timestamp * 1000).toLocaleString('th-TH')}
                          </div>
                        )}

                        <div className="flex flex-col gap-2 mt-2">
                          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">บันทึกขั้นตอนการทดสอบ (Steps)</span>
                          {e2eReport.steps?.map((step: string, i: number) => (
                            <div key={i} className="text-xs p-2 rounded bg-slate-900/60 text-slate-300 border border-white/[0.02]">
                              {step}
                            </div>
                          ))}
                          
                          {e2eReport.errors?.map((err: string, i: number) => (
                            <div key={i} className="text-xs p-2 rounded bg-rose-950/40 text-rose-300 border border-rose-900/30">
                              Error: {err}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="flex-1 flex flex-col items-center justify-center text-center p-4">
                        <p className="text-xs text-slate-500 italic">ไม่พบประวัติรายงาน E2E กรุณารันสคริปต์ python scripts/run_e2e_diagnostics.py จาก Terminal หลังบ้าน</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Side: Visual Screenshots Zone */}
                <div className="flex-1 flex flex-col rounded-xl border border-white/5 bg-slate-950/20 overflow-hidden">
                  <div className="bg-slate-950/60 border-b border-slate-900 px-4 py-2 flex items-center justify-between">
                    <span className="text-[10px] font-bold text-yellow-500 uppercase tracking-widest flex items-center gap-1.5 font-pixel">
                      <ImageIcon size={12} /> Visual Verification (มุมมอง User หน้าบ้านจริง)
                    </span>
                    <div className="flex gap-1">
                      {[
                        { id: '04_canvas_opened', label: '1. Original' },
                        { id: '05_after_detect', label: '2. YOLO Overlay' },
                        { id: '06_after_ocr_translate', label: '3. OCR Results' },
                        { id: '07_final_rendered', label: '4. Final Output' }
                      ].map(t => (
                        <button
                          key={t.id}
                          onClick={() => setActiveReportTab(t.id)}
                          className={`text-[10px] px-2.5 py-1 rounded font-bold transition-all ${
                            activeReportTab === t.id 
                              ? 'bg-yellow-950 text-yellow-300 border border-yellow-500/20' 
                              : 'text-slate-500 hover:text-slate-300 hover:bg-zinc-900'
                          }`}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  <div className="flex-1 bg-slate-950 flex items-center justify-center p-4 overflow-hidden relative">
                    {e2eReport ? (
                      <img 
                        src={`/static/diagnostics/${activeReportTab}.png`} 
                        alt="E2E Screenshot" 
                        className="max-w-full max-h-full object-contain rounded-lg border border-slate-800 shadow-2xl"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                    ) : (
                      <p className="text-xs text-slate-500 italic">ไม่พบคลังภาพจำลองความถูกต้องของการทดสอบ</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* INPAINT PREVIEW MODAL */}
      {inpaintPreviewImage && (
        <div className="fixed inset-0 bg-slate-950/85 backdrop-filter backdrop-blur-sm flex flex-col items-center justify-center z-50 animate-fade-in p-6">
          <div className="w-[80vw] h-[80vh] flex flex-col bg-zinc-950/60 border border-white/10 rounded-2xl p-5 overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/5 pb-3.5 mb-4">
              <div>
                <h3 className="text-base font-extrabold text-white">Smart Inpaint Preview (ก่อนบันทึก)</h3>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">ลบคำแปลออกด้วย Inpaint++ อัตโนมัติ</p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    setInpaintPreviewImage(null);
                    await runPipelineStep('inpaint');
                  }}
                  className="px-4 py-2 text-xs font-extrabold text-white glow-btn hover-zoom rounded-lg"
                >
                  Apply & Save
                </button>
                <button
                  onClick={() => setInpaintPreviewImage(null)}
                  className="px-4 py-2 text-xs font-bold rounded-lg bg-slate-900 border border-white/5 text-slate-400 hover:bg-slate-800 hover:text-white transition-all shadow-inner"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="flex-1 bg-slate-950 rounded-xl overflow-hidden flex items-center justify-center p-4 relative">
              <img 
                src={inpaintPreviewImage} 
                alt="Inpaint Preview" 
                className="max-w-full max-h-full object-contain rounded-lg border border-slate-800 shadow-2xl" 
              />
            </div>
          </div>
        </div>
      )}

      {/* MASK EDITOR MODAL */}
      {selectedBlockForMaskEdit && (
        (() => {
          const blockToEdit = activePage?.text_blocks.find(b => b.id === selectedBlockForMaskEdit);
          if (!blockToEdit) return null;
          return (
            <MaskEditorModal
              blockId={selectedBlockForMaskEdit}
              blockIndex={blockToEdit.block_index}
              pageId={activePage?.id}
              initialKernel={activeProject?.settings?.mask_dilation_kernel ?? 3}
              highQualityMaskAvailable={
                settingsPerformanceProfile === 'performance'
                || (
                  settingsPerformanceProfile === 'custom'
                  && settingsPerformanceCustom.prefer_gpu
                  && settingsPerformanceCustom.ocr_workers >= 3
                )
              }
              onClose={() => setSelectedBlockForMaskEdit(null)}
              onSaved={(reclean, cleanMode) => {
                setSelectedBlockForMaskEdit(null);
                showToast(
                  reclean || cleanMode === 'region_background'
                    ? "บันทึกมาสก์แล้ว — กำลังคลีนภาพเบื้องหลัง…"
                    : "แก้ไขมาสก์ข้อความสำเร็จ!",
                  "success"
                );
                if (reclean || cleanMode === 'region_background') {
                  setCleanPreviewRevision(Date.now());
                  // Inpainting runs asynchronously in background (takes ~3s for LaMA ONNX).
                  // Guarantee clean preview refresh once inpainting completes.
                  setTimeout(() => {
                    setCleanPreviewRevision(Date.now());
                  }, 3800);
                }
                const state = useProjectStore.getState();
                const currentPage = state.activePage;
                if (currentPage && currentPage.id === activePage?.id) {
                  const textBlocks = currentPage.text_blocks.map((block) =>
                    block.id === selectedBlockForMaskEdit
                      ? { ...block, mask_type: 'custom' as const }
                      : block
                  );
                  const updatedPage = { ...currentPage, text_blocks: textBlocks };
                  useProjectStore.setState({
                    activePage: updatedPage,
                    activeProject: state.activeProject
                      ? {
                          ...state.activeProject,
                          pages: state.activeProject.pages.map((page) =>
                            page.id === updatedPage.id ? updatedPage : page
                          ),
                        }
                      : null,
                    selectedBlock: state.selectedBlock?.id === selectedBlockForMaskEdit
                      ? { ...state.selectedBlock, mask_type: 'custom' }
                      : state.selectedBlock,
                    selectedBlocks: state.selectedBlocks.map((block) =>
                      block.id === selectedBlockForMaskEdit
                        ? { ...block, mask_type: 'custom' as const }
                        : block
                    ),
                  });
                }
              }}
            />
          );
        })()
      )}



      {/* GLOBAL SETTINGS MODAL */}
      {showGlobalSettingsModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in p-2 font-sans">
          <div className="flex h-[min(760px,94vh)] w-[min(1180px,96vw)] flex-col overflow-hidden rounded-lg border border-zinc-800/80 glass-panel-heavy shadow-2xl relative text-slate-200 animate-slide-up">
            
            {/* Header bar */}
            <div className="bg-zinc-950/60 px-5 py-4 flex items-center justify-between border-b border-zinc-900/80 shrink-0">
              <span className="text-xs font-bold text-amber-400 tracking-widest uppercase font-pixel flex items-center gap-2">
                🌐 Global Settings (ตั้งค่าระบบ)
              </span>
              <button 
                type="button"
                onClick={closeGlobalSettings}
                className="text-slate-500 hover:text-amber-400 transition-colors cursor-pointer text-xs font-bold font-pixel border border-zinc-900 hover:border-yellow-400/20 bg-zinc-900/40 px-2.5 py-1 rounded-sm"
              >
                Done (✕)
              </button>
            </div>

            <div className="flex-1 flex overflow-hidden bg-zinc-950/20">
              
              {/* Internal Left Sidebar */}
              {settingsGlobalSearch.trim() === '' ? (
                <div className="w-56 max-[960px]:w-14 border-r border-zinc-900/60 bg-zinc-950/45 flex flex-col p-4 max-[960px]:p-2 gap-2.5 shrink-0 select-none max-[960px]:[&>button]:justify-center max-[960px]:[&>button]:gap-0 max-[960px]:[&>button]:overflow-hidden max-[960px]:[&>button]:px-1 max-[960px]:[&>button]:text-[0px] max-[960px]:[&>button>span]:text-xs">
                  {/* Search input */}
                  <div className="relative mb-2 max-[960px]:hidden">
                    <input 
                      type="text" 
                      placeholder="Search settings..."
                      value={settingsGlobalSearch}
                      onChange={(e) => setSettingsGlobalSearch(e.target.value)}
                      className="w-full pl-7 pr-3 py-1.5 text-[10px] rounded-md text-white bg-zinc-900 border border-zinc-850 focus:outline-none focus:border-yellow-500/50 transition-all font-sans"
                    />
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 text-[10px]">🔍</span>
                  </div>

                  <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest font-pixel mb-1 max-[960px]:hidden">Categories</span>

                  <button
                    type="button"
                    title="AI Provider & API Keys"
                    onClick={() => setSettingsGlobalCategory('ai_provider')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'ai_provider'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>🔑</span> AI Provider & Keys
                  </button>

                  <button
                    type="button"
                    title="AI Detection & Scan"
                    onClick={() => setSettingsGlobalCategory('ai_detection')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'ai_detection'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>🧠</span> AI Detection & Scan
                  </button>

                  <button
                    type="button"
                    title="Typography & Style"
                    onClick={() => setSettingsGlobalCategory('typography')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'typography'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>📝</span> Typography & Style
                  </button>

                  <button
                    type="button"
                    title="Font Templates"
                    onClick={() => setSettingsGlobalCategory('templates')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'templates'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>🎨</span> Font Templates
                  </button>

                  <button
                    type="button"
                    title="Typesetting & Thai Linguistic Rules"
                    onClick={() => setSettingsGlobalCategory('typesetting_rules')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'typesetting_rules'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>📜</span> Typesetting Rules
                  </button>

                  <button
                    type="button"
                    title="Cleanup Pipeline"
                    onClick={() => setSettingsGlobalCategory('pipeline')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'pipeline'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>🧼</span> Cleanup Pipeline
                  </button>

                  <button
                    type="button"
                    title="Performance"
                    onClick={() => setSettingsGlobalCategory('performance')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'performance'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>⚡</span> Performance
                  </button>

                  <button
                    type="button"
                    title="Directories"
                    onClick={() => setSettingsGlobalCategory('workspace_dirs')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'workspace_dirs'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>📂</span> Directories
                  </button>

                  <button
                    type="button"
                    title="Keyboard Shortcuts"
                    onClick={() => setSettingsGlobalCategory('keyboard_shortcuts')}
                    className={`flex items-center gap-2.5 px-3 py-2 text-left rounded-md transition-all font-pixel text-[9px] uppercase tracking-wider border cursor-pointer ${
                      settingsGlobalCategory === 'keyboard_shortcuts'
                        ? 'bg-yellow-500/10 border-yellow-500/25 text-amber-400 font-bold'
                        : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400 hover:bg-zinc-900/25'
                    }`}
                  >
                    <span>⌨️</span> Shortcuts
                  </button>
                </div>
              ) : (
                <div className="w-56 max-[960px]:w-44 border-r border-zinc-900/60 bg-zinc-950/45 flex flex-col p-4 max-[960px]:p-2.5 gap-2.5 shrink-0 select-none">
                  <div className="relative mb-2">
                    <input 
                      type="text" 
                      placeholder="Search settings..."
                      value={settingsGlobalSearch}
                      onChange={(e) => setSettingsGlobalSearch(e.target.value)}
                      className="w-full pl-7 pr-7 py-1.5 text-[10px] rounded-md text-white bg-zinc-900 border border-zinc-850 focus:outline-none focus:border-yellow-500/50 transition-all font-sans"
                    />
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 text-[10px]">🔍</span>
                    <button 
                      type="button" 
                      onClick={() => setSettingsGlobalSearch('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-[10px] font-bold"
                    >
                      ✕
                    </button>
                  </div>
                  <span className="text-[8px] font-bold text-slate-450 uppercase tracking-widest font-pixel">Unified Search</span>
                  <p className="text-[9px] text-slate-500 font-sans leading-relaxed">แสดงการตั้งค่าสากลทั้งหมดที่ตรงกัน</p>
                </div>
              )}

              {/* Right Settings Content Form */}
              <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950/25">
                <div className="flex-1 overflow-y-auto p-6 max-[960px]:p-3 flex flex-col gap-6 text-xs scrollbar-thin">
                  
                  {(() => {
                    const isGlobalSectionVisible = (sectionId: string, title: string, category: string) => {
                      if (settingsGlobalSearch.trim() !== '') {
                        return title.toLowerCase().includes(settingsGlobalSearch.toLowerCase()) || 
                               sectionId.toLowerCase().includes(settingsGlobalSearch.toLowerCase());
                      }
                      return settingsGlobalCategory === category;
                    };

                    const shortcutDefinitions = [
                      { id: 'findBalloon', label: 'Find Balloon (ค้นหากล่องคำพูด)', defaultKey: 'Ctrl+F' },
                      { id: 'selectMode', label: 'Select & Draw Mode (โหมดเลือกและวาดกล่อง - คลิกซ้ายเลือก/คลิกขวาค้างวาด)', defaultKey: 'V' },
                      { id: 'textEditMode', label: 'Text Tool (แก้ไขข้อความและบรรทัดแบบ Photoshop)', defaultKey: 'T' },
                      { id: 'drawBoxMode', label: 'Select & Draw Mode Alternate (โหมดเลือกและวาดกล่อง)', defaultKey: 'M' },
                      { id: 'brushMode', label: 'Mask Brush Mode (โหมดแปรงระบายสีลบอักษร)', defaultKey: 'B' },
                      { id: 'deleteBlock', label: 'Delete Active Block (ลบเลเยอร์คำพูด)', defaultKey: 'Delete' },
                      { id: 'deselectBlock', label: 'Deselect Block (ยกเลิกการเลือกเลเยอร์)', defaultKey: 'Escape' },
                      { id: 'cycleNextBlock', label: 'Cycle to Next Block (ข้ามไปบล็อกถัดไป)', defaultKey: 'Tab' },
                      { id: 'cyclePrevBlock', label: 'Cycle to Previous Block (ย้อนไปบล็อกก่อนหน้า)', defaultKey: 'Shift+Tab' },
                      { id: 'exportOcrTxt', label: 'Export OCR Text (ส่งออกเฉพาะคำสแกน)', defaultKey: 'Ctrl+Shift+S' },
                      { id: 'prevPage', label: 'Previous Page (ย้อนไปหน้าก่อนหน้า)', defaultKey: 'PageUp' },
                      { id: 'nextPage', label: 'Next Page (ข้ามไปหน้าถัดไป)', defaultKey: 'PageDown' },
                      { id: 'toggleTranslated', label: 'Toggle Translation Preview (สลับพรีวิวแปลการ์ตูน)', defaultKey: 'Shift+T' },
                      { id: 'toggleInpainted', label: 'Toggle Background Inpainting (สลับการลบข้อความพื้นหลัง)', defaultKey: 'Shift+C' },
                      { id: 'undo', label: 'Undo (ย้อนกลับการแก้ไข)', defaultKey: 'Ctrl+Z' },
                      { id: 'redo', label: 'Redo (ทำซ้ำการแก้ไข)', defaultKey: 'Ctrl+Y' },
                    ];

                    const handleBrowseFolder = async (type: 'load' | 'save') => {
                      const currentPath = type === 'load' ? defaultLoadProjectPath : defaultSaveOcrPath;
                      try {
                        const res = await fetch(`/api/utils/browse-folder?default_directory=${encodeURIComponent(currentPath)}`, {
                          method: 'POST'
                        });
                        if (res.ok) {
                          const data = await res.json();
                          if (data.success && data.path) {
                            if (type === 'load') {
                              setDefaultLoadProjectPath(data.path);
                            } else {
                              setDefaultSaveOcrPath(data.path);
                            }
                            showToast("บันทึกเส้นทางโฟลเดอร์เรียบร้อย", "success");
                          }
                        }
                      } catch (err) {
                        console.error("Browse folder failed:", err);
                        showToast("ไม่สามารถเปิดเบราว์เซอร์โฟลเดอร์ได้", "error");
                      }
                    };

                    const selectedTemplate = stylePresets[selectedTemplateKey];
                    const selectedTemplateFont = selectedTemplate?.font_stack[0] || '';
                    const strokeEnabled = Boolean(selectedTemplate && (
                      selectedTemplate.stroke_enabled ?? selectedTemplate.stroke_width > 0
                    ));
                    const glowEnabled = Boolean(selectedTemplate && (
                      selectedTemplate.outline_glow_enabled
                        ?? ((selectedTemplate.outline_glow_radius ?? 0) > 0
                          && (selectedTemplate.outline_glow_opacity ?? 0) > 0)
                    ));
                    const previewGlowColor = selectedTemplate?.outline_glow_color
                      || selectedTemplate?.stroke_color
                      || '#ffffff';
                    const previewGlow = glowEnabled && selectedTemplate
                      ? `0 0 ${Math.max(1, selectedTemplate.outline_glow_radius ?? 0)}px ${colorWithOpacity(previewGlowColor, selectedTemplate.outline_glow_opacity ?? 0)}`
                      : 'none';
                    const templateFontOptions = Array.from(new Set(
                      [selectedTemplateFont, ...systemFonts].filter(Boolean),
                    ));
                    const updateTemplateDraft = (patch: Partial<TextTemplate>) => {
                      if (!templateDraftBaselineRef.current) {
                        templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
                      }
                      setStylePresets(current => ({
                        ...current,
                        [selectedTemplateKey]: { ...current[selectedTemplateKey], ...patch },
                      }));
                      setTemplateSettingsDirty(true);
                    };

                    return (
                      <>
                        {isGlobalSectionVisible('templates', 'Font Templates Layer Style Colors Fonts Presets', 'templates') && (
                          <div className="flex flex-col min-h-[560px] overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/45 shadow-xl animate-slide-up">
                            {/* ================= 1. TOP CLIENT / PROJECT PRESET HEADER BAR ================= */}
                            <div className="border-b border-zinc-800 bg-zinc-900/80 p-3 flex flex-wrap items-center justify-between gap-3">
                              {/* Left: Client Profile Dropdown & Info */}
                              <div className="flex flex-wrap items-center gap-2.5">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1 font-pixel shrink-0">
                                    <span>👤</span>
                                    <span>Client Preset:</span>
                                  </span>
                                  <select
                                    value={selectedClientId}
                                    onChange={(e) => {
                                      if (e.target.value === '__NEW__') {
                                        setIsAddingClientModalOpen(true);
                                      } else {
                                        handleSelectClientProfile(e.target.value);
                                      }
                                    }}
                                    className="bg-zinc-950 border border-zinc-700 hover:border-amber-500/60 text-white text-xs font-bold rounded-lg px-3 py-1.5 focus:outline-none focus:border-amber-500 cursor-pointer min-w-[210px]"
                                  >
                                    {clientProfiles.map(p => (
                                      <option key={p.id} value={p.id}>
                                        {p.name} {p.default_font_family ? `(${p.default_font_family})` : ''}
                                      </option>
                                    ))}
                                    <option value="__NEW__">➕ เพิ่มโปรไฟล์ลูกค้าใหม่ (+ New Client)...</option>
                                  </select>
                                </div>

                                {/* Profile Meta Badge */}
                                {activeClientProfile && (
                                  <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-zinc-950/80 border border-zinc-800 text-[10px] text-slate-400 font-mono">
                                    <span>ฟอนต์หลัก: <strong className="text-amber-300 font-sans font-bold">{activeClientProfile.default_font_family || 'TH Sarabun New'}</strong></span>
                                    <span>·</span>
                                    <span>{Object.keys(activeClientProfile.text_templates || {}).length} บทบาท</span>
                                    {activeClientProfile.description && (
                                      <>
                                        <span>·</span>
                                        <span className="text-slate-400 font-sans truncate max-w-[180px]" title={activeClientProfile.description}>{activeClientProfile.description}</span>
                                      </>
                                    )}
                                  </div>
                                )}
                              </div>

                              {/* Right: Action Buttons */}
                              <div className="flex flex-wrap items-center gap-1.5 font-pixel text-[9.5px]">
                                {/* Add Client Button */}
                                <button
                                  type="button"
                                  onClick={() => setIsAddingClientModalOpen(true)}
                                  className="px-2.5 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 font-bold transition-all cursor-pointer flex items-center gap-1"
                                  title="สร้างโปรไฟล์ลูกค้าใหม่ (Add New Client Profile)"
                                >
                                  <span>➕</span> เพิ่มลูกค้า
                                </button>

                                {/* Duplicate Profile */}
                                <button
                                  type="button"
                                  onClick={handleDuplicateClientProfile}
                                  className="px-2.5 py-1.5 rounded border border-zinc-700 bg-zinc-900 text-slate-300 hover:text-white hover:border-zinc-600 font-bold transition-all cursor-pointer flex items-center gap-1"
                                  title="คัดลอกโปรไฟล์นี้เป็นชุดใหม่ (Duplicate Profile)"
                                >
                                  <span>📋</span> คัดลอก
                                </button>

                                {/* Rename Profile */}
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (activeClientProfile) {
                                      setRenameClientProfileName(activeClientProfile.name);
                                      setRenameClientProfileDesc(activeClientProfile.description || '');
                                      setIsRenamingClientModalOpen(true);
                                    }
                                  }}
                                  className="px-2.5 py-1.5 rounded border border-zinc-700 bg-zinc-900 text-slate-300 hover:text-white hover:border-zinc-600 font-bold transition-all cursor-pointer flex items-center gap-1"
                                  title="แก้ไขชื่อและคำอธิบายโปรไฟล์ (Rename Profile)"
                                >
                                  <span>✏️</span> เปลี่ยนชื่อ
                                </button>

                                {/* Delete Profile */}
                                <button
                                  type="button"
                                  disabled={clientProfiles.length <= 1}
                                  onClick={handleDeleteClientProfile}
                                  className="px-2 py-1.5 rounded border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20 font-bold transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                                  title="ลบโปรไฟล์ลูกค้านี้ (Delete Profile)"
                                >
                                  <span>🗑️</span>
                                </button>

                                <div className="h-4 w-px bg-zinc-700 mx-1 hidden sm:block" />

                                {/* Import Client JSON */}
                                <input
                                  type="file"
                                  ref={clientProfileImportFileRef}
                                  onChange={handleImportClientProfiles}
                                  accept=".json"
                                  className="hidden"
                                />
                                <button
                                  type="button"
                                  onClick={() => clientProfileImportFileRef.current?.click()}
                                  className="px-2.5 py-1.5 rounded border border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 font-bold transition-all cursor-pointer flex items-center gap-1"
                                  title="นำเข้าไฟล์ Font Templates / Client Profile จาก JSON (Import JSON)"
                                >
                                  <span>📥</span> นำเข้า
                                </button>

                                {/* Export Dropdown Button */}
                                <div className="relative inline-block text-left">
                                  <button
                                    type="button"
                                    onClick={() => setShowExportDropdown(!showExportDropdown)}
                                    className="px-2.5 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 font-bold transition-all cursor-pointer flex items-center gap-1"
                                    title="ส่งออกและเซฟไฟล์ JSON ออกสู่เครื่อง"
                                  >
                                    <span>📤</span> ส่งออก / เซฟออก <span>▾</span>
                                  </button>

                                  {showExportDropdown && (
                                    <div className="absolute right-0 mt-1.5 w-60 rounded-xl bg-zinc-950 border border-zinc-700 shadow-2xl z-50 p-1.5 font-sans text-xs animate-fade-in divide-y divide-zinc-850">
                                      <div className="p-1">
                                        <button
                                          type="button"
                                          onClick={() => {
                                            setShowExportDropdown(false);
                                            handleExportCurrentProfile();
                                          }}
                                          className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-zinc-900 text-slate-200 hover:text-emerald-300 flex flex-col gap-0.5 cursor-pointer transition-colors"
                                        >
                                          <span className="font-bold flex items-center gap-1.5">
                                            <span>💾</span> บันทึกเฉพาะโปรไฟล์นี้ (.json)
                                          </span>
                                          <span className="text-[10px] text-slate-400 font-mono">
                                            {activeClientProfile?.name || 'Current Profile'}
                                          </span>
                                        </button>
                                      </div>
                                      <div className="p-1">
                                        <button
                                          type="button"
                                          onClick={() => {
                                            setShowExportDropdown(false);
                                            handleExportAllProfiles();
                                          }}
                                          className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-zinc-900 text-slate-200 hover:text-amber-300 flex flex-col gap-0.5 cursor-pointer transition-colors"
                                        >
                                          <span className="font-bold flex items-center gap-1.5">
                                            <span>📦</span> บันทึกโปรไฟล์ทั้งหมด (.json)
                                          </span>
                                          <span className="text-[10px] text-slate-400 font-mono">
                                            ครบทั้ง {clientProfiles.length} โปรไฟล์ลูกค้า
                                          </span>
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                </div>

                                {/* Apply to Active Project Button */}
                                {activeProject && (
                                  <button
                                    type="button"
                                    onClick={handleApplyProfileToCurrentProject}
                                    className="px-3 py-1.5 rounded bg-yellow-500 hover:bg-yellow-400 text-black font-extrabold shadow-md shadow-yellow-500/20 transition-all cursor-pointer flex items-center gap-1 ml-1"
                                    title="นำชุดฟอนต์โปรไฟล์นี้ไปใช้งานกับโปรเจกต์มังงะที่เปิดอยู่ทันที"
                                  >
                                    <span>⚡</span> ปรับใช้กับโปรเจกต์
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* ================= 2. MAIN TEMPLATE SPLIT LAYOUT ================= */}
                            <div className="flex flex-1 min-h-[480px] overflow-hidden">
                              {/* Left Roles Sidebar */}
                              <aside className="flex w-72 max-[1100px]:w-56 max-[800px]:w-44 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/70">
                                <div className="p-3 border-b border-zinc-800 space-y-2">
                                  <div className="flex items-center justify-between">
                                    <h4 className="font-bold text-yellow-400 tracking-wider font-pixel text-[10px] uppercase">🎨 Roles ({Object.keys(stylePresets).length})</h4>
                                    <span className="text-[9px] text-slate-500 font-mono">Template List</span>
                                  </div>
                                  {/* Search / Filter Input */}
                                  <input
                                    type="text"
                                    value={roleSearchQuery}
                                    onChange={(e) => setRoleSearchQuery(e.target.value)}
                                    placeholder="🔍 ค้นหาบทบาท/ฟอนต์..."
                                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[10px] text-white outline-none focus:border-amber-500"
                                  />
                                </div>
                                <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                                  {Object.entries(stylePresets)
                                    .filter(([key, style]) => {
                                      if (!roleSearchQuery.trim()) return true;
                                      const q = roleSearchQuery.toLowerCase().trim();
                                      const name = (style.name || '').toLowerCase();
                                      const tag = (style.semantic_tag || '').toLowerCase();
                                      const font = (style.font_stack?.[0] || '').toLowerCase();
                                      const id = (style.id || key).toLowerCase();
                                      return name.includes(q) || tag.includes(q) || font.includes(q) || id.includes(q);
                                    })
                                    .map(([key, style]) => (
                                    <button
                                      type="button"
                                      key={key}
                                      onClick={() => setSelectedTemplateKey(key)}
                                      className={`w-full flex items-center gap-3 border p-2.5 max-[960px]:p-2 text-left transition-all rounded-lg cursor-pointer ${selectedTemplateKey === key ? 'border-yellow-500/50 bg-yellow-500/15 shadow-sm' : 'border-zinc-850 bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900'}`}
                                    >
                                      <span className="h-8 w-8 max-[960px]:h-6 max-[960px]:w-6 rounded border border-zinc-700 shadow-inner shrink-0" style={{ background: style.color_hex, boxShadow: `inset 0 0 0 ${style.stroke_enabled === false ? 0 : Math.max(0, style.stroke_width)}px ${style.stroke_color}` }} />
                                      <span className="min-w-0 flex-1">
                                        <span className="block truncate text-[11px] font-bold text-slate-200">{style.semantic_tag || style.name}</span>
                                        <span className="block truncate text-[9px] text-slate-400 font-mono">
                                          {style.font_stack[0]} · {style.font_size}px
                                          {style.semantic_tag ? ` · {${style.semantic_tag}}` : ''}
                                        </span>
                                      </span>
                                    </button>
                                  ))}
                                </div>
                                <div className="grid grid-cols-2 gap-2 border-t border-zinc-800 p-3">
                                  <input
                                    type="file"
                                    ref={importTemplateFileRef}
                                    accept=".json"
                                    onChange={handleImportTemplates}
                                    className="hidden"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!templateDraftBaselineRef.current) {
                                        templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
                                      }
                                      const id = `template_${Date.now()}`;
                                      const base = selectedTemplate || DEFAULT_TEXT_TEMPLATES.bubble;
                                      setStylePresets(current => ({
                                        ...current,
                                        [id]: {
                                          ...base,
                                          id,
                                          name: 'รูปแบบใหม่',
                                          semantic_tag: base.semantic_tag || 'รูปแบบใหม่',
                                          font_stack: [...base.font_stack],
                                          padding: { ...base.padding },
                                        },
                                      }));
                                      setSelectedTemplateKey(id);
                                      setTemplateSettingsDirty(true);
                                    }}
                                    className="rounded-md border border-yellow-500/30 bg-yellow-500/10 px-2 py-1.5 text-[9px] font-bold text-yellow-400 hover:bg-yellow-500/20 font-pixel text-center cursor-pointer"
                                  >＋ Add Role</button>
                                  <button
                                    type="button"
                                    disabled={Object.keys(stylePresets).length <= 1}
                                    onClick={() => {
                                      if (!selectedTemplate || !window.confirm(`Delete template "${selectedTemplate.name}"?`)) return;
                                      if (!templateDraftBaselineRef.current) {
                                        templateDraftBaselineRef.current = cloneTextTemplates(stylePresets);
                                      }
                                      setStylePresets(current => {
                                        const next = { ...current };
                                        delete next[selectedTemplateKey];
                                        setSelectedTemplateKey(Object.keys(next)[0]);
                                        return next;
                                      });
                                      setTemplateSettingsDirty(true);
                                    }}
                                    className="rounded-md border border-rose-500/20 px-2 py-1.5 text-[9px] font-bold text-rose-400 hover:bg-rose-500/10 disabled:opacity-30 font-pixel text-center cursor-pointer"
                                  >− Delete</button>
                                  <button
                                    type="button"
                                    onClick={() => importTemplateFileRef.current?.click()}
                                    className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-1.5 text-[9px] font-bold text-cyan-300 hover:bg-cyan-500/20 font-pixel text-center cursor-pointer"
                                    title="นำเข้าไฟล์ Font Templates JSON"
                                  >📥 Import</button>
                                  <button
                                    type="button"
                                    onClick={handleExportTemplates}
                                    className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1.5 text-[9px] font-bold text-emerald-300 hover:bg-emerald-500/20 font-pixel text-center cursor-pointer"
                                    title="ส่งออกไฟล์ Font Templates JSON"
                                  >📤 Export</button>
                                </div>
                              </aside>

                              {/* Right Layer Style Editor */}
                              {selectedTemplate && (
                                <section className="flex-1 overflow-y-auto p-6 max-[1100px]:p-4 max-[800px]:p-3">
                                  <div className="mb-5 flex items-start justify-between gap-4 border-b border-zinc-800 pb-4 max-[760px]:flex-col">
                                    <div className="min-w-0">
                                      <h3 className="text-base font-bold text-white">Layer Style: {selectedTemplate.name}</h3>
                                      <p className="mt-1 text-[10px] text-slate-500">การแก้ไขอยู่ใน Draft จนกว่าจะกด Save Templates</p>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2 max-[760px]:self-end">
                                      <button
                                        type="button"
                                        onClick={() => importTemplateFileRef.current?.click()}
                                        className="border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-2 text-[9px] font-bold text-cyan-300 hover:bg-cyan-500/20 font-pixel cursor-pointer"
                                        title="นำเข้าไฟล์ Font Templates JSON"
                                      >📥 Import JSON</button>
                                      <button
                                        type="button"
                                        onClick={handleExportTemplates}
                                        className="border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-2 text-[9px] font-bold text-emerald-300 hover:bg-emerald-500/20 font-pixel cursor-pointer"
                                        title="ส่งออกไฟล์ Font Templates JSON"
                                      >📤 Export JSON</button>
                                      <button
                                        type="button"
                                        disabled={!templateSettingsDirty}
                                        onClick={discardTemplateDraft}
                                        className="border border-zinc-700 bg-zinc-900 px-3 py-2 text-[9px] font-bold text-slate-300 hover:text-white disabled:cursor-default disabled:opacity-30 font-pixel cursor-pointer"
                                      >Revert</button>
                                      <button
                                        type="button"
                                        disabled={!templateSettingsDirty}
                                        onClick={() => void saveTemplateDraft()}
                                        className="bg-yellow-500 px-4 py-2 text-[10px] font-bold text-black shadow-[2px_2px_0_#000] hover:bg-yellow-400 disabled:cursor-default disabled:opacity-40 font-pixel cursor-pointer"
                                      >Save Templates</button>
                                    </div>
                                  </div>

                                  <div className="grid min-h-[430px] grid-cols-[142px_minmax(0,1fr)] max-[960px]:grid-cols-[118px_minmax(0,1fr)] border border-zinc-800 bg-zinc-950/50 rounded-lg overflow-hidden">
                                    <aside className="border-r border-zinc-800 bg-zinc-950 py-2">
                                      {([
                                        ['type', 'Typography'],
                                        ['fill', 'Fill & Gradient'],
                                        ['stroke', 'Stroke'],
                                        ['glow', 'Outer Glow'],
                                        ['shadow', 'Drop Shadow'],
                                      ] as const).map(([key, label]) => (
                                        <div key={key} className={`flex items-center border-l-2 ${templateLayerStyleTab === key ? 'border-yellow-500 bg-zinc-800/80' : 'border-transparent'}`}>
                                          <input
                                            type="checkbox"
                                            checked={
                                              key === 'type' || 
                                              key === 'fill' || 
                                              (key === 'stroke' ? strokeEnabled : key === 'glow' ? glowEnabled : Boolean(selectedTemplate.drop_shadow_enabled))
                                            }
                                            disabled={key === 'type' || key === 'fill'}
                                            onChange={(event) => {
                                              if (key === 'stroke') {
                                                updateTemplateDraft({
                                                  stroke_enabled: event.target.checked,
                                                  ...(event.target.checked && selectedTemplate.stroke_width <= 0 ? { stroke_width: 1 } : {}),
                                                });
                                              }
                                              if (key === 'glow') {
                                                updateTemplateDraft({
                                                  outline_glow_enabled: event.target.checked,
                                                  ...(event.target.checked && (selectedTemplate.outline_glow_radius ?? 0) <= 0 ? { outline_glow_radius: 7 } : {}),
                                                  ...(event.target.checked && (selectedTemplate.outline_glow_opacity ?? 0) <= 0 ? { outline_glow_opacity: 0.35 } : {}),
                                                });
                                              }
                                              if (key === 'shadow') {
                                                updateTemplateDraft({
                                                  drop_shadow_enabled: event.target.checked,
                                                  ...(event.target.checked && (selectedTemplate.drop_shadow_blur ?? 0) <= 0 ? { drop_shadow_blur: 8 } : {}),
                                                  ...(event.target.checked && (selectedTemplate.drop_shadow_opacity ?? 0) <= 0 ? { drop_shadow_opacity: 0.6 } : {}),
                                                });
                                              }
                                            }}
                                            className="ml-3 h-3.5 w-3.5 accent-yellow-500 cursor-pointer"
                                          />
                                          <button type="button" onClick={() => setTemplateLayerStyleTab(key)} className={`min-w-0 flex-1 px-2 py-2.5 text-left text-[10px] font-bold cursor-pointer ${templateLayerStyleTab === key ? 'text-white' : 'text-slate-400 hover:text-white'}`}>{label}</button>
                                        </div>
                                      ))}
                                    </aside>

                                    <div className="min-w-0 p-5 max-[960px]:p-3">
                                      {templateLayerStyleTab === 'type' && (
                                        <div className="grid grid-cols-2 gap-4">
                                          <label className="col-span-2 text-[9px] font-bold uppercase tracking-wider text-slate-500">Semantic Tag<input value={selectedTemplate.name} onChange={e => updateTemplateDraft({ name: e.target.value, semantic_tag: e.target.value })} className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs normal-case text-white outline-none focus:border-yellow-500 rounded" /></label>
                                          <label className="col-span-2 text-[9px] font-bold uppercase tracking-wider text-slate-500">Font<select value={selectedTemplateFont} onChange={e => updateTemplateDraft({ font_stack: [e.target.value] })} className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs normal-case text-white rounded cursor-pointer">{templateFontOptions.length === 0 && <option value="">Loading fonts...</option>}{templateFontOptions.map(font => <option key={font} value={font}>{font}{!systemFonts.includes(font) ? ' (not detected)' : ''}</option>)}</select></label>
                                          {/* Auto Size Font Toggle */}
                                           <div className="col-span-2 flex items-center justify-between rounded-lg border border-yellow-500/30 bg-yellow-500/[0.05] p-3 my-1">
                                             <div>
                                               <span className="block text-xs font-bold text-yellow-400">✨ Auto Size Font (ขยาย/ย่อฟอนต์ตามกล่อง)</span>
                                               <span className="mt-0.5 block text-[10px] text-slate-400">
                                                 เมื่อเปิดใช้งาน ระบบจะคำนวณปรับขนาดฟอนต์ให้พอดีกับกล่องข้อความอัตโนมัติ (ปิดการระบุขนาดตัวเลขตายตัว)
                                               </span>
                                             </div>
                                             <input
                                               type="checkbox"
                                               checked={Boolean(selectedTemplate.auto_font_size || selectedTemplate.font_size === 0)}
                                               onChange={(e) => {
                                                 const isAuto = e.target.checked;
                                                 updateTemplateDraft({
                                                   auto_font_size: isAuto,
                                                   font_size: isAuto ? 0 : (selectedTemplate.font_size || 52),
                                                 } as Partial<TextTemplate>);
                                               }}
                                               className="h-4 w-4 accent-yellow-500 cursor-pointer"
                                             />
                                           </div>

                                           {Boolean(selectedTemplate.auto_font_size || selectedTemplate.font_size === 0) ? (
                                             <div className="col-span-2 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-md text-xs font-bold text-yellow-400 flex items-center gap-2">
                                               <span>⚡ Auto Size Active — Fixed font size options are locked (System dynamically calculates text scaling inside block bounds).</span>
                                             </div>
                                           ) : (
                                             <>
                                               <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">
                                                 Default size
                                                 <input
                                                   type="number"
                                                   value={selectedTemplate.font_size}
                                                   onChange={e => updateTemplateDraft({ font_size: Number(e.target.value) })}
                                                   className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded"
                                                 />
                                               </label>
                                               <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">
                                                 Minimum
                                                 <input
                                                   type="number"
                                                   value={selectedTemplate.min_font_size}
                                                   onChange={e => updateTemplateDraft({ min_font_size: Number(e.target.value) })}
                                                   className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded"
                                                 />
                                               </label>
                                               <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">
                                                 Maximum
                                                 <input
                                                   type="number"
                                                   value={selectedTemplate.max_font_size}
                                                   onChange={e => updateTemplateDraft({ max_font_size: Number(e.target.value) })}
                                                   className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded"
                                                 />
                                               </label>
                                             </>
                                           )}
                                           {(() => {
                                             const currentStyleValue = selectedTemplate.bold && selectedTemplate.italic
                                               ? 'Bold Italic'
                                               : selectedTemplate.bold
                                               ? 'Bold'
                                               : selectedTemplate.italic
                                               ? 'Italic'
                                               : (selectedTemplate.font_stack.length > 1 && ['italic', 'bold', 'bold italic', 'bold_italic', 'regular'].includes(selectedTemplate.font_stack[1].toLowerCase())
                                                   ? selectedTemplate.font_stack[1].replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())
                                                   : 'Regular');

                                             const matchedFontKey = Object.keys(systemFontDetails).find(
                                               k => k.toLowerCase() === selectedTemplateFont.toLowerCase()
                                             );
                                             const rawStyles = (matchedFontKey ? systemFontDetails[matchedFontKey] : null) || ['Regular', 'Italic', 'Bold', 'Bold Italic'];
                                             const formattedStyles = rawStyles.map((s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()));
                                             const standardStyles = ['Regular', 'Italic', 'Bold', 'Bold Italic'];
                                             const styleOptions = Array.from(new Set([...formattedStyles, ...standardStyles]));

                                             return (
                                               <div className="col-span-2 grid grid-cols-2 gap-4">
                                                 <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Style
                                                   <select 
                                                     value={currentStyleValue} 
                                                     onChange={e => {
                                                       const styleChoice = e.target.value;
                                                       const isBold = styleChoice.toLowerCase().includes('bold') || styleChoice.toLowerCase().includes('black');
                                                       const isItalic = styleChoice.toLowerCase().includes('italic') || styleChoice.toLowerCase().includes('oblique');
                                                       const newStack = [selectedTemplate.font_stack[0], styleChoice];
                                                       updateTemplateDraft({
                                                         font_stack: newStack,
                                                         bold: isBold,
                                                         italic: isItalic,
                                                       });
                                                     }} 
                                                     className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded cursor-pointer"
                                                   >
                                                     {styleOptions.map((style: string) => (
                                                       <option key={style} value={style}>{style}</option>
                                                     ))}
                                                   </select>
                                                 </label>
                                                 <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 flex flex-col">
                                                   <span>Faux Support</span>
                                                   <div className="mt-1.5 flex gap-1 bg-zinc-900 border border-zinc-700 p-1 rounded">
                                                     <button 
                                                       type="button" 
                                                       onClick={() => {
                                                         const nextBold = !selectedTemplate.bold;
                                                         const nextStyle = nextBold && selectedTemplate.italic ? 'Bold Italic' : nextBold ? 'Bold' : selectedTemplate.italic ? 'Italic' : 'Regular';
                                                         updateTemplateDraft({
                                                           bold: nextBold,
                                                           font_stack: [selectedTemplate.font_stack[0], nextStyle]
                                                         });
                                                       }} 
                                                       className={`flex-1 font-serif text-sm px-2 py-1 flex items-center justify-center font-bold transition-colors cursor-pointer rounded ${selectedTemplate.bold ? 'bg-zinc-700 text-white' : 'text-slate-400 hover:text-slate-200'}`} 
                                                       title="Faux Bold"
                                                     >
                                                       T
                                                     </button>
                                                     <button 
                                                       type="button" 
                                                       onClick={() => {
                                                         const nextItalic = !selectedTemplate.italic;
                                                         const nextStyle = selectedTemplate.bold && nextItalic ? 'Bold Italic' : selectedTemplate.bold ? 'Bold' : nextItalic ? 'Italic' : 'Regular';
                                                         updateTemplateDraft({
                                                           italic: nextItalic,
                                                           font_stack: [selectedTemplate.font_stack[0], nextStyle]
                                                         });
                                                       }} 
                                                       className={`flex-1 font-serif text-sm px-2 py-1 flex items-center justify-center italic transition-colors cursor-pointer rounded ${selectedTemplate.italic ? 'bg-zinc-700 text-white' : 'text-slate-400 hover:text-slate-200'}`} 
                                                       title="Faux Italic"
                                                     >
                                                       T
                                                     </button>
                                                   </div>
                                                 </div>
                                               </div>
                                             );
                                           })()}
                                          <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Alignment<select value={selectedTemplate.text_align} onChange={e => updateTemplateDraft({ text_align: e.target.value as TextTemplate['text_align'] })} className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded cursor-pointer"><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
                                          <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Leading<input type="number" min="0.8" max="3" step="0.05" value={selectedTemplate.line_height_ratio} onChange={e => updateTemplateDraft({ line_height_ratio: Number(e.target.value) })} className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded" /></label>
                                          <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Tracking<input type="number" min="-200" max="500" step="10" value={selectedTemplate.letter_spacing} onChange={e => updateTemplateDraft({ letter_spacing: Number(e.target.value) })} className="mt-1.5 w-full border border-zinc-700 bg-zinc-900 p-2.5 text-xs text-white rounded" /></label>
                                        </div>
                                      )}
                                      {templateLayerStyleTab === 'fill' && <div className="max-w-md space-y-5"><h4 className="font-pixel text-[10px] font-bold uppercase text-slate-200">Fill Overlay</h4><ColorField label="Color" value={selectedTemplate.color_hex} onChange={(color_hex) => updateTemplateDraft({ color_hex })} /></div>}
                                      {templateLayerStyleTab === 'stroke' && <div className="max-w-md space-y-5"><h4 className="font-pixel text-[10px] font-bold uppercase text-slate-200">Stroke</h4><ColorField label="Stroke color" value={selectedTemplate.stroke_color} onChange={(stroke_color) => updateTemplateDraft({ stroke_color })} /><label className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">Size <span className="float-right font-mono text-slate-300">{selectedTemplate.stroke_width}px</span><input type="range" min="0" max="20" step="0.5" value={selectedTemplate.stroke_width} onChange={e => updateTemplateDraft({ stroke_width: Number(e.target.value) })} className="mt-3 w-full accent-yellow-500 cursor-pointer" /></label></div>}
                                      {templateLayerStyleTab === 'glow' && <div className="max-w-md space-y-5"><h4 className="font-pixel text-[10px] font-bold uppercase text-slate-200">Outer Glow</h4><ColorField label="Glow color" value={selectedTemplate.outline_glow_color || selectedTemplate.stroke_color} onChange={(outline_glow_color) => updateTemplateDraft({ outline_glow_color })} /><label className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">Size <span className="float-right font-mono text-slate-300">{selectedTemplate.outline_glow_radius ?? 0}px</span><input type="range" min="0" max="100" step="0.5" value={selectedTemplate.outline_glow_radius ?? 0} onChange={e => updateTemplateDraft({ outline_glow_radius: Number(e.target.value) })} className="mt-3 w-full accent-yellow-500 cursor-pointer" /></label><label className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">Opacity <span className="float-right font-mono text-slate-300">{Math.round((selectedTemplate.outline_glow_opacity ?? 0) * 100)}%</span><input type="range" min="0" max="100" step="1" value={Math.round((selectedTemplate.outline_glow_opacity ?? 0) * 100)} onChange={e => updateTemplateDraft({ outline_glow_opacity: Number(e.target.value) / 100 })} className="mt-3 w-full accent-yellow-500 cursor-pointer" /></label></div>}
                                      {templateLayerStyleTab === 'shadow' && (
                                        <div className="max-w-md space-y-5">
                                          <h4 className="font-pixel text-[10px] font-bold uppercase text-slate-200">Drop Shadow</h4>
                                          <ColorField label="Shadow color" value={selectedTemplate.drop_shadow_color || '#000000'} onChange={(drop_shadow_color) => updateTemplateDraft({ drop_shadow_color })} />
                                          <label className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">Blur <span className="float-right font-mono text-slate-300">{selectedTemplate.drop_shadow_blur ?? 0}px</span><input type="range" min="0" max="50" step="0.5" value={selectedTemplate.drop_shadow_blur ?? 0} onChange={e => updateTemplateDraft({ drop_shadow_blur: Number(e.target.value) })} className="mt-3 w-full accent-yellow-500 cursor-pointer" /></label>
                                          <label className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">Opacity <span className="float-right font-mono text-slate-300">{Math.round((selectedTemplate.drop_shadow_opacity ?? 0) * 100)}%</span><input type="range" min="0" max="100" step="1" value={Math.round((selectedTemplate.drop_shadow_opacity ?? 0) * 100)} onChange={e => updateTemplateDraft({ drop_shadow_opacity: Number(e.target.value) / 100 })} className="mt-3 w-full accent-yellow-500 cursor-pointer" /></label>
                                        </div>
                                      )}
                                      <div className="mt-6 border-t border-zinc-800 pt-4">
                                        <div className="mb-2 flex items-center justify-between text-[8px] font-bold uppercase tracking-wider text-slate-500">
                                          <span>Live Preview</span>
                                          <span className="font-mono normal-case text-slate-600">
                                            {strokeEnabled ? 'Stroke on' : 'Stroke off'} · {glowEnabled ? 'Glow on' : 'Glow off'}
                                          </span>
                                        </div>
                                        <div className="flex h-20 items-center justify-center rounded border border-zinc-800 bg-zinc-950 p-4">
                                          <span
                                            style={{
                                              color: selectedTemplate.color_hex,
                                              fontFamily: selectedTemplateFont || undefined,
                                              fontSize: '20px',
                                              fontWeight: selectedTemplate.bold ? 'bold' : 'normal',
                                              fontStyle: selectedTemplate.italic ? 'italic' : 'normal',
                                              letterSpacing: `${selectedTemplate.letter_spacing || 0}px`,
                                              WebkitTextStroke: strokeEnabled
                                                ? `${selectedTemplate.stroke_width}px ${selectedTemplate.stroke_color}`
                                                : undefined,
                                              textShadow: previewGlow,
                                            }}
                                          >
                                            Houmi Text ตัวอย่างคำพูด
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </section>
                              )}
                            </div>

                            {/* ================= 3. MODALS FOR ADDING / RENAMING CLIENT PROFILE ================= */}
                            {isAddingClientModalOpen && (
                              <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-fade-in">
                                <div className="bg-zinc-950 border border-amber-500/40 rounded-xl p-5 w-full max-w-md shadow-2xl space-y-4 animate-slide-up">
                                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
                                    <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5 font-pixel">
                                      <span>➕</span> สร้างโปรไฟล์ลูกค้า / โปรเจกต์ใหม่
                                    </h4>
                                    <button
                                      type="button"
                                      onClick={() => setIsAddingClientModalOpen(false)}
                                      className="text-slate-400 hover:text-white text-xs cursor-pointer p-1"
                                    >
                                      ✕
                                    </button>
                                  </div>

                                  <div className="space-y-3 font-sans text-xs">
                                    <div>
                                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                                        ชื่อลูกค้า / ชื่อโปรเจกต์ (Profile Name) *
                                      </label>
                                      <input
                                        type="text"
                                        value={newClientProfileName}
                                        onChange={(e) => setNewClientProfileName(e.target.value)}
                                        placeholder="เช่น สำนักพิมพ์ Aniverse / ลูกค้าเว็บตูน คุณ A"
                                        className="w-full bg-zinc-900 border border-zinc-700 focus:border-amber-500 rounded-lg p-2 text-white font-bold outline-none"
                                        autoFocus
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter') {
                                            handleAddNewClientProfile(newClientProfileName, newClientProfileDesc);
                                          }
                                        }}
                                      />
                                    </div>

                                    <div>
                                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                                        คำอธิบายเพิ่มเติม (Description - ตัวเลือก)
                                      </label>
                                      <input
                                        type="text"
                                        value={newClientProfileDesc}
                                        onChange={(e) => setNewClientProfileDesc(e.target.value)}
                                        placeholder="เช่น ชุดฟอนต์ทางการสำหรับมังงะแนวแฟนตาซี"
                                        className="w-full bg-zinc-900 border border-zinc-700 focus:border-amber-500 rounded-lg p-2 text-slate-200 outline-none"
                                      />
                                    </div>

                                    <p className="text-[10px] text-slate-400">
                                      💡 โปรไฟล์ใหม่จะคัดลอกชุดสไตล์ Font Templates ปัจจุบันมาเป็นค่าเริ่มต้น เพื่อให้ท่านปรับแต่งต่อได้ทันที
                                    </p>
                                  </div>

                                  <div className="flex justify-end gap-2 pt-2 border-t border-zinc-850 font-pixel text-xs">
                                    <button
                                      type="button"
                                      onClick={() => setIsAddingClientModalOpen(false)}
                                      className="px-3 py-1.5 rounded border border-zinc-800 bg-zinc-900 text-slate-400 hover:text-white cursor-pointer"
                                    >
                                      ยกเลิก
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleAddNewClientProfile(newClientProfileName, newClientProfileDesc)}
                                      className="px-4 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-bold cursor-pointer shadow-md shadow-amber-500/20"
                                    >
                                      สร้างโปรไฟล์
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            {isRenamingClientModalOpen && (
                              <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-fade-in">
                                <div className="bg-zinc-950 border border-zinc-700 rounded-xl p-5 w-full max-w-md shadow-2xl space-y-4 animate-slide-up">
                                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
                                    <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5 font-pixel">
                                      <span>✏️</span> แก้ไขข้อมูลโปรไฟล์ลูกค้า
                                    </h4>
                                    <button
                                      type="button"
                                      onClick={() => setIsRenamingClientModalOpen(false)}
                                      className="text-slate-400 hover:text-white text-xs cursor-pointer p-1"
                                    >
                                      ✕
                                    </button>
                                  </div>

                                  <div className="space-y-3 font-sans text-xs">
                                    <div>
                                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                                        ชื่อโปรไฟล์ลูกค้า (Profile Name) *
                                      </label>
                                      <input
                                        type="text"
                                        value={renameClientProfileName}
                                        onChange={(e) => setRenameClientProfileName(e.target.value)}
                                        className="w-full bg-zinc-900 border border-zinc-700 focus:border-amber-500 rounded-lg p-2 text-white font-bold outline-none"
                                        autoFocus
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter') {
                                            handleRenameClientProfile(renameClientProfileName, renameClientProfileDesc);
                                          }
                                        }}
                                      />
                                    </div>

                                    <div>
                                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                                        คำอธิบายเพิ่มเติม (Description)
                                      </label>
                                      <input
                                        type="text"
                                        value={renameClientProfileDesc}
                                        onChange={(e) => setRenameClientProfileDesc(e.target.value)}
                                        className="w-full bg-zinc-900 border border-zinc-700 focus:border-amber-500 rounded-lg p-2 text-slate-200 outline-none"
                                      />
                                    </div>
                                  </div>

                                  <div className="flex justify-end gap-2 pt-2 border-t border-zinc-850 font-pixel text-xs">
                                    <button
                                      type="button"
                                      onClick={() => setIsRenamingClientModalOpen(false)}
                                      className="px-3 py-1.5 rounded border border-zinc-800 bg-zinc-900 text-slate-400 hover:text-white cursor-pointer"
                                    >
                                      ยกเลิก
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleRenameClientProfile(renameClientProfileName, renameClientProfileDesc)}
                                      className="px-4 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-bold cursor-pointer shadow-md shadow-amber-500/20"
                                    >
                                      บันทึกการแก้ไข
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {isGlobalSectionVisible('typesetting_rules', 'Typesetting Rules Thai Linguistic Segmentation Particles Glue Clitics Words', 'typesetting_rules') && (
                          <div className="animate-slide-up">
                            <TypesettingRulesSettingsPanel showToast={showToast} />
                          </div>
                        )}

                        {isGlobalSectionVisible('performance', 'Performance Profile Hardware GPU CPU Preview Workers', 'performance') && (
                          <div className="flex flex-col gap-4 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <div>
                              <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase">⚡ Performance Profile</h4>
                              <p className="text-[10px] text-slate-500 mt-1">เลือกตามสเปกเครื่อง ค่านี้ควบคุม OCR workers, Preview, Typesetting และนโยบาย GPU จริง</p>
                            </div>

                            <div className="grid grid-cols-3 gap-2.5">
                              {(Object.entries(PERFORMANCE_PROFILE_INFO) as Array<[Exclude<PerformanceProfile, 'custom'>, typeof PERFORMANCE_PROFILE_INFO.eco]>).map(([profile, info]) => (
                                <button
                                  key={profile}
                                  type="button"
                                  onClick={() => updateGlobalSetting('performance_profile', profile)}
                                  className={`p-3 rounded-md border text-left transition-all cursor-pointer ${
                                    settingsPerformanceProfile === profile
                                      ? 'border-yellow-500/60 bg-yellow-500/10 shadow-[0_0_12px_rgba(234,179,8,0.08)]'
                                      : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'
                                  }`}
                                >
                                  <span className={`block text-[10px] font-pixel font-bold uppercase ${settingsPerformanceProfile === profile ? 'text-yellow-400' : 'text-slate-300'}`}>{info.label}</span>
                                  <span className="block text-[9px] text-slate-500 leading-relaxed mt-1.5">{info.description}</span>
                                  <span className="block text-[8px] font-mono text-slate-600 mt-2">Preview {info.preview} · {info.workers} worker{info.workers > 1 ? 's' : ''}</span>
                                </button>
                              ))}
                            </div>

                            <button
                              type="button"
                              onClick={() => updateGlobalSetting('performance_profile', 'custom')}
                              className={`p-3 rounded-md border text-left transition-all cursor-pointer ${
                                settingsPerformanceProfile === 'custom' ? 'border-yellow-500/60 bg-yellow-500/10' : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'
                              }`}
                            >
                              <span className="text-[10px] font-pixel font-bold uppercase text-slate-300">Custom</span>
                              <span className="text-[9px] text-slate-500 ml-3">กำหนดงบการทำงานเอง</span>
                            </button>

                            {settingsPerformanceProfile === 'custom' && (
                              <div className="grid grid-cols-3 gap-3 p-3 rounded-md border border-zinc-800 bg-zinc-950/50">
                                <label className="text-[9px] text-slate-500">
                                  Preview width
                                  <input type="number" min="600" max="2400" step="100" value={settingsPerformanceCustom.preview_width}
                                    onChange={(e) => updateGlobalSetting('performance_custom', { ...settingsPerformanceCustom, preview_width: Number(e.target.value) })}
                                    className="mt-1 w-full p-2 rounded bg-zinc-900 border border-zinc-800 text-slate-200" />
                                </label>
                                <label className="text-[9px] text-slate-500">
                                  Layout candidates
                                  <input type="number" min="12" max="96" value={settingsPerformanceCustom.typesetting_candidates}
                                    onChange={(e) => updateGlobalSetting('performance_custom', { ...settingsPerformanceCustom, typesetting_candidates: Number(e.target.value) })}
                                    className="mt-1 w-full p-2 rounded bg-zinc-900 border border-zinc-800 text-slate-200" />
                                </label>
                                <label className="text-[9px] text-slate-500">
                                  OCR workers
                                  <input type="number" min="1" max="4" value={settingsPerformanceCustom.ocr_workers}
                                    onChange={(e) => updateGlobalSetting('performance_custom', { ...settingsPerformanceCustom, ocr_workers: Number(e.target.value) })}
                                    className="mt-1 w-full p-2 rounded bg-zinc-900 border border-zinc-800 text-slate-200" />
                                </label>
                                <label className="col-span-3 flex items-center gap-2 text-[10px] text-slate-300 cursor-pointer">
                                  <input type="checkbox" checked={settingsPerformanceCustom.prefer_gpu}
                                    onChange={(e) => updateGlobalSetting('performance_custom', { ...settingsPerformanceCustom, prefer_gpu: e.target.checked })}
                                    className="accent-yellow-500" />
                                  Prefer GPU when a working provider is available
                                </label>
                              </div>
                            )}

                            {/* Hardware Auto-Optimize Section */}
                            <div className="mt-2 p-3.5 rounded-lg bg-gradient-to-r from-amber-500/10 via-yellow-500/5 to-transparent border border-amber-500/30 flex flex-col gap-3">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="text-base">🚀</span>
                                  <div>
                                    <h5 className="font-bold text-amber-300 text-xs font-pixel uppercase">Hardware Auto-Optimization</h5>
                                    <p className="text-[10px] text-slate-400">ตรวจจับสเปก CPU / GPU (NVIDIA RTX/AMD/Intel) และตั้งค่าความเร็วที่ดีที่สุดให้อัตโนมัติใน 1 คลิก</p>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={handleAutoOptimizeHardware}
                                  disabled={isOptimizingHardware}
                                  className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-black font-bold text-[11px] shadow-md shadow-amber-500/20 cursor-pointer disabled:opacity-50 transition-all flex items-center gap-1.5"
                                >
                                  {isOptimizingHardware ? (
                                    <>
                                      <span className="inline-block w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin"></span>
                                      <span>กำลังปรับแต่ง...</span>
                                    </>
                                  ) : (
                                    <>
                                      <span>⚡</span>
                                      <span>Auto-Optimize Hardware (1-Click)</span>
                                    </>
                                  )}
                                </button>
                              </div>

                              {hardwareReport && (
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-amber-500/20 text-[10px] font-mono">
                                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-850">
                                    <span className="text-slate-500 block text-[9px]">CPU</span>
                                    <span className="text-slate-200 font-semibold truncate block">{hardwareReport.cpu_name || 'Detecting...'}</span>
                                    <span className="text-amber-400 text-[9px]">{hardwareReport.cpu_cores} Cores</span>
                                  </div>
                                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-850">
                                    <span className="text-slate-500 block text-[9px]">GPU</span>
                                    <span className="text-amber-300 font-semibold truncate block">{hardwareReport.gpu_name || 'No dedicated GPU'}</span>
                                    {hardwareReport.gpu_vram_gb && <span className="text-amber-400 text-[9px]">{hardwareReport.gpu_vram_gb} GB VRAM</span>}
                                  </div>
                                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-850">
                                    <span className="text-slate-500 block text-[9px]">RAM</span>
                                    <span className="text-slate-200 font-semibold block">{hardwareReport.ram_total_gb} GB</span>
                                    <span className="text-slate-400 text-[9px]">Avail: {hardwareReport.ram_available_gb} GB</span>
                                  </div>
                                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-850">
                                    <span className="text-slate-500 block text-[9px]">ACTIVE ACCELERATOR</span>
                                    <span className="text-emerald-400 font-bold block truncate">{hardwareReport.acceleration_type || 'Auto'}</span>
                                    <span className="text-[9px] text-yellow-400 font-bold">{hardwareReport.optimal_provider || 'Ready'}</span>
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Standalone GPU Inpaint Server Section */}
                            <div className="mt-2 p-3.5 rounded-lg bg-gradient-to-r from-cyan-500/10 via-blue-500/5 to-transparent border border-cyan-500/30 flex flex-col gap-3">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="text-base">⚡</span>
                                  <div>
                                    <h5 className="font-bold text-cyan-300 text-xs font-pixel uppercase">Standalone GPU Inpaint Server (PyTorch CUDA)</h5>
                                    <p className="text-[10px] text-slate-400">เชื่อมต่อหรือระบุโฟลเดอร์เซิร์ฟเวอร์ Inpainting บน GPU แยกเดี่ยว (ความเร็วสูงพิเศษ 0.05s/หน้า)</p>
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  <a
                                    href="/api/system/download-inpaint-server"
                                    target="_blank"
                                    rel="noreferrer"
                                    className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-cyan-300 border border-cyan-500/30 text-[10px] font-bold transition-all flex items-center gap-1"
                                    title="ดาวน์โหลดแพ็กเกจ Inpaint Server Zip ไปเปิดใช้งานบนเครื่อง"
                                  >
                                    <span>📥</span>
                                    <span>โหลด GPU Server (.zip)</span>
                                  </a>
                                </div>
                              </div>

                              {/* Inpaint Server Folder Path Selection */}
                              <div className="flex items-center gap-2 pt-0.5">
                                <div className="flex-1 relative">
                                  <input
                                    type="text"
                                    value={inpaintServerFolderPath}
                                    onChange={(e) => {
                                      const val = e.target.value;
                                      setInpaintServerFolderPath(val);
                                      localStorage.setItem('houmi_inpaint_server_path', val);
                                      updateGlobalSetting('inpaint_server_path', val);
                                    }}
                                    placeholder="โฟลเดอร์เซิร์ฟเวอร์ เช่น C:\inpaint_server หรือ ImageTrans\plugins\Lamal"
                                    className="w-full bg-zinc-950/80 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-amber-200 font-mono focus:border-amber-500 outline-none"
                                  />
                                </div>
                                <button
                                  type="button"
                                  onClick={async () => {
                                    try {
                                      const res = await fetch(`/api/utils/browse-folder?default_directory=${encodeURIComponent(inpaintServerFolderPath)}`, { method: 'POST' });
                                      if (res.ok) {
                                        const data = await res.json();
                                        if (data.success && data.path) {
                                          setInpaintServerFolderPath(data.path);
                                          localStorage.setItem('houmi_inpaint_server_path', data.path);
                                          updateGlobalSetting('inpaint_server_path', data.path);
                                          showToast(`เลือกโฟลเดอร์เซิร์ฟเวอร์: ${data.path}`, 'success');
                                        }
                                      }
                                    } catch {
                                      showToast('ไม่สามารถเปิดหน้าต่างเลือกโฟลเดอร์ได้', 'error');
                                    }
                                  }}
                                  className="px-3 py-1.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-[11px] font-bold transition-all flex items-center gap-1 shrink-0 cursor-pointer shadow"
                                >
                                  📁 เลือกโฟลเดอร์...
                                </button>
                              </div>

                              {/* Server Port / URL and Test Connection */}
                              <div className="flex items-center gap-2 pt-0.5">
                                <div className="flex-1 relative">
                                  <input
                                    type="text"
                                    value={gpuInpaintUrl}
                                    onChange={(e) => setGpuInpaintUrl(e.target.value)}
                                    placeholder="http://127.0.0.1:2328/inpaint"
                                    className="w-full bg-zinc-950/80 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-cyan-200 font-mono focus:border-cyan-500 outline-none"
                                  />
                                </div>
                                <button
                                  type="button"
                                  onClick={handleTestInpaintServer}
                                  disabled={isTestingInpaintServer}
                                  className="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-[11px] disabled:opacity-50 cursor-pointer transition-all flex items-center gap-1 shadow shrink-0"
                                >
                                  {isTestingInpaintServer ? (
                                    <>
                                      <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                                      <span>กำลังทดสอบ...</span>
                                    </>
                                  ) : (
                                    <>
                                      <span>🔍</span>
                                      <span>ทดสอบเชื่อมต่อ (Test)</span>
                                    </>
                                  )}
                                </button>
                              </div>

                              {inpaintServerTestResult && (
                                <div className={`text-[10px] p-2 rounded border flex items-center justify-between ${
                                  inpaintServerTestResult.success
                                    ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                                    : 'bg-red-950/40 border-red-500/40 text-red-300'
                                }`}>
                                  <div className="flex items-center gap-1.5">
                                    <span>{inpaintServerTestResult.success ? '🟢' : '🔴'}</span>
                                    <span>{inpaintServerTestResult.message}</span>
                                  </div>
                                  {inpaintServerTestResult.gpu_name && (
                                    <span className="font-mono bg-black/40 px-1.5 py-0.5 rounded text-[9px] text-cyan-300">
                                      {inpaintServerTestResult.gpu_name} ({inpaintServerTestResult.latency_ms} ms)
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Balloon Detection Options */}
                        {isGlobalSectionVisible('balloon', 'Balloon Detection Options', 'ai_detection') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🎈 Balloon Detection Options</h4>
                            <div className="grid grid-cols-1 gap-3.5">
                              <div className="col-span-2">
                                <label className="flex items-center gap-3 cursor-pointer select-none bg-amber-500/10 hover:bg-amber-500/15 border border-amber-500/30 p-3 rounded-lg text-amber-200 transition-all shadow-sm">
                                  <input 
                                    type="checkbox"
                                    checked={settingsEnableSmartBalloon}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('enable_smart_balloon', val);
                                      try {
                                        localStorage.setItem('houmi_setting_enable_smart_balloon', JSON.stringify(val));
                                      } catch {}
                                      const curProj = useProjectStore.getState().activeProject;
                                      if (curProj) {
                                        useProjectStore.getState().updateProjectSettings(curProj.id, {
                                          ...(curProj.settings || {}),
                                          enable_smart_balloon: val,
                                        });
                                      }
                                    }}
                                    className="w-4 h-4 rounded border-amber-500/50 bg-zinc-950 text-amber-400 accent-amber-500 cursor-pointer"
                                  />
                                  <div className="flex flex-col">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-bold text-amber-300">🎈 Smart Balloon V15 (Adaptive Shape & Flow)</span>
                                      {settingsEnableSmartBalloon && (
                                        <span className="px-1.5 py-0.2 bg-amber-400/20 text-amber-300 border border-amber-400/30 rounded text-[8px] font-pixel font-bold">
                                          ACTIVE
                                        </span>
                                      )}
                                    </div>
                                    <span className="text-[10px] font-normal text-amber-300/70 mt-0.5">
                                      ตรวจจับรูปทรงบอลลูนจริง ตัดคำตามขอบโค้ง/มุมแหลม และจัดตำแหน่งกึ่งกลางมวล (Visual Centroid) อัตโนมัติ
                                    </span>
                                  </div>
                                </label>
                              </div>

                              <div className="col-span-2">
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">YOLO Balloon Model</label>
                                <select 
                                  value={settingsBalloonModel}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('balloon_model', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="Chinese Webtoon (SQ)">🇨🇳 Chinese Webtoon (SQ) - YOLOv8 [แนะนำสำหรับม่านฮวาจีน]</option>
                                  <option value="Comic-Translate (8k Multi-Style)">🎨 Comic-Translate 8k - YOLOv8 [ฟูลขอบเขตลูกโป่ง Inpainting เนียนสุด]</option>
                                  <option value="Manga Panel & Text (YOLO26n)">⚡ Manga Panel & Text - YOLO26n [โมเดลใหม่ล่าสุด ตรวจกรอบช่อง+ข้อความ]</option>
                                  <option value="RF-DETR (Transformer)">🤖 RF-DETR Transformer [ตรวจจับข้อความซ้อน/แถบยาวแม่นยำสูง]</option>
                                  <option value="Japanese Manga & CG (YOLO11s)">🇯🇵 Japanese Manga & CG - YOLO11s</option>
                                  <option value="Korean Webtoon (YOLOv8)">🇰🇷 Korean Webtoon - YOLOv8 (SAO Default)</option>
                                </select>
                              </div>

                              <div className="col-span-2 flex flex-col gap-2 text-slate-300 pt-1">
                                <label className="flex items-center gap-2 cursor-pointer select-none hover:text-slate-200 transition-colors">
                                  <input 
                                    type="checkbox" 
                                    checked={settingsInferTextDirection}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('infer_text_direction', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Infer Text Direction (คาดเดาทิศทางข้อความแนวตั้ง/แนวนอนอัตโนมัติ)</span>
                                </label>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* AI Provider Settings */}
                        {isGlobalSectionVisible('ai_provider', 'AI Provider Engine Keys Failover Gemini Antigravity', 'ai_provider') && (
                          <div className="bg-zinc-900/40 p-5 rounded-xl border border-amber-500/35 shadow-xl animate-slide-up select-none">
                            <div className="flex items-center gap-2 border-b border-zinc-800 pb-3 mb-4">
                              <span className="text-amber-400 text-base">🔑</span>
                              <div>
                                <h4 className="text-xs font-bold text-amber-300 uppercase tracking-wider font-pixel">
                                  AI Provider Engine & Multi-Key Priority Failover Pool
                                </h4>
                                <span className="text-[10px] text-slate-400 font-sans block mt-0.5">
                                  จัดการโหมด AI Engine, เพิ่ม/ลบ API Keys และปรับเปลี่ยนลำดับความสำคัญ (Priority Sequence) สากล
                                </span>
                              </div>
                            </div>

                            <AIProviderSettingsPanel showToast={showToast} />
                          </div>
                        )}

                        {/* OCR Scanning Settings */}
                        {isGlobalSectionVisible('ocr', 'OCR Engine Settings', 'ai_detection') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🔍 OCR Scanning</h4>
                            <div className="flex flex-col gap-2.5 text-slate-300">
                              <label className="flex items-center gap-2 cursor-pointer select-none hover:text-slate-200 transition-colors">
                                <input 
                                  type="checkbox" 
                                  checked={settingsAutoOcr}
                                  onChange={(e) => {
                                    const val = e.target.checked;
                                    updateGlobalSetting('auto_ocr', val);
                                  }}
                                  className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                />
                                <span>Auto OCR (สแกนตรวจจับอักษรอัตโนมัติทันทีเมื่ออัปโหลดรูปภาพใหม่)</span>
                              </label>
                            </div>
                          </div>
                        )}

                        {/* Typography & Style Settings */}
                        {isGlobalSectionVisible('editorStyle', 'Editor & Layout Style', 'typography') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🎨 Editor & Layout Style</h4>
                            <div className="flex flex-col gap-2.5 text-slate-300">
                              <label className="flex items-center gap-2 cursor-pointer select-none">
                                <input 
                                  type="checkbox"
                                  checked={settingsEnableRichText}
                                  onChange={(e) => {
                                    const val = e.target.checked;
                                    updateGlobalSetting('enable_rich_text', val);
                                  }}
                                  className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                />
                                <span>Enable rich text editing within the canvas textboxes</span>
                              </label>

                              <label className="flex items-center gap-2 cursor-pointer select-none">
                                <input 
                                  type="checkbox"
                                  checked={settingsEnableCjkVerticalTextEngine}
                                  onChange={(e) => {
                                    const val = e.target.checked;
                                    updateGlobalSetting('enable_cjk_vertical_text_engine', val);
                                  }}
                                  className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                />
                                <span>Enable CJK vertical text layout engine</span>
                              </label>
                            </div>
                          </div>
                        )}

                        {isGlobalSectionVisible('fontStyle', 'Font Style Presets', 'typography') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🔤 Font Style Defaults</h4>
                            <div className="grid grid-cols-2 gap-4">
                              <div className="col-span-2">
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Default Template for Imported Text</label>
                                <select value={settingsDefaultTextTemplateId} onChange={e => updateGlobalSetting('default_text_template_id', e.target.value)} className="w-full p-2.5 text-xs rounded-lg text-white bg-zinc-950 border border-zinc-800 focus:outline-none focus:border-yellow-500">
                                  {Object.entries(stylePresets).map(([key, template]) => <option key={key} value={key}>{template.name} · {template.font_stack[0]} · {template.font_size}px</option>)}
                                </select>
                                <p className="mt-1 text-[9px] text-slate-600">ใช้ทั้งฟอนต์ สี น้ำหนัก ระยะบรรทัด และค่า Typesetting จาก Template นี้เมื่อ Import</p>
                              </div>
                              <label className="col-span-2 flex items-center gap-2 cursor-pointer text-slate-300">
                                <input type="checkbox" checked={settingsLockTranslationToDetectedBox} onChange={e => updateGlobalSetting('lock_translation_to_detected_box', e.target.checked)} className="w-3.5 h-3.5 accent-yellow-500" />
                                <span>Lock translated text to the original detected box (ไม่ขยายหรือเลื่อนกรอบตาม Balloon)</span>
                              </label>
                              <label className="col-span-2 flex items-center gap-2 cursor-pointer text-slate-300">
                                <input type="checkbox" checked={settingsMatchSourceFontSize} onChange={e => updateGlobalSetting('match_source_font_size', e.target.checked)} className="w-3.5 h-3.5 accent-yellow-500" />
                                <span>Match translated font size to the original text</span>
                              </label>
                              {settingsMatchSourceFontSize && (
                                <div className="col-span-2">
                                  <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Source Font Scale: {settingsSourceFontScale.toFixed(2)}×</label>
                                  <input type="range" min="0.7" max="1.5" step="0.05" value={settingsSourceFontScale} onChange={e => updateGlobalSetting('source_font_scale', Number(e.target.value))} className="w-full accent-yellow-500" />
                                  <p className="mt-1 text-[9px] text-slate-600">1.00× = ใกล้ขนาดต้นฉบับ, ระบบยังลดลงได้หากข้อความยาวกว่า</p>
                                </div>
                              )}
                              <div className="col-span-2 flex flex-col gap-2.5 text-slate-300">
                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsAutoFontResize}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('auto_font_resize', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Auto font resize (ปรับขนาดฟอนต์คำแปลให้พอดีกล่องข้อความอัตโนมัติ)</span>
                                </label>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Min Font Size (px)</label>
                                <input 
                                  type="number" 
                                  value={settingsMinFontSize}
                                  onChange={(e) => {
                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                    updateGlobalSetting('min_font_size', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Max Font Size (px)</label>
                                <input 
                                  type="number" 
                                  value={settingsMaxFontSize}
                                  onChange={(e) => {
                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                    updateGlobalSetting('max_font_size', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>
                            </div>
                          </div>
                        )}

                        {isGlobalSectionVisible('textMerging', 'Text Merging Options', 'typography') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🔗 Text Merging Options</h4>
                            <div className="grid grid-cols-2 gap-4">
                              <div className="col-span-2">
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Sort Criteria (จัดลำดับกล่องข้อความ)</label>
                                <select 
                                  value={settingsSortCriteria}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('sort_criteria', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="Distance to the origin">Distance to the origin</option>
                                  <option value="Top-left corner">Top-left corner</option>
                                  <option value="Manga reading order (RTL)">Manga reading order (RTL)</option>
                                </select>
                              </div>

                              <div className="col-span-2 flex flex-col gap-2.5 text-slate-400">
                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsSortBasedOnPanels}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('sort_based_on_panels', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Sort text blocks based on detected manga panels first</span>
                                </label>
                              </div>
                            </div>
                          </div>
                        )}

                        {isGlobalSectionVisible('textRemoval', 'Text Removal & Inpainting', 'pipeline') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🧼 Cleanup Pipeline</h4>
                            
                            {/* Section 1: Core AI Models Selection Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              {/* Card 1: Default Mask Engine */}
                              <div className="p-3.5 bg-zinc-950/80 rounded-xl border border-zinc-800 space-y-2">
                                <label className="block text-slate-200 font-bold text-xs flex items-center gap-1 font-pixel">
                                  <span>🎭</span> DEFAULT MASK ENGINE (ระบบตรวจจับและสร้าง MASK)
                                </label>
                                <select 
                                  value={settingsDefaultMaskGenMethod || 'hybrid'}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('default_mask_gen_method', val);
                                    updateGlobalSetting('mask_gen_method', val);
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 bg-zinc-900 border border-zinc-700 focus:outline-none focus:border-yellow-500 cursor-pointer font-sans"
                                >
                                  <option value="hybrid">Godkiller Intelligent Hybrid Mask (แนะนำ SOTA - แยกหมึกอักษร ไม่กินเส้นบอลลูน)</option>
                                  <option value="imagetrans">ImageTrans Binarization Mask (โหมดดั้งเดิม ImageTrans - ไบนารีแยกกลุ่มตัวอักษร)</option>
                                  <option value="contour">Adaptive Morphology & Contours (โหมดมังงะขาวดำ - ตรวจจับขอบรวดเร็ว)</option>
                                  <option value="sam">Meta SAM AI Segmenter (Segment Anything ONNX - เหมาะกับ SFX ซับซ้อน)</option>
                                  <option value="balloon">Full Bounding Box Mask (ล้างเต็มกรอบสี่เหลี่ยม - โหมดตัดพื้นขาว)</option>
                                </select>
                                <span className="text-[10px] text-slate-400 block font-sans">
                                  อัลกอริทึมตรวจจับและแยกพิกเซลตัวอักษรออกจากภาพวาด ก่อนส่งให้ AI Inpaint ลบข้อความ
                                </span>
                              </div>

                              {/* Card 2: Default Inpainter Model */}
                              <div className="p-3.5 bg-zinc-950/80 rounded-xl border border-zinc-800 space-y-2">
                                <label className="block text-slate-200 font-bold text-xs flex items-center gap-1 font-pixel">
                                  <span>🧼</span> DEFAULT INPAINTER ENGINE (โมเดล AI ลบข้อความและเติมฉากหลัง)
                                </label>
                                <select 
                                  value={settingsDefaultImageInpaintMethod === 'Telea' ? 'Telea' : (settingsInpaintEngine === 'mat_onnx' ? 'mat_onnx' : (settingsInpaintEngine === 'lama_onnx' ? 'lama_onnx' : 'lama_manga'))}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    const isTelea = val === 'Telea';
                                    const isMat = val === 'mat_onnx';
                                    const inpaintMethod = isTelea ? 'Telea' : (isMat ? 'MAT' : 'LamaInpaint');
                                    const engineName = isTelea ? 'telea' : (isMat ? 'mat_onnx' : (val === 'lama_onnx' ? 'lama_onnx' : 'lama_manga'));
                                    updateGlobalSetting('default_image_inpaint_method', inpaintMethod);
                                    updateGlobalSetting('inpaint_engine', engineName);
                                    updateGlobalSetting('active_inpaint_engine', engineName);
                                    updateGlobalSetting('force_lama_inpaint', !isTelea);
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 bg-zinc-900 border border-zinc-700 focus:outline-none focus:border-yellow-500 cursor-pointer font-sans font-bold"
                                >
                                  <option value="lama_manga">AnimeMangaInpainting (LaMa-Manga ONNX - แนะนำ SOTA 198MB)</option>
                                  <option value="lama_onnx">Godkiller Standard LaMa (Big-LaMa ONNX - 208MB)</option>
                                  <option value="mat_onnx">MAT Inpainter (Mask-Aware Transformer ONNX)</option>
                                  <option value="Telea">OpenCV Telea (Fast Interpolation CPU - พรีวิวเร็ว &lt;5ms)</option>
                                </select>
                                <span className="text-[10px] text-slate-400 block font-sans">
                                  โมเดล AI ลบตัวหนังสือ: AnimeMangaInpainting เทรนด้วย Anime & Manga กว่า 300,000 ภาพ คมชัดทั้งมังงะและเว็บตูนสี
                                </span>
                              </div>

                              {/* Card 3: Inpaint Strategy (กลยุทธ์การคลีนและแบ่งช่อง) */}
                              <div className="p-3.5 bg-zinc-950/80 rounded-xl border border-zinc-800 space-y-2 col-span-1 md:col-span-2">
                                <div className="flex items-center justify-between">
                                  <label className="block text-slate-200 font-bold text-xs flex items-center gap-1.5 font-pixel">
                                    <span>⚡</span> INPAINT STRATEGY (กลยุทธ์การคลีนและแบ่งช่องตามสเปคเครื่อง)
                                  </label>
                                  <span className="text-[10px] text-amber-400 font-mono bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                                    Multi-Mode Architecture
                                  </span>
                                </div>
                                <select
                                  value={settingsInpaintStrategy || 'region'}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('inpaint_strategy', val);
                                    const curProj = useProjectStore.getState().activeProject;
                                    if (curProj) {
                                      useProjectStore.getState().updateProjectSettings(curProj.id, {
                                        ...(curProj.settings || {}),
                                        inpaint_strategy: val,
                                      });
                                    }
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 bg-zinc-900 border border-zinc-700 focus:outline-none focus:border-yellow-500 cursor-pointer font-sans font-bold text-yellow-300"
                                >
                                  <option value="region">🔶 Region-Based (รวมกลุ่มบอลลูนใกล้กัน - เร็ว คมชัด แนะนำสำหรับ GPU ทั่วไป)</option>
                                  <option value="per_block">🔷 Per-Block (ทีละบอลลูน 1:1 - เสถียรสูงสุด ประหยัดแรม สำหรับ CPU-only / GPU เบา)</option>
                                  <option value="parallel">⚡ Parallel Workers (ประมวลผลหลายบอลลูนพร้อมกัน - เร็วสุดขีด สำหรับ GPU แรง)</option>
                                </select>
                                <span className="text-[10px] text-slate-400 block font-sans">
                                  เลือกรูปแบบการส่งภาพเข้า AI: หากเครื่องช้าหรือมีแรมจำกัด แนะนำเลือก <b>🔷 Per-Block</b> เพื่อความเสถียรและความเร็วสูงสุด 100%
                                </span>
                              </div>
                            </div>

                            {/* Section 2: Fine-Tuning Parameters */}
                            <div className="p-4 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-3.5">
                              <div>
                                <div className="flex items-center justify-between mb-1.5">
                                  <label className="text-xs font-bold text-slate-300 font-pixel">
                                    🔍 MASK EXPANSION DILATION (ขยายขอบมาสก์เก็บรอยหมึก)
                                  </label>
                                  <span className="text-xs font-mono text-yellow-400 font-bold">{settingsMaskDilationKernel} px</span>
                                </div>
                                <div className="flex items-center gap-3">
                                  <input 
                                    type="range" 
                                    min="0" 
                                    max="56" 
                                    value={settingsMaskDilationKernel} 
                                    onChange={(e) => {
                                      const val = Math.max(0, Math.min(56, parseInt(e.target.value) || 0));
                                      updateGlobalSetting('mask_dilation_kernel', val);
                                      updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                    }} 
                                    className="flex-1 accent-yellow-500 cursor-pointer" 
                                  />
                                  <input 
                                    type="number" 
                                    min="0" 
                                    max="56" 
                                    value={settingsMaskDilationKernel} 
                                    onChange={(e) => {
                                      const val = Math.max(0, Math.min(56, parseInt(e.target.value) || 0));
                                      updateGlobalSetting('mask_dilation_kernel', val);
                                      updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                    }} 
                                    className="w-16 p-1.5 text-xs text-center rounded bg-zinc-900 border border-zinc-700 text-white font-mono font-bold focus:outline-none focus:border-yellow-500" 
                                  />
                                </div>
                                <span className="mt-1 block text-[10px] text-slate-400 font-sans">ขยายขอบมาสก์ 0 ถึง 56px เพื่อคลุมขอบหมึกฟุ้ง (Anti-aliasing) ของตัวอักษรให้สะอาดหมดจด (แนะนำ 2 - 4px)</span>
                              </div>

                              <div className="pt-1">
                                <label className="flex items-center gap-2.5 cursor-pointer text-slate-200 text-xs font-semibold">
                                  <input
                                    type="checkbox"
                                    checked={settingsMaskMagneticLineFill}
                                    onChange={(e) => updateGlobalSetting('mask_magnetic_line_fill', e.target.checked)}
                                    className="w-4 h-4 rounded border-zinc-700 bg-zinc-950 text-yellow-500 accent-yellow-500 cursor-pointer"
                                  />
                                  <span className="flex items-center gap-1 font-pixel text-yellow-400">
                                    <span>🧲</span>
                                    <span>MAGNETIC LINE MASK (เชื่อมเต็มบรรทัด - ไม่แหว่งกลาง)</span>
                                  </span>
                                </label>
                                <span className="text-[10px] text-slate-400 block mt-1 pl-6.5">
                                  เชื่อมช่องว่างระหว่างคำในแต่ละบรรทัดเข้าด้วยกันเป็นแถบสี่เหลี่ยมต่อเนื่อง ลบตัวหนังสือทั้งแถวเนียนสนิท ไม่แหว่งกลาง และไม่กินขอบบอลลูน
                                </span>
                              </div>

                              <div>
                                <label className="block text-xs font-bold text-slate-300 font-pixel mb-1">
                                  📐 INPAINT CONTEXT PADDING (ระยะขอบภาพอ้างอิงรอบข้อความ: px)
                                </label>
                                <input 
                                  type="number" 
                                  min="0" 
                                  max="512" 
                                  value={settingsInpaintContextPadding} 
                                  onChange={(e) => {
                                    updateGlobalSetting('inpaint_context_padding', Math.max(0, Math.min(512, Number(e.target.value) || 0)));
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }} 
                                  className="w-full p-2.5 text-xs rounded-lg text-white bg-zinc-900 border border-zinc-700 focus:outline-none focus:border-yellow-500 font-bold font-mono" 
                                />
                                <span className="mt-1 block text-[10px] text-slate-400 font-sans">ระยะขอบภาพรอบตัวหนังสือที่ส่งให้ AI ใช้สังเกตทิศทางลายเส้นและโครงสร้างฉากหลังเพื่อวาดต่อ (แนะนำ 96px)</span>
                              </div>
                            </div>

                            {/* Section 3: Batch Re-clean Action */}
                            <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                              <div>
                                <span className="text-xs font-bold text-yellow-400 flex items-center gap-1.5 font-pixel">
                                  <span>🧹</span> สั่งคลีนรูปภาพใหม่ทั้งหมด (Re-clean All Project Pages)
                                </span>
                                <p className="text-[10px] text-slate-300 leading-relaxed mt-1 font-sans">
                                  ล้างแคชภาพคลีนเดิม และสั่งให้ Godkiller Inpainting Engine ประมวลผลลบข้อความใหม่ทุกหน้าด้วยโมเดลที่เลือก
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  if (!activeProject) return;
                                  showConfirmDialog(
                                    'คุณต้องการล้างแคชและสั่งคลีนรูปภาพใหม่ทั้งหมดทุกหน้าใช่หรือไม่?',
                                    async () => {
                                      try {
                                        // 1. Immediately persist active mask dilation settings to DB
                                        const updatedSettings = {
                                          ...(activeProject.settings || {}),
                                          mask_dilation_kernel: settingsMaskDilationKernel,
                                          mask_magnetic_line_fill: settingsMaskMagneticLineFill,
                                          inpaint_context_padding: settingsInpaintContextPadding,
                                          cleanup_pipeline_profile: 'custom',
                                        };
                                        await updateProjectSettings(activeProject.id, updatedSettings);
                                        // 2. Clear old cached masks and stale clean images
                                        await apiFetch(`/api/pipeline/masks?project_id=${activeProject.id}`, { method: 'DELETE' });
                                      } catch (e) {
                                        console.warn("Reset masks / settings sync failed:", e);
                                      }
                                      runBatchPipeline('inpaint');
                                      setShowGlobalSettingsModal(false);
                                    },
                                    'ยืนยันการล้างแคชและคลีนรูปใหม่'
                                  );
                                }}
                                className="w-full md:w-auto py-2.5 px-4 bg-yellow-500 hover:bg-yellow-400 text-zinc-950 font-bold rounded-lg text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-yellow-500/20 shrink-0 cursor-pointer font-sans"
                              >
                                <span>🚀</span>
                                <span>สั่งคลีนรูปภาพใหม่ทั้งหมดทุกหน้า (Re-clean All Pages Now)</span>
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Pipeline & I/O Settings */}
                        {isGlobalSectionVisible('inputSetting', 'Input Pipeline Settings', 'pipeline') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">📥 Input Pipeline Settings</h4>
                            <div className="grid grid-cols-2 gap-4">
                              <div className="col-span-2 flex flex-col gap-2.5 text-slate-300">
                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsScaleImageBeforeDetection}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('scale_image_before_detection', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Scale the image before running AI detection</span>
                                </label>
                              </div>

                              {settingsScaleImageBeforeDetection && (
                                <div className="col-span-2 animate-fade-in">
                                  <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Target Image Scale Width (px)</label>
                                  <input 
                                    type="number" 
                                    value={settingsScaleImageSize}
                                    onChange={(e) => {
                                      const val = Math.max(128, parseInt(e.target.value) || 128);
                                      updateGlobalSetting('scale_image_size', val);
                                    }}
                                    className="w-40 p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                  />
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {isGlobalSectionVisible('textRemoval', 'Text Removal & Inpainting', 'pipeline') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">🧼 Cleanup Pipeline</h4>
                            <p className="text-[11px] leading-relaxed text-slate-450">เลือกโหมดเดียวสำหรับการลบข้อความ: ระบบจะใช้ Smart Mask เฉพาะรอยหมึกข้อความ ไม่ขยายกินขอบบอลลูน และเลือกเครื่องมือเติมภาพให้ตรงกับโหมดที่เลือก</p>

                            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                              <button
                                type="button"
                                onClick={() => applyCleanupPipelineProfile('smart_lama')}
                                className={`text-left p-3 rounded-lg border transition-colors cursor-pointer ${settingsCleanupPipelineProfile === 'smart_lama' ? 'border-yellow-500 bg-yellow-500/10' : 'border-zinc-800 bg-zinc-950/40 hover:border-yellow-500/50'}`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-bold text-xs text-yellow-400">✦ Smart Clean</span>
                                  {settingsCleanupPipelineProfile === 'smart_lama' && <span className="text-[9px] font-pixel text-yellow-300">ACTIVE</span>}
                                </div>
                                <p className="mt-1 text-[10px] leading-relaxed text-slate-300">Smart Mask + LaMa ทุกครั้ง เหมาะกับภาพส่งงานและฉากที่ต้องเก็บรายละเอียดพื้นหลัง</p>
                              </button>
                              <button
                                type="button"
                                onClick={() => applyCleanupPipelineProfile('fast_preview')}
                                className={`text-left p-3 rounded-lg border transition-colors cursor-pointer ${settingsCleanupPipelineProfile === 'fast_preview' ? 'border-cyan-500 bg-cyan-500/10' : 'border-zinc-800 bg-zinc-950/40 hover:border-cyan-500/50'}`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-bold text-xs text-cyan-300">⚡ Fast Preview</span>
                                  {settingsCleanupPipelineProfile === 'fast_preview' && <span className="text-[9px] font-pixel text-cyan-200">ACTIVE</span>}
                                </div>
                                <p className="mt-1 text-[10px] leading-relaxed text-slate-300">Smart Mask + Telea เร็วสำหรับตรวจงาน; อาจเติมฉากซับซ้อนได้ไม่ละเอียดเท่า LaMa</p>
                              </button>
                            </div>

                            <div className="flex flex-col gap-2 rounded-lg border border-zinc-800 bg-zinc-950/35 p-3 text-slate-300">
                              <label className="flex items-start gap-2 cursor-pointer select-none">
                                <input
                                  type="checkbox"
                                  checked={settingsCleanupMaskStrategy === 'smart' && settingsProcessByTextAreas}
                                  onChange={(e) => {
                                    updateGlobalSetting('cleanup_mask_strategy', e.target.checked ? 'smart' : 'box');
                                    updateGlobalSetting('process_by_text_areas', e.target.checked);
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }}
                                  className="mt-0.5 w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                />
                                <span><strong className="text-slate-200">Use Smart Mask automatically</strong><br /><span className="text-[10px] text-slate-500">สร้างมาสก์เฉพาะตัวอักษรในกรอบที่ตรวจพบ; การใช้ Smart Segment แบบลากใน Mask Editor ยังคงเป็นการเก็บรายละเอียดเพิ่มด้วยมือ</span></span>
                              </label>
                              <label className="flex items-start gap-2 cursor-pointer select-none">
                                <input
                                  type="checkbox"
                                  checked={settingsForceLamaInpaint}
                                  onChange={(e) => {
                                    updateGlobalSetting('force_lama_inpaint', e.target.checked);
                                    updateGlobalSetting('default_image_inpaint_method', e.target.checked ? 'LamaInpaint' : 'Telea');
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }}
                                  className="mt-0.5 w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                />
                                <span><strong className="text-slate-200">Always prefer LaMa</strong><br /><span className="text-[10px] text-slate-500">ใช้ LaMa บน provider ที่มีอยู่ (GPU หรือ CPU); จะถอยไป Telea เฉพาะตอนโมเดลใช้งานไม่ได้หรือเกิดข้อผิดพลาดเท่านั้น</span></span>
                              </label>
                            </div>

                            <details className="rounded-lg border border-zinc-800 bg-zinc-950/25 p-3 group">
                              <summary className="cursor-pointer select-none text-[10px] font-pixel uppercase tracking-wider text-slate-400 group-open:text-amber-400">Advanced mask refinement</summary>
                              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <label className="text-[10px] text-slate-400">Mask edge expansion (px)
                                  <input type="number" min="0" max="56" value={settingsMaskDilationKernel} onChange={(e) => {
                                    updateGlobalSetting('mask_dilation_kernel', Math.max(0, Math.min(56, parseInt(e.target.value) || 0)));
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }} className="mt-1 w-full p-2 text-xs rounded-lg text-white focus:outline-none input-glass font-bold" />
                                  <span className="mt-1 block text-[9px] text-slate-600">แนะนำ 3px เพื่อเก็บขอบตัวอักษรโดยไม่กินเส้นบอลลูน</span>
                                </label>
                                <label className="text-[10px] text-slate-400">Minimum LaMa context (px)
                                  <input type="number" min="0" max="512" value={settingsInpaintContextPadding} onChange={(e) => {
                                    updateGlobalSetting('inpaint_context_padding', Math.max(0, Math.min(512, Number(e.target.value) || 0)));
                                    updateGlobalSetting('cleanup_pipeline_profile', 'custom');
                                  }} className="mt-1 w-full p-2 text-xs rounded-lg text-white focus:outline-none input-glass font-bold" />
                                  <span className="mt-1 block text-[9px] text-slate-600">บริบทภาพที่ LaMa เห็นรอบ Mask โดยไม่ขยายพื้นที่ลบ</span>
                                </label>
                              </div>
                            </details>

                            <div className="hidden grid grid-cols-2 gap-4" aria-hidden="true">
                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Erase Method</label>
                                <select 
                                  value={settingsAccurateTextEraseMode}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('accurate_text_erase_mode', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="Image inpainting">Image inpainting (ลบตัวอักษรและวาดพื้นหลังใหม่)</option>
                                  <option value="Fill solid color">Fill solid color (เติมสีพื้นทึบ)</option>
                                </select>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Inpaint Model</label>
                                <select 
                                  value={settingsDefaultImageInpaintMethod}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('default_image_inpaint_method', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="LamaInpaint">LaMa (Local Masking AI - SOTA)</option>
                                  <option value="PatchMatch">PatchMatch (Fast Classic Algorithm)</option>
                                </select>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Inpaint Radius</label>
                                <input 
                                  type="number" 
                                  value={settingsImageInpaintingRadius}
                                  onChange={(e) => {
                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                    updateGlobalSetting('image_inpainting_radius', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Mask Dilation Kernel (px)</label>
                                <input 
                                  type="number" 
                                  value={settingsMaskDilationKernel}
                                  onChange={(e) => {
                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                    updateGlobalSetting('mask_dilation_kernel', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Minimum Inpaint Context (px)</label>
                                <input type="number" min="0" max="512" value={settingsInpaintContextPadding} onChange={e => updateGlobalSetting('inpaint_context_padding', Math.max(0, Math.min(512, Number(e.target.value) || 0)))} className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold" />
                                <p className="mt-1 text-[9px] text-slate-600">ค่าแนะนำ 96px · ค่านี้เป็นขั้นต่ำ ระบบจะเพิ่มเป็น 64–160px ตามขนาดกลุ่มข้อความ เพื่อให้ LaMa เห็นภาพต่อเนื่องรอบ Mask โดยไม่ขยายพื้นที่ลบ</p>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Mask Gen Method</label>
                                <select 
                                  value={settingsDefaultMaskGenMethod}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('default_mask_gen_method', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="Built-in binary generator">Built-in binary generator</option>
                                  <option value="OCR text mask generator">OCR text mask generator</option>
                                </select>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Feathering Sigma</label>
                                <input 
                                  type="number" 
                                  value={settingsMaskFeatheringSigma}
                                  onChange={(e) => {
                                    const val = Math.max(0, parseInt(e.target.value) || 0);
                                    updateGlobalSetting('mask_feathering_sigma', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Inpaint Max Width (px)</label>
                                <input 
                                  type="number" 
                                  value={settingsInpaintingMaxWidth}
                                  onChange={(e) => {
                                    const val = Math.max(128, parseInt(e.target.value) || 128);
                                    updateGlobalSetting('inpainting_max_width', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Sliding Window Overlap</label>
                                <input 
                                  type="number" 
                                  value={settingsSlidingWindowOverlap}
                                  onChange={(e) => {
                                    const val = Math.max(0, parseInt(e.target.value) || 0);
                                    updateGlobalSetting('sliding_window_overlap', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-white focus:outline-none input-glass font-bold"
                                />
                              </div>

                              <div className="col-span-2 flex flex-col gap-2.5 text-slate-300 mt-2.5">
                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsEnableSlidingWindows}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('enable_sliding_windows', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Enable Sliding Windows (ประมวลผลอินเพนท์แบบแบ่งช่อง)</span>
                                </label>

                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsStripFurigana}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('strip_furigana', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Strip Furigana (ลบตัวกำกับคำอ่านภาษาญี่ปุ่นก่อนลบอักษร)</span>
                                </label>

                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsWhenGeneratingMaskCheckSeparation}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('when_generating_mask_check_separation', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Check Separation when generating mask (ตรวจสอบความแยกส่วนเมื่อสร้างมาสก์)</span>
                                </label>

                                <label className="flex items-center gap-2 cursor-pointer select-none">
                                  <input 
                                    type="checkbox"
                                    checked={settingsConsiderFgBgDepth}
                                    onChange={(e) => {
                                      const val = e.target.checked;
                                      updateGlobalSetting('consider_fg_bg_depth', val);
                                    }}
                                    className="w-3.5 h-3.5 rounded-sm border-zinc-850 bg-zinc-950 text-yellow-500 accent-yellow-500"
                                  />
                                  <span>Consider Foreground/Background Depth (ประเมินความลึกหน้า/หลังมาสก์)</span>
                                </label>
                              </div>
                            </div>
                          </div>
                        )}

                        {isGlobalSectionVisible('outputSetting', 'Output & Export Settings', 'pipeline') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">📤 Output & Export Settings</h4>
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-pixel">Default Export Format (TXT)</label>
                                <select 
                                  value={settingsDefaultTxtMode}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    updateGlobalSetting('default_txt_mode', val);
                                  }}
                                  className="w-full p-2.5 text-xs rounded-lg text-slate-100 focus:outline-none input-glass cursor-pointer font-sans"
                                >
                                  <option value="both">Both (ข้อความสแกนคู่คำแปล)</option>
                                  <option value="translation">Translation (คำแปลเท่านั้น)</option>
                                  <option value="ocr">OCR (คำสแกนเท่านั้น)</option>
                                </select>
                              </div>

                            </div>
                          </div>
                        )}

                        {/* WORKSPACE DIRECTORIES */}
                        {isGlobalSectionVisible('workspace_dirs', 'Workspace Directories', 'workspace_dirs') && (
                          <div className="flex flex-col gap-4 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">📂 Default Workspace Directories</h4>
                            
                            <div className="flex flex-col gap-4">
                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 font-pixel">Default Load Project Path (โฟลเดอร์โครงการเริ่มต้น)</label>
                                <div className="flex gap-2">
                                  <input 
                                    type="text" 
                                    placeholder="ยังไม่ได้กำหนดโฟลเดอร์เริ่มต้น (ไม่มีการกรอกค่า)"
                                    value={defaultLoadProjectPath}
                                    onChange={(e) => setDefaultLoadProjectPath(e.target.value)}
                                    className="flex-1 p-2 text-xs rounded bg-zinc-950 border border-zinc-800 text-slate-200 focus:outline-none focus:border-yellow-500/50"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => handleBrowseFolder('load')}
                                    className="px-3.5 py-1.5 bg-zinc-900 border border-zinc-800 text-[10px] text-amber-400 hover:bg-zinc-800 rounded font-pixel cursor-pointer"
                                  >
                                    Browse...
                                  </button>
                                </div>
                              </div>

                              <div>
                                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 font-pixel">Default Save OCR Path (โฟลเดอร์บันทึกไฟล์สแกนหลัก)</label>
                                <div className="flex gap-2">
                                  <input 
                                    type="text" 
                                    placeholder="เลือกโฟลเดอร์เพื่อบันทึกไฟล์ส่งออกโดยตรง"
                                    value={defaultSaveOcrPath}
                                    onChange={(e) => setDefaultSaveOcrPath(e.target.value)}
                                    className="flex-1 p-2 text-xs rounded bg-zinc-950 border border-zinc-800 text-slate-200 focus:outline-none focus:border-yellow-500/50"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => handleBrowseFolder('save')}
                                    className="px-3.5 py-1.5 bg-zinc-900 border border-zinc-800 text-[10px] text-amber-400 hover:bg-zinc-800 rounded font-pixel cursor-pointer"
                                  >
                                    Browse...
                                  </button>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 3. KEYBOARD SHORTCUTS */}
                        {isGlobalSectionVisible('keyboard_shortcuts', 'Custom Keyboard Shortcuts', 'keyboard_shortcuts') && (
                          <div className="flex flex-col gap-3.5 bg-zinc-900/25 p-4.5 rounded-lg border border-zinc-900/60 shadow-sm animate-slide-up">
                            <h4 className="font-bold text-amber-400 tracking-wider font-pixel text-[10px] uppercase border-b border-zinc-900 pb-1.5">⌨️ Custom Keyboard Shortcuts</h4>
                            
                            <div className="flex justify-between items-center mb-1">
                              <span className="text-[9px] text-slate-500 font-sans">คลิกที่คีย์ลัดเพื่อทำการผูกปุ่มลัดคีย์บอร์ดใหม่</span>
                              <button
                                type="button"
                                onClick={() => {
                                  resetKeyBindings();
                                  showToast("กู้คืนคีย์ลัดเริ่มต้นทั้งหมดแล้ว", "success");
                                }}
                                className="px-2.5 py-1 bg-zinc-900 border border-zinc-800 text-[10px] text-amber-400 hover:bg-zinc-800 rounded font-pixel cursor-pointer"
                              >
                                Reset to Defaults
                              </button>
                            </div>
                            <div className="grid grid-cols-1 gap-2 bg-zinc-950/40 p-4 rounded border border-zinc-900 max-h-[220px] overflow-y-auto">
                              {shortcutDefinitions.map(def => (
                                <div key={def.id} className="flex justify-between items-center py-1 border-b border-zinc-900/50 last:border-none">
                                  <span className="text-slate-300 font-sans text-xs">{def.label}</span>
                                  <div className="flex items-center gap-1.5">
                                    {[0, 1, 2].map(slot => {
                                      const values = (keyBindings[def.id] || '').split('|').map(value => value.trim()).filter(Boolean);
                                      const activeKey = `${def.id}:${slot}`;
                                      return <button key={slot} type="button" onClick={() => setActiveBindingAction(activeKey)} className={`min-w-16 px-2 py-1 text-[9px] font-mono border rounded transition-all cursor-pointer ${activeBindingAction === activeKey ? 'bg-yellow-500/20 border-yellow-500/50 text-amber-400 animate-pulse' : 'bg-zinc-900 border-zinc-800 text-slate-400 hover:border-yellow-400/30 hover:text-yellow-400'}`}>
                                        {activeBindingAction === activeKey ? 'Press...' : values[slot] || `+ Key ${slot + 1}`}
                                      </button>;
                                    })}
                                    {(keyBindings[def.id] && keyBindings[def.id] !== def.defaultKey) && (
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setKeyBinding(def.id, def.defaultKey);
                                          showToast("กู้คืนคีย์ลัดมาตรฐานแล้ว", "info");
                                        }}
                                        className="text-[10px] text-slate-500 hover:text-red-400 transition-colors p-0.5"
                                        title="Reset to default key"
                                      >
                                        ✕
                                      </button>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    );
                  })()}

                </div>
              </div>

            </div>

          </div>
        </div>
      )}{/* STYLE PRESETS MODAL */}
      {showMultiPageStyleModal && activeProject && (() => {
        const query = multiPageSearch.trim().toLocaleLowerCase();
        const rows = activeProject.pages.flatMap(page =>
          page.text_blocks.map(block => ({ page, block }))
        ).filter(({ page, block }) => {
          if (multiPageFilter !== 'all' && page.id !== multiPageFilter) return false;
          if (!query) return true;
          return `${page.page_number} ${block.block_index} ${block.source_text} ${block.translation} ${block.font_family}`
            .toLocaleLowerCase().includes(query);
        });
        const selectVisible = () => setMultiPageSelectedIds(previous => {
          const next = new Set(previous);
          rows.forEach(({ block }) => next.add(block.id));
          return next;
        });
        return (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/85 p-5 backdrop-blur-sm animate-fade-in font-sans">
            <div className="flex h-[88vh] w-[min(1180px,96vw)] flex-col overflow-hidden rounded-lg border border-yellow-500/25 bg-[#0b0b0e] shadow-2xl">
              <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950 px-5 py-4">
                <div>
                  <h2 className="font-pixel text-sm font-bold uppercase tracking-wider text-yellow-400">Multi-page Font Editor</h2>
                  <p className="mt-1 text-[11px] text-slate-500">เลือก Layer จากหลายหน้า แล้วใช้ Template หรือแก้เฉพาะค่าที่ต้องการ ค่าเดิมแสดงในตารางด้านล่าง</p>
                </div>
                <button onClick={() => setShowMultiPageStyleModal(false)} className="rounded border border-zinc-800 px-3 py-2 text-xs text-slate-400 hover:border-red-500/40 hover:text-red-400 cursor-pointer">✕ Close</button>
              </div>

              <div className="grid grid-cols-5 gap-3 border-b border-zinc-800 bg-zinc-950/70 p-4">
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Template
                  <select value={multiPageTemplateKey} onChange={event => setMultiPageTemplateKey(event.target.value)} className="mt-1.5 w-full rounded border border-zinc-800 bg-zinc-900 p-2 text-xs text-slate-200">
                    <option value="">Keep current template</option>
                    {Object.entries(stylePresets).map(([key, template]) => <option key={key} value={key}>{template.name}</option>)}
                  </select>
                </label>
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Font Family
                  <select value={multiPageFontFamily} onChange={event => setMultiPageFontFamily(event.target.value)} className="mt-1.5 w-full rounded border border-zinc-800 bg-zinc-900 p-2 text-xs text-slate-200">
                    <option value="">Keep each current font</option>
                    {systemFonts.map(font => <option key={font} value={font}>{font}</option>)}
                  </select>
                </label>
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Font Size
                  <input value={multiPageFontSize} onChange={event => setMultiPageFontSize(event.target.value)} inputMode="decimal" placeholder="Keep current" className="mt-1.5 w-full rounded border border-zinc-800 bg-zinc-900 p-2 text-xs text-slate-200" />
                </label>
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Text Color
                  <div className="mt-1.5 flex gap-2">
                    <input type="color" value={/^#[0-9a-f]{6}$/i.test(multiPageColor) ? multiPageColor : '#111111'} onChange={event => setMultiPageColor(event.target.value)} className="h-8 w-10 rounded border border-zinc-800 bg-zinc-900" />
                    <input value={multiPageColor} onChange={event => setMultiPageColor(event.target.value)} placeholder="Keep" className="min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-900 px-2 text-xs text-slate-200" />
                  </div>
                </label>
                <div className="grid grid-cols-2 gap-2 text-[9px] font-bold uppercase tracking-wider text-slate-500">
                  <label>Bold<select value={multiPageBold} onChange={event => setMultiPageBold(event.target.value as 'keep' | 'on' | 'off')} className="mt-1.5 w-full rounded border border-zinc-800 bg-zinc-900 p-2 text-xs text-slate-200"><option value="keep">Keep</option><option value="on">On</option><option value="off">Off</option></select></label>
                  <label>Italic<select value={multiPageItalic} onChange={event => setMultiPageItalic(event.target.value as 'keep' | 'on' | 'off')} className="mt-1.5 w-full rounded border border-zinc-800 bg-zinc-900 p-2 text-xs text-slate-200"><option value="keep">Keep</option><option value="on">On</option><option value="off">Off</option></select></label>
                </div>
              </div>

              <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
                <select value={multiPageFilter} onChange={event => setMultiPageFilter(event.target.value)} className="rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-slate-300">
                  <option value="all">All pages</option>
                  {activeProject.pages.map(page => <option key={page.id} value={page.id}>Page {page.page_number} · {page.text_blocks.length} layers</option>)}
                </select>
                <input value={multiPageSearch} onChange={event => setMultiPageSearch(event.target.value)} placeholder="Search source, translation, font…" className="min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-slate-200" />
                <button onClick={selectVisible} className="rounded border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-[10px] font-bold text-yellow-400 cursor-pointer">Select visible ({rows.length})</button>
                <button onClick={() => setMultiPageSelectedIds(new Set())} className="rounded border border-zinc-800 px-3 py-2 text-[10px] text-slate-400 cursor-pointer">Clear</button>
              </div>

              <div className="min-h-0 flex-1 overflow-auto">
                <div className="sticky top-0 z-10 grid grid-cols-[44px_80px_70px_minmax(180px,1fr)_170px_80px_90px] gap-2 border-b border-zinc-800 bg-zinc-950 px-4 py-2 text-[8px] font-bold uppercase tracking-wider text-slate-500">
                  <span></span><span>Page</span><span>Layer</span><span>Text</span><span>Current Font</span><span>Size</span><span>Style</span>
                </div>
                {rows.map(({ page, block }) => {
                  const checked = multiPageSelectedIds.has(block.id);
                  return <label key={block.id} className={`grid grid-cols-[44px_80px_70px_minmax(180px,1fr)_170px_80px_90px] items-center gap-2 border-b border-zinc-900 px-4 py-2.5 text-xs cursor-pointer ${checked ? 'bg-yellow-500/[0.06]' : 'hover:bg-zinc-900/40'}`}>
                    <input type="checkbox" checked={checked} onChange={() => setMultiPageSelectedIds(previous => { const next = new Set(previous); checked ? next.delete(block.id) : next.add(block.id); return next; })} className="h-4 w-4 accent-yellow-500" />
                    <span className="font-pixel text-[9px] text-yellow-500">Page {page.page_number}</span>
                    <span className="text-slate-400">#{block.block_index + 1}</span>
                    <span className="truncate text-slate-200" title={`${block.source_text} → ${block.translation}`}>{block.translation?.trim() || block.source_text?.trim() || '(empty)'}</span>
                    <span className="truncate text-slate-300" title={block.font_family}>{block.font_family}</span>
                    <span className="font-mono text-slate-300">{effectiveFontSize(block)} px</span>
                    <span className="text-[10px] text-slate-500">{block.bold ? 'Bold' : 'Regular'}{block.italic ? ' · Italic' : ''}<span className="ml-1 inline-block h-2.5 w-2.5 rounded-full border border-zinc-700" style={{ backgroundColor: block.color_hex }} /></span>
                  </label>;
                })}
                {rows.length === 0 && <div className="p-12 text-center text-sm text-slate-500">ไม่พบ Layer ตามตัวกรอง</div>}
              </div>

              <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-950 px-5 py-4">
                <span className="text-xs text-slate-400">Selected <strong className="text-yellow-400">{multiPageSelectedIds.size}</strong> layers across project</span>
                <button disabled={multiPageSelectedIds.size === 0 || isSavingBlocks} onClick={applyMultiPageStyle} className="rounded bg-yellow-500 px-5 py-2.5 text-xs font-bold text-black hover:bg-yellow-400 disabled:opacity-40 cursor-pointer">Apply to selected layers</button>
              </div>
            </div>
          </div>
        );
      })()}

      {showPresetsModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in font-sans">
          <div className="w-[500px] p-6.5 rounded-sm border border-zinc-800 bg-zinc-950 shadow-2xl relative overflow-hidden text-slate-100 flex flex-col max-h-[80vh]">
            <div className="absolute top-[-30%] left-[-30%] w-[60%] h-[60%] bg-yellow-500/5 rounded-full filter blur-[40px] pointer-events-none" />
            
            <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2 z-10 relative font-pixel uppercase tracking-wider">
              🎨 Style Presets & Typography Templates
            </h3>

            <div className="flex-1 overflow-y-auto pr-1 flex flex-col gap-4 z-10 relative mb-4">
              {/* Save current block style as preset */}
              {selectedBlock ? (
                <div className="bg-zinc-900/40 border border-zinc-900 p-3 rounded-sm flex flex-col gap-2.5">
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider font-pixel">Save Current Typography Preset</span>
                  <div className="flex gap-2">
                    <input 
                      type="text" 
                      placeholder="Preset Name (e.g. SFX, Bubble, Title)..."
                      value={newPresetName}
                      onChange={(e) => setNewPresetName(e.target.value)}
                      className="flex-1 p-2 text-xs rounded-sm text-white focus:outline-none input-glass border border-zinc-800 bg-zinc-900 font-bold"
                    />
                    <button
                      onClick={async () => {
                        if (!newPresetName.trim()) {
                          showToast("Please enter a preset name", "error");
                          return;
                        }
                        await savePreset(newPresetName.trim(), templateFromBlock(newPresetName.trim(), selectedBlock));
                        setNewPresetName('');
                        showToast(`Saved preset "${newPresetName}"`, 'success');
                      }}
                      className="px-3 py-1.5 text-xs font-bold bg-yellow-500 text-black border border-yellow-600 rounded-sm hover:bg-amber-400 transition-all cursor-pointer font-pixel shadow-[2px_2px_0_#000]"
                    >
                      Save Preset
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-[11px] text-slate-500 italic p-3 border border-dashed border-zinc-800 rounded-sm bg-zinc-900/10">
                  Select a textbox on the canvas to save its current style as a template preset.
                </div>
              )}

              {/* List existing presets */}
              <div className="flex flex-col gap-2.5">
                <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider font-pixel">Available Presets</span>
                <div className="flex flex-col gap-2 divide-y divide-zinc-900 max-h-60 overflow-y-auto pr-1 font-sans">
                  {Object.entries(stylePresets).map(([name, style]) => (
                    <div key={name} className="flex items-center justify-between gap-3 py-2 text-xs font-sans">
                      <div className="flex flex-1 flex-col gap-1 min-w-0">
                        <span className="font-extrabold text-slate-200">{name}</span>
                        <span className="text-[10px] text-slate-500">
                          {style.font_stack.join(' → ')} / {style.min_font_size}–{style.max_font_size}px / <span style={{ color: style.color_hex }} className="font-mono">{style.color_hex}</span> {style.bold && '• Bold'} {style.italic && '• Italic'}
                        </span>
                        <select
                          value={style.font_stack[0] || ''}
                          aria-label={`Font for ${name}`}
                          title="เลือกฟอนต์จากเครื่อง"
                          onChange={(event) => {
                            const font = event.target.value;
                            const fontStack = [font];
                            setStylePresets(current => ({
                              ...current,
                              [name]: { ...current[name], font_stack: fontStack },
                            }));
                          }}
                          onBlur={() => void persistTemplates(stylePresets)}
                          className="w-full p-1.5 text-[10px] rounded-sm text-slate-300 bg-zinc-900 border border-zinc-800 focus:border-yellow-500 focus:outline-none"
                        >
                          {systemFonts.map(font => (
                            <option key={font} value={font}>{font}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex gap-2">
                        {selectedBlock && (
                          <button
                            onClick={async () => {
                              await applyTextTemplate(style);
                            }}
                            className="px-2.5 py-1 text-[10px] font-bold border border-zinc-800 text-yellow-500 hover:border-yellow-500 bg-zinc-900/60 hover:bg-zinc-900 transition-all rounded-sm cursor-pointer font-pixel uppercase tracking-wider"
                          >
                            Apply
                          </button>
                        )}
                        <button
                          onClick={() => {
                            if (window.confirm(`Delete preset "${name}"?`)) {
                              void deletePreset(name);
                              showToast(`Deleted preset "${name}"`, 'info');
                            }
                          }}
                          className="p-1 text-slate-500 hover:text-rose-400 hover:bg-zinc-900 rounded-sm transition-all cursor-pointer"
                          title="Delete Preset"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {Object.keys(stylePresets).length === 0 && (
                    <div className="text-xs text-slate-500 italic py-4 text-center">
                      No presets saved yet.
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-end border-t border-zinc-900 pt-4 shrink-0 font-pixel">
              <button 
                onClick={() => setShowPresetsModal(false)}
                className="px-4.5 py-2 text-xs font-bold rounded-sm bg-zinc-900 border border-zinc-800 text-slate-300 hover:bg-zinc-850 hover:text-amber-400 transition-all shadow-inner"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Preview Modal */}
      {showImportPreview && importPreviewData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl w-[95%] max-w-[1200px] h-[85vh] max-h-[90vh] flex flex-col p-6 gap-4">
            <div className="flex items-center justify-between shrink-0">
              <h2 className="text-base font-bold text-white font-pixel">📋 ตรวจสอบไฟล์คำแปลก่อนนำเข้า</h2>
              <button
                onClick={() => { setShowImportPreview(false); setImportPreviewData(null); setImportPreviewFile(null); }}
                className="text-slate-400 hover:text-white text-xl cursor-pointer"
              >✕</button>
            </div>

            {/* Summary Bar */}
            <div className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg p-3 shrink-0">
              <span className="text-[10px] font-pixel font-bold text-slate-400">FORMAT: <span className="text-yellow-400">{importPreviewData.format || 'auto'}</span></span>
              <div className="h-4 w-px bg-zinc-700" />
              <span className="text-[10px] font-bold text-emerald-400">✓ {importPreviewData.summary?.ok || 0} สำเร็จ</span>
              <span className="text-[10px] font-bold text-amber-400">⚠ {importPreviewData.summary?.warning || 0} เตือน</span>
              <span className="text-[10px] font-bold text-rose-400">✕ {importPreviewData.summary?.error || 0} ผิดพลาด</span>
              <span className="text-[10px] font-bold text-slate-500">⊘ {importPreviewData.summary?.skip || 0} ข้าม</span>
            </div>

            {!importPreviewData.success && importPreviewData.errors?.length > 0 && (
              <div className="bg-rose-950/50 border border-rose-500/30 rounded-lg p-3 text-xs text-rose-300 shrink-0">
                {importPreviewData.errors.join('; ')}
              </div>
            )}

            {/* Records Table */}
            <div className="flex-1 overflow-y-auto border border-zinc-800 rounded-lg">
              <table className="w-full text-xs table-fixed">
                <thead className="sticky top-0 bg-zinc-900 text-[9px] font-pixel uppercase tracking-wider text-slate-400 z-10">
                  <tr>
                    <th className="px-3 py-3 text-left w-12">
                      <input
                        type="checkbox"
                        checked={
                          importPreviewData.preview_records.filter((r: any) => r.status !== 'error' && r.status !== 'skip').length > 0 &&
                          importPreviewData.preview_records
                            .filter((r: any) => r.status !== 'error' && r.status !== 'skip')
                            .every((r: any) => !excludedLines.has(r.line_number))
                        }
                        onChange={(e) => {
                          const checked = e.target.checked;
                          setExcludedLines(prev => {
                            const next = new Set(prev);
                            importPreviewData.preview_records.forEach((r: any) => {
                              if (r.status !== 'error' && r.status !== 'skip') {
                                if (checked) {
                                  next.delete(r.line_number);
                                } else {
                                  next.add(r.line_number);
                                }
                              }
                            });
                            return next;
                          });
                        }}
                        className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
                        title="เลือกทั้งหมด / ไม่เลือกทั้งหมด"
                      />
                    </th>
                    <th className="px-3 py-3 text-left w-14">#</th>
                    <th className="px-3 py-3 text-left w-20">Layer</th>
                    <th className="px-3 py-3 text-left w-24">สถานะ</th>
                    <th className="px-3 py-3 text-left w-[30%]">คำต้นฉบับ</th>
                    <th className="px-3 py-3 text-left w-[30%]">คำแปล</th>
                    <th className="px-3 py-3 text-left w-[30%]">หมายเหตุ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                  {(importPreviewData.preview_records || []).map((rec: any, idx: number) => (
                    <tr key={idx} className={`${
                      rec.status === 'error' ? 'bg-rose-950/20' :
                      rec.status === 'warning' ? 'bg-amber-950/20' :
                      rec.status === 'skip' ? 'bg-zinc-900/20 opacity-50' :
                      ''
                    }`}>
                      <td className="px-3 py-3">
                        <input
                          type="checkbox"
                          disabled={rec.status === 'error' || rec.status === 'skip'}
                          checked={!excludedLines.has(rec.line_number)}
                          onChange={() => {
                            setExcludedLines(prev => {
                              const next = new Set(prev);
                              if (next.has(rec.line_number)) {
                                next.delete(rec.line_number);
                              } else {
                                next.add(rec.line_number);
                              }
                              return next;
                            });
                          }}
                          className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                        />
                      </td>
                      <td className="px-3 py-3 text-slate-500 font-mono">{rec.line_number}</td>
                      <td className="px-3 py-3 text-yellow-500/80 font-mono">{rec.block_index ? `#${rec.block_index}` : '—'}</td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          rec.status === 'ok' ? 'bg-emerald-500/20 text-emerald-400' :
                          rec.status === 'warning' ? 'bg-amber-500/20 text-amber-400' :
                          rec.status === 'error' ? 'bg-rose-500/20 text-rose-400' :
                          'bg-zinc-800 text-slate-500'
                        }`}>{
                          rec.status === 'ok' ? '✓' :
                          rec.status === 'warning' ? '⚠' :
                          rec.status === 'error' ? '✕' : '⊘'
                        }</span>
                      </td>
                      <td className="px-3 py-3 text-slate-400 font-sans break-words whitespace-pre-wrap leading-relaxed align-top" title={rec.source_text}>{rec.source_text || '—'}</td>
                      <td className="px-3 py-3 text-slate-200 font-sans break-words whitespace-pre-wrap leading-relaxed align-top">
                        <div>{rec.translation}</div>
                        {rec.semantic_role_label && (
                          <span
                            className="inline-flex mt-1.5 px-1.5 py-0.5 rounded-sm border border-cyan-500/30 bg-cyan-500/10 text-[9px] font-bold text-cyan-300"
                            title={`AI semantic role: ${rec.semantic_role}`}
                          >
                            {`{${rec.semantic_role_label}}`}
                          </span>
                        )}
                      </td>
                      <td className={`px-3 py-3 font-sans break-words whitespace-pre-wrap leading-relaxed align-top ${rec.status === 'error' ? 'text-rose-400/90' : rec.status === 'warning' ? 'text-amber-450/90' : 'text-slate-500'}`}>{rec.message || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 shrink-0">
              <button
                onClick={() => { setShowImportPreview(false); setImportPreviewData(null); setImportPreviewFile(null); }}
                className="px-4 py-2 text-xs font-bold bg-zinc-900 border border-zinc-800 text-slate-400 hover:text-white rounded-md cursor-pointer font-pixel"
              >
                ยกเลิก
              </button>
              <button
                onClick={handleConfirmImport}
                disabled={importPreviewData.preview_records.filter((r: any) => r.status !== 'error' && r.status !== 'skip' && !excludedLines.has(r.line_number)).length === 0}
                className="px-5 py-2 text-xs font-bold bg-yellow-500 text-black rounded-md hover:bg-yellow-400 disabled:opacity-30 cursor-pointer font-pixel shadow-[2px_2px_0_#000]"
              >
                ✓ นำเข้ารายการที่เลือก ({importPreviewData.preview_records.filter((r: any) => r.status !== 'error' && r.status !== 'skip' && !excludedLines.has(r.line_number)).length})
              </button>
            </div>
          </div>
        </div>
      )}

      <HotkeyModal isOpen={showHotkeyModal} onClose={() => setShowHotkeyModal(false)} />
      <AIProviderSettingsModal
        isOpen={showAIProviderSettingsModal}
        onClose={() => setShowAIProviderSettingsModal(false)}
        showToast={showToast}
      />
      <UpdateModal isOpen={isUpdateModalOpen} manifest={updateManifest} onClose={() => setIsUpdateModalOpen(false)} />
      <UpdateSuccessModal
        isOpen={isUpdateSuccessModalOpen}
        version={justUpdatedVersion || '0.4.0'}
        patchNotes={justUpdatedNotes}
        onClose={handleCloseUpdateSuccessModal}
      />

      {/* Floating Toast Notifications */}
      <div className="fixed top-6 right-6 z-50 flex flex-col gap-3 max-w-sm pointer-events-none font-sans">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`p-4 rounded-xl border backdrop-blur-md shadow-2xl flex items-center gap-3 pointer-events-auto animate-slide-in transition-all duration-300 ${
              toast.type === 'success'
                ? 'bg-emerald-950/85 border-emerald-500/30 text-emerald-200'
                : toast.type === 'error'
                  ? 'bg-rose-950/85 border-rose-500/30 text-rose-200'
                  : 'bg-slate-900/85 border-white/10 text-slate-200'
            }`}
          >
            <div className={`w-2 h-2 rounded-full ${
              toast.type === 'success' 
                ? 'bg-emerald-400 animate-pulse' 
                : toast.type === 'error' 
                  ? 'bg-rose-400 animate-pulse' 
                  : 'bg-yellow-400 animate-pulse'
            }`} />
            <span className="text-xs font-bold">{toast.message}</span>
          </div>
        ))}
      </div>

      {/* Action Debug Console Drawer (Matrix UI) */}
      <DebugConsoleDrawer />

    </div>
  );
};

export default App;
