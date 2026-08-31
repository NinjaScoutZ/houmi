import React, { useState, useEffect } from 'react';
import { Terminal, Bug, X, Trash2 } from 'lucide-react';
import { getWebSocketOrigin } from '../api/runtime';

interface DebugConsoleDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DebugConsoleDrawer: React.FC<DebugConsoleDrawerProps> = ({
  isOpen,
  onClose,
}) => {
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    const wsUrl = `${getWebSocketOrigin()}/ws/telemetry`;
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      setIsConnected(true);
      setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] 🟢 Admin Live Telemetry Connected to ${wsUrl}`]);
      socket.send(JSON.stringify({ type: 'ping', client: 'HoumiAdminConsole' }));
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] 📡 ${JSON.stringify(data)}`]);
      } catch {
        setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] 📄 ${event.data}`]);
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
      setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] 🔴 Admin Live Telemetry Disconnected.`]);
    };

    return () => {
      socket.close();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-[9999] w-full max-w-xl bg-zinc-950/95 border-l border-zinc-800 shadow-2xl backdrop-blur-xl flex flex-col text-slate-100 animate-in slide-in-from-right duration-200 font-sans select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 bg-zinc-900/80">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center font-bold font-pixel">
            <Bug size={16} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2 font-pixel uppercase tracking-wider">
              <span>Admin Live Debug Console</span>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`}></span>
            </h2>
            <p className="text-[11px] text-slate-400">
              สถานะ: {isConnected ? 'เชื่อมต่อเซิร์ฟเวอร์เรียบร้อย (Online Telemetry Active)' : 'ไม่ได้เชื่อมต่อ'}
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

      {/* Logs Viewport */}
      <div className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-zinc-950 text-zinc-300">
        {logs.length === 0 ? (
          <div className="text-slate-600 text-center pt-10 italic">
            กำลังรอ Log ข้อมูลการทำงานและ Diagnostic Telemetry จากเซิร์ฟเวอร์...
          </div>
        ) : (
          logs.map((log, idx) => (
            <div key={idx} className="hover:bg-zinc-900/60 p-1.5 rounded-lg border border-transparent hover:border-zinc-800 transition whitespace-pre-wrap break-all">
              {log}
            </div>
          ))
        )}
      </div>

      {/* Footer controls */}
      <div className="p-3 border-t border-zinc-800 bg-zinc-900/80 flex items-center justify-between font-pixel">
        <span className="text-[11px] text-slate-500 flex items-center gap-1">
          <Terminal size={12} className="text-amber-400" />
          <span>Live Server Stream &bull; Admin Mode</span>
        </span>
        <button
          onClick={() => setLogs([])}
          className="px-3 py-1 bg-zinc-850 hover:bg-zinc-800 border border-zinc-700 text-slate-300 hover:text-rose-300 rounded-lg text-xs transition cursor-pointer flex items-center gap-1"
        >
          <Trash2 size={12} />
          <span>เคลียร์ Log</span>
        </button>
      </div>
    </div>
  );
};
