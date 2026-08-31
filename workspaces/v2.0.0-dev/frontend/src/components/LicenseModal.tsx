import React, { useState } from 'react';
import { KeyRound, User, UserPlus, RefreshCw, Terminal, Globe, AlertCircle, CheckCircle2, ShieldCheck, Settings } from 'lucide-react';
import { centralApiFetch, localApiFetch, setSessionTokens } from '../api/runtime';

interface LicenseModalProps {
  isOpen: boolean;
  onActivated: () => void;
}

export const LicenseModal: React.FC<LicenseModalProps> = ({
  isOpen,
  onActivated,
}) => {
  const [activeTab, setActiveTab] = useState<'redeem' | 'login' | 'register'>('redeem');
  const [redeemCode, setRedeemCode] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [serverUrl, setServerUrl] = useState(() => {
    return localStorage.getItem('houmi_central_server_url') || '';
  });
  const [showServerSetting, setShowServerSetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [connectionStatus, setConnectionStatus] = useState<'checking' | 'online' | 'offline'>('online');
  const [isRetrying, setIsRetrying] = useState(false);

  const checkServerConnection = async () => {
    setIsRetrying(true);
    setConnectionStatus('checking');
    try {
      const res = await centralApiFetch('/api/auth/license-status', { method: 'GET' });
      if (res.ok || res.status < 500) {
        setConnectionStatus('online');
      } else {
        setConnectionStatus('offline');
      }
    } catch {
      setConnectionStatus('offline');
    } finally {
      setIsRetrying(false);
    }
  };

  const handleOpenDebugConsole = async () => {
    try {
      if ((window as any).pywebview?.api?.show_console) {
        await (window as any).pywebview.api.show_console();
      } else {
        await localApiFetch('/api/diagnostics/show-console', { method: 'POST' });
      }
    } catch (e) {
      console.warn('Console trigger error:', e);
    }
  };

  if (!isOpen) return null;

  const saveServerUrlPreference = () => {
    if (serverUrl.trim()) {
      localStorage.setItem('houmi_central_server_url', serverUrl.trim());
    } else {
      localStorage.removeItem('houmi_central_server_url');
    }
  };

  const handleRedeem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!redeemCode.trim()) {
      setError('กรุณากรอกรหัส Redeem Code');
      return;
    }

    saveServerUrlPreference();
    setIsSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await centralApiFetch('/api/auth/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: redeemCode.trim() }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'รหัส Redeem Code ไม่ถูกต้องหรือหมดอายุแล้ว');
      }

      await localApiFetch('/api/license/save-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).catch(err => console.warn('Failed to save offline token:', err));

      setSuccessMessage('เปิดใช้งานสิทธิ์ License สำเร็จเรียบร้อยแล้ว!');
      setTimeout(() => {
        onActivated();
      }, 1200);
    } catch (err: any) {
      setError(err.message || 'เปิดใช้งานไม่สำเร็จ');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('กรุณากรอก Username และ Password');
      return;
    }

    saveServerUrlPreference();
    setIsSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await centralApiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: username.trim(), password: password.trim() }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');
      }

      if (data.access_token) {
        setSessionTokens(data.access_token, data.refresh_token || null);
      }

      await localApiFetch('/api/license/save-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).catch(err => console.warn('Failed to save offline token:', err));

      setSuccessMessage('เข้าสู่ระบบและยืนยันสิทธิ์สมาชิกสำเร็จเรียบร้อยแล้ว!');
      setTimeout(() => {
        onActivated();
      }, 1200);
    } catch (err: any) {
      setError(err.message || 'เข้าสู่ระบบไม่สำเร็จ');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !email.trim() || !password.trim()) {
      setError('กรุณากรอกข้อมูลให้ครบทุกช่อง');
      return;
    }

    saveServerUrlPreference();
    setIsSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await centralApiFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), email: email.trim(), password: password.trim() }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'การสมัครสมาชิกไม่สำเร็จ');
      }

      setSuccessMessage('สมัครสมาชิกสำเร็จเรียบร้อย! กำลังสลับไปหน้าเข้าสู่ระบบ...');
      setTimeout(() => {
        setActiveTab('login');
        setSuccessMessage(null);
      }, 1500);
    } catch (err: any) {
      setError(err.message || 'การสมัครสมาชิกไม่สำเร็จ');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 font-sans select-none animate-fade-in">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden text-slate-100 p-6 space-y-4 animate-in zoom-in-95">
        <div className="text-center space-y-1.5">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-amber-500/15 border border-amber-500/30 text-amber-400 font-bold mb-1 shadow-inner">
            <ShieldCheck size={24} />
          </div>
          <h2 className="text-lg font-bold tracking-tight text-white font-pixel uppercase tracking-wider">
            เปิดใช้งานสิทธิ์ Houmi Studio
          </h2>
          <p className="text-[11.5px] text-slate-400 leading-relaxed">
            ยืนยันสิทธิ์ด้วย <strong>Redeem Code</strong>, <strong>เข้าสู่ระบบ</strong> หรือ <strong>สมัครสมาชิก</strong> <br />
            หลังจากยืนยันเรียบร้อยแล้ว ท่านสามารถใช้งานในโหมด Offline ต่อได้ทันที
          </p>
        </div>

        {/* Server IP/URL Setting Toggle */}
        <div className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5">
              <Globe size={13} className="text-amber-400" />
              <span>Server:</span>
              <span className="text-amber-400 font-mono text-[10.5px]">
                {serverUrl.trim() ? serverUrl.trim() : 'https://houmi.click'}
              </span>
            </span>
            <button
              type="button"
              onClick={() => setShowServerSetting(!showServerSetting)}
              className="text-[10px] text-amber-400 hover:text-amber-300 font-pixel font-bold flex items-center gap-1 cursor-pointer"
            >
              <Settings size={11} />
              <span>{showServerSetting ? 'ซ่อนการตั้งค่า' : 'เปลี่ยน Server'}</span>
            </button>
          </div>

          {showServerSetting && (
            <div className="space-y-1 pt-1 border-t border-zinc-800">
              <label className="block text-[10px] text-slate-400">
                ใส่ IP หรือ Domain ของเซิร์ฟเวอร์กลาง (ค่าเริ่มต้น: https://houmi.click):
              </label>
              <input
                type="text"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                placeholder="https://houmi.click"
                className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded-lg text-xs font-mono text-white placeholder-zinc-600 outline-none focus:border-amber-500 transition"
              />
            </div>
          )}
        </div>

        {/* Server Connection Status & Debug Console Bar */}
        <div className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-3 space-y-2 font-pixel">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs">
              {connectionStatus === 'checking' || isRetrying ? (
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
              ) : connectionStatus === 'online' ? (
                <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50"></span>
              ) : (
                <span className="w-2 h-2 rounded-full bg-rose-500 shadow-sm shadow-rose-500/50"></span>
              )}
              <span className="font-semibold text-slate-300 text-[10.5px]">
                {connectionStatus === 'checking' || isRetrying
                  ? 'กำลังตรวจสอบการเชื่อมต่อ...'
                  : connectionStatus === 'online'
                  ? 'เชื่อมต่อเซิร์ฟเวอร์กลางสำเร็จ [ออนไลน์]'
                  : 'ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์กลางได้ [โหมดออฟไลน์]'}
              </span>
            </div>

            <button
              type="button"
              onClick={checkServerConnection}
              disabled={isRetrying}
              className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 hover:text-amber-300 text-[10.5px] font-bold rounded-lg transition flex items-center gap-1 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw size={11} className={isRetrying ? 'animate-spin' : ''} />
              <span>Retry</span>
            </button>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-zinc-800 text-[10.5px]">
            <span className="text-zinc-500 font-mono">Node &bull; PostgreSQL</span>
            <button
              type="button"
              onClick={handleOpenDebugConsole}
              className="text-amber-400/90 hover:text-amber-300 font-semibold flex items-center gap-1 cursor-pointer"
            >
              <Terminal size={12} />
              <span>เปิด CMD Window (Debug)</span>
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="grid grid-cols-3 p-1 bg-zinc-950 border border-zinc-800 rounded-xl text-xs font-bold gap-1 font-pixel">
          <button
            type="button"
            onClick={() => { setActiveTab('redeem'); setError(null); setSuccessMessage(null); }}
            className={`py-2 rounded-lg transition flex items-center justify-center gap-1.5 cursor-pointer ${activeTab === 'redeem' ? 'bg-amber-500 text-black shadow' : 'text-slate-400 hover:text-white'}`}
          >
            <KeyRound size={13} />
            <span>Redeem</span>
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('login'); setError(null); setSuccessMessage(null); }}
            className={`py-2 rounded-lg transition flex items-center justify-center gap-1.5 cursor-pointer ${activeTab === 'login' ? 'bg-amber-500 text-black shadow' : 'text-slate-400 hover:text-white'}`}
          >
            <User size={13} />
            <span>ล็อกอิน</span>
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('register'); setError(null); setSuccessMessage(null); }}
            className={`py-2 rounded-lg transition flex items-center justify-center gap-1.5 cursor-pointer ${activeTab === 'register' ? 'bg-amber-500 text-black shadow' : 'text-slate-400 hover:text-white'}`}
          >
            <UserPlus size={13} />
            <span>สมัครไอดี</span>
          </button>
        </div>

        {error && (
          <div className="p-3 bg-rose-500/15 border border-rose-500/30 rounded-xl text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle size={14} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {successMessage && (
          <div className="p-3 bg-emerald-500/15 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 size={14} className="shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        {activeTab === 'redeem' ? (
          <form onSubmit={handleRedeem} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 font-pixel text-[10.5px]">
                Redeem Code (รหัสสิทธิ์เปิดใช้งาน)
              </label>
              <input
                type="text"
                value={redeemCode}
                onChange={(e) => setRedeemCode(e.target.value)}
                placeholder="HOUMI-XXXX-XXXX-XXXX"
                className="w-full px-4 py-2.5 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs font-mono text-center tracking-widest text-white uppercase placeholder-zinc-600 outline-none transition"
                disabled={isSubmitting}
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !redeemCode.trim()}
              className="w-full py-3 px-4 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 active:scale-[0.99] disabled:opacity-50 text-black font-bold font-pixel rounded-xl shadow-lg shadow-amber-500/20 text-xs transition duration-150 cursor-pointer flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full animate-spin"></span>
                  <span>กำลังยืนยันสิทธิ์...</span>
                </>
              ) : (
                <span>เปิดใช้งาน License (Activate)</span>
              )}
            </button>
          </form>
        ) : activeTab === 'login' ? (
          <form onSubmit={handleLogin} className="space-y-3 font-pixel">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 text-[10.5px]">
                Username / Email (ชื่อบัญชีผู้ใช้)
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin หรือชื่อผู้ใช้ของคุณ"
                className="w-full px-3.5 py-2 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs text-white placeholder-zinc-600 outline-none transition font-sans"
                disabled={isSubmitting}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 text-[10.5px]">
                Password (รหัสผ่าน)
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3.5 py-2 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs text-white placeholder-zinc-600 outline-none transition font-sans"
                disabled={isSubmitting}
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !username.trim() || !password.trim()}
              className="w-full py-3 px-4 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 active:scale-[0.99] disabled:opacity-50 text-black font-bold font-pixel rounded-xl shadow-lg shadow-amber-500/20 text-xs transition duration-150 cursor-pointer flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full animate-spin"></span>
                  <span>กำลังตรวจสอบบัญชี...</span>
                </>
              ) : (
                <span>เข้าสู่ระบบยืนยันสิทธิ์ (Log In)</span>
              )}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="space-y-3 font-pixel">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 text-[10.5px]">
                Username (ตั้งชื่อบัญชี)
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ตั้งชื่อผู้ใช้ภาษาอังกฤษ"
                className="w-full px-3.5 py-2 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs text-white placeholder-zinc-600 outline-none transition font-sans"
                disabled={isSubmitting}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 text-[10.5px]">
                Email (อีเมล)
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="email@example.com"
                className="w-full px-3.5 py-2 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs text-white placeholder-zinc-600 outline-none transition font-sans"
                disabled={isSubmitting}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 text-[10.5px]">
                Password (รหัสผ่านอย่างน้อย 8 ตัว)
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3.5 py-2 bg-zinc-900 border border-zinc-800 focus:border-amber-500 rounded-xl text-xs text-white placeholder-zinc-600 outline-none transition font-sans"
                disabled={isSubmitting}
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !username.trim() || !email.trim() || password.length < 8}
              className="w-full py-3 px-4 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 active:scale-[0.99] disabled:opacity-50 text-black font-bold font-pixel rounded-xl shadow-lg shadow-amber-500/20 text-xs transition duration-150 cursor-pointer flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full animate-spin"></span>
                  <span>กำลังสร้างบัญชี...</span>
                </>
              ) : (
                <span>สมัครสมาชิกใหม่ (Register)</span>
              )}
            </button>
          </form>
        )}

        <div className="text-center text-[10.5px] text-zinc-500 border-t border-zinc-800 pt-3 font-mono">
          Houmi Studio Licensing Service v0.1.2 &bull; Monotonic Hardware Signature
        </div>
      </div>
    </div>
  );
};
