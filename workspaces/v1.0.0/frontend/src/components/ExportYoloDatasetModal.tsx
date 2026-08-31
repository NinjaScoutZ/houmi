import React, { useState, useEffect } from 'react';
import { useProjectStore } from '../stores/projectStore';
import { X, CheckSquare, Square, FolderArchive, Sparkles } from 'lucide-react';

interface ExportYoloDatasetModalProps {
  onClose: () => void;
}

export const ExportYoloDatasetModal: React.FC<ExportYoloDatasetModalProps> = ({ onClose }) => {
  const projects = useProjectStore((state) => state.projects);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Sort projects by update time (latest first)
  const sortedProjects = [...projects].sort((a, b) => {
    const timeA = new Date(a.updated_at || a.created_at).getTime();
    const timeB = new Date(b.updated_at || b.created_at).getTime();
    return timeB - timeA;
  });

  // Pre-select the top 10 most recent projects on mount
  useEffect(() => {
    const recent10 = sortedProjects.slice(0, 10).map((p) => p.id);
    setSelectedIds(new Set(recent10));
  }, [projects]);

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const handleSelectAll = () => {
    setSelectedIds(new Set(projects.map((p) => p.id)));
  };

  const handleDeselectAll = () => {
    setSelectedIds(new Set());
  };

  const handleSelectRecent10 = () => {
    const recent10 = sortedProjects.slice(0, 10).map((p) => p.id);
    setSelectedIds(new Set(recent10));
  };

  const handleExport = () => {
    if (selectedIds.size === 0) return;
    const idsStr = Array.from(selectedIds).join(',');
    const link = document.createElement('a');
    link.href = `/api/projects/export-yolo-dataset?project_ids=${idsStr}`;
    link.setAttribute('download', 'yolo_dataset.zip');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 animate-fade-in font-sans select-none p-4">
      <div className="w-[580px] max-h-[500px] rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl relative overflow-hidden text-slate-200 flex flex-col animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-850 bg-zinc-900/60 relative z-10">
          <div className="flex items-center gap-2">
            <FolderArchive className="text-amber-400 w-5 h-5" />
            <span className="text-sm font-bold tracking-wider font-pixel text-amber-400 uppercase">
              Export YOLO Training Dataset
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition-colors p-1 hover:bg-zinc-800 rounded-lg cursor-pointer"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Info Box */}
        <div className="px-5 pt-4 text-[11px] text-slate-400 leading-relaxed z-10 shrink-0">
          <p>
            เลือกโครงการที่ต้องการรวมพิกัดกรอบข้อความและรูปภาพต้นฉบับเพื่อส่งออกเป็นชุดข้อมูลสำหรับฝึกสอนโมเดลตรวจจับกล่องข้อความ (YOLO Balloon Detector) ระบบจะส่งออกคลาสทั้งหมดเป็นคลาส <code className="text-amber-400 font-mono">0</code>
          </p>
        </div>

        {/* Selection Helpers */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-900 text-[10px] z-10 shrink-0 font-pixel">
          <button
            onClick={handleSelectRecent10}
            className="px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-amber-500/50 hover:bg-amber-500/10 hover:text-amber-300 transition-all cursor-pointer font-bold"
          >
            Select 10 Recent (10 ตอนล่าสุด)
          </button>
          <button
            onClick={handleSelectAll}
            className="px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-800 hover:text-white transition-all cursor-pointer font-bold"
          >
            Select All (ทั้งหมด)
          </button>
          <button
            onClick={handleDeselectAll}
            className="px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-800 hover:text-white transition-all cursor-pointer font-bold"
          >
            Deselect All (ไม่เลือกเลย)
          </button>
        </div>

        {/* Projects List */}
        <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-1.5 z-10">
          {sortedProjects.map((p, idx) => {
            const isSelected = selectedIds.has(p.id);
            const isTop10 = idx < 10;
            return (
              <div
                key={p.id}
                onClick={() => toggleSelect(p.id)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg border transition-all cursor-pointer select-none ${
                  isSelected
                    ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                    : 'border-zinc-900 bg-zinc-900/30 text-slate-300 hover:border-zinc-800 hover:bg-zinc-900/60'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {isSelected ? (
                    <CheckSquare size={15} className="text-amber-400 shrink-0" />
                  ) : (
                    <Square size={15} className="text-zinc-600 shrink-0" />
                  )}
                  <span className="text-xs truncate font-medium">{p.name}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {isTop10 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 font-bold border border-amber-500/30 font-pixel">
                      Recent
                    </span>
                  )}
                  <span className="text-[9px] text-zinc-500 font-mono">
                    {new Date(p.updated_at || p.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-4 border-t border-zinc-850 bg-zinc-900/60 relative z-10 shrink-0 font-pixel">
          <div className="text-[10px] text-zinc-400 font-mono">
            Selected: <span className="text-amber-400 font-bold">{selectedIds.size}</span> project(s)
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-bold text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={selectedIds.size === 0}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-xl text-black bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 active:scale-95 disabled:opacity-50 disabled:pointer-events-none transition-all shadow-lg shadow-amber-500/20 cursor-pointer"
            >
              <Sparkles size={13} />
              <span>Export Dataset</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
