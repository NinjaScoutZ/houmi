import React, { useState } from 'react';
import { 
  Bug, X, Trash2, Download, Copy, Play, Pause, Search, Filter, 
  Activity, Layers, Database, Radio, Terminal, ChevronRight, AlertCircle, 
  CheckCircle2, Clock, ShieldAlert
} from 'lucide-react';
import { useDebugStore, type ActionCategory, type ActionLogItem } from '../stores/debugStore';

export const DebugConsoleDrawer: React.FC = () => {
  const {
    isOpen,
    isPaused,
    activeTab,
    actions,
    filterCategory,
    searchQuery,
    metrics,
    closeDrawer,
    setPaused,
    setActiveTab,
    setFilterCategory,
    setSearchQuery,
    clearActions,
    exportActionsJson,
    exportActionsLog,
  } = useDebugStore();

  const [selectedAction, setSelectedAction] = useState<ActionLogItem | null>(null);
  const [copiedNotification, setCopiedNotification] = useState(false);

  if (!isOpen) return null;

  const filteredActions = actions.filter((item) => {
    if (filterCategory !== 'ALL' && item.category !== filterCategory) return false;
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      item.name.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      (item.error && item.error.toLowerCase().includes(q)) ||
      (item.payload && JSON.stringify(item.payload).toLowerCase().includes(q))
    );
  });

  const handleCopyJson = () => {
    const json = exportActionsJson();
    navigator.clipboard.writeText(json);
    setCopiedNotification(true);
    setTimeout(() => setCopiedNotification(false), 2000);
  };

  const handleDownloadLog = () => {
    const text = exportActionsLog();
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `houmi-debug-actions-${Date.now()}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getCategoryBadge = (category: ActionCategory) => {
    switch (category) {
      case 'CANVAS_ACTION':
        return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
      case 'AI_PIPELINE':
        return 'bg-purple-500/15 text-purple-300 border-purple-500/30';
      case 'NETWORK_API':
        return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
      case 'PROJECT_LIFECYCLE':
        return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
      case 'HOTKEY':
        return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
      case 'SYSTEM_ERROR':
        return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
      default:
        return 'bg-zinc-800 text-zinc-300 border-zinc-700';
    }
  };

  const getStatusIcon = (item: ActionLogItem) => {
    if (item.status === 'error' || item.category === 'SYSTEM_ERROR') {
      return <AlertCircle size={14} className="text-rose-400 shrink-0" />;
    }
    if (item.status === 'warning') {
      return <ShieldAlert size={14} className="text-amber-400 shrink-0" />;
    }
    return <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />;
  };

  return (
    <aside 
      className="fixed bottom-0 left-0 right-0 z-50 h-[420px] bg-[#0c0c12]/95 border-t border-amber-500/30 backdrop-blur-xl shadow-2xl flex flex-col font-sans select-none animate-slide-up text-slate-200"
      aria-label="Action Debug Console"
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/80 bg-zinc-950/80 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 font-mono font-bold text-amber-400 text-xs">
            <Bug size={16} className="text-amber-400 animate-pulse" />
            <span>ACTION DEBUG MATRIX</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300">
              v1.0.5
            </span>
          </div>

          {/* Metrics summary */}
          <div className="flex items-center gap-2 pl-4 border-l border-zinc-800 text-[10px] font-mono text-slate-400">
            <span className="flex items-center gap-1">
              <Activity size={12} className="text-amber-400" /> Total: <strong className="text-slate-200">{metrics.totalActions}</strong>
            </span>
            <span className="flex items-center gap-1">
              <Layers size={12} className="text-cyan-400" /> Canvas: <strong className="text-slate-200">{metrics.canvasMutations}</strong>
            </span>
            <span className="flex items-center gap-1">
              <Database size={12} className="text-emerald-400" /> API: <strong className="text-slate-200">{metrics.networkCalls}</strong>
            </span>
            {metrics.errorCount > 0 && (
              <span className="flex items-center gap-1 text-rose-400 font-bold bg-rose-500/10 px-1.5 py-0.5 rounded border border-rose-500/20">
                <AlertCircle size={12} /> {metrics.errorCount} Errors
              </span>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* Pause / Resume */}
          <button
            type="button"
            onClick={() => setPaused(!isPaused)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-bold border transition-colors cursor-pointer ${
              isPaused 
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30' 
                : 'bg-zinc-900 text-slate-300 border-zinc-800 hover:bg-zinc-800'
            }`}
          >
            {isPaused ? <Play size={12} /> : <Pause size={12} />}
            {isPaused ? 'Resume' : 'Pause'}
          </button>

          {/* Copy JSON */}
          <button
            type="button"
            onClick={handleCopyJson}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium bg-zinc-900 text-slate-300 border border-zinc-800 hover:bg-zinc-800 hover:text-amber-300 transition-colors cursor-pointer"
            title="Copy all actions as JSON"
          >
            <Copy size={12} />
            {copiedNotification ? 'Copied!' : 'Copy JSON'}
          </button>

          {/* Export Log */}
          <button
            type="button"
            onClick={handleDownloadLog}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium bg-zinc-900 text-slate-300 border border-zinc-800 hover:bg-zinc-800 hover:text-amber-300 transition-colors cursor-pointer"
            title="Export actions to .log file"
          >
            <Download size={12} />
            Export Log
          </button>

          {/* Clear */}
          <button
            type="button"
            onClick={clearActions}
            className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
            title="Clear Action History"
          >
            <Trash2 size={15} />
          </button>

          {/* Close */}
          <button
            type="button"
            onClick={closeDrawer}
            className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close Debug Console (Ctrl+Shift+D or F12)"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Filter / Search Tooling Bar */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-zinc-850 bg-zinc-950/40 shrink-0 gap-3">
        {/* Category Filters */}
        <div className="flex items-center gap-1 overflow-x-auto text-[10.5px]">
          {(['ALL', 'UI_INTERACTION', 'CANVAS_ACTION', 'AI_PIPELINE', 'PROJECT_LIFECYCLE', 'NETWORK_API', 'HOTKEY', 'SYSTEM_ERROR'] as const).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setFilterCategory(cat)}
              className={`px-2 py-0.5 rounded-full border transition-colors cursor-pointer font-mono whitespace-nowrap ${
                filterCategory === cat
                  ? 'bg-amber-500 text-black font-bold border-amber-400'
                  : 'bg-zinc-900 text-slate-400 border-zinc-800 hover:bg-zinc-800 hover:text-slate-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Search Bar */}
        <div className="relative flex items-center w-64">
          <Search size={12} className="absolute left-2.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search action, payload, error..."
            className="w-full pl-7 pr-3 py-0.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/60 font-mono"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2 text-slate-500 hover:text-slate-300"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Body: 2-Column Split (Action Timeline vs JSON Payload Inspector) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Action Stream (Scrollable) */}
        <div className="flex-1 overflow-y-auto divide-y divide-zinc-900 font-mono text-[11px] custom-scrollbar">
          {filteredActions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-1.5 py-12">
              <Radio size={20} className="text-slate-600 animate-pulse" />
              <p>No actions logged yet in this filter.</p>
              <p className="text-[10px]">Interactions on Canvas, AI Pipeline, and Network are captured in real-time.</p>
            </div>
          ) : (
            filteredActions.map((item) => (
              <div
                key={item.id}
                onClick={() => setSelectedAction(item)}
                className={`flex items-center justify-between px-4 py-2 cursor-pointer transition-colors ${
                  selectedAction?.id === item.id 
                    ? 'bg-amber-500/10 border-l-2 border-amber-400' 
                    : 'hover:bg-zinc-900/60'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {getStatusIcon(item)}
                  <span className="text-slate-500 text-[10px] shrink-0">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border shrink-0 ${getCategoryBadge(item.category)}`}>
                    {item.category}
                  </span>
                  <span className="font-semibold text-slate-200 truncate">
                    {item.name}
                  </span>
                  {item.durationMs != null && (
                    <span className="text-[10px] text-zinc-500 flex items-center gap-0.5 shrink-0">
                      <Clock size={10} /> {item.durationMs}ms
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {item.error && (
                    <span className="text-rose-400 text-[10px] truncate max-w-xs font-sans">
                      {item.error}
                    </span>
                  )}
                  <ChevronRight size={14} className="text-zinc-600" />
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right: Selected Action Payload Inspector */}
        <div className="w-[420px] border-l border-zinc-800/80 bg-zinc-950/60 flex flex-col overflow-hidden shrink-0">
          <div className="px-3 py-2 border-b border-zinc-850 bg-zinc-900/40 flex items-center justify-between text-[11px] font-mono">
            <span className="font-bold text-amber-300 flex items-center gap-1.5">
              <Terminal size={13} /> Action Payload & Details
            </span>
            {selectedAction && (
              <span className="text-[10px] text-slate-500">
                ID: {selectedAction.id}
              </span>
            )}
          </div>

          <div className="flex-1 p-3 overflow-y-auto font-mono text-[11px] text-slate-300 custom-scrollbar">
            {selectedAction ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-[10px] bg-zinc-900/60 p-2.5 rounded border border-zinc-850">
                  <div>
                    <span className="text-slate-500 block">Category:</span>
                    <strong className="text-slate-200">{selectedAction.category}</strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Timestamp:</span>
                    <strong className="text-slate-200">{new Date(selectedAction.timestamp).toISOString()}</strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Status:</span>
                    <strong className={selectedAction.status === 'error' ? 'text-rose-400' : 'text-emerald-400'}>
                      {selectedAction.status || 'success'}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Execution Time:</span>
                    <strong className="text-slate-200">{selectedAction.durationMs != null ? `${selectedAction.durationMs}ms` : 'Instant'}</strong>
                  </div>
                </div>

                {selectedAction.error && (
                  <div className="bg-rose-950/40 border border-rose-500/40 p-2.5 rounded text-rose-300 text-xs">
                    <strong className="block text-rose-400 font-bold mb-1">Error Message:</strong>
                    {selectedAction.error}
                  </div>
                )}

                {selectedAction.payload ? (
                  <div>
                    <span className="text-slate-500 text-[10px] block mb-1">Payload JSON:</span>
                    <pre className="bg-black/70 p-2.5 rounded border border-zinc-800 text-[10.5px] overflow-x-auto text-emerald-300 whitespace-pre-wrap">
                      {JSON.stringify(selectedAction.payload, null, 2)}
                    </pre>
                  </div>
                ) : (
                  <p className="text-slate-500 text-[10px] italic">No payload parameters attached to this action.</p>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-1 text-center py-12">
                <Terminal size={20} className="text-slate-600" />
                <p>Select an action on the left to inspect its parameters and state.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
};
