import { create } from 'zustand';
import {
  applyBlockResponse,
  getPageMutationRevision,
  getMutationRevision,
  incrementPageMutationRevision,
  incrementMutationRevision,
  shouldAcceptPageResponse,
  shouldAcceptResponse,
} from '../utils/blockUpdateTracker';
import type { MinimalProjectState } from '../utils/blockUpdateTracker';
import { apiFetch, getApiBaseUrl } from '../api/runtime';
import {
  loadClientProjectProfiles,
  clientProfileToProjectSettings,
  CLIENT_PROFILES_STORAGE_KEY,
  ACTIVE_CLIENT_PROFILE_STORAGE_KEY,
} from '../utils/clientProfiles';

export interface TextBlock {
  id: string;
  page_id: string;
  block_index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation_deg: number;
  source_text: string;
  translation: string;
  font_family: string;
  font_size: number;
  color_hex: string;
  bold: boolean;
  italic: boolean;
  text_direction: 'horizontal' | 'vertical';
  text_align: 'left' | 'center' | 'right';
  balloon_type: 'bubble' | 'narrative' | 'sfx';
  confidence: number;
  extra_metadata: Record<string, any>;
  is_visible?: boolean;
  is_locked?: boolean;
  mask_type?: 'custom' | 'adaptive' | 'box';
  smart_x?: number;
  smart_y?: number;
  smart_width?: number;
  smart_height?: number;
  smart_mask_path?: string;
  stroke_color?: string;
  stroke_width?: number;
  line_spacing?: number;
  letter_spacing?: number;
  font_color?: string;
  direction?: 'horizontal' | 'vertical';
}

export interface Page {
  id: string;
  project_id: string;
  page_number: number;
  name: string;
  width: number;
  height: number;
  source_image_path: string;
  inpainted_image_path?: string;
  rendered_image_path?: string;
  status: string;
  text_blocks: TextBlock[];
}

export interface Project {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  created_at: string;
  updated_at: string;
  settings: Record<string, any>;
  pages: Page[];
}

export interface TMSuggestion {
  id: string;
  source_text: string;
  translation: string;
  score: number;
  frequency: number;
  is_exact: boolean;
  project_id: string | null;
}

export interface CanvasRenderCapture {
  pageId: string;
  blob: Blob;
  backgroundKind: 'clean' | 'source';
}

interface ProjectState {
  projects: Project[];
  activeProject: Project | null;
  activePage: Page | null;
  selectedBlock: TextBlock | null;
  selectedBlocks: TextBlock[];
  statusMessage: string;
  isProcessing: boolean;
  tmSuggestions: TMSuggestion[];
  undoStack: any[];
  redoStack: any[];
  zoomLevel: number | null;
  setZoomLevel: (zoom: number | null) => void;
  
