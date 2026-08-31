import { useState } from 'react';
import { AlertCircle, CheckCircle2, Download, RefreshCw } from 'lucide-react';
import { checkForPatch, installPatch, type PatchCheckResult } from '../desktop/updater';
import { HOUMI_RELEASE_CHANNEL, HOUMI_VERSION_LABEL } from '../version';

interface PatchUpdateButtonProps {
  updatesEnabled: boolean;
}

export function PatchUpdateButton({ updatesEnabled }: PatchUpdateButtonProps) {
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<PatchCheckResult | null>(null);

  const runCheck = async () => {
    setChecking(true);
    setResult(null);
    try {
      setResult(await checkForPatch(updatesEnabled));
    } finally {
      setChecking(false);
    }
  };

  const install = async () => {
    if (!result || result.status !== 'available') return;
    setInstalling(true);
    try {
      await installPatch(result, setProgress);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setResult({ status: 'error', message });
      setInstalling(false);
    }
  };

  const targetVer = result?.status === 'available'
    ? (result.info?.latest_version || result.update?.version || '')
    : '';

  const message = result?.status === 'current'
    ? `ใช้งานรุ่นล่าสุด ${HOUMI_VERSION_LABEL}`
    : result?.status === 'disabled'
      ? 'Patch ยังไม่เปิด'
      : result?.status === 'unsupported'
        ? 'Patch อัตโนมัติใช้ได้เฉพาะตัวติดตั้ง Desktop'
        : result?.status === 'error'
          ? `ตรวจ Patch ไม่สำเร็จ: ${result.message}`
          : result?.status === 'available'
            ? `พบรุ่นใหม่ v${targetVer}`
            : '';

  return (
    <div className="flex items-center gap-1.5">
      <span title={`Houmi Studio ${HOUMI_VERSION_LABEL} · ${HOUMI_RELEASE_CHANNEL}`} className="text-[9px] text-slate-500 font-mono">
        {HOUMI_VERSION_LABEL}
      </span>
      <button
        type="button"
        onClick={result?.status === 'available' ? install : runCheck}
        disabled={checking || installing}
        title={message || 'ตรวจสอบ Patch'}
        className="inline-flex items-center gap-1 rounded border border-zinc-800 px-1.5 py-0.5 text-[9px] text-slate-400 hover:border-yellow-500/40 hover:text-yellow-300 disabled:opacity-50"
      >
        {installing ? <Download size={10} /> : result?.status === 'available' ? <Download size={10} /> : <RefreshCw size={10} className={checking ? 'animate-spin' : ''} />}
        {installing ? (progress == null ? 'PATCH…' : `PATCH ${progress}%`) : result?.status === 'available' ? 'INSTALL' : 'PATCH'}
      </button>
      {result?.status === 'current' && <CheckCircle2 size={11} className="text-emerald-400" />}
      {result?.status === 'error' && <AlertCircle size={11} className="text-amber-400" />}
    </div>
  );
}
