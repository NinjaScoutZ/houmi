import React, { useState } from 'react';
import { apiFetch, setSessionTokens } from '../api/runtime';

interface LoginModalProps {
  isOpen: boolean;
  onAuthenticated: () => void;
  onClose: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onAuthenticated, onClose }) => {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      if (isRegisterMode) {
        // Registration Flow
        const regResponse = await apiFetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, email, password }),
        });
        const regPayload = await regResponse.json().catch(() => ({})) as { detail?: string };
        if (!regResponse.ok) {
          throw new Error(regPayload.detail || 'สมัครสมาชิกไม่สำเร็จ');
        }

        // Automatic Login after Registration
        const loginResponse = await apiFetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: username, password, remember_me: true }),
        });
        const loginPayload = await loginResponse.json().catch(() => ({})) as { access_token?: string; refresh_token?: string; detail?: string };
        if (!loginResponse.ok || !loginPayload.access_token || !loginPayload.refresh_token) {
          throw new Error(loginPayload.detail || 'เข้าสู่ระบบอัตโนมัติไม่สำเร็จ กรุณาเข้าสู่ระบบด้วยตนเอง');
        }
        setSessionTokens(loginPayload.access_token, loginPayload.refresh_token);
        onAuthenticated();
      } else {
        // Login Flow
        const response = await apiFetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: username || email, password, remember_me: true }),
        });
        const payload = await response.json().catch(() => ({})) as { access_token?: string; refresh_token?: string; detail?: string };
        if (!response.ok || !payload.access_token || !payload.refresh_token) {
          throw new Error(payload.detail || 'เข้าสู่ระบบไม่สำเร็จ');
        }
        setSessionTokens(payload.access_token, payload.refresh_token);
        onAuthenticated();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'ดำเนินการไม่สำเร็จ');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <div className="mb-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-yellow-400">Remote Workspace</p>
          <h2 className="mt-2 text-xl font-bold text-white">
            {isRegisterMode ? 'สมัครสมาชิก Houmi' : 'เข้าสู่ระบบ Houmi'}
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            {isRegisterMode ? 'สร้างบัญชีผู้ใช้ใหม่เพื่อเริ่มต้นใช้งาน' : 'Remote Mode ต้องใช้บัญชีที่ได้รับอนุมัติและสิทธิ์การใช้งาน'}
          </p>
        </div>

        {/* Tab Selector */}
        <div className="mb-5 flex border-b border-zinc-900 pb-2">
          <button
            type="button"
            onClick={() => { setIsRegisterMode(false); setError(null); }}
            className={`flex-1 text-center text-xs font-bold transition-colors cursor-pointer py-1 ${
              !isRegisterMode ? 'text-yellow-500 border-b border-yellow-500' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            เข้าสู่ระบบ (Login)
          </button>
          <button
            type="button"
            onClick={() => { setIsRegisterMode(true); setError(null); }}
            className={`flex-1 text-center text-xs font-bold transition-colors cursor-pointer py-1 ${
              isRegisterMode ? 'text-yellow-500 border-b border-yellow-500' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            สมัครสมาชิก (Register)
          </button>
        </div>

        {isRegisterMode ? (
          <>
            <label className="mb-3 block text-xs text-slate-400">
              Username
              <input 
                value={username} 
                onChange={(event) => setUsername(event.target.value)} 
                required 
                autoComplete="username" 
                minLength={3}
                maxLength={50}
                className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-yellow-500" 
              />
            </label>
            <label className="mb-3 block text-xs text-slate-400">
              Email Address
              <input 
                type="email"
                value={email} 
                onChange={(event) => setEmail(event.target.value)} 
                required 
                autoComplete="email" 
                className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-yellow-500" 
              />
            </label>
          </>
        ) : (
          <label className="mb-3 block text-xs text-slate-400">
            Username หรือ Email
            <input 
              value={username} 
              onChange={(event) => setUsername(event.target.value)} 
              required 
              autoComplete="username" 
              className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-yellow-500" 
            />
          </label>
        )}

        <label className="mb-4 block text-xs text-slate-400">
          Password
          <input 
            type="password" 
            value={password} 
            onChange={(event) => setPassword(event.target.value)} 
            required 
            autoComplete={isRegisterMode ? 'new-password' : 'current-password'} 
            minLength={8}
            className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-yellow-500" 
          />
        </label>

        {error && <p className="mb-4 rounded border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p>}
        
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border border-zinc-800 px-3 py-2 text-xs text-slate-400 hover:text-white">ปิด</button>
          <button type="submit" disabled={isSubmitting} className="rounded bg-yellow-500 px-4 py-2 text-xs font-bold text-black hover:bg-yellow-400 disabled:opacity-50">
            {isSubmitting ? 'กำลังดำเนินการ…' : isRegisterMode ? 'สมัครสมาชิก' : 'เข้าสู่ระบบ'}
          </button>
        </div>
      </form>
    </div>
  );
};
