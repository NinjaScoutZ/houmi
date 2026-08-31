import React, { useState } from 'react';
import { Rocket, Sparkles, X, CheckCircle2, Info, Loader2, RotateCw } from 'lucide-react';
import { apiFetch } from '../api/runtime';

interface UpdateModalProps {
  isOpen: boolean;
  manifest: {
    current_version: string;
    latest_version: string;
    patch_notes?: string;
    download_size_mb?: number;
  } | null;
  onClose: () => void;
}

export const UpdateModal: React.FC<UpdateModalProps> = ({
  isOpen,
  manifest,
  onClose,
}) => {
  const [isUpdating, setIsUpdating] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<string | null>(null);

  if (!isOpen || !manifest) return null;

  const handleApplyUpdate = async () => {
    setIsUpdating(true);
    setUpdateStatus('กำลังดาวน์โหลดแพตช์อัปเดตใหม่ในระบบ...');

    try {
      const res = await apiFetch('/api/system/apply-patch', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (data.status === 'success') {
        localStorage.setItem('houmi_just_updated_version', manifest.latest_version);
        localStorage.setItem('houmi_just_updated_notes', manifest.patch_notes || '');
        setIsSuccess(true);
        setUpdateStatus(data.message || 'ดาวน์โหลดและติดตั้งแพตช์สำเร็จแล้ว! กำลังรีโหลดแอปใน 3 วินาที...');
        setTimeout(() => {
          window.location.reload();
        }, 3000);
      } else {
        setUpdateStatus(`อัปเดตไม่สำเร็จ: ${data.message || 'ข้อผิดพลาดระบบ'}`);
      }
    } catch (err: any) {
      setUpdateStatus(`อัปเดตไม่สำเร็จ: ${err.message || 'ข้อผิดพลาดระบบ'}`);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 font-sans select-none animate-fade-in">
      <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden text-slate-100 p-6 space-y-5 animate-in zoom-in-95">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center font-bold shadow-inner font-pixel">
              <Rocket size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-white font-pixel uppercase tracking-wider">
                พบอัปเดตเวอร์ชันใหม่! (v{manifest.latest_version})
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                เวอร์ชันปัจจุบัน: v{manifest.current_version} &rarr; เวอร์ชันล่าสุด: v{manifest.latest_version}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 space-y-2">
          <h3 className="text-[11px] font-bold text-amber-400 uppercase tracking-wider font-pixel flex items-center gap-1.5">
            <Sparkles size={12} />
            <span>รายละเอียดสิ่งที่ปรับปรุง (Patch Notes)</span>
          </h3>
          <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
            {manifest.patch_notes || 'การปรับปรุงประสิทธิภาพและแก้ไขบัคทั่วไป'}
          </p>
          {manifest.download_size_mb && (
            <p className="text-[11px] text-slate-500 pt-2 border-t border-zinc-800 font-mono">
              ขนาดดาวน์โหลดประมาณ: {manifest.download_size_mb} MB
            </p>
          )}
        </div>

        {updateStatus && (
          <div className={`p-3 border rounded-xl text-xs flex items-center gap-2 ${
            isSuccess ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300' : 'bg-amber-500/15 border-amber-500/40 text-amber-300'
          }`}>
            {isSuccess ? <CheckCircle2 size={15} /> : <Info size={15} />}
            <span>{updateStatus}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2 font-pixel">
          {!isSuccess && (
            <button
              onClick={onClose}
              className="px-4 py-2 bg-zinc-850 hover:bg-zinc-800 text-slate-300 font-bold border border-zinc-700 rounded-xl text-xs transition cursor-pointer"
            >
              ไว้ทีหลัง
            </button>
          )}
          {isSuccess ? (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-xl text-xs shadow-lg shadow-emerald-500/20 transition cursor-pointer flex items-center gap-2"
            >
              <RotateCw size={14} />
              <span>รีโหลดเปิดใช้งานเวอร์ชันใหม่ทันที (Reload App Now)</span>
            </button>
          ) : (
            <button
              onClick={handleApplyUpdate}
              disabled={isUpdating}
              className="px-5 py-2.5 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-black font-bold rounded-xl text-xs shadow-lg shadow-amber-500/20 transition cursor-pointer flex items-center gap-2 disabled:opacity-50"
            >
              {isUpdating ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>กำลังอัปเดตแพตช์ในระบบ...</span>
                </>
              ) : (
                <>
                  <Sparkles size={14} />
                  <span>อัปเดตแพตช์ผ่านระบบทันที (Update Patch)</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
