import { create } from 'zustand';

export type ActionCategory = 
  | 'UI_INTERACTION'
  | 'CANVAS_ACTION'
  | 'AI_PIPELINE'
  | 'PROJECT_LIFECYCLE'
  | 'NETWORK_API'
  | 'HOTKEY'
  | 'SYSTEM_ERROR';

export interface ActionLogItem {
  id: string;
  timestamp: number;
  category: ActionCategory;
  name: string;
  payload?: any;
  durationMs?: number;
  status?: 'success' | 'warning' | 'error' | 'pending';
  error?: string;
}

interface DebugState {
  isOpen: boolean;
  activeTab: 'actions' | 'state' | 'telemetry';
  isPaused: boolean;
  actions: ActionLogItem[];
  filterCategory: ActionCategory | 'ALL';
  searchQuery: string;
  metrics: {
    totalActions: number;
    errorCount: number;
    canvasMutations: number;
    networkCalls: number;
  };
  
  // Actions
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  setActiveTab: (tab: 'actions' | 'state' | 'telemetry') => void;
  setPaused: (paused: boolean) => void;
  setFilterCategory: (category: ActionCategory | 'ALL') => void;
  setSearchQuery: (query: string) => void;
  
  addAction: (action: Omit<ActionLogItem, 'id' | 'timestamp'>) => void;
  clearActions: () => void;
  exportActionsJson: () => string;
  exportActionsLog: () => string;
}

const MAX_ACTION_HISTORY = 2000;

export const useDebugStore = create<DebugState>((set, get) => ({
  isOpen: false,
  activeTab: 'actions',
  isPaused: false,
  actions: [],
  filterCategory: 'ALL',
  searchQuery: '',
  metrics: {
    totalActions: 0,
    errorCount: 0,
    canvasMutations: 0,
    networkCalls: 0,
  },

  toggleDrawer: () => set((state) => ({ isOpen: !state.isOpen })),
  openDrawer: () => set({ isOpen: true }),
  closeDrawer: () => set({ isOpen: false }),
  setActiveTab: (activeTab) => set({ activeTab }),
  setPaused: (isPaused) => set({ isPaused }),
  setFilterCategory: (filterCategory) => set({ filterCategory }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),

  addAction: (item) => {
    if (get().isPaused) return;

    const newAction: ActionLogItem = {
      ...item,
      id: `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      timestamp: Date.now(),
    };

    set((state) => {
      const isError = item.status === 'error' || item.category === 'SYSTEM_ERROR';
      const isCanvas = item.category === 'CANVAS_ACTION';
      const isNetwork = item.category === 'NETWORK_API';

      const nextActions = [newAction, ...state.actions];
      if (nextActions.length > MAX_ACTION_HISTORY) {
        nextActions.length = MAX_ACTION_HISTORY;
      }

      return {
        actions: nextActions,
        metrics: {
          totalActions: state.metrics.totalActions + 1,
          errorCount: state.metrics.errorCount + (isError ? 1 : 0),
          canvasMutations: state.metrics.canvasMutations + (isCanvas ? 1 : 0),
          networkCalls: state.metrics.networkCalls + (isNetwork ? 1 : 0),
        },
      };
    });
  },

  clearActions: () => set({
    actions: [],
    metrics: {
      totalActions: 0,
      errorCount: 0,
      canvasMutations: 0,
      networkCalls: 0,
    },
  }),

  exportActionsJson: () => {
    const { actions, metrics } = get();
    return JSON.stringify({
      version: '1.0.5',
      exportTimestamp: new Date().toISOString(),
      metrics,
      actions,
    }, null, 2);
  },

  exportActionsLog: () => {
    const { actions } = get();
    return actions.map((a) => {
      const time = new Date(a.timestamp).toISOString();
      const dur = a.durationMs != null ? ` [${a.durationMs}ms]` : '';
      const err = a.error ? ` ERR: ${a.error}` : '';
      const payloadStr = a.payload ? ` | PAYLOAD: ${JSON.stringify(a.payload)}` : '';
      return `[${time}] [${a.category}] [${a.status || 'info'}] ${a.name}${dur}${err}${payloadStr}`;
    }).join('\n');
  },
}));
