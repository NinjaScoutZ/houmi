import React, { useState, useMemo, useRef } from 'react';
import { Upload, X, Type, Search } from 'lucide-react';
import { injectFontStylesheet, type FontFamilyMeta } from '../utils/fontLoader';

export interface FontPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedFont: string;
  onSelectFont: (fontFamily: string) => void;
  availableFamilies?: Record<string, FontFamilyMeta>;
  fontList?: string[];
  onFontUploaded?: () => void;
}

export const FontPickerModal: React.FC<FontPickerModalProps> = ({
  isOpen,
  onClose,
  selectedFont,
  onSelectFont,
  availableFamilies = {},
  fontList = [],
  onFontUploaded,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<'all' | 'manga' | 'thai' | 'custom' | 'system'>('all');
  const [sampleText, setSampleText] = useState('นี่คือตัวอย่างฟอนต์ (Sample Text 123)');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Group fonts & combine props
  const allFamilies = useMemo(() => {
    const map = new Map<string, { family: string; category?: string; styles?: string[]; isCustom?: boolean }>();

    // 1. From availableFamilies (detailed metadata)
    Object.entries(availableFamilies).forEach(([fam, meta]) => {
      map.set(fam.toLowerCase(), {
        family: fam,
        category: meta.category,
        styles: meta.styles,
        isCustom: meta.category === 'custom',
      });
    });

    // 2. From simple fontList (fallback)
    fontList.forEach((fam) => {
      const lower = fam.toLowerCase();
      if (!map.has(lower)) {
        map.set(lower, { family: fam, category: 'system' });
      }
    });

    return Array.from(map.values()).sort((a, b) => a.family.localeCompare(b.family));
  }, [availableFamilies, fontList]);

  // Filter based on search query and category
  const filteredFamilies = useMemo(() => {
    return allFamilies.filter((item) => {
      const matchesSearch = item.family.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchesSearch) return false;

      if (activeCategory === 'all') return true;
      if (activeCategory === 'custom') return !!item.isCustom;
      if (activeCategory === 'thai') return item.category === 'thai' || /thai|sarabun|mitr|kanit|prompt|chula/i.test(item.family);
      if (activeCategory === 'manga') return item.category === 'manga' || /manga|comic|anime|cc|wild|blambot/i.test(item.family);
      if (activeCategory === 'system') return !item.isCustom && item.category !== 'thai' && item.category !== 'manga';

      return true;
    });
  }, [allFamilies, searchQuery, activeCategory]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const validExtensions = ['.ttf', '.otf', '.woff2', '.ttc'];
    const fileName = file.name.toLowerCase();
    if (!validExtensions.some((ext) => fileName.endsWith(ext))) {
      setUploadError('Invalid font format. Please upload .ttf, .otf, or .woff2 files.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/fonts/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      injectFontStylesheet();
      if (onFontUploaded) onFontUploaded();
      if (data.family) {
        onSelectFont(data.family);
      }
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload font');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-150 font-sans select-none">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden text-slate-100 animate-in zoom-in-95">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/80">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 font-bold font-pixel">
              <Type size={16} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100 font-pixel uppercase tracking-wider">Font Explorer & Manager</h2>
              <p className="text-[11px] text-slate-400">เลือกและจัดการฟอนต์สำหรับ Canvas และ PSD Export</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".ttf,.otf,.woff2,.ttc"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="px-3.5 py-1.5 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black font-bold font-pixel text-xs rounded-xl shadow-md shadow-amber-500/10 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {isUploading ? (
                <span>Uploading...</span>
              ) : (
                <>
                  <Upload size={13} />
                  <span>Upload Font (.ttf/.otf)</span>
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
              title="Close"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {uploadError && (
          <div className="px-6 py-2 bg-rose-950/60 border-b border-rose-800 text-rose-300 text-xs flex items-center justify-between">
            <span>{uploadError}</span>
            <button onClick={() => setUploadError(null)} className="text-rose-400 hover:text-rose-200 cursor-pointer">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Controls & Categories Bar */}
        <div className="p-4 border-b border-zinc-800 bg-zinc-900/50 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
          <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-xl border border-zinc-800 text-xs overflow-x-auto font-pixel">
            {(
              [
                { id: 'all', label: 'All Fonts' },
                { id: 'manga', label: 'Manga / SFX' },
                { id: 'thai', label: 'Thai Dialogue' },
                { id: 'custom', label: 'Custom Fonts' },
                { id: 'system', label: 'System' },
              ] as const
            ).map((cat) => (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`px-3 py-1 rounded-lg transition-all font-semibold whitespace-nowrap cursor-pointer text-[11px] ${
                  activeCategory === cat.id
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-800/60'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <div className="relative flex-1 max-w-xs">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search font family..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition-colors"
            />
          </div>
        </div>

        {/* Sample text preview modifier */}
        <div className="px-6 py-2.5 bg-zinc-950/60 border-b border-zinc-800 flex items-center gap-3 text-xs">
          <span className="text-slate-400 text-[11px] uppercase tracking-wider font-semibold whitespace-nowrap font-pixel">Preview Text:</span>
          <input
            type="text"
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            className="flex-1 bg-transparent text-slate-300 focus:outline-none focus:text-white text-xs border-b border-transparent focus:border-amber-500/40 transition-colors"
            placeholder="Type sample text to preview..."
          />
        </div>

        {/* Font List Cards Grid */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 gap-2.5">
          {filteredFamilies.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-sm italic">
              No fonts found matching "{searchQuery}"
            </div>
          ) : (
            filteredFamilies.map((item) => {
              const isSelected = selectedFont.toLowerCase() === item.family.toLowerCase();
              return (
                <div
                  key={item.family}
                  onClick={() => {
                    onSelectFont(item.family);
                    onClose();
                  }}
                  className={`group p-3.5 rounded-xl border transition-all cursor-pointer flex flex-col gap-2 ${
                    isSelected
                      ? 'bg-amber-500/10 border-amber-500/50 shadow-md shadow-amber-500/5'
                      : 'bg-zinc-900/50 border-zinc-850 hover:border-zinc-700 hover:bg-zinc-850/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-200 group-hover:text-amber-400 transition-colors font-pixel">
                        {item.family}
                      </span>
                      {isSelected && (
                        <span className="px-2 py-0.5 rounded text-[9.5px] font-bold bg-amber-500 text-black font-pixel">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {item.styles && item.styles.length > 0 && (
                        <span className="text-[9.5px] text-slate-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800 font-mono">
                          {item.styles.join(', ')}
                        </span>
                      )}
                      <span className="text-[9.5px] uppercase px-1.5 py-0.5 rounded font-mono text-slate-400 bg-zinc-900 border border-zinc-800 font-pixel">
                        {item.category || 'system'}
                      </span>
                    </div>
                  </div>

                  <div
                    style={{ fontFamily: item.family }}
                    className="text-lg text-slate-100 tracking-wide overflow-hidden text-ellipsis whitespace-nowrap py-1"
                  >
                    {sampleText}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-zinc-800 bg-zinc-900/80 flex items-center justify-between text-xs text-slate-400 font-pixel">
          <span>{filteredFamilies.length} fonts available</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-slate-200 rounded-lg transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
