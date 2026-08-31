import React, { useState } from 'react';
import { ensureFontLoaded, isFontAvailable, rescanFonts, type FontFamilyMeta } from '../utils/fontLoader';
import { FontPickerModal } from './FontPickerModal';
import { AlertTriangle, RefreshCw, Folder } from 'lucide-react';

export interface FontSelectorProps {
  value: string;
  onChange: (fontFamily: string) => void;
  availableFonts?: string[];
  availableFamilies?: Record<string, FontFamilyMeta>;
  className?: string;
  onFontUploaded?: () => void;
  onRescanFonts?: (rescan?: boolean) => void | Promise<void>;
}

const DEFAULT_MANGA_FONTS = [
  'FC Sukhumvit',
  'Prompt',
  'Sarabun',
  'Wild Words',
  'Anime Ace',
  'CC Wild Words',
  'Anime Ace BB',
  'Manga Temple',
  'BadaBoom BB',
  'Komika Hand',
  'Tahoma',
  'Arial',
  'Inter',
  'sans-serif',
];

export const FontSelector: React.FC<FontSelectorProps> = ({
  value,
  onChange,
  availableFonts,
  availableFamilies,
  className = '',
  onFontUploaded,
  onRescanFonts,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isRescanning, setIsRescanning] = useState(false);
  const [rescanSuccessMessage, setRescanSuccessMessage] = useState<string | null>(null);

  const fontList = availableFonts && availableFonts.length > 0 ? availableFonts : DEFAULT_MANGA_FONTS;
  const isMissing = Boolean(value) && !isFontAvailable(value, availableFamilies, availableFonts);

  const handleSelect = (font: string) => {
    ensureFontLoaded(font);
    onChange(font);
  };

  const handleRescan = async () => {
    setIsRescanning(true);
    setRescanSuccessMessage(null);
    try {
      if (onRescanFonts) {
        await onRescanFonts(true);
      } else {
        await rescanFonts();
      }
      await ensureFontLoaded(value);
      setRescanSuccessMessage('รีเฟรชข้อมูลฟอนต์เรียบร้อยแล้ว');
      setTimeout(() => setRescanSuccessMessage(null), 3000);
    } catch (e) {
      console.error(e);
    } finally {
      setIsRescanning(false);
    }
  };

  return (
    <>
      <div className={`flex flex-col gap-1.5 ${className}`}>
        <div className="flex items-center gap-1.5">
          <select
            value={value}
            onChange={(e) => handleSelect(e.target.value)}
            className={`flex-1 bg-zinc-900 border rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none font-sans cursor-pointer ${
              isMissing 
                ? 'border-amber-500/60 text-amber-200 focus:border-amber-400 ring-1 ring-amber-500/20' 
                : 'border-zinc-800 focus:border-orange-500'
            }`}
          >
            {fontList.map((font) => {
              const fontMissing = !isFontAvailable(font, availableFamilies, availableFonts);
              return (
                <option key={font} value={font} style={{ fontFamily: font }}>
                  {font}{fontMissing ? ' (⚠️ ไม่พบในเครื่อง)' : ''}
                </option>
              );
            })}
          </select>

          <button
            type="button"
            onClick={handleRescan}
            disabled={isRescanning}
            title="รีเฟรชการสแกนฟอนต์จาก Windows และ data/fonts/"
            className="p-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-slate-300 hover:text-amber-300 rounded-lg text-xs transition-colors flex items-center justify-center shrink-0 disabled:opacity-50"
          >
            <RefreshCw size={13} className={isRescanning ? 'animate-spin text-amber-400' : ''} />
          </button>

          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            title="เปิดตัวเลือกฟอนต์พร้อมพรีวิวตัวอย่าง (Font Explorer)"
            className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-orange-500/50 text-orange-400 rounded-lg text-xs font-bold transition-colors flex items-center justify-center shrink-0 shadow-sm"
          >
            Aa
          </button>
        </div>

        {/* Missing Font Alert Banner */}
        {isMissing && (
          <div className="p-2 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-300 flex flex-col gap-1 animate-in fade-in slide-in-from-top-1">
            <div className="flex items-center justify-between gap-1.5">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-200">
                <AlertTriangle size={13} className="text-amber-400 shrink-0" />
                <span className="truncate">ไม่พบไฟล์ฟอนต์ "{value}"</span>
              </div>
              <button
                type="button"
                onClick={handleRescan}
                disabled={isRescanning}
                className="px-2 py-0.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/50 rounded text-[10px] font-bold transition-all flex items-center gap-1 shrink-0 cursor-pointer disabled:opacity-50"
              >
                <RefreshCw size={9} className={isRescanning ? 'animate-spin' : ''} />
                <span>{isRescanning ? 'กำลังสแกน…' : 'รีเฟรช'}</span>
              </button>
            </div>
            <div className="text-[9.5px] text-amber-300/80 leading-snug">
              ระบบแสดงผลด้วยฟอนต์สำรอง (Tahoma) · นำไฟล์ <span className="font-mono font-bold text-amber-200">.ttf</span> ไปวางที่ <span className="font-mono font-bold text-amber-200">e:\houmi\data\fonts\</span> แล้วกดรีเฟรช
            </div>
          </div>
        )}

        {/* Rescan success flash */}
        {rescanSuccessMessage && !isMissing && (
          <div className="text-[10px] text-emerald-400 font-semibold px-1 animate-in fade-in">
            ✓ {rescanSuccessMessage}
          </div>
        )}
      </div>

      <FontPickerModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        selectedFont={value}
        onSelectFont={handleSelect}
        availableFamilies={availableFamilies}
        fontList={fontList}
        onFontUploaded={async () => {
          await handleRescan();
          onFontUploaded?.();
        }}
      />
    </>
  );
};

