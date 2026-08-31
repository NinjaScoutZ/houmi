import React, { useState, useEffect } from 'react';
import { Sparkles, Cpu, FileText, CheckCircle2, AlertTriangle, Layers, X, Minimize2, Maximize2 } from 'lucide-react';

export interface DobkleProgressData {
  status: 'running' | 'success' | 'failed' | 'completed';
  phase: 'building_pdf' | 'ai_inference' | 'parsing_and_styling' | 'fallback' | 'completed';
  phase_title: string;
  message: string;
  progress: number;
  completed_blocks: number;
  total_blocks: number;
  total_pages: number;
}

interface DobkleOcrProgressModalProps {
  isOpen: boolean;
  data: DobkleProgressData | null;
  onClose: () => void;
}

export const DobkleOcrProgressModal: React.FC<DobkleOcrProgressModalProps> = ({ isOpen, data, onClose }) => {
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [logs, setLogs] = useState<{ time: string; text: string }[]>([]);
  const [isMinimized, setIsMinimized] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) {
      setElapsedSeconds(0);
      setLogs([]);
      setIsMinimized(false);
      return;
    }

    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen]);

  useEffect(() => {
    if (data?.message) {
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
      setLogs((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].text === data.message) {
          return prev;
        }
        return [...prev.slice(-6), { time: timeStr, text: data.message }];
      });
    }
  }, [data?.message]);

  if (!isOpen || !data) return null;

  const pct = Math.min(100, Math.max(0, Math.round((data.progress || 0) * 100)));
  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const steps = [
    { key: 'building_pdf', label: '1. เตรียม PDF ทั้งตอน', icon: FileText },
    { key: 'ai_inference', label: '2. Gemini VLM Ingest', icon: Cpu },
    { key: 'parsing_and_styling', label: '3. สไตล์ & ฟอนต์', icon: Sparkles },
    { key: 'fallback', label: '4. ตรวจเก็บตก', icon: CheckCircle2 },
  ];

  const getStepStatus = (stepKey: string) => {
    const order = ['building_pdf', 'ai_inference', 'parsing_and_styling', 'fallback', 'completed'];
    const currentIdx = order.indexOf(data.phase || 'building_pdf');
    const stepIdx = order.indexOf(stepKey);

    if (data.phase === 'completed' || currentIdx > stepIdx) return 'completed';
    if (currentIdx === stepIdx) return 'active';
    return 'pending';
  };

  if (isMinimized) {
    return (
      <div className="fixed bottom-6 right-6 z-50 bg-zinc-950/95 border border-yellow-500/50 rounded-xl p-3 shadow-2xl backdrop-blur-md flex items-center gap-3 animate-fade-in text-xs font-pixel">
        <div className="w-3 h-3 rounded-full bg-yellow-400 animate-ping" />
        <div>
          <div className="text-yellow-400 font-bold">{data.phase_title}</div>
          <div className="text-[10px] text-slate-400">{pct}% — {formatTimer(elapsedSeconds)}s</div>
        </div>
        <button
          onClick={() => setIsMinimized(false)}
          className="p-1 text-slate-400 hover:text-white rounded transition"
          title="ขยายหน้าต่าง"
        >
          <Maximize2 size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in">
      <div className="w-full max-w-lg bg-gradient-to-b from-zinc-950 via-zinc-900 to-zinc-950 border border-yellow-500/40 rounded-2xl shadow-[0_0_50px_rgba(234,179,8,0.15)] overflow-hidden text-slate-200 font-pixel">
        
        {/* Header Bar */}
        <div className="px-5 py-3.5 border-b border-zinc-800/80 bg-zinc-950/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-yellow-500/15 border border-yellow-500/30 text-yellow-400 animate-pulse">
              <Sparkles size={16} />
            </div>
            <div>
              <h3 className="text-xs font-bold text-yellow-300 tracking-wider flex items-center gap-2">
                DOBKLE OCR AI — REALTIME PIPELINE
              </h3>
              <p className="text-[10px] text-slate-400">ประมวลผลทั้งตอนใน 1 Request (Single Multi-Page PDF)</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-yellow-400 bg-yellow-950/50 border border-yellow-500/30 px-2 py-0.5 rounded">
              ⏱️ {formatTimer(elapsedSeconds)}
            </span>
            <button
              onClick={() => setIsMinimized(true)}
              className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition"
              title="ย่อหน้าต่าง"
            >
              <Minimize2 size={14} />
            </button>
            {data.phase === 'completed' && (
              <button
                onClick={onClose}
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-zinc-800 transition"
                title="ปิดหน้าต่าง"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Body Content */}
        <div className="p-6 flex flex-col gap-5">
          
          {/* Realtime Stepper */}
          <div className="grid grid-cols-4 gap-2">
            {steps.map((s) => {
              const status = getStepStatus(s.key);
              const Icon = s.icon;
              return (
                <div
                  key={s.key}
                  className={`flex flex-col items-center text-center p-2.5 rounded-xl border transition-all ${
                    status === 'active'
                      ? 'bg-yellow-500/15 border-yellow-500 text-yellow-300 shadow-[0_0_15px_rgba(234,179,8,0.2)] scale-102'
                      : status === 'completed'
                      ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-400'
                      : 'bg-zinc-950/50 border-zinc-800 text-slate-500'
                  }`}
                >
                  <div className={`p-1.5 rounded-full mb-1.5 ${
                    status === 'active' ? 'bg-yellow-400 text-black animate-spin' : status === 'completed' ? 'bg-emerald-500 text-black' : 'bg-zinc-800 text-slate-400'
                  }`}>
                    <Icon size={12} />
                  </div>
                  <span className="text-[9px] font-bold tracking-tight">{s.label}</span>
                </div>
              );
            })}
          </div>

          {/* Current Stage Status Box */}
          <div className="p-3.5 bg-zinc-950 border border-zinc-800/90 rounded-xl flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-yellow-400 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-yellow-400 animate-ping" />
                {data.phase_title}
              </span>
              <span className="font-mono text-[11px] text-slate-300 font-bold">
                {pct}%
              </span>
            </div>

            {/* Glowing Shimmer Progress Bar */}
            <div className="w-full bg-zinc-900 border border-zinc-800 h-2.5 rounded-full overflow-hidden p-0.5">
              <div
                className="h-full rounded-full bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-300 transition-all duration-500 shadow-[0_0_12px_rgba(234,179,8,0.8)]"
                style={{ width: `${pct}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1">
              <span>{data.message}</span>
              {data.total_blocks > 0 && (
                <span className="font-mono text-yellow-400 font-bold shrink-0 ml-2">
                  📦 {data.completed_blocks > 0 ? data.completed_blocks : data.total_blocks} บอลลูน ({data.total_pages || 1} หน้า)
                </span>
              )}
            </div>
          </div>

          {/* Realtime Terminal Log */}
          <div className="bg-black/90 border border-zinc-800/80 rounded-xl p-3 flex flex-col gap-1.5 text-[9px] font-mono text-slate-400 max-h-28 overflow-y-auto">
            <div className="text-[8px] text-slate-500 uppercase tracking-widest pb-1 border-b border-zinc-900 flex items-center gap-1">
              <span className="text-emerald-400">●</span> REALTIME PIPELINE ACTIVITY STREAM
            </div>
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-2 leading-tight">
                <span className="text-slate-600">[{log.time}]</span>
                <span className={i === logs.length - 1 ? 'text-yellow-300 font-bold' : 'text-slate-400'}>
                  {log.text}
                </span>
              </div>
            ))}
          </div>

          {/* Completed Footer Action */}
          {data.phase === 'completed' && (
            <button
              onClick={onClose}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-400 text-black font-extrabold text-xs shadow-lg shadow-emerald-500/20 hover:brightness-110 transition cursor-pointer active:scale-98"
            >
              🎉 เสร็จสิ้นสมบูรณ์! เปิดดูข้อความ
            </button>
          )}

        </div>
      </div>
    </div>
  );
};
