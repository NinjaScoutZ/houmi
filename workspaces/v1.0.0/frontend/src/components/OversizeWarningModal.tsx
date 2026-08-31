import React, { useState } from 'react';
import { AlertTriangle, Scissors, X, Check, ShieldAlert, Folder, Image as ImageIcon } from 'lucide-react';

export interface OversizeScanReport {
  has_oversize: boolean;
  threshold_height: number;
  total_images: number;
  oversize_count: number;
  max_height: number;
  oversize_files: Array<{
    filename: string;
    path: string;
    width: number;
    height: number;
  }>;
  suggested_split_height: number;
  suggested_enforce_width: number;
}

interface OversizeWarningModalProps {
  isOpen: boolean;
  folderPath: string;
  scanReport: OversizeScanReport | null;
  isProcessing?: boolean;
  onReject: () => void;
  onConfirmSplit: (options: {
    splitHeight: number;
    enforceWidth: number | null;
    backupOriginal: boolean;
  }) => void;
  onProceedAnyway: () => void;
}

export const OversizeWarningModal: React.FC<OversizeWarningModalProps> = ({
  isOpen,
  folderPath,
  scanReport,
  isProcessing = false,
  onReject,
  onConfirmSplit,
  onProceedAnyway,
}) => {
  const [splitHeight, setSplitHeight] = useState<number>(5000);
  const [enforceWidth, setEnforceWidth] = useState<string>('');
  const [backupOriginal, setBackupOriginal] = useState<boolean>(true);
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  if (!isOpen || !scanReport) return null;

  const folderName = folderPath.split(/[/\\]/).filter(Boolean).pop() || folderPath;

  const handleSplitSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const widthNum = enforceWidth.trim() ? parseInt(enforceWidth.trim(), 10) : null;
    onConfirmSplit({
      splitHeight: splitHeight || 5000,
      enforceWidth: widthNum && widthNum > 0 ? widthNum : null,
      backupOriginal,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in font-sans select-none">
      <div className="bg-zinc-950 border border-amber-500/40 rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95">
        {/* Header */}
        <div className="bg-amber-950/40 border-b border-amber-500/30 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2 font-pixel uppercase tracking-wider">
                ตรวจพบภาพเว็บตูนขนาดยาวพิเศษ
              </h3>
              <p className="text-[11px] text-amber-300/80 font-mono">
                Oversize Warning ({scanReport.oversize_count} of {scanReport.total_images} files exceed {scanReport.threshold_height.toLocaleString()}px)
              </p>
            </div>
          </div>
          <button
            onClick={onReject}
            disabled={isProcessing}
            className="text-zinc-400 hover:text-white transition-colors p-1.5 rounded-lg hover:bg-zinc-800 cursor-pointer"
            title="ยกเลิกและปิด"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1 text-slate-300 text-sm">
          {/* Explanation Banner */}
          <div className="bg-zinc-900/80 rounded-xl p-4 border border-zinc-800 space-y-2">
            <div className="flex items-center gap-2 text-slate-200 font-semibold font-pixel text-xs">
              <Folder className="w-4 h-4 text-amber-400" />
              <span>โฟลเดอร์: <code className="text-xs bg-zinc-950 px-2 py-0.5 rounded text-amber-300 font-mono">{folderName}</code></span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              รูปภาพในโฟลเดอร์นี้มีความยาวสูงสุดถึง <strong className="text-amber-400 font-mono">{scanReport.max_height.toLocaleString()} px</strong> ซึ่งอาจส่งผลให้การประมวลผล Inpainting และการเปิดหน้าจอช้า แนะนำให้ใช้ระบบ <strong className="text-emerald-400">Smart Stitch & Split</strong> ตัดแบ่งภาพเป็นหน้ามาตรฐาน (~5,000 px) อัตโนมัติ โดยระบบจะตัดตามช่องว่างขาว/ดำ ไม่ตัดผ่ากลางตัวการ์ตูนหรือช่องคำพูด
            </p>
          </div>

          {/* List of Oversize Files */}
          <div className="space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-pixel">
              รายการภาพที่ยาวเกินกำหนด ({scanReport.oversize_files.length} ภาพ)
            </span>
            <div className="bg-zinc-900/60 rounded-xl border border-zinc-800 max-h-32 overflow-y-auto p-2 space-y-1">
              {scanReport.oversize_files.map((file, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-zinc-800/60 transition-colors">
                  <div className="flex items-center gap-2 truncate">
                    <ImageIcon className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span className="truncate text-slate-300 text-[11.5px]">{file.filename}</span>
                  </div>
                  <span className="font-mono text-amber-400 font-semibold shrink-0 ml-3 text-[11px]">
                    {file.width} × {file.height.toLocaleString()} px
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Split Configuration Controls */}
          <form id="smart-split-form" onSubmit={handleSplitSubmit} className="space-y-4 pt-2 font-pixel">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5 uppercase tracking-wider text-[10.5px]">
                  ความสูงเป้าหมายต่อหน้า (Split Height)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={2000}
                    max={15000}
                    step={500}
                    value={splitHeight}
                    onChange={(e) => setSplitHeight(parseInt(e.target.value, 10) || 5000)}
                    disabled={isProcessing}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-amber-500"
                  />
                  <span className="text-xs text-slate-400 shrink-0 font-mono">px</span>
                </div>
                {/* Presets */}
                <div className="flex gap-1.5 mt-2">
                  {[4000, 5000, 7500, 10000].map((val) => (
                    <button
                      type="button"
                      key={val}
                      onClick={() => setSplitHeight(val)}
                      className={`text-[10px] font-mono px-2 py-0.5 rounded-lg transition-colors cursor-pointer ${
                        splitHeight === val
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                          : 'bg-zinc-900 border border-zinc-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {val / 1000}k
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5 uppercase tracking-wider text-[10.5px]">
                  ปรับความกว้างคงที่ (Enforce Width) <span className="text-slate-500 font-sans text-[10px]">(ไม่บังคับ)</span>
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={300}
                    max={4000}
                    placeholder="ความกว้างเดิม"
                    value={enforceWidth}
                    onChange={(e) => setEnforceWidth(e.target.value)}
                    disabled={isProcessing}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder:text-slate-600 font-mono focus:outline-none focus:border-amber-500"
                  />
                  <span className="text-xs text-slate-400 shrink-0 font-mono">px</span>
                </div>
                <div className="flex gap-1.5 mt-2">
                  <button
                    type="button"
                    onClick={() => setEnforceWidth('')}
                    className={`text-[10px] px-2 py-0.5 rounded-lg transition-colors cursor-pointer ${
                      !enforceWidth
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                        : 'bg-zinc-900 border border-zinc-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    เดิม
                  </button>
                  {[720, 800, 1080].map((val) => (
                    <button
                      type="button"
                      key={val}
                      onClick={() => setEnforceWidth(String(val))}
                      className={`text-[10px] font-mono px-2 py-0.5 rounded-lg transition-colors cursor-pointer ${
                        enforceWidth === String(val)
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                          : 'bg-zinc-900 border border-zinc-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {val}px
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Backup Checkbox */}
            <div className="flex items-center gap-2.5 pt-1 font-sans">
              <input
                type="checkbox"
                id="backup-checkbox"
                checked={backupOriginal}
                onChange={(e) => setBackupOriginal(e.target.checked)}
                disabled={isProcessing}
                className="w-4 h-4 rounded border-zinc-700 bg-zinc-900 accent-amber-400"
              />
              <label htmlFor="backup-checkbox" className="text-xs text-slate-300 select-none cursor-pointer">
                สำรองภาพต้นฉบับไว้ในโฟลเดอร์ <code className="text-amber-300 bg-zinc-900 px-1 py-0.5 rounded border border-zinc-800">_original_raw/</code> เพื่อความปลอดภัย
              </label>
            </div>
          </form>
        </div>

        {/* Footer Actions */}
        <div className="bg-zinc-900/80 border-t border-zinc-800 px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 font-pixel">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              type="button"
              onClick={onReject}
              disabled={isProcessing}
              className="w-full sm:w-auto px-4 py-2 rounded-xl text-xs font-bold bg-zinc-850 hover:bg-zinc-800 text-slate-300 hover:text-white transition-colors border border-zinc-700 cursor-pointer"
            >
              ปฏิเสธ (ไม่เปิดโปรเจกต์)
            </button>

            {showAdvanced && (
              <button
                type="button"
                onClick={onProceedAnyway}
                disabled={isProcessing}
                className="px-3 py-2 rounded-xl text-xs font-medium text-amber-400/80 hover:text-amber-300 hover:bg-amber-500/10 transition-colors cursor-pointer"
                title="เปิดโปรเจกต์ด้วยภาพเดิมโดยไม่ตัดแบ่ง (อาจทำให้เครื่องทำงานหนัก)"
              >
                เปิดตามเดิม
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            {!showAdvanced && (
              <button
                type="button"
                onClick={() => setShowAdvanced(true)}
                className="text-[11px] text-slate-500 hover:text-slate-400 transition-colors cursor-pointer"
              >
                ตัวเลือกเพิ่มเติม...
              </button>
            )}
            <button
              type="submit"
              form="smart-split-form"
              disabled={isProcessing}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black shadow-lg shadow-amber-500/20 transition-all cursor-pointer disabled:opacity-50"
            >
              {isProcessing ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                  <span>กำลังแบ่งภาพ...</span>
                </>
              ) : (
                <>
                  <Scissors className="w-3.5 h-3.5" />
                  <span>ยินยอม & แบ่งภาพอัตโนมัติ</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