  // API Call Actions
  fetchProjects: () => Promise<void>;
  createProject: (name: string, sourceLang: string, targetLang: string, settings?: Record<string, unknown>) => Promise<Project>;
  selectProject: (projectId: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  oversizeWarningData: { folderPath: string; scanReport: any } | null;
  setOversizeWarningData: (data: { folderPath: string; scanReport: any } | null) => void;
  smartSplitAndOpen: (folderPath: string, options: { splitHeight: number; enforceWidth: number | null; backupOriginal: boolean }) => Promise<any>;
  browseFolderProject: (defaultLoadPath?: string, targetFolderPath?: string, initialSettings?: Record<string, unknown>) => Promise<any>;
  
  uploadPage: (projectId: string, pageNumber: number, file: File) => Promise<void>;
  selectPage: (pageId: string) => Promise<void>;
  deletePage: (pageId: string) => Promise<void>;
  
  createBlock: (pageId: string, blockData: Partial<TextBlock>, skipHistory?: boolean) => Promise<TextBlock | null>;
  updateBlock: (blockId: string, updateData: Partial<TextBlock>, skipHistory?: boolean) => Promise<void>;
  syncAutoFitFontSize: (blockId: string, fontSize: number) => void;
  updateBlocksBulk: (updates: Array<{ blockId: string; data: Partial<TextBlock> }>) => Promise<void>;
  deleteBlock: (blockId: string, skipHistory?: boolean) => Promise<void>;
  deleteBlocks: (blockIds: string[], skipHistory?: boolean) => Promise<void>;
  isSavingBlocks: boolean;
  uploadPageMask: (pageId: string, maskImageBlob: Blob) => Promise<void>;
  
  fetchTMSuggestions: (text: string, projectId?: string) => Promise<void>;
  clearTMSuggestions: () => void;
  setStatus: (message: string, isProcessing?: boolean) => void;
  getCanvasMaskBlob: (() => Promise<Blob | null>) | null;
  getCanvasRenderCapture: ((forceTranslated?: boolean) => Promise<CanvasRenderCapture | null>) | null;
  canvasRenderPageId: string | null;
  updateProjectSettings: (projectId: string, settings: Record<string, any>) => Promise<void>;

  undo: () => Promise<void>;
  redo: () => Promise<void>;
  mergeBlocks: (pageId: string, blockIds: string[]) => Promise<void>;
  reorderBlockZIndex: (pageId: string, blockId: string, action: 'bring_to_front' | 'bring_forward' | 'send_backward' | 'send_to_back') => Promise<void>;
  copiedStyle: Record<string, any> | null;
  copyBlockStyle: (blockId: string) => void;
  pasteBlockStyle: (blockId: string) => Promise<void>;
  splitBlock: (blockId: string, direction: 'horizontal' | 'vertical') => Promise<void>;
  deleteAndInpaintBlock: (blockId: string) => Promise<void>;
  
  keyBindings: Record<string, string>;
  setKeyBinding: (action: string, keys: string) => void;
  resetKeyBindings: () => void;
  
  translationEngine: 'google' | 'gemini';
  geminiApiKey: string;
  setTranslationEngine: (engine: 'google' | 'gemini') => void;
  setGeminiApiKey: (key: string) => void;
  
  defaultLoadProjectPath: string;
  defaultSaveOcrPath: string;
  setDefaultLoadProjectPath: (path: string) => void;
  setDefaultSaveOcrPath: (path: string) => void;
}

export const API_BASE = getApiBaseUrl();
let projectSettingsRequestRevision = 0;

// Map to accumulate pending block updates and track their timeout IDs
const pendingBlockUpdates = new Map<
  string,
  {
    timeoutId: any;
    accumData: any;
    originalBeforeBlock: any;
    mutationRevision: number;
    saveTracked: boolean;
  }
>();
// Serialize server mutations that touch the same block. Without this queue, a
// slower single-block PUT can commit after a newer bulk preset request and make
// the preset appear to apply briefly before reverting.
const blockMutationChains = new Map<string, Promise<void>>();
let activeBlockSaveCount = 0;

const beginBlockSave = () => {
  activeBlockSaveCount += 1;
  useProjectStore.setState({ isSavingBlocks: true });
};

const endBlockSave = () => {
  activeBlockSaveCount = Math.max(0, activeBlockSaveCount - 1);
  useProjectStore.setState({ isSavingBlocks: activeBlockSaveCount > 0 });
};

const enqueueBlockMutation = (
  blockIds: string[],
  operation: () => Promise<void>
): Promise<void> => {
  const uniqueBlockIds = Array.from(new Set(blockIds));
  const predecessors = uniqueBlockIds
    .map((blockId) => blockMutationChains.get(blockId))
    .filter((promise): promise is Promise<void> => Boolean(promise));
  const run = Promise.all(predecessors.map((promise) => promise.catch(() => undefined)))
    .then(operation);

  uniqueBlockIds.forEach((blockId) => blockMutationChains.set(blockId, run));
  const cleanup = () => {
    uniqueBlockIds.forEach((blockId) => {
      if (blockMutationChains.get(blockId) === run) {
        blockMutationChains.delete(blockId);
      }
    });
  };
  run.then(cleanup, cleanup);
  return run;
};

export const flushPendingBlockUpdates = async (specificBlockId?: string) => {
  const promises: Promise<void>[] = [];
  const entries = Array.from(pendingBlockUpdates.entries());
  
  for (const [id, val] of entries) {
    if (specificBlockId && id !== specificBlockId) continue;
    
    clearTimeout(val.timeoutId);
    pendingBlockUpdates.delete(id);
    const reqMutationRev = val.mutationRevision;

    const promise = (async () => {
      try {
        const res = await apiFetch(`${API_BASE}/blocks/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(val.accumData)
        });
        if (!res.ok) throw new Error("Failed to flush update");
        const updatedBlock = await res.json();

        if (!shouldAcceptResponse(id, reqMutationRev)) {
          console.warn("Discarding stale typesetting response for block:", id);
          return;
        }

        const store = useProjectStore.getState();
        const updatedState = applyBlockResponse(
          store as unknown as MinimalProjectState,
          id,
          updatedBlock as TextBlock
        );
        useProjectStore.setState(updatedState as unknown as Partial<ProjectState>);

        const targetPage = store.activeProject?.pages.find(page => page.text_blocks.some(block => block.id === id))
          || store.activePage;
        if (targetPage) {
          // Push to history
          const before: Partial<TextBlock> = {};
          const after: Partial<TextBlock> = {};
          Object.keys(val.accumData).forEach((key) => {
            const k = key as keyof TextBlock;
            if (val.originalBeforeBlock[k] !== val.accumData[k]) {
              (before as any)[k] = val.originalBeforeBlock[k];
              (after as any)[k] = val.accumData[k];
            }
          });

          if (Object.keys(before).length > 0) {
            useProjectStore.setState(state => ({
              undoStack: [...state.undoStack, {
                type: 'update',
                payload: { pageId: targetPage.id, blockId: id, before, after }
              }],
              redoStack: []
            }));
          }
        }
      } catch (err) {
        console.error("Failed to flush pending update for block:", id, err);
      } finally {
        if (val.saveTracked) endBlockSave();
      }
    })();
    promises.push(promise);
  }
  await Promise.all(promises);

  // Also drain any inflight geometry (non-text) mutation chains so that
  // coordinates are persisted in the database before a pipeline step reads them.
  const inflightChains = Array.from(blockMutationChains.values());
  if (inflightChains.length > 0) {
    await Promise.all(inflightChains.map(p => p.catch(() => undefined)));
  }
};

/** Silently discard all pending block updates without sending PUT requests.
 *  Used after OCR to prevent stale debounced saves
 *  from overwriting fresh results fetched from the server. */
export const discardPendingBlockUpdates = () => {
  for (const [, val] of pendingBlockUpdates.entries()) {
    if (val.timeoutId !== null) {
      clearTimeout(val.timeoutId);
    }
    if (val.saveTracked) endBlockSave();
  }
  pendingBlockUpdates.clear();
};

export const DEFAULT_KEY_BINDINGS: Record<string, string> = {
  findBalloon: 'Ctrl+F',
  selectMode: 'V',
  drawBoxMode: 'M',
  brushMode: 'B',
  deleteBlock: 'Delete',
  deselectBlock: 'Escape',
  cycleNextBlock: 'Tab',
  cyclePrevBlock: 'Shift+Tab',
  exportOcrTxt: 'Ctrl+Shift+S',
  undo: 'Ctrl+Z',
  redo: 'Ctrl+Y|Ctrl+Shift+Z',
};

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  activeProject: null,
  activePage: null,
  selectedBlock: null,
  selectedBlocks: [],
  keyBindings: (() => {
    try {
      const stored = localStorage.getItem('houmi_key_bindings');
      return stored ? JSON.parse(stored) : { ...DEFAULT_KEY_BINDINGS };
    } catch {
      return { ...DEFAULT_KEY_BINDINGS };
    }
  })(),
  setKeyBinding: (action, keys) => {
    const updated = { ...get().keyBindings, [action]: keys };
    set({ keyBindings: updated });
    try {
      localStorage.setItem('houmi_key_bindings', JSON.stringify(updated));
    } catch (e) {
      console.warn(e);
    }
  },
  resetKeyBindings: () => {
    set({ keyBindings: { ...DEFAULT_KEY_BINDINGS } });
    try {
      localStorage.removeItem('houmi_key_bindings');
    } catch (e) {
      console.warn(e);
    }
  },
  translationEngine: (() => {
    try {
      const stored = localStorage.getItem('houmi_translation_engine');
      return (stored === 'gemini' || stored === 'google') ? stored : 'google';
    } catch {
      return 'google';
    }
  })(),
  geminiApiKey: (() => {
    try {
      return localStorage.getItem('houmi_gemini_api_key') || '';
    } catch {
      return '';
    }
  })(),
  setTranslationEngine: (engine) => {
    set({ translationEngine: engine });
    try {
      localStorage.setItem('houmi_translation_engine', engine);
    } catch (e) {
      console.warn(e);
    }
  },
  setGeminiApiKey: (key) => {
    set({ geminiApiKey: key });
    try {
      localStorage.setItem('houmi_gemini_api_key', key);
    } catch (e) {
      console.warn(e);
    }
  },
  defaultLoadProjectPath: (() => {
    try {
      return localStorage.getItem('houmi_default_load_project_path') || '';
    } catch {
      return '';
    }
  })(),
  defaultSaveOcrPath: (() => {
    try {
      return localStorage.getItem('houmi_default_save_ocr_path') || '';
    } catch {
      return '';
    }
  })(),
  setDefaultLoadProjectPath: (path) => {
    set({ defaultLoadProjectPath: path });
    try {
      localStorage.setItem('houmi_default_load_project_path', path);
    } catch (e) {
      console.warn(e);
    }
  },
  setDefaultSaveOcrPath: (path) => {
    set({ defaultSaveOcrPath: path });
    try {
      localStorage.setItem('houmi_default_save_ocr_path', path);
    } catch (e) {
      console.warn(e);
    }
  },
  statusMessage: 'Ready',
  isProcessing: false,
  tmSuggestions: [],
  getCanvasMaskBlob: null,
  getCanvasRenderCapture: null,
  canvasRenderPageId: null,
  undoStack: [],
  redoStack: [],
  zoomLevel: null,
  isSavingBlocks: false,

  setZoomLevel: (zoom) => set({ zoomLevel: zoom }),
  setStatus: (message, isProcessing = false) => set({ statusMessage: message, isProcessing }),


  fetchProjects: async () => {
    try {
      const res = await apiFetch(`${API_BASE}/projects`);
      if (!res.ok) throw new Error("Failed to fetch projects");
      const data = await res.json();
      set({ projects: data });
    } catch (err: any) {
      set({ statusMessage: `Error: ${err.message}` });
    }
  },

  createProject: async (name, sourceLang, targetLang, settings = {}) => {
    get().setStatus('Creating project...', true);
    const res = await apiFetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, source_lang: sourceLang, target_lang: targetLang, settings })
    });
    if (!res.ok) {
      get().setStatus('Failed to create project', false);
      throw new Error("Failed to create project");
    }
    const newProj = await res.json();
    await get().fetchProjects();
    get().setStatus('Project created', false);
    return newProj;
  },

  selectProject: async (projectId) => {
    await flushPendingBlockUpdates();
    get().setStatus('Loading project...', true);
    try {
      const res = await apiFetch(`${API_BASE}/projects/${projectId}`);
      if (!res.ok) throw new Error("Failed to fetch project details");
      const project = await res.json();
      
      const pagesRes = await apiFetch(`${API_BASE}/projects/${projectId}/pages`);
      const pages = pagesRes.ok ? await pagesRes.json() : [];
      
      project.pages = pages;
      set({ activeProject: project, activePage: pages[0] || null, selectedBlock: null, selectedBlocks: [], zoomLevel: null });
      if (pages && pages.length > 0 && pages[0]?.id) {
        try {
          await get().selectPage(pages[0].id);
        } catch (e) {
          console.warn("Failed to auto-select first page:", e);
        }
      }
      get().setStatus('Project loaded', false);
    } catch (err: any) {
      get().setStatus(`Error loading project: ${err.message}`, false);
    }
  },

  deleteProject: async (projectId) => {
    get().setStatus('Deleting project...', true);
    try {
      const res = await apiFetch(`${API_BASE}/projects/${projectId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error("Failed to delete project");
      await get().fetchProjects();
      if (get().activeProject?.id === projectId) {
        set({ activeProject: null, activePage: null, selectedBlock: null });
      }
      get().setStatus('Project deleted', false);
    } catch (err: any) {
      get().setStatus(`Error: ${err.message}`, false);
    }
  },

  updateProjectSettings: async (projectId, settings) => {
    const requestRevision = ++projectSettingsRequestRevision;
    try {
      const res = await apiFetch(`${API_BASE}/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings })
      });
      if (!res.ok) throw new Error("Failed to update project settings");
      const updatedProj = await res.json();

      // A slower settings response must not overwrite a newer user choice.
      if (requestRevision !== projectSettingsRequestRevision) return;
      const currentProject = get().activeProject;
      if (currentProject?.id === projectId) {
        updatedProj.pages = currentProject.pages;
        set({ activeProject: updatedProj });
      }
    } catch (err: any) {
      if (requestRevision === projectSettingsRequestRevision) {
        console.error("Error saving project settings:", err);
      }
      throw err;
    }
  },
  
  oversizeWarningData: null,
  setOversizeWarningData: (data) => set({ oversizeWarningData: data }),

  smartSplitAndOpen: async (folderPath, options) => {
    get().setStatus('✂️ Splitting webtoon images...', true);
    try {
      const splitRes = await apiFetch(`${API_BASE}/projects/smart-split`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder_path: folderPath,
          split_height: options.splitHeight,
          enforce_width: options.enforceWidth,
          backup_original: options.backupOriginal,
        }),
      });

      if (!splitRes.ok) {
        const errData = await splitRes.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to split images");
      }

      set({ oversizeWarningData: null });
      get().setStatus('Loading split project...', true);
      // Now open the freshly split folder with allow_oversize: true
      return await get().browseFolderProject(undefined, folderPath, { force_fresh: true, allow_oversize: true });
    } catch (err: any) {
      get().setStatus(`Error during smart split: ${err.message}`, false);
      throw err;
    }
  },
  
  browseFolderProject: async (defaultLoadPath, targetFolderPath, initialSettings = {}) => {
    get().setStatus('Browsing local folder...', true);
    try {
      let url = `${API_BASE}/projects/browse-folder`;
      const params = new URLSearchParams();
      if (defaultLoadPath) params.append('default_load_path', defaultLoadPath);
      if (targetFolderPath) params.append('folder_path', targetFolderPath);
      if (params.toString()) {
        url += `?${params.toString()}`;
      }

      // Inject Global Baseline (source_lang, ocr_engine, active client profile)
      const globalSourceLang = localStorage.getItem('houmi_source_lang') || 'ko';
      const globalOcrEngine = localStorage.getItem('houmi_ocr_engine') || 'ppocrv5';
      const activeClientId = localStorage.getItem(ACTIVE_CLIENT_PROFILE_STORAGE_KEY) || localStorage.getItem('houmi_active_client_profile_id') || '';
      const profiles = loadClientProjectProfiles(localStorage.getItem(CLIENT_PROFILES_STORAGE_KEY));
      const activeProfile = profiles.find(p => p.id === activeClientId) || profiles[0];
      const clientSettings = activeProfile ? clientProfileToProjectSettings(activeProfile) : {};

      const mergedSettings = {
        source_lang: globalSourceLang,
        ocr_engine: globalOcrEngine,
        ...clientSettings,
        ...initialSettings,
      };

      const res = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mergedSettings),
      });
      if (res.status === 400) {
        // Cancelled or invalid folder
        get().setStatus('Ready', false);
        return null;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to import folder");
      }
      
      const proj = await res.json();
      if (proj && proj.status === 'oversize_warning') {
        get().setStatus('⚠️ Oversize images detected', false);
        set({
          oversizeWarningData: {
            folderPath: proj.folder_path,
            scanReport: proj.scan_report,
          },
        });
        return proj;
      }

      set({ oversizeWarningData: null });
      await get().fetchProjects();
      await get().selectProject(proj.id);
      get().setStatus('Project loaded', false);
      return proj;
    } catch (err: any) {
      get().setStatus(`Error importing folder: ${err.message}`, false);
      throw err;
    }
  },

  uploadPage: async (projectId, pageNumber, file) => {
    get().setStatus(`Uploading page ${pageNumber}...`, true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await apiFetch(`${API_BASE}/projects/${projectId}/pages?page_number=${pageNumber}`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error("Upload failed");
      
      // Reload project pages
      if (get().activeProject?.id === projectId) {
        await get().selectProject(projectId);
      }
      get().setStatus('Upload completed', false);
    } catch (err: any) {
      get().setStatus(`Upload error: ${err.message}`, false);
    }
  },

  selectPage: async (pageId) => {
    await flushPendingBlockUpdates();
    const requestPageRevision = getPageMutationRevision(pageId);
    get().setStatus('Loading page...', false);
    try {
      const res = await apiFetch(`${API_BASE}/pages/${pageId}`);
      if (!res.ok) throw new Error("Failed to load page");
      const page = await res.json();

      // Fetch mask status for all blocks on this page
      try {
        const maskRes = await apiFetch(`${API_BASE}/pages/${pageId}/mask-status`);
        if (maskRes.ok) {
          const maskData = await maskRes.json();
          const maskMap = new Map(
            maskData.statuses.map((s: any) => [s.block_id, s.mask_type])
          );
          // Enrich blocks with mask_type
          page.text_blocks = page.text_blocks.map((block: TextBlock) => ({
            ...block,
            mask_type: maskMap.get(block.id) || 'box',
          }));
        }
      } catch (maskErr) {
        console.warn('Failed to fetch mask status:', maskErr);
      }

      if (!shouldAcceptPageResponse(pageId, requestPageRevision)) {
        console.warn('Discarding stale page response after a local block mutation:', pageId);
        get().setStatus('Page kept current', false);
        return;
      }

      const activeProj = get().activeProject;
      const updatedPages = activeProj ? activeProj.pages.map(p => p.id === page.id ? page : p) : [];
      set({
        activePage: page,
        activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
        selectedBlock: null,
        selectedBlocks: []
      });

      // Prefetch adjacent pages for instant page switching (0ms delay)
      try {
        if (activeProj && activeProj.pages && activeProj.pages.length > 1) {
          const idx = activeProj.pages.findIndex(p => p.id === page.id);
          if (idx !== -1) {
            const adjacent = [];
            if (idx > 0) adjacent.push(activeProj.pages[idx - 1]);
            if (idx < activeProj.pages.length - 1) adjacent.push(activeProj.pages[idx + 1]);

            adjacent.forEach(adjPage => {
              const previewImg = new Image();
              previewImg.src = `/api/pages/${adjPage.id}/preview`;
            });
          }
        }
      } catch (prefetchErr) {
        console.warn('Adjacent page prefetch failed silently:', prefetchErr);
      }

      get().setStatus('Page loaded', false);
    } catch (err: any) {
      get().setStatus(`Error loading page: ${err.message}`, false);
    }
  },

  deletePage: async (pageId) => {
    get().setStatus('Deleting page...', true);
    try {
      const res = await apiFetch(`${API_BASE}/pages/${pageId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error("Failed to delete page");
      
      const activeProjId = get().activeProject?.id;
      if (activeProjId) {
        await get().selectProject(activeProjId);
      }
      get().setStatus('Page deleted', false);
    } catch (err: any) {
      get().setStatus(`Error: ${err.message}`, false);
    }
  },

  createBlock: async (pageId, blockData, skipHistory = false) => {
    await flushPendingBlockUpdates();
    get().setStatus('Adding text block...', false);
    try {
      const res = await apiFetch(`${API_BASE}/pages/${pageId}/blocks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          block_index: blockData.block_index !== undefined ? blockData.block_index : 0,
          x: blockData.x || 0,
          y: blockData.y || 0,
          width: blockData.width || 100,
          height: blockData.height || 50,
          rotation_deg: blockData.rotation_deg || 0.0,
          source_text: blockData.source_text || '',
          translation: blockData.translation || '',
          font_family: blockData.font_family || 'NotoSansThai',
          font_size: blockData.font_size || 20,
          color_hex: blockData.color_hex || '#000000',
          bold: blockData.bold || false,
          italic: blockData.italic || false,
          text_direction: blockData.text_direction || 'horizontal',
          text_align: blockData.text_align || 'center',
          balloon_type: blockData.balloon_type || 'bubble',
          extra_metadata: blockData.extra_metadata || {}
        })
      });
      if (!res.ok) throw new Error("Failed to create text block");
      const newBlock = await res.json();
      
      // Update local state
      const page = get().activePage;
      if (page && page.id === pageId) {
        const updatedBlocks = [...page.text_blocks, newBlock];
        const newPage = { ...page, text_blocks: updatedBlocks };
        const activeProj = get().activeProject;
        const updatedPages = activeProj ? activeProj.pages.map(p => p.id === page.id ? newPage : p) : [];
        set({ 
          activePage: newPage, 
          activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
          selectedBlock: newBlock,
          selectedBlocks: [newBlock]
        });
      }
      
      if (!skipHistory) {
        set(state => ({
          undoStack: [...state.undoStack, {
            type: 'create',
            payload: { pageId, blockId: newBlock.id, blockData: newBlock }
          }],
          redoStack: []
        }));
      }

      get().setStatus('Block added', false);
      return newBlock;
    } catch (err: any) {
      get().setStatus(`Error: ${err.message}`, false);
      return null;
    }
  },

  updateBlock: async (blockId, updateData, skipHistory = false) => {
    // 1. Find the block and its owner page across the entire project if not on activePage
    const activeProj = get().activeProject;
    let targetPage = get().activePage;
    let beforeBlock = targetPage?.text_blocks.find(b => b.id === blockId);

    if (!beforeBlock && activeProj) {
      for (const p of activeProj.pages) {
        const b = p.text_blocks.find(x => x.id === blockId);
        if (b) {
          targetPage = p;
          beforeBlock = b;
          break;
        }
      }
    }

    if (targetPage && beforeBlock) {
      incrementPageMutationRevision(targetPage.id);
      const invalidatesTypesetting = 'translation' in updateData || 'source_text' in updateData;
      const optimisticMetadata = invalidatesTypesetting
        ? {
            ...(beforeBlock.extra_metadata || {}),
            typesetting_spec: beforeBlock.extra_metadata?.typesetting_spec
              ? { ...beforeBlock.extra_metadata.typesetting_spec, layout_status: 'stale' }
              : undefined,
          }
        : beforeBlock.extra_metadata;
      const updatedBlock = {
        ...beforeBlock,
        ...updateData,
        ...(invalidatesTypesetting ? { extra_metadata: optimisticMetadata } : {}),
      };
      const updatedBlocks = targetPage.text_blocks.map(b => b.id === blockId ? updatedBlock : b);
      const newPage = { ...targetPage, text_blocks: updatedBlocks };
      const updatedPages = activeProj ? activeProj.pages.map(p => p.id === targetPage.id ? newPage : p) : [];
      
      const isCurrentPage = targetPage.id === get().activePage?.id;
      set({ 
        activePage: isCurrentPage ? newPage : get().activePage,
        activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
        selectedBlock: get().selectedBlock?.id === blockId ? updatedBlock : get().selectedBlock,
        selectedBlocks: get().selectedBlocks.map(b => b.id === blockId ? updatedBlock : b)
      });
      // 2. Debounce and buffer all block updates (geometry, text, styling, fonts).
      // Instant optimistic update has already applied to Zustand state in RAM (0ms).
      // Flushes to backend after 300ms of user inactivity (or immediately when switching pages/saving).
      const currentMutationRev = incrementMutationRevision(blockId);

      let entry = pendingBlockUpdates.get(blockId);
      if (entry) {
        if (entry.timeoutId !== null) {
          clearTimeout(entry.timeoutId);
        }
        entry.accumData = { ...entry.accumData, ...updateData };
        entry.mutationRevision = currentMutationRev;
      } else {
        if (beforeBlock) {
          beginBlockSave();
          entry = {
            timeoutId: null,
            accumData: { ...updateData },
            originalBeforeBlock: { ...beforeBlock },
            mutationRevision: currentMutationRev,
            saveTracked: true,
          };
          pendingBlockUpdates.set(blockId, entry);
        }
      }

      if (entry) {
        entry.timeoutId = setTimeout(async () => {
          await flushPendingBlockUpdates(blockId);
        }, 300);
      }
    }
  },

  syncAutoFitFontSize: (blockId, fontSize) => {
    if (!Number.isFinite(fontSize) || fontSize <= 0) return;

    set((state) => {
      const patchBlock = (block: TextBlock): TextBlock => {
        if (block.id !== blockId) return block;
        const metadata = block.extra_metadata || {};
        const spec = metadata.typesetting_spec;
        if (block.font_size === fontSize && (!spec || spec.font_size === fontSize)) {
          return block;
        }
        const previousSpecSize = Number(spec?.font_size);
        const previousLineHeight = Number(spec?.line_height);
        const lineHeightRatio = previousSpecSize > 0 && previousLineHeight > 0
          ? previousLineHeight / previousSpecSize
          : Number(metadata.line_height_ratio || 1.2);
        return {
          ...block,
          font_size: fontSize,
          extra_metadata: {
            ...metadata,
            manual_font_size: null,
            font_size_mode: 'auto',
            typesetting_spec: spec
              ? { ...spec, font_size: fontSize, line_height: fontSize * lineHeightRatio }
              : spec,
          },
        };
      };
      const patchPage = (page: Page): Page => ({
        ...page,
        text_blocks: page.text_blocks.map(patchBlock),
      });

      return {
        activePage: state.activePage ? patchPage(state.activePage) : null,
        activeProject: state.activeProject
          ? { ...state.activeProject, pages: state.activeProject.pages.map(patchPage) }
          : null,
        selectedBlock: state.selectedBlock ? patchBlock(state.selectedBlock) : null,
        selectedBlocks: state.selectedBlocks.map(patchBlock),
      };
    });
  },

  updateBlocksBulk: async (updates) => {
    if (updates.length === 0) return;
    beginBlockSave();
    try {
      await flushPendingBlockUpdates();
      const pagesTouched = new Set<string>();
      const currentProject = get().activeProject;
      for (const { blockId } of updates) {
        const owner = currentProject?.pages.find(page =>
          page.text_blocks.some(block => block.id === blockId)
        );
        if (owner) pagesTouched.add(owner.id);
      }
      pagesTouched.forEach(incrementPageMutationRevision);
      const revisions = new Map(updates.map(({ blockId }) => [blockId, incrementMutationRevision(blockId)]));
      const updateMap = new Map(updates.map(({ blockId, data }) => [blockId, data]));
      const patchState = (state: ProjectState, replacements?: Map<string, TextBlock>) => {
        const patchBlock = (block: TextBlock): TextBlock => {
          const replacement = replacements?.get(block.id);
          if (replacement) return replacement;
          const data = updateMap.get(block.id);
          return data ? { ...block, ...data } : block;
        };
        const patchPage = (page: Page): Page => ({ ...page, text_blocks: page.text_blocks.map(patchBlock) });
        const activePage = state.activePage ? patchPage(state.activePage) : null;
        const activeProject = state.activeProject
          ? { ...state.activeProject, pages: state.activeProject.pages.map(patchPage) }
          : null;
        return {
          activePage,
          activeProject,
          selectedBlock: state.selectedBlock ? patchBlock(state.selectedBlock) : null,
          selectedBlocks: state.selectedBlocks.map(patchBlock),
        };
      };
      set((state) => patchState(state) as Partial<ProjectState>);
      
      await enqueueBlockMutation(updates.map(({ blockId }) => blockId), async () => {
        const response = await apiFetch(`${API_BASE}/blocks/bulk`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ updates: updates.map(({ blockId, data }) => ({ block_id: blockId, data })) }),
        });
        if (!response.ok) throw new Error('Failed to update selected blocks');
        const blocks = await response.json() as TextBlock[];
        const accepted = new Map(blocks
          .filter((block) => shouldAcceptResponse(block.id, revisions.get(block.id) || 0))
          .map((block) => [block.id, block]));
        set((state) => patchState(state, accepted) as Partial<ProjectState>);
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      get().setStatus(`Error: ${message}`, false);
      const pageId = get().activePage?.id;
      if (pageId) await get().selectPage(pageId);
    } finally {
      endBlockSave();
    }
  },

  deleteBlock: async (blockId, skipHistory = false) => {
    await flushPendingBlockUpdates();
    beginBlockSave();
    get().setStatus('Deleting text block...', false);
    try {
      const page = get().activePage;
      const blockToDelete = page?.text_blocks.find(b => b.id === blockId);
      if (page) incrementPageMutationRevision(page.id);
      incrementMutationRevision(blockId);

      await enqueueBlockMutation([blockId], async () => {
        const res = await apiFetch(`${API_BASE}/blocks/${blockId}`, { method: 'DELETE' });
        if (!res.ok && res.status !== 404) throw new Error("Failed to delete block");
      });
      
      if (page) {
        const updatedBlocks = page.text_blocks.filter(b => b.id !== blockId);
        const newPage = { ...page, text_blocks: updatedBlocks };
        const activeProj = get().activeProject;
        const updatedPages = activeProj ? activeProj.pages.map(p => p.id === page.id ? newPage : p) : [];
        
        const nextSelectedBlocks = get().selectedBlocks.filter(b => b.id !== blockId);
        const nextSelectedBlock = get().selectedBlock?.id === blockId 
          ? (nextSelectedBlocks[0] || null) 
          : get().selectedBlock;

        set({ 
          activePage: newPage, 
          activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
          selectedBlock: nextSelectedBlock,
          selectedBlocks: nextSelectedBlocks
        });
      }

      if (!skipHistory && blockToDelete) {
        set(state => ({
          undoStack: [...state.undoStack, {
            type: 'delete',
            payload: { pageId: blockToDelete.page_id, blockId, blockData: blockToDelete }
          }],
          redoStack: []
        }));
      }

      get().setStatus('Block deleted', false);
    } catch (err: any) {
      get().setStatus(`Error: ${err.message}`, false);
    } finally {
      endBlockSave();
    }
  },

  deleteBlocks: async (blockIds, skipHistory = false) => {
    if (blockIds.length === 0) return;
    await flushPendingBlockUpdates();
    beginBlockSave();
    get().setStatus('Deleting text blocks...', false);
    try {
      const page = get().activePage;
      const blocksToDelete = page?.text_blocks.filter(b => blockIds.includes(b.id)) || [];
      if (page) incrementPageMutationRevision(page.id);
      blockIds.forEach(incrementMutationRevision);

      await enqueueBlockMutation(blockIds, async () => {
        const promises = blockIds.map(id => apiFetch(`${API_BASE}/blocks/${id}`, { method: 'DELETE' }));
        const results = await Promise.all(promises);
        const failed = results.filter(res => !res.ok && res.status !== 404);
        if (failed.length > 0) throw new Error("Failed to delete some blocks");
      });

      if (page) {
        const updatedBlocks = page.text_blocks.filter(b => !blockIds.includes(b.id));
        const newPage = { ...page, text_blocks: updatedBlocks };
        const activeProj = get().activeProject;
        const updatedPages = activeProj ? activeProj.pages.map(p => p.id === page.id ? newPage : p) : [];
        set({
          activePage: newPage,
          activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
          selectedBlock: null,
          selectedBlocks: []
        });
      }

      if (!skipHistory && blocksToDelete.length > 0) {
        const undoActions = blocksToDelete.map(b => ({
          type: 'delete',
          payload: { pageId: b.page_id, blockId: b.id, blockData: b }
        }));
        const redoActions = blocksToDelete.map(b => ({
          type: 'delete',
          payload: { pageId: b.page_id, blockId: b.id }
        }));
        set(state => ({
          undoStack: [...state.undoStack, {
            type: 'composite',
            payload: { undoActions, redoActions }
          }],
          redoStack: []
        }));
      }

      get().setStatus('Blocks deleted', false);
    } catch (err: any) {
      get().setStatus(`Error: ${err.message}`, false);
    } finally {
      endBlockSave();
    }
  },

  undo: async () => {
    await flushPendingBlockUpdates();
    const { undoStack, redoStack } = get();
    if (undoStack.length === 0) return;

    const action = undoStack[undoStack.length - 1];
    const newUndoStack = undoStack.slice(0, -1);

    // Auto-navigate to page if action occurred on a different page
    const findPageId = (act: any): string | null => {
      if (act.payload?.pageId) return act.payload.pageId;
      if (act.type === 'composite' && act.payload.undoActions?.length > 0) {
        return findPageId(act.payload.undoActions[0]);
      }
      return null;
    };

    const targetPageId = findPageId(action);
    if (targetPageId && get().activePage?.id !== targetPageId) {
      await get().selectPage(targetPageId);
    }

    const executeAction = async (act: any) => {
      if (act.type === 'create') {
        await get().deleteBlock(act.payload.blockId, true);
      } else if (act.type === 'update') {
        await get().updateBlock(act.payload.blockId, act.payload.before, true);
      } else if (act.type === 'delete') {
        const newBlock = await get().createBlock(act.payload.pageId, act.payload.blockData, true);
        if (newBlock) {
          const oldId = act.payload.blockId;
          act.payload.blockId = newBlock.id;
          // Sync composite redoActions if applicable
          if (action.type === 'composite') {
            const redoAct = action.payload.redoActions.find((r: any) => r.payload.blockId === oldId);
            if (redoAct) {
              redoAct.payload.blockId = newBlock.id;
            }
          }
        }
      } else if (act.type === 'composite') {
        // Composite actions are undone in reverse order
        for (let i = act.payload.undoActions.length - 1; i >= 0; i--) {
          await executeAction(act.payload.undoActions[i]);
        }
      }
    };

    get().setStatus('Undoing last action...', false);
    try {
      await executeAction(action);
      set({
        undoStack: newUndoStack,
        redoStack: [...redoStack, action],
        selectedBlock: null,
        selectedBlocks: []
      });
      get().setStatus('Action undone', false);
    } catch (err: any) {
      get().setStatus(`Undo failed: ${err.message}`, false);
    }
  },

  redo: async () => {
    await flushPendingBlockUpdates();
    const { undoStack, redoStack } = get();
    if (redoStack.length === 0) return;

    const action = redoStack[redoStack.length - 1];
    const newRedoStack = redoStack.slice(0, -1);

    // Auto-navigate to page if action occurred on a different page
    const findPageId = (act: any): string | null => {
      if (act.payload?.pageId) return act.payload.pageId;
      if (act.type === 'composite' && act.payload.redoActions?.length > 0) {
        return findPageId(act.payload.redoActions[0]);
      }
      return null;
    };

    const targetPageId = findPageId(action);
    if (targetPageId && get().activePage?.id !== targetPageId) {
      await get().selectPage(targetPageId);
    }

    const executeAction = async (act: any) => {
      if (act.type === 'create') {
        const newBlock = await get().createBlock(act.payload.pageId, act.payload.blockData, true);
        if (newBlock) {
          const oldId = act.payload.blockId;
          act.payload.blockId = newBlock.id;
          // Sync composite undoActions if applicable
          if (action.type === 'composite') {
            const undoAct = action.payload.undoActions.find((u: any) => u.payload.blockId === oldId);
            if (undoAct) {
              undoAct.payload.blockId = newBlock.id;
            }
          }
        }
      } else if (act.type === 'update') {
        await get().updateBlock(act.payload.blockId, act.payload.after, true);
      } else if (act.type === 'delete') {
        await get().deleteBlock(act.payload.blockId, true);
      } else if (act.type === 'composite') {
        // Composite actions are redone in forward order
        for (const subAct of act.payload.redoActions) {
          await executeAction(subAct);
        }
      }
    };

    get().setStatus('Redoing last action...', false);
    try {
      await executeAction(action);
      set({
        undoStack: [...undoStack, action],
        redoStack: newRedoStack,
        selectedBlock: null,
        selectedBlocks: []
      });
      get().setStatus('Action redone', false);
    } catch (err: any) {
      get().setStatus(`Redo failed: ${err.message}`, false);
    }
  },

  mergeBlocks: async (pageId, blockIds) => {
    await flushPendingBlockUpdates();
    if (blockIds.length <= 1) return;
    get().setStatus('Merging text blocks...', false);
    
    try {
      const page = get().activePage;
      if (!page) return;

      const blocksToMerge = page.text_blocks.filter(b => blockIds.includes(b.id));
      if (blocksToMerge.length === 0) return;

      // 1. Calculate bounding box union
      let minX = Infinity, minY = Infinity;
      let maxX = -Infinity, maxY = -Infinity;
      
      blocksToMerge.forEach((b) => {
        if (b.x < minX) minX = b.x;
        if (b.y < minY) minY = b.y;
        if (b.x + b.width > maxX) maxX = b.x + b.width;
        if (b.y + b.height > maxY) maxY = b.y + b.height;
      });

      const width = maxX - minX;
      const height = maxY - minY;

      // 2. Sort blocks vertically to concatenate texts correctly
      const sortedBlocks = [...blocksToMerge].sort((a, b) => a.y - b.y);
      const combinedSource = sortedBlocks.map(b => b.source_text).filter(Boolean).join('\n');
      const combinedTranslation = sortedBlocks.map(b => b.translation).filter(Boolean).join('\n');

      // Use properties of the first block as base
      const baseBlock = sortedBlocks[0];

      // 3. Prepare undo/redo composite action history
      const undoActions: any[] = [];
      const redoActions: any[] = [];

      // Add all deletes to redo actions, and creates to undo actions
      blocksToMerge.forEach((b) => {
        redoActions.push({
          type: 'delete',
          payload: { pageId, blockId: b.id }
        });
        undoActions.push({
          type: 'delete', // undo a delete means recreate, but let's represent the individual recreations
          payload: { pageId, blockId: b.id, blockData: b }
        });
      });

      // 4. Delete the blocks (skip individual histories)
      for (const b of blocksToMerge) {
        await get().deleteBlock(b.id, true);
      }

      // 5. Create the merged block
      const mergedBlock = await get().createBlock(pageId, {
        block_index: baseBlock.block_index,
        x: minX,
        y: minY,
        width,
        height,
        source_text: combinedSource,
        translation: combinedTranslation,
        font_family: baseBlock.font_family,
        font_size: baseBlock.font_size,
        color_hex: baseBlock.color_hex,
        bold: baseBlock.bold,
        italic: baseBlock.italic,
        text_direction: baseBlock.text_direction,
        text_align: baseBlock.text_align,
        balloon_type: baseBlock.balloon_type,
        extra_metadata: baseBlock.extra_metadata || {}
      }, true);

      if (mergedBlock) {
        // Add create to redo actions, and delete to undo actions
        redoActions.push({
          type: 'create',
          payload: { pageId, blockId: mergedBlock.id, blockData: mergedBlock }
        });
        undoActions.unshift({ // delete of merged block should run first on undo
          type: 'create', // undo of a create is a delete, so executeAction will delete it
          payload: { pageId, blockId: mergedBlock.id }
        });

        // Push composite action to history
        set(state => ({
          undoStack: [...state.undoStack, {
            type: 'composite',
            payload: { undoActions, redoActions }
          }],
          redoStack: [],
          selectedBlock: mergedBlock,
          selectedBlocks: [mergedBlock]
        }));
      }

      get().setStatus('Blocks merged', false);
    } catch (err: any) {
      get().setStatus(`Merge failed: ${err.message}`, false);
    }
  },

  reorderBlockZIndex: async (pageId, blockId, action) => {
    await flushPendingBlockUpdates();
    const activeP = get().activePage;
    const page = activeP?.id === pageId ? activeP : get().activeProject?.pages.find(p => p.id === pageId);
    if (!page || !page.text_blocks || page.text_blocks.length <= 1) return;

    const ordered = [...page.text_blocks].sort((a, b) => a.block_index - b.block_index);
    const index = ordered.findIndex(b => b.id === blockId);
    if (index === -1) return;

    const newOrdered = [...ordered];
    const targetBlock = newOrdered[index];

    if (action === 'bring_to_front') {
      if (index === newOrdered.length - 1) return;
      newOrdered.splice(index, 1);
      newOrdered.push(targetBlock);
    } else if (action === 'bring_forward') {
      if (index === newOrdered.length - 1) return;
      newOrdered[index] = newOrdered[index + 1];
      newOrdered[index + 1] = targetBlock;
    } else if (action === 'send_backward') {
      if (index === 0) return;
      newOrdered[index] = newOrdered[index - 1];
      newOrdered[index - 1] = targetBlock;
    } else if (action === 'send_to_back') {
      if (index === 0) return;
      newOrdered.splice(index, 1);
      newOrdered.unshift(targetBlock);
    }

    const updates: Array<{ blockId: string; data: Partial<TextBlock> }> = [];
    const updatedBlocks = newOrdered.map((block, idx) => {
      if (block.block_index !== idx) {
        updates.push({ blockId: block.id, data: { block_index: idx } });
      }
      return { ...block, block_index: idx };
    });

    if (updates.length === 0) return;

    const newPage = { ...page, text_blocks: updatedBlocks };
    const activeProj = get().activeProject;
    const updatedPages = activeProj ? activeProj.pages.map(p => p.id === page.id ? newPage : p) : [];
    
    set({
      activePage: get().activePage?.id === page.id ? newPage : get().activePage,
      activeProject: activeProj ? { ...activeProj, pages: updatedPages } : null,
      selectedBlock: get().selectedBlock?.id === blockId ? (updatedBlocks.find(b => b.id === blockId) || get().selectedBlock) : get().selectedBlock,
      selectedBlocks: get().selectedBlocks.map(sb => updatedBlocks.find(b => b.id === sb.id) || sb)
    });

    await get().updateBlocksBulk(updates);
  },

  uploadPageMask: async (pageId, maskImageBlob) => {
    try {
      const formData = new FormData();
      formData.append('file', maskImageBlob, 'mask.png');
      const res = await apiFetch(`${API_BASE}/pages/${pageId}/mask`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error("Failed to upload manual mask");
    } catch (err: any) {
      console.error("Mask upload error:", err);
      get().setStatus(`Failed to save manual mask: ${err.message}`, false);
    }
  },

  fetchTMSuggestions: async (text, projectId) => {
    if (!text || !text.trim()) {
      set({ tmSuggestions: [] });
      return;
    }
    try {
      let url = `${API_BASE}/tm/suggest?text=${encodeURIComponent(text)}`;
      if (projectId) {
        url += `&project_id=${projectId}`;
      }
      const res = await apiFetch(url);
      if (!res.ok) throw new Error("Failed to fetch suggestions");
      const data = await res.json();
      set({ tmSuggestions: data.suggestions || [] });
    } catch (err: any) {
      console.error("Failed to fetch TM suggestions:", err);
    }
  },

  clearTMSuggestions: () => set({ tmSuggestions: [] }),

  copiedStyle: null,

  copyBlockStyle: (blockId: string) => {
    const page = get().activePage;
    const block = page?.text_blocks.find((b) => b.id === blockId);
    if (!block) return;
    const style: Record<string, any> = {
      font_family: block.font_family,
      font_size: block.font_size,
      color_hex: block.color_hex || block.font_color || '#000000',
      stroke_color: block.stroke_color,
      stroke_width: block.stroke_width,
      text_align: block.text_align,
      text_direction: block.text_direction || block.direction || 'horizontal',
      bold: block.bold,
      italic: block.italic,
      line_spacing: block.line_spacing,
      letter_spacing: block.letter_spacing,
    };
    set({ copiedStyle: style });
    get().setStatus('Text style copied', false);
  },

  pasteBlockStyle: async (blockId: string) => {
    const { copiedStyle } = get();
    if (!copiedStyle) return;
    await get().updateBlock(blockId, copiedStyle);
    get().setStatus('Text style applied', false);
  },

  splitBlock: async (blockId: string, direction: 'horizontal' | 'vertical') => {
    const page = get().activePage;
    const block = page?.text_blocks.find((b) => b.id === blockId);
    if (!page || !block) return;

    if (direction === 'horizontal') {
      const h1 = Math.max(10, Math.round(block.height / 2));
      const h2 = Math.max(10, block.height - h1);
      await get().updateBlock(block.id, { height: h1 });
      await get().createBlock(page.id, {
        x: block.x,
        y: block.y + h1,
        width: block.width,
        height: h2,
        font_family: block.font_family,
        font_size: block.font_size,
        color_hex: block.color_hex || block.font_color || '#000000',
        stroke_color: block.stroke_color,
        stroke_width: block.stroke_width,
        text_align: block.text_align,
        text_direction: block.text_direction || 'horizontal',
      });
    } else {
      const w1 = Math.max(10, Math.round(block.width / 2));
      const w2 = Math.max(10, block.width - w1);
      await get().updateBlock(block.id, { width: w1 });
      await get().createBlock(page.id, {
        x: block.x + w1,
        y: block.y,
        width: w2,
        height: block.height,
        font_family: block.font_family,
        font_size: block.font_size,
        color_hex: block.color_hex || block.font_color || '#000000',
        stroke_color: block.stroke_color,
        stroke_width: block.stroke_width,
        text_align: block.text_align,
        text_direction: block.text_direction || 'horizontal',
      });
    }
    get().setStatus(`Block split ${direction}ly`, false);
  },

  deleteAndInpaintBlock: async (blockId: string) => {
    const page = get().activePage;
    const block = page?.text_blocks.find((b) => b.id === blockId);
    if (!page || !block) return;

    try {
      await apiFetch(`${API_BASE}/pipeline/spot-heal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_id: page.id,
          bbox: [Math.round(block.x), Math.round(block.y), Math.round(block.width), Math.round(block.height)],
        }),
      });
    } catch (e) {
      console.warn('Spot inpaint before delete failed:', e);
    }
    await get().deleteBlock(blockId);
  }
}));
