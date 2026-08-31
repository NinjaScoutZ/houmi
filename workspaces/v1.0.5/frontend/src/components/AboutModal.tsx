import React from 'react';
import { HOUMI_VERSION_LABEL } from '../version';
import { PatchUpdateButton } from './PatchUpdateButton';
import { Sparkles, User, Clock } from 'lucide-react';

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenLoginModal: () => void;
  onOpenChangelog?: () => void;
  userInfo?: {
    username?: string;
    role?: string;
    status?: string;
    expiresInDays?: number;
    mode?: 'local' | 'online';
  };
}

export const AboutModal: React.FC<AboutModalProps> = ({
  isOpen,
  onClose,
  onOpenLoginModal,
  onOpenChangelog,
  userInfo = { username: 'admin', role: 'admin', status: 'active', expiresInDays: 365, mode: 'local' }
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 font-sans text-slate-200 select-none animate-fade-in">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-zinc-800 bg-zinc-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 shadow-inner">
              <Sparkles size={20} className="animate-pulse" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-yellow-400 uppercase tracking-wider">Houmi Studio</h3>
              <p className="text-xs text-slate-400">Premium AI-Assisted Manga Translation & Typesetting Suite</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white px-3 py-1 rounded-lg border border-zinc-800 bg-zinc-900 text-xs font-semibold hover:bg-zinc-800 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 text-xs">
          {/* Version & Patch Status */}
          <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-semibold">Software Version</span>
              <span className="font-mono font-bold text-yellow-400 bg-yellow-500/10 px-2.5 py-0.5 rounded border border-yellow-500/20">
                {HOUMI_VERSION_LABEL}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-semibold">Patch Update Status</span>
              <PatchUpdateButton updatesEnabled={true} />
            </div>
            {onOpenChangelog && (
              <div className="flex items-center justify-between pt-2 border-t border-zinc-800/80">
                <span className="text-slate-400 font-semibold">Changelog & Features</span>
                <button
                  type="button"
                  onClick={() => { onClose(); onOpenChangelog(); }}
                  className="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg text-[11px] font-bold font-pixel transition-all cursor-pointer flex items-center gap-1"
                >
                  <span>📋 มีอะไรใหม่ในเวอร์ชันนี้</span>
                </button>
              </div>
            )}
          </div>

          {/* User Account & License Days Info */}
          <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-300 font-bold">
                <User size={14} className="text-yellow-400" />
                <span>Account Identity</span>
              </div>
              <button
                onClick={() => { onClose(); onOpenLoginModal(); }}
                className="text-[10px] text-yellow-400 hover:underline font-semibold"
              >
                Switch Account / Login 🔄
              </button>
            </div>
            
            <div className="space-y-2 pt-1 border-t border-zinc-800/80">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Username</span>
                <span className="font-bold text-white font-mono">{userInfo.username || 'Guest / Local'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Operating Mode</span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${userInfo.mode === 'online' ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'}`}>
                  {userInfo.mode === 'online' ? '⚡ Online Mode (Host)' : '🟢 Local Grace Mode'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Subscription Remaining</span>
                <div className="flex items-center gap-1.5 font-bold text-green-400">
                  <Clock size={13} />
                  <span>{userInfo.expiresInDays ? `${userInfo.expiresInDays} Days Left` : 'Active License'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Copyright & Info */}
          <div className="text-center text-slate-500 text-[11px] space-y-1">
            <p>© 2026 Houmi Studio. All rights reserved.</p>
            <p>Protected by Ed25519 Local Grace Licensing & Argon2id Authentication.</p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-900/40 text-center">
          <button
            onClick={onClose}
            className="w-full py-2 bg-zinc-800 hover:bg-zinc-700 text-slate-200 font-bold rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
