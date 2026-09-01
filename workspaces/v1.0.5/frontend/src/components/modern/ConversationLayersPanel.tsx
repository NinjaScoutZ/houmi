import React, { useState } from 'react';
import { Search, ArrowUpDown, Copy, Trash2, Eye, Zap, Palette, Check } from 'lucide-react';
import type { TextBlock } from '../../stores/projectStore';

interface ConversationLayersPanelProps {
  blocks: TextBlock[];
  selectedBlockId: string | null;
  onSelectBlock: (blockId: string) => void;
  onUpdateBlockText: (blockId: string, text: string) => void;
  onUpdateBlockTranslation: (blockId: string, translation: string) => void;
  onDeleteBlock: (blockId: string) => void;
  onSortRTL: () => void;
}

export const ConversationLayersPanel: React.FC<ConversationLayersPanelProps> = ({
  blocks,
  selectedBlockId,
  onSelectBlock,
  onUpdateBlockText,
  onUpdateBlockTranslation,
  onDeleteBlock,
  onSortRTL,
}) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const filteredBlocks = blocks.filter((b) => {
    if (filterType !== 'all' && b.type !== filterType && b.bubble_type !== filterType) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const src = (b.source_text || '').toLowerCase();
      const trans = (b.target_text || '').toLowerCase();
      return src.includes(q) || trans.includes(q);
    }
    return true;
  });

  return (
    <div className="flex-1 flex flex-col bg-[#0c0c12] min-h-0 font-sans select-none">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-[#20202c] bg-[#101018] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-amber-400 font-bold">💬</span>
          <h3 className="text-xs font-black tracking-wider text-slate-100 uppercase font-pixel">
            บทสนทนา & เลเยอร์ ({blocks.length})
          </h3>
        </div>
        <button
          type="button"
          onClick={onSortRTL}
          className="px-2.5 py-1 rounded-lg bg-[#181824] hover:bg-zinc-800 border border-[#262638] text-[10.5px] font-bold text-amber-300 hover:text-amber-200 flex items-center gap-1 transition-colors cursor-pointer shadow-sm"
          title="จัดเรียงลำดับบล็อกข้อความตามทิศทางมังงะ (ขวาไปซ้าย / บนลงล่าง)"
        >
          <ArrowUpDown size={12} />
          <span>เรียงลำดับ (RTL)</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="p-2.5 border-b border-[#1c1c28] bg-[#0e0e14] shrink-0">
        <div className="relative flex items-center">
          <Search size={13} className="absolute left-2.5 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="ค้นหาข้อความ, คำแปล, สไตล์..."
            className="w-full pl-7 pr-3 py-1.5 text-xs rounded-xl bg-[#08080c] border border-[#20202c] text-slate-200 placeholder-zinc-600 focus:outline-none focus:border-amber-500/70"
          />
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 mt-2 overflow-x-auto no-scrollbar py-0.5">
          {['all', 'dialogue', 'shout', 'monologue', 'caption'].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilterType(type)}
              className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase transition-all whitespace-nowrap cursor-pointer ${
                filterType === type
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                  : 'bg-[#14141e] text-zinc-500 hover:text-zinc-300 border border-[#20202c]'
              }`}
            >
              {type === 'all' ? `All (${blocks.length})` : type}
            </button>
          ))}
        </div>
      </div>

      {/* Layer Cards List */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2.5 custom-scrollbar">
        {filteredBlocks.length === 0 ? (
          <div className="p-6 text-center text-zinc-500 text-xs font-semibold">
            ไม่มีรายการบล็อกข้อความ
          </div>
        ) : (
          filteredBlocks.map((b, idx) => {
            const isSelected = selectedBlockId === b.id;
            return (
              <div
                key={b.id}
                onClick={() => onSelectBlock(b.id)}
                className={`rounded-2xl border transition-all duration-200 p-3 flex flex-col gap-2 cursor-pointer ${
                  isSelected
                    ? 'border-amber-500 bg-[#161622] shadow-[0_0_20px_rgba(245,158,11,0.12)] ring-1 ring-amber-500/40'
                    : 'border-[#20202c] bg-[#111118] hover:border-zinc-700 hover:bg-[#14141f]'
                }`}
              >
                {/* Layer Card Top Meta */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-black font-mono text-amber-400">
                      #{idx + 1}
                    </span>
                    <span className="text-[11px] font-bold text-slate-200">
                      {b.bubble_type === 'shout' ? 'ตะโกน / เอฟเฟกต์' : 'ตัวละครพูด'}
                    </span>
                    <span className="text-[9px] font-mono text-zinc-500 bg-[#181824] px-1.5 py-0.5 rounded border border-white/5">
                      {Math.round((b.confidence || 0.95) * 100)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteBlock(b.id);
                      }}
                      className="p-1 text-zinc-500 hover:text-rose-400 rounded hover:bg-zinc-800 transition-colors"
                      title="Delete block"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                {/* Source OCR Input Box */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[9.5px] font-bold text-zinc-500 font-mono">
                    <span>ต้นฉบับ (SOURCE OCR)</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopy(b.source_text || '', `src-${b.id}`);
                      }}
                      className="text-zinc-500 hover:text-amber-300 flex items-center gap-1 cursor-pointer"
                    >
                      {copiedId === `src-${b.id}` ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
                      <span>{copiedId === `src-${b.id}` ? 'Copied' : 'copy'}</span>
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    value={b.source_text || ''}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onUpdateBlockText(b.id, e.target.value)}
                    placeholder="ข้อความต้นฉบับจากการตรวจจับ..."
                    className="w-full p-2 text-xs rounded-xl bg-[#09090e] border border-[#1e1e2a] text-slate-300 focus:outline-none focus:border-amber-500/60 resize-none font-sans leading-relaxed"
                  />
                </div>

                {/* Thai Translation Typeset Box */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[9.5px] font-bold text-amber-400/90 font-mono">
                    <span>✨ คำแปล (THAI TYPESET)</span>
                    <span className="text-zinc-500 uppercase">
                      {b.font_family || 'PROMPT'} · {Math.round(b.font_size || 32)}PX
                    </span>
                  </div>
                  <textarea
                    rows={2}
                    value={b.target_text || ''}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onUpdateBlockTranslation(b.id, e.target.value)}
                    placeholder="พิมพ์คำแปลภาษาไทย..."
                    className="w-full p-2 text-xs rounded-xl bg-[#09090e] border border-[#1e1e2a] text-amber-200 focus:outline-none focus:border-amber-500/60 resize-none font-sans font-semibold leading-relaxed"
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
