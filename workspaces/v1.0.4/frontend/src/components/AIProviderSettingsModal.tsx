import React, { useState, useEffect } from 'react';
import { Key, Shield, Plus, Trash2, CheckCircle, AlertTriangle, ArrowUp, ArrowDown, X, Sparkles } from 'lucide-react';
import { apiFetch } from '../api/runtime';
import { ConfirmModal } from './ConfirmModal';

export interface ApiKeyItem {
  id: string;
  label: string;
  masked_key: string;
  provider: string;
  enabled: boolean;
  priority: number;
  status: 'active' | 'cooldown' | 'error';
  last_used?: string;
  error_message?: string;
}

export interface AIProviderSettingsPanelProps {
  showToast?: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export const AIProviderSettingsPanel: React.FC<AIProviderSettingsPanelProps> = ({ showToast: parentShowToast }) => {
  const showToast = (msg: string, type?: 'info' | 'success' | 'warning' | 'error') => {
    const mappedType = type === 'warning' ? 'info' : type;
    parentShowToast?.(msg, mappedType);
  };
  const [provider, setProvider] = useState<string>('auto');
  const [model, setModel] = useState<string>('gemini-3.7-flash');
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [loading, setLoading] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await apiFetch('/api/settings/ai-provider');
      if (res.ok) {
        const data = await res.json();
        setProvider(data.provider || 'auto');
        setModel(data.model || 'gemini-3.7-flash');
        setKeys(data.keys || []);
      }
    } catch (err: any) {
      console.error('Failed to fetch AI Provider settings:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchSettings();
  }, []);

  const handleProviderChange = async (newProv: string) => {
    setProvider(newProv);
    try {
      await apiFetch('/api/settings/ai-provider', {
        method: 'PUT',
        body: JSON.stringify({ provider: newProv }),
      });
      showToast(`เปลี่ยน AI Provider เป็น ${newProv} เรียบร้อย`, 'success');
    } catch (err: any) {
      showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
    }
  };

  const handleModelChange = async (newModel: string) => {
    setModel(newModel);
    try {
      await apiFetch('/api/settings/ai-provider', {
        method: 'PUT',
        body: JSON.stringify({ model: newModel }),
      });
      showToast(`เปลี่ยนโมเดล AI เป็น ${newModel} เรียบร้อย`, 'success');
    } catch (err: any) {
      showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
    }
  };

  const handleAddKey = async () => {
    if (!newKey.trim()) {
      showToast('กรุณากรอก API Key', 'warning');
      return;
    }
    try {
      await apiFetch('/api/settings/ai-provider/keys', {
        method: 'POST',
        body: JSON.stringify({
          key: newKey.trim(),
          label: newLabel.trim() || `Key #${keys.length + 1}`,
          provider: 'google_api',
        }),
      });
      setNewKey('');
      setNewLabel('');
      showToast('เพิ่ม API Key เข้าสู่ Failover Pool สำเร็จ!', 'success');
      await fetchSettings();
    } catch (err: any) {
      showToast(`เพิ่ม Key ล้มเหลว: ${err.message}`, 'error');
    }
  };

  const handleDeleteKey = async (id: string) => {
    try {
      await apiFetch(`/api/settings/ai-provider/keys/${id}`, { method: 'DELETE' });
      showToast('ลบ API Key เรียบร้อย', 'info');
      await fetchSettings();
    } catch (err: any) {
      showToast(`ลบ Key ล้มเหลว: ${err.message}`, 'error');
    }
  };

