import React, { useState, useEffect } from 'react';
import { 
  Scissors, X, Folder, Image as ImageIcon, 
  Loader2, Search, FolderOpen, Settings2, CheckCircle2, AlertCircle
} from 'lucide-react';
import type { OversizeScanReport } from './OversizeWarningModal';

interface SmartStitchModalProps {
  isOpen: boolean;
  initialFolderPath?: string;
  isProcessing?: boolean;
  onClose: () => void;
  onExecuteSplit: (options: {
    folderPath: string;
    splitHeight: number;
    enforceWidth: number | null;
    backupOriginal: boolean;
  }) => Promise<{ success: boolean; message?: string; output_images_count?: number }>;
  onExecuteStitch?: (options: {
    folderPath: string;
    targetHeight: number;
    enforceWidth: number | null;
    backupOriginal: boolean;
  }) => Promise<{ success: boolean; message?: string; output_images_count?: number }>;
  onBrowseFolder?: () => Promise<string | null>;
}

export const SmartStitchModal: React.FC<SmartStitchModalProps> = ({
  isOpen,
  initialFolderPath = '',
  isProcessing = false,
  onClose,
  onExecuteSplit,
  onExecuteStitch,
  onBrowseFolder,
}) => {
  const [folderPath, setFolderPath] = useState<string>(initialFolderPath);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanReport, setScanReport] = useState<OversizeScanReport | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  const [operationMode, setOperationMode] = useState<'stitch' | 'split'>('stitch');
  const [splitHeight, setSplitHeight] = useState<number>(5000);
  const [stitchHeight, setStitchHeight] = useState<number>(18000);
  const [enforceWidth, setEnforceWidth] = useState<string>('');
  const [backupOriginal, setBackupOriginal] = useState<boolean>(true);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [splitResult, setSplitResult] = useState<{ success: boolean; message: string; count?: number } | null>(null);

  useEffect(() => {
    if (isOpen) {
      const path = initialFolderPath || '';
      setFolderPath(path);
      setSplitResult(null);
      setScanError(null);
      if (path.trim()) {
        void handleScanFolder(path.trim());
      } else {
        setScanReport(null);
      }
    }
  }, [isOpen, initialFolderPath]);

  if (!isOpen) return null;

  const handleScanFolder = async (targetPath: string, customThreshold?: number) => {
    if (!targetPath || !targetPath.trim()) return;
    setIsScanning(true);
    setScanError(null);
    setSplitResult(null);

    const threshold = customThreshold !== undefined ? customThreshold : 20000;

    try {
      const res = await fetch('/api/projects/check-oversize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: targetPath.trim(), threshold_height: threshold }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Failed to scan folder' }));
        throw new Error(data.detail || 'Failed to scan folder');
      }

      const report: OversizeScanReport = await res.json();
      setScanReport(report);
    } catch (err: any) {
      setScanError(err.message || 'เกิดข้อผิดพลาดในการสแกนโฟลเดอร์');
      setScanReport(null);
    } finally {
      setIsScanning(false);
    }
  };

  const handleBrowse = async () => {
    if (onBrowseFolder) {
      const selected = await onBrowseFolder();
      if (selected) {
        setFolderPath(selected);
        void handleScanFolder(selected);
      }
    } else {
      try {
        const res = await fetch('/api/projects/browse-folder', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          if (data.folder_path) {
            setFolderPath(data.folder_path);
            void handleScanFolder(data.folder_path);
          }
        }
      } catch (err) {
        console.warn('Browse folder API failed:', err);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderPath.trim()) return;

    setIsExecuting(true);
    setSplitResult(null);

    const widthNum = enforceWidth.trim() ? parseInt(enforceWidth.trim(), 10) : null;

    let result: { success: boolean; message?: string; output_images_count?: number };
    if (operationMode === 'stitch' && onExecuteStitch) {
      result = await onExecuteStitch({
        folderPath: folderPath.trim(),
        targetHeight: stitchHeight || 18000,
        enforceWidth: widthNum && widthNum > 0 ? widthNum : null,
        backupOriginal,
      });
    } else {
      const targetH = splitHeight || 5000;
      result = await onExecuteSplit({
        folderPath: folderPath.trim(),
        splitHeight: targetH,
        enforceWidth: widthNum && widthNum > 0 ? widthNum : null,
        backupOriginal,
      });
    }

    setIsExecuting(false);
    const finalCount = result.output_images_count ?? (result as any)?.total_pages ?? (result as any)?.count ?? 0;
    if (result.success) {
      setSplitResult({
        success: true,
        message: result.message || (operationMode === 'stitch' ? `รวมต่อภาพสำเร็จเรียบร้อย! (${finalCount} ไฟล์)` : `ตัดแบ่งภาพสำเร็จเรียบร้อย! (${finalCount} ไฟล์)`),
        count: finalCount,
      });
      // Refresh scan report after operation
      void handleScanFolder(folderPath.trim());
    } else {
      setSplitResult({
        success: false,
        message: result.message || 'การประมวลผลภาพล้มเหลว',
      });
    }
  };

  const splitHeightPresets = [3000, 4000, 5000, 6000, 8000];
  const stitchHeightPresets = [12000, 15000, 18000, 20000, 25000];
  const widthPresets = [
    { label: 'คงเดิม (Original)', value: '' },
    { label: '720px', value: '720' },
    { label: '800px', value: '800' },
    { label: '1080px', value: '1080' },
    { label: '1200px', value: '1200' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in font-sans">
      <div className="bg-zinc-950 border border-amber-500/40 rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Modal Header */}
        <div className="bg-gradient-to-r from-amber-950/40 via-zinc-900 to-zinc-950 border-b border-amber-500/30 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-inner">
              <Scissors className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>Smart Stitch & Image Splitter</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono font-normal">
                  Gutter Detection
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                รวมต่อภาพ หรือ ตัดแบ่งภาพเว็บตูนอัตโนมัติตามร่องขาว/ดำ ป้องกันภาพยาวเกินและไม่ผ่ากลางตัวการ์ตูน
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isProcessing || isExecuting}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1.5 rounded-lg hover:bg-zinc-800 cursor-pointer"
            title="ปิดหน้าต่าง"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1 text-slate-300 text-sm">
          
          {/* Operation Mode Tabs */}
          <div className="grid grid-cols-2 gap-2 p-1 bg-zinc-900 border border-zinc-800 rounded-xl">
            <button
              type="button"
              onClick={() => setOperationMode('stitch')}
              className={`py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                operationMode === 'stitch'
                  ? 'bg-amber-500 text-black shadow-md shadow-amber-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-800'
              }`}
            >
              <span>🪡 โหมดต่อภาพ (Smart Stitch / รวมเป็นแถบยาว)</span>
            </button>
            <button
              type="button"
              onClick={() => setOperationMode('split')}
              className={`py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                operationMode === 'split'
                  ? 'bg-amber-500 text-black shadow-md shadow-amber-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-800'
              }`}
            >
              <span>✂️ โหมดตัดแบ่งภาพ (Smart Split / ตัดเป็นหน้าย่อย)</span>
            </button>
          </div>

          {/* Step 1: Folder Selection */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Folder className="w-4 h-4 text-amber-400" />
              <span>โฟลเดอร์ภาพที่ต้องการประมวลผล (Target Folder)</span>
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="เช่น E:\Chapter Download\Webtoon\Chapter 01"
                className="flex-1 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 font-mono placeholder:text-slate-600 focus:outline-none shadow-inner"
              />
              <button
                type="button"
                onClick={handleBrowse}
                disabled={isExecuting || isScanning}
                className="px-3.5 py-2.5 rounded-xl bg-zinc-850 hover:bg-zinc-800 border border-zinc-700 hover:border-amber-500/50 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shrink-0"
              >
                <FolderOpen className="w-4 h-4 text-amber-400" />
                <span>เลือกโฟลเดอร์...</span>
              </button>
              <button
                type="button"
                onClick={() => handleScanFolder(folderPath)}
                disabled={!folderPath.trim() || isExecuting || isScanning}
                className="px-3.5 py-2.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shrink-0 disabled:opacity-40"
              >
                {isScanning ? <Loader2 className="w-4 h-4 animate-spin text-amber-400" /> : <Search className="w-4 h-4 text-amber-400" />}
                <span>สแกนภาพ</span>
              </button>
            </div>
            {scanError && (
              <p className="text-xs text-rose-400 flex items-center gap-1.5 bg-rose-950/40 p-2.5 rounded-lg border border-rose-900/50">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{scanError}</span>
              </p>
            )}
          </div>

          {/* Step 2: Scan Summary Card */}
          {scanReport && (
            <div className="bg-zinc-900/90 rounded-xl p-4 border border-zinc-800 space-y-3 shadow-inner">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
                <span className="text-xs font-bold text-slate-300 flex items-center gap-2">
                  <ImageIcon className="w-4 h-4 text-amber-400" />
                  <span>ผลการสแกนภาพในโฟลเดอร์</span>
                </span>
                <span className="text-xs text-slate-400">
                  พบทั้งหมด <strong className="text-amber-400 font-mono">{scanReport.total_images}</strong> ไฟล์
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800 text-center">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-bold">ความยาวสูงสุด</span>
                  <span className={`text-sm font-mono font-bold ${scanReport.max_height > 8000 ? 'text-amber-400' : 'text-slate-200'}`}>
                    {scanReport.max_height.toLocaleString()} px
                  </span>
                </div>

                <div className="bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800 text-center">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-bold">จำนวนไฟล์ในโฟลเดอร์</span>
                  <span className="text-sm font-mono font-bold text-sky-400">
                    {scanReport.total_images} ไฟล์
                  </span>
                </div>

                <div className="bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800 text-center col-span-2 sm:col-span-1">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-bold">ความกว้างแนะนำ</span>
                  <span className="text-sm font-mono font-bold text-emerald-400">
                    {scanReport.suggested_enforce_width} px
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Settings & Parameters */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-zinc-900/60 rounded-xl p-4 border border-zinc-800 space-y-4">
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-amber-400" />
                <span>
                  {operationMode === 'stitch' ? 'การตั้งค่าการรวมต่อภาพ (Smart Stitch Settings)' : 'การตั้งค่าการตัดแบ่ง (Smart Split Settings)'}
                </span>
              </span>

              {/* Target Height Selector depending on mode */}
              {operationMode === 'stitch' ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300">
                      ความยาวแถบยาวเป้าหมาย (Target Stitched Height):
                    </label>
                    <span className="text-xs font-mono font-bold text-amber-400">{stitchHeight.toLocaleString()} px</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {stitchHeightPresets.map((h) => (
                      <button
                        key={h}
                        type="button"
                        onClick={() => setStitchHeight(h)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition-all cursor-pointer ${
                          stitchHeight === h
                            ? 'bg-amber-500 text-black border-amber-400 shadow-md shadow-amber-500/20'
                            : 'bg-zinc-950 border-zinc-800 text-slate-300 hover:border-zinc-700'
                        }`}
                      >
                        {h.toLocaleString()} px
                      </button>
                    ))}
                  </div>
                  <input
                    type="range"
                    min={10000}
                    max={30000}
                    step={1000}
                    value={stitchHeight}
                    onChange={(e) => setStitchHeight(parseInt(e.target.value, 10))}
                    className="w-full accent-amber-500 cursor-pointer"
                  />
                  <p className="text-[11px] text-slate-400">
                    💡 ระบบจะรวมภาพสั้นในโฟลเดอร์ให้ยาวประมาณ {stitchHeight.toLocaleString()} px โดยตัดที่ร่องว่างระหว่างช่องการ์ตูนโดยอัตโนมัติ
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300">
                      ความยาวหน้าเป้าหมาย (Target Slice Height):
                    </label>
                    <span className="text-xs font-mono font-bold text-amber-400">{splitHeight.toLocaleString()} px</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {splitHeightPresets.map((h) => (
                      <button
                        key={h}
                        type="button"
                        onClick={() => setSplitHeight(h)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition-all cursor-pointer ${
                          splitHeight === h
                            ? 'bg-amber-500 text-black border-amber-400 shadow-md shadow-amber-500/20'
                            : 'bg-zinc-950 border-zinc-800 text-slate-300 hover:border-zinc-700'
                        }`}
                      >
                        {h.toLocaleString()} px
                      </button>
                    ))}
                  </div>
                  <input
                    type="range"
                    min={2000}
                    max={12000}
                    step={500}
                    value={splitHeight}
                    onChange={(e) => setSplitHeight(parseInt(e.target.value, 10))}
                    className="w-full accent-amber-500 cursor-pointer"
                  />
                </div>
              )}

              {/* Enforce Width Selector */}
              <div className="space-y-2 pt-1 border-t border-zinc-800">
                <label className="text-xs font-semibold text-slate-300 block">
                  ปรับขนาดความกว้างภาพ (Enforce Width / Resize):
                </label>
                <div className="flex flex-wrap gap-2">
                  {widthPresets.map((w) => (
                    <button
                      key={w.label}
                      type="button"
                      onClick={() => setEnforceWidth(w.value)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                        enforceWidth === w.value
                          ? 'bg-amber-500 text-black border-amber-400 font-bold shadow-md shadow-amber-500/20'
                          : 'bg-zinc-950 border-zinc-800 text-slate-300 hover:border-zinc-700'
                      }`}
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Backup Originals Checkbox */}
              <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer pt-1 border-t border-zinc-800 select-none">
                <input
                  type="checkbox"
                  checked={backupOriginal}
                  onChange={(e) => setBackupOriginal(e.target.checked)}
                  className="rounded border-zinc-700 bg-zinc-900 text-amber-500 focus:ring-amber-500/50 w-4 h-4 cursor-pointer"
                />
                <span className="font-medium">
                  สำรองไฟล์ภาพต้นฉบับไว้ในโฟลเดอร์ <code className="text-[11px] text-amber-300 bg-zinc-950 px-1.5 py-0.5 rounded">_original_raw/</code> (ปลอดภัย 100%)
                </span>
              </label>
            </div>

            {/* Split Result Banner */}
            {splitResult && (
              <div className={`p-3.5 rounded-xl border flex items-center gap-3 animate-slide-in ${
                splitResult.success 
                  ? 'bg-emerald-950/80 border-emerald-500/40 text-emerald-200' 
                  : 'bg-rose-950/80 border-rose-500/40 text-rose-200'
              }`}>
                {splitResult.success ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
                )}
                <div className="flex-1 text-xs">
                  <p className="font-bold">{splitResult.message}</p>
                  {splitResult.count !== undefined && (
                    <p className="text-[11px] opacity-80 mt-0.5">
                      จำนวนหน้าในโปรเจกต์ปัจจุบัน: {splitResult.count} หน้า
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isExecuting}
                className="px-4 py-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 text-slate-400 hover:text-slate-200 text-xs font-semibold transition-all cursor-pointer"
              >
                ปิด
              </button>
              <button
                type="submit"
                disabled={!folderPath.trim() || isExecuting || isScanning}
                className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-black font-bold text-xs flex items-center gap-2 shadow-lg shadow-amber-500/20 active:scale-95 transition-all cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>กำลังตรวจหาร่องขาวและประมวลผลภาพ...</span>
                  </>
                ) : operationMode === 'stitch' ? (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>เริ่มต่อภาพ (Smart Stitch)</span>
                  </>
                ) : (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>เริ่มตัดแบ่งภาพ (Smart Split)</span>
                  </>
                )}
              </button>
            </div>
          </form>

        </div>
      </div>
    </div>
  );
};
