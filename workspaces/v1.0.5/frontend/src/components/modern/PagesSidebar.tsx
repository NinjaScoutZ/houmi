import React, { useState } from 'react';
import { Upload, Trash2, Image as ImageIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Page } from '../../stores/projectStore';

interface PagesSidebarProps {
  pages: Page[];
  activePage: Page | null;
  onSelectPage: (pageId: string) => void;
  onUploadPages: (files: FileList | File[]) => void;
  onDeletePage: (pageId: string, pageNumber: number) => void;
  isProcessing?: boolean;
  isOpen: boolean;
  onToggleOpen: () => void;
}

export const PagesSidebar: React.FC<PagesSidebarProps> = ({
  pages,
  activePage,
  onSelectPage,
  onUploadPages,
  onDeletePage,
  isProcessing = false,
  isOpen,
  onToggleOpen,
}) => {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onUploadPages(e.dataTransfer.files);
    }
  };

  if (!isOpen) {
    return (
      <div className="w-10 bg-[#0c0c12] border-r border-[#20202c] flex flex-col items-center py-3 select-none shrink-0 z-30">
        <button
          type="button"
          onClick={onToggleOpen}
          className="p-1.5 rounded-lg bg-[#14141e] border border-[#262638] text-slate-400 hover:text-amber-400 transition-colors cursor-pointer"
          title="Open Pages Sidebar (P)"
        >
          <ChevronRight size={16} />
        </button>
        <span className="mt-4 text-[10px] font-mono text-zinc-500 font-bold uppercase rotate-90 whitespace-nowrap tracking-wider">
          PAGES ({pages.length})
        </span>
      </div>
    );
  }

  return (
    <aside
      className={`w-64 sm:w-72 bg-[#0c0c12] border-r border-[#20202c] flex flex-col shrink-0 select-none transition-all duration-300 z-30 font-sans ${
        dragOver ? 'border-amber-500/60 bg-amber-500/5' : ''
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Sidebar Header */}
      <div className="h-11 px-3.5 border-b border-[#20202c] bg-[#101018] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-black tracking-wider text-slate-200 uppercase font-pixel">
            PAGES ({pages.length})
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <label
            className={`px-2.5 py-1 rounded-lg text-[10.5px] font-bold flex items-center gap-1 transition-all cursor-pointer ${
              isProcessing
                ? 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
                : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/10'
            }`}
            title="Upload new manga pages"
          >
            <Upload size={12} />
            <span>+ Add</span>
            {!isProcessing && (
              <input
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files.length > 0) {
                    onUploadPages(e.target.files);
                  }
                }}
              />
            )}
          </label>
          <button
            type="button"
            onClick={onToggleOpen}
            className="p-1 text-slate-500 hover:text-slate-300 rounded hover:bg-zinc-800/60 transition-colors cursor-pointer"
            title="Collapse Sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        </div>
      </div>

      {/* Pages Card List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
        {pages.length === 0 ? (
          <div className="h-48 border border-dashed border-zinc-800 rounded-2xl flex flex-col items-center justify-center p-4 text-center text-zinc-500">
            <ImageIcon size={28} className="mb-2 text-zinc-600" />
            <p className="text-xs font-semibold text-zinc-400">ยังไม่มีหน้าในโปรเจกต์</p>
            <p className="text-[10.5px] mt-0.5 text-zinc-600">ลากไฟล์รูปภาพมาวางที่นี่ หรือกดปุ่ม + Add ด้านบน</p>
          </div>
        ) : (
          pages.map((p) => {
            const isActive = activePage?.id === p.id;
            const previewUrl = `/api/pages/${p.id}/preview`;
            return (
              <div
                key={p.id}
                onClick={() => onSelectPage(p.id)}
                className={`group relative flex flex-col rounded-2xl border transition-all duration-200 cursor-pointer overflow-hidden ${
                  isActive
                    ? 'border-amber-500 bg-[#161622] shadow-[0_0_20px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/50'
                    : 'border-[#20202c] bg-[#111118] hover:border-zinc-700 hover:bg-[#14141f]'
                }`}
              >
                {/* Image Preview Container */}
                <div className="w-full h-44 bg-[#0a0a0f] relative overflow-hidden flex items-center justify-center">
                  <img
                    src={previewUrl}
                    alt={`Page ${p.page_number}`}
                    loading="lazy"
                    className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                    }}
                  />
                  {/* Delete Button on Hover */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeletePage(p.id, p.page_number);
                    }}
                    className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/70 hover:bg-rose-600/90 text-zinc-400 hover:text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all border border-white/10 cursor-pointer shadow-lg"
                    title={`Delete Page ${p.page_number}`}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>

                {/* Card Footer Info */}
                <div className="p-2.5 flex items-center justify-between border-t border-[#1c1c28] bg-[#0e0e14]">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`text-xs font-bold font-mono ${isActive ? 'text-amber-300' : 'text-slate-300'}`}>
                      Page {p.page_number}
                    </span>
                    <span className="text-[10px] text-zinc-500 truncate font-mono">
                      {p.name || `0${p.page_number}.png`}
                    </span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[9px] font-black uppercase font-mono tracking-wider ${
                      isActive
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        : p.status === 'processed'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-zinc-800 text-zinc-400'
                    }`}
                  >
                    {isActive ? 'ACTIVE' : p.status || 'PENDING'}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
