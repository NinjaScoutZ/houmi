import { useEffect, useState } from 'react';
import { Activity, Cloud, CloudOff, HardDrive } from 'lucide-react';
import { apiFetch, buildApiUrl, isRemoteRuntime, isTauriRuntime } from '../api/runtime';
import { countPendingMutations } from '../offline/offlineStore';

type Status = 'local' | 'cloud' | 'offline' | 'starting';

export function OfflineStatusBadge() {
  const [status, setStatus] = useState<Status>('starting');
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      if (isRemoteRuntime() && !navigator.onLine) {
        if (!cancelled) setStatus('offline');
        return;
      }

      try {
        const response = await apiFetch(buildApiUrl('/api/health'), { cache: 'no-store' });
        if (!cancelled) {
          setStatus(response.ok ? (isTauriRuntime() ? 'local' : isRemoteRuntime() ? 'cloud' : 'local') : 'offline');
        }
      } catch {
        if (!cancelled) setStatus('offline');
      }

      try {
        const count = await countPendingMutations();
        if (!cancelled) setPending(count);
      } catch {
        // IndexedDB may be unavailable in a restricted browser context.
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    window.addEventListener('online', refresh);
    window.addEventListener('offline', refresh);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener('online', refresh);
      window.removeEventListener('offline', refresh);
    };
  }, []);

  const metadata = {
    local: { label: 'LOCAL', icon: HardDrive, className: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5' },
    cloud: { label: 'CLOUD', icon: Cloud, className: 'text-sky-400 border-sky-500/20 bg-sky-500/5' },
    offline: { label: 'OFFLINE', icon: CloudOff, className: 'text-amber-400 border-amber-500/20 bg-amber-500/5' },
    starting: { label: 'STARTING', icon: Activity, className: 'text-slate-400 border-slate-500/20 bg-slate-500/5' },
  }[status];
  const Icon = metadata.icon;

  return (
    <span
      title={pending > 0 ? `${pending} queued offline mutation(s)` : 'Houmi runtime status'}
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[9px] font-semibold tracking-wider ${metadata.className}`}
    >
      <Icon size={10} />
      {metadata.label}
      {pending > 0 && <span className="font-mono">·{pending}</span>}
    </span>
  );
}