  const handleToggleKey = async (id: string, enabled: boolean) => {
    try {
      await apiFetch(`/api/settings/ai-provider/keys/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      });
      await fetchSettings();
    } catch (err: any) {
      showToast(`อัปเดตสถานะ Key ล้มเหลว: ${err.message}`, 'error');
    }
  };

  const handleMovePriority = async (index: number, direction: 'up' | 'down') => {
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= keys.length) return;

    const updatedKeys = [...keys];
    const [movedKey] = updatedKeys.splice(index, 1);
    updatedKeys.splice(targetIndex, 0, movedKey);

    setKeys(updatedKeys);
    try {
      await apiFetch('/api/settings/ai-provider/keys/reorder', {
        method: 'POST',
        body: JSON.stringify({ key_ids: updatedKeys.map(k => k.id) }),
      });
      showToast('ปรับลำดับความสำคัญ (Priority) เรียบร้อย', 'success');
      await fetchSettings();
    } catch (err: any) {
      showToast(`ปรับลำดับล้มเหลว: ${err.message}`, 'error');
    }
  };

  return (
    <div className="flex flex-col gap-4 text-xs font-sans select-none">
      {/* Provider Selection */}
      <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-lg flex flex-col gap-2 font-pixel">
        <label className="font-bold text-slate-300 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <Key size={13} className="text-amber-400" /> AI Engine / Provider Mode
        </label>
        <div className="grid grid-cols-3 gap-2 pt-1">
          {[
            { id: 'auto', name: '⚡ Auto Failover', desc: 'สลับ Key อัตโนมัติเมื่อติด Rate Limit (429)' },
            { id: 'google_api', name: '🔑 Google Gemini API', desc: 'ใช้ API Key Pool ตามลำดับ Priority' },
            { id: 'agy', name: '🧠 Antigravity SDK', desc: 'ใช้โมเดลในเครื่อง / AGY CLI' },
          ].map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => void handleProviderChange(p.id)}
              className={`p-2.5 rounded-md border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                provider === p.id
                  ? 'border-amber-500 bg-amber-500/15 text-amber-300 shadow-sm shadow-amber-500/20 font-bold'
                  : 'border-zinc-800 bg-zinc-950 text-slate-400 hover:border-zinc-700 hover:text-slate-200'
              }`}
            >
              <span className="text-[11px] text-white font-bold">{p.name}</span>
              <span className="text-[9px] text-slate-400 leading-tight font-sans">{p.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Model Selection */}
      <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-lg flex flex-col gap-2 font-pixel">
        <div className="flex items-center justify-between">
          <label className="font-bold text-slate-300 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Sparkles size={13} className="text-yellow-400" /> AI Vision & Translation Model
          </label>
          <span className="text-[10px] text-emerald-400 font-mono font-bold">⚡ Fast & Cheap</span>
        </div>
        <select
          value={model}
          onChange={(e) => void handleModelChange(e.target.value)}
          className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 rounded-md text-xs outline-none focus:border-amber-500 font-pixel cursor-pointer"
        >
          <option value="gemini-3.7-flash">Gemini 3.7 Flash (เร็วที่สุด ฉลาด ประหยัดโทเค็น - แนะนำ)</option>
          <option value="gemini-3.6-flash">Gemini 3.6 Flash (ประหยัด รวดเร็ว มีประสิทธิภาพ)</option>
          <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
          <option value="gemini-3.1-pro">Gemini 3.1 Pro (โมเดลขนาดใหญ่)</option>
          <option value="Claude Sonnet 4.6 (Thinking)">Claude Sonnet 4.6 (Thinking)</option>
        </select>
        <span className="text-[9.5px] text-slate-400 font-sans">
          โมเดล 3.7 และ 3.6 รองรับทั้งการอ่านข้อความแบบ OCR (Grid Batch) และวิเคราะห์สไตล์บทพูดได้อย่างรวดเร็ว
        </span>
      </div>

      {/* Add New Key Form */}
      <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-lg flex flex-col gap-2.5 font-pixel">
        <label className="font-bold text-slate-300 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <Plus size={13} className="text-emerald-400" /> เพิ่ม Gemini API Key เข้า Failover Pool
        </label>
        <div className="grid grid-cols-3 gap-2 font-sans">
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="ชื่อ Key (เช่น Key สำรอง #1)"
            className="bg-zinc-950 border border-zinc-800 text-white px-2.5 py-1.5 rounded-md text-xs outline-none focus:border-amber-500 font-pixel"
          />
          <input
            type="password"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="AIzaSy..."
            className="col-span-2 bg-zinc-950 border border-zinc-800 text-white px-2.5 py-1.5 rounded-md text-xs outline-none focus:border-amber-500 font-mono"
          />
        </div>
        <button
          type="button"
          onClick={() => void handleAddKey()}
          className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/50 text-emerald-300 font-bold font-pixel rounded-md transition-all cursor-pointer flex items-center justify-center gap-1.5 text-xs shadow-sm"
        >
          <Plus size={14} /> เพิ่ม Key เข้าสู่ Failover Pool
        </button>
      </div>

      {/* Key Pool List with Priority Controls */}
      <div className="flex flex-col gap-2 font-pixel">
        <div className="flex items-center justify-between px-1">
          <span className="font-bold text-slate-400 uppercase tracking-wider text-[10.5px] flex items-center gap-1.5">
            <Sparkles size={12} className="text-amber-400" /> Multi-Key Pool & Priority Sequence ({keys.length} Keys)
          </span>
          <span className="text-[9.5px] text-slate-500 font-sans">
            ปุ่ม 🔼/🔽 เพื่อเลือกลำดับความสำคัญ Key แรกจะถูกใช้งานก่อนเสมอ
          </span>
        </div>

        {keys.length === 0 ? (
          <div className="p-6 text-center border border-dashed border-zinc-800 rounded-lg text-slate-500 italic bg-zinc-900/20 font-sans">
            ยังไม่มี API Key ในระบบ (ระบบจะใช้ Gemini API default หรือเพิ่ม Key ด้านบน)
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {keys.map((k, idx) => (
              <div
                key={k.id}
                className={`p-3 rounded-lg border flex items-center justify-between gap-3 transition-all ${
                  k.enabled
                    ? 'bg-zinc-900/80 border-zinc-800 shadow-sm'
                    : 'bg-zinc-950/50 border-zinc-900 opacity-60'
                }`}
              >
                {/* Priority & Reorder Controls */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <div className="flex flex-col gap-0.5">
                    <button
                      type="button"
                      disabled={idx === 0}
                      onClick={() => void handleMovePriority(idx, 'up')}
                      className="p-1 rounded bg-zinc-800 hover:bg-amber-500/20 hover:text-amber-300 text-slate-400 disabled:opacity-30 cursor-pointer transition-colors"
                      title="เลื่อนขึ้น (เพิ่มความสำคัญ Priority)"
                    >
                      <ArrowUp size={11} />
                    </button>
                    <button
                      type="button"
                      disabled={idx === keys.length - 1}
                      onClick={() => void handleMovePriority(idx, 'down')}
                      className="p-1 rounded bg-zinc-800 hover:bg-amber-500/20 hover:text-amber-300 text-slate-400 disabled:opacity-30 cursor-pointer transition-colors"
                      title="เลื่อนลง (ลดความสำคัญ Priority)"
                    >
                      <ArrowDown size={11} />
                    </button>
                  </div>
                  <span className="px-2 py-1 rounded bg-amber-500/15 border border-amber-500/40 text-amber-300 font-mono font-bold text-[10.5px]">
                    Priority #{idx + 1}
                  </span>
                </div>

                {/* Key Info */}
                <div className="flex flex-col min-w-0 flex-1 font-sans">
                  <span className="font-bold text-white truncate text-[11.5px] flex items-center gap-1.5">
                    <span>{k.label}</span>
                    <span className="font-mono text-slate-400 font-normal text-[10px]">({k.masked_key})</span>
                  </span>
                  {k.status === 'cooldown' ? (
                    <span className="text-[9.5px] text-rose-400 flex items-center gap-1 font-pixel mt-0.5">
                      <AlertTriangle size={11} /> HTTP 429 Quota Exceeded (อยู่ในช่วง Cooldown - ระบบสลับไปใช้ Key ถัดไป)
                    </span>
                  ) : (
                    <span className="text-[9.5px] text-emerald-400 flex items-center gap-1 font-pixel mt-0.5">
                      <CheckCircle size={11} /> พร้อมใช้งาน (Priority Sequence #{idx + 1})
                    </span>
                  )}
                </div>

                {/* Enable / Delete */}
                <div className="flex items-center gap-2 shrink-0 font-pixel">
                  <button
                    type="button"
                    onClick={() => void handleToggleKey(k.id, !k.enabled)}
                    className={`px-2.5 py-1 rounded text-[10px] font-bold cursor-pointer transition-all ${
                      k.enabled
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        : 'bg-zinc-800 text-slate-500 border border-zinc-700'
                    }`}
                  >
                    {k.enabled ? 'เปิดใช้งาน' : 'ปิดใช้งาน'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTargetId(k.id)}
                    className="p-1.5 text-zinc-500 hover:text-rose-400 hover:bg-rose-500/10 rounded transition-colors cursor-pointer"
                    title="ลบ Key นี้"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmModal
        isOpen={Boolean(deleteTargetId)}
        title="ยืนยันการลบ API Key"
        message="คุณต้องการลบ API Key นี้ออกจาก Failover Pool ใช่หรือไม่?"
        confirmText="ลบ Key ถาวร"
        cancelText="ยกเลิก"
        type="danger"
        onConfirm={() => {
          if (deleteTargetId) {
            void handleDeleteKey(deleteTargetId);
            setDeleteTargetId(null);
          }
        }}
        onClose={() => setDeleteTargetId(null)}
      />
    </div>
  );
};

export interface AIProviderSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  showToast?: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export const AIProviderSettingsModal: React.FC<AIProviderSettingsModalProps> = ({
  isOpen,
  onClose,
  showToast,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in font-pixel select-none">
      <div className="w-full max-w-xl bg-zinc-950 border border-amber-500/40 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="px-5 py-3.5 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="text-amber-400" size={16} />
            <h3 className="text-sm font-bold text-amber-300 uppercase tracking-wider">
              🛡️ Multi-Key Priority & Auto-Failover Pool (ระบบสลับ API Key อัตโนมัติ)
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition-colors p-1 cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 flex-1 overflow-y-auto">
          <AIProviderSettingsPanel showToast={showToast} />
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 bg-zinc-900/90 border-t border-zinc-800 flex justify-between items-center font-pixel">
          <span className="text-[10px] text-slate-400">
            💡 ระบบจะวนใช้ Key ตามลำดับ Priority #1 &rarr; #2 &rarr; #3 โดยอัตโนมัติ
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/50 text-amber-300 font-bold rounded-md transition-colors cursor-pointer text-xs"
          >
            ปิดหน้าต่าง
          </button>
        </div>
      </div>
    </div>
  );
};
