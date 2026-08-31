import React, { useEffect, useState } from 'react';
import { GitCommit, Tag, Layers, RefreshCw, CheckCircle, ShieldAlert, FileText, Plus, Trash2, Save, Search, X, Edit3, Eye } from 'lucide-react';

interface DevNode {
  id: string;
  label: string;
  title: string;
  type: string;
  is_customer_release: boolean;
  timestamp: string;
  tags: string[];
  summary: string;
  changes: Array<{ category: string; description: string }>;
  modified_files: string[];
}

interface DevNoteItem {
  filename: string;
  title: string;
  updated_at: string;
  size: number;
}

interface DevMapDashboardProps {
  onClose?: () => void;
  initialTab?: 'dev_map' | 'dev_notes';
}

export const DevMapDashboard: React.FC<DevMapDashboardProps> = ({ onClose, initialTab = 'dev_map' }) => {
  const [activeTab, setActiveTab] = useState<'dev_map' | 'dev_notes'>(initialTab);

  // Dev Map State
  const [nodes, setNodes] = useState<DevNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<DevNode | null>(null);
  const [loadingMap, setLoadingMap] = useState<boolean>(true);

  // Dev Notes State
  const [notes, setNotes] = useState<DevNoteItem[]>([]);
  const [selectedNoteFile, setSelectedNoteFile] = useState<string | null>(null);
  const [noteTitle, setNoteTitle] = useState<string>('');
  const [noteContent, setNoteContent] = useState<string>('');
  const [noteSearch, setNoteSearch] = useState<string>('');
  const [loadingNotes, setLoadingNotes] = useState<boolean>(false);
  const [_isEditingNote, setIsEditingNote] = useState<boolean>(false);
  const [noteSaving, setNoteSaving] = useState<boolean>(false);
  const [noteMode, setNoteMode] = useState<'edit' | 'preview'>('edit');

  const fetchHistory = async () => {
    setLoadingMap(true);
    try {
      const res = await fetch('/api/dev-map/history');
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes || []);
        if (data.nodes && data.nodes.length > 0) {
          setSelectedNode(data.nodes[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch dev map:', err);
    } finally {
      setLoadingMap(false);
    }
  };

  const fetchNotes = async () => {
    setLoadingNotes(true);
    try {
      const res = await fetch('/api/dev-map/notes');
      if (res.ok) {
        const data = await res.json();
        setNotes(data.notes || []);
        if (data.notes && data.notes.length > 0 && !selectedNoteFile) {
          loadNoteContent(data.notes[0].filename);
        }
      }
    } catch (err) {
      console.error('Failed to fetch notes:', err);
    } finally {
      setLoadingNotes(false);
    }
  };

  const loadNoteContent = async (filename: string) => {
    try {
      const res = await fetch(`/api/dev-map/notes/${encodeURIComponent(filename)}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedNoteFile(data.filename);
        setNoteTitle(data.title || filename.replace('.md', ''));
        setNoteContent(data.content || '');
        setIsEditingNote(false);
      }
    } catch (err) {
      console.error('Failed to read note:', err);
    }
  };

  const handleCreateNewNote = () => {
    setSelectedNoteFile(null);
    setNoteTitle('New Developer Note');
    setNoteContent('# New Developer Note\n\nWrite your technical notes, rules, or roadmap thoughts here...\n');
    setIsEditingNote(true);
    setNoteMode('edit');
  };

  const handleSaveNote = async () => {
    if (!noteTitle.trim()) return;
    setNoteSaving(true);
    try {
      const filename = selectedNoteFile || `${noteTitle.trim().replace(/\s+/g, '_')}.md`;
      const res = await fetch('/api/dev-map/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename,
          content: noteContent,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedNoteFile(data.filename);
        setIsEditingNote(false);
        fetchNotes();
      }
    } catch (err) {
      console.error('Failed to save note:', err);
    } finally {
      setNoteSaving(false);
    }
  };

  const handleDeleteNote = async (filename: string) => {
    if (!window.confirm(`คุณต้องการลบ Note "${filename}" ใช่หรือไม่?`)) return;
    try {
      const res = await fetch(`/api/dev-map/notes/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setSelectedNoteFile(null);
        setNoteTitle('');
        setNoteContent('');
        fetchNotes();
      }
    } catch (err) {
      console.error('Failed to delete note:', err);
    }
  };

  useEffect(() => {
    fetchHistory();
    fetchNotes();
  }, []);

  const filteredNotes = notes.filter(n =>
    n.title.toLowerCase().includes(noteSearch.toLowerCase()) ||
    n.filename.toLowerCase().includes(noteSearch.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/95 backdrop-blur-md flex flex-col text-slate-100 font-sans animate-fade-in">
      {/* Header bar */}
      <div className="bg-zinc-950 px-6 py-4 flex items-center justify-between border-b border-zinc-900 shrink-0">
        <div className="flex items-center gap-4">
          <h2 className="text-sm font-bold font-pixel uppercase tracking-widest text-amber-400 flex items-center gap-2">
            🚀 Houmi Dev Studio Hub
          </h2>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 bg-zinc-900/80 p-1 rounded-lg border border-zinc-800">
            <button
              type="button"
              onClick={() => setActiveTab('dev_map')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold font-pixel tracking-wider uppercase transition-all cursor-pointer ${
                activeTab === 'dev_map'
                  ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers size={14} className="text-cyan-400" />
              Dev Map & Changelog
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('dev_notes')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold font-pixel tracking-wider uppercase transition-all cursor-pointer ${
                activeTab === 'dev_notes'
                  ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText size={14} className="text-amber-400" />
              Dev Notes ({notes.length})
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {activeTab === 'dev_map' ? (
            <button
              type="button"
              onClick={fetchHistory}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-xs font-pixel text-slate-300 transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingMap ? 'animate-spin' : ''}`} /> Refresh Map
            </button>
          ) : (
            <button
              type="button"
              onClick={fetchNotes}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-xs font-pixel text-slate-300 transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingNotes ? 'animate-spin' : ''}`} /> Refresh Notes
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-zinc-900 transition-colors cursor-pointer"
              title="Close (✕)"
            >
              <X size={20} />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'dev_map' ? (
          /* TAB 1: DEV MAP & CHANGELOG */
          <div className="flex h-full w-full overflow-hidden p-6 gap-6">
            {/* Left: Flowchart Timeline Node List */}
            <div className="w-1/2 flex flex-col border-r border-zinc-900 pr-6 overflow-y-auto">
              <div className="mb-4">
                <p className="text-xs text-slate-400">
                  แผนผังโหนดการพัฒนา และประวัติเวอร์ชันระบบ (Append-Only Dev Patch System)
                </p>
              </div>

              {/* Nodes Timeline Tree */}
              <div className="relative border-l-2 border-zinc-800 ml-4 pl-6 space-y-4">
                {nodes.map((node) => {
                  const isSelected = selectedNode?.id === node.id;
                  return (
                    <div
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`cursor-pointer transition-all p-4 rounded-xl border ${
                        isSelected
                          ? 'border-amber-500/80 bg-amber-500/10 shadow-lg shadow-amber-950/30'
                          : 'border-zinc-850 bg-zinc-900/50 hover:border-zinc-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold font-pixel ${
                            node.is_customer_release
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          }`}
                        >
                          {node.is_customer_release ? <CheckCircle className="w-3 h-3" /> : <GitCommit className="w-3 h-3" />}
                          {node.label}
                        </span>
                        <span className="text-xs font-mono text-slate-400">
                          {new Date(node.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <h3 className="text-sm font-bold mt-2 text-slate-100 font-sans">{node.title}</h3>
                      {node.summary && <p className="text-xs text-slate-400 mt-1 line-clamp-2">{node.summary}</p>}

                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {node.tags?.map((t, idx) => (
                          <span key={idx} className="inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-950 text-slate-300 text-[10px] rounded border border-zinc-850 font-mono">
                            <Tag className="w-2.5 h-2.5" /> {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Node Details Inspector Pane */}
            <div className="w-1/2 pl-2 flex flex-col overflow-y-auto">
              {selectedNode ? (
                <div className="space-y-5">
                  <div className="border-b border-zinc-900 pb-4">
                    <span className="text-xs uppercase tracking-wider text-amber-400 font-mono font-bold">
                      Patch Node Details ({selectedNode.id})
                    </span>
                    <h2 className="text-lg font-bold mt-1 text-white">{selectedNode.title}</h2>
                    <p className="text-xs text-slate-400 mt-1 font-mono">Author: {(selectedNode as any).author || 'Antigravity AI'}</p>
                  </div>

                  {selectedNode.summary && (
                    <div className="bg-zinc-900/80 p-4 rounded-xl border border-zinc-800 space-y-1">
                      <h4 className="text-xs font-bold text-amber-400 font-pixel uppercase tracking-wider">Summary Statement</h4>
                      <p className="text-xs text-slate-200 leading-relaxed font-sans">{selectedNode.summary}</p>
                    </div>
                  )}

                  <div>
                    <h4 className="text-xs font-bold text-slate-300 uppercase font-pixel tracking-wider mb-3">Recorded Patch Changes</h4>
                    <div className="space-y-2">
                      {selectedNode.changes?.map((ch, i) => (
                        <div key={i} className="flex gap-2 text-xs bg-zinc-900/60 p-3 rounded-lg border border-zinc-800">
                          <span className="font-bold text-amber-400 font-pixel shrink-0">[{ch.category}]</span>
                          <span className="text-slate-200">{ch.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedNode.modified_files?.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-slate-300 uppercase font-pixel tracking-wider mb-2">Modified Files List</h4>
                      <ul className="text-xs font-mono text-slate-400 space-y-1 bg-zinc-950 p-3 rounded-lg border border-zinc-850 max-h-48 overflow-y-auto">
                        {selectedNode.modified_files.map((file, i) => (
                          <li key={i} className="truncate text-slate-300">• {file}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-slate-500">
                  <ShieldAlert className="w-8 h-8 mb-2" />
                  <p className="text-xs font-pixel">Select a patch node from the left tree to inspect</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* TAB 2: DEV NOTES MANAGER */
          <div className="flex h-full w-full overflow-hidden p-6 gap-6">
            {/* Left: Notes File Explorer */}
            <div className="w-80 flex flex-col border-r border-zinc-900 pr-5 shrink-0">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold font-pixel uppercase tracking-wider text-amber-400">
                  Developer Notes List
                </h3>
                <button
                  type="button"
                  onClick={handleCreateNewNote}
                  className="flex items-center gap-1 px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 rounded-md text-[10px] font-bold uppercase tracking-wider cursor-pointer transition-all"
                >
                  <Plus size={12} /> New Note
                </button>
              </div>

              {/* Search Bar */}
              <div className="relative mb-3">
                <input
                  type="text"
                  placeholder="Search developer notes..."
                  value={noteSearch}
                  onChange={(e) => setNoteSearch(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-amber-500/50"
                />
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              </div>

              {/* Notes List */}
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
                {filteredNotes.length === 0 ? (
                  <p className="text-xs text-slate-500 text-center py-6">No developer notes found</p>
                ) : (
                  filteredNotes.map((n) => {
                    const isSel = selectedNoteFile === n.filename;
                    return (
                      <div
                        key={n.filename}
                        onClick={() => loadNoteContent(n.filename)}
                        className={`p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                          isSel
                            ? 'border-amber-500/60 bg-amber-500/10 text-amber-300 font-bold'
                            : 'border-zinc-850 bg-zinc-900/50 text-slate-300 hover:border-zinc-700 hover:bg-zinc-900'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="truncate font-sans font-medium">{n.title}</span>
                          {isSel && <FileText size={12} className="text-amber-400 shrink-0" />}
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono mt-1">
                          <span>{new Date(n.updated_at).toLocaleDateString()}</span>
                          <span>{(n.size / 1024).toFixed(1)} KB</span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right: Note Content Reader / Editor Pane */}
            <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950/60 rounded-xl border border-zinc-900 p-5">
              {noteTitle !== '' || selectedNoteFile ? (
                <div className="flex-1 flex flex-col overflow-hidden space-y-4">
                  {/* Note Header & Action Controls */}
                  <div className="flex items-center justify-between border-b border-zinc-900 pb-3">
                    <input
                      type="text"
                      value={noteTitle}
                      onChange={(e) => {
                        setNoteTitle(e.target.value);
                        setIsEditingNote(true);
                      }}
                      placeholder="Note Title..."
                      className="bg-transparent text-base font-bold text-white border-b border-transparent hover:border-zinc-700 focus:border-amber-400 focus:outline-none px-1 py-0.5 font-sans w-2/3"
                    />

                    <div className="flex items-center gap-2">
                      <div className="flex items-center bg-zinc-900 p-1 rounded-lg border border-zinc-800 text-[10px] font-pixel">
                        <button
                          type="button"
                          onClick={() => setNoteMode('edit')}
                          className={`px-2 py-1 rounded flex items-center gap-1 uppercase cursor-pointer ${
                            noteMode === 'edit' ? 'bg-amber-500/20 text-amber-300 font-bold' : 'text-slate-400'
                          }`}
                        >
                          <Edit3 size={10} /> Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => setNoteMode('preview')}
                          className={`px-2 py-1 rounded flex items-center gap-1 uppercase cursor-pointer ${
                            noteMode === 'preview' ? 'bg-amber-500/20 text-amber-300 font-bold' : 'text-slate-400'
                          }`}
                        >
                          <Eye size={10} /> Preview
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={handleSaveNote}
                        disabled={noteSaving}
                        className="flex items-center gap-1 px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded-lg font-pixel transition-colors cursor-pointer shadow-md disabled:opacity-50"
                      >
                        <Save size={14} /> {noteSaving ? 'Saving...' : 'Save Note'}
                      </button>

                      {selectedNoteFile && (
                        <button
                          type="button"
                          onClick={() => handleDeleteNote(selectedNoteFile)}
                          className="p-1.5 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 rounded-lg transition-colors cursor-pointer"
                          title="Delete Note"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Note Body: Editor vs Preview */}
                  <div className="flex-1 overflow-hidden flex flex-col">
                    {noteMode === 'edit' ? (
                      <textarea
                        value={noteContent}
                        onChange={(e) => {
                          setNoteContent(e.target.value);
                          setIsEditingNote(true);
                        }}
                        placeholder="Write your note in Markdown format..."
                        className="w-full h-full bg-zinc-900/40 border border-zinc-800 rounded-lg p-4 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500/50 resize-none leading-relaxed"
                      />
                    ) : (
                      <div className="w-full h-full bg-zinc-900/40 border border-zinc-800 rounded-lg p-5 overflow-y-auto font-sans text-xs leading-relaxed text-slate-200 space-y-3">
                        <pre className="whitespace-pre-wrap font-mono text-xs text-slate-300">
                          {noteContent}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-slate-500">
                  <FileText className="w-8 h-8 mb-2 text-slate-600" />
                  <p className="text-xs font-pixel">Select a note or click "+ New Note" to create one</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
