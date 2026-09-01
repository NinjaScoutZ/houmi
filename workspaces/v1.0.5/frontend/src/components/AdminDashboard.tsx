import React, { useState, useEffect } from 'react';

export interface AdminDashboardProps {
  isOpen: boolean;
  onClose: () => void;
  apiFetch: (endpoint: string, options?: RequestInit) => Promise<any>;
}

export const AdminDashboard: React.FC<AdminDashboardProps> = ({ isOpen, onClose, apiFetch }) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'codes' | 'audit'>('overview');
  const [users, setUsers] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [genPrefix, setGenPrefix] = useState('HOUMI-VIP');
  const [genDays, setGenDays] = useState(30);
  const [genCount, setGenCount] = useState(1);
  const [generatedCodes, setGeneratedCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadDashboardData();
    }
  }, [isOpen, activeTab]);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'overview' || activeTab === 'users') {
        const res = await apiFetch('/api/admin/users');
        if (res.ok) {
          const userData = await res.json();
          if (userData && userData.users) {
            setUsers(userData.users);
          }
        }
      }
      if (activeTab === 'audit') {
        const res = await apiFetch('/api/admin/audit-logs');
        if (res.ok) {
          const auditData = await res.json();
          if (auditData && auditData.logs) {
            setAuditLogs(auditData.logs);
          }
        }
      }
    } catch (err: any) {
      console.error('Failed to load admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateCodes = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/admin/redeem-codes/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefix: genPrefix, duration_days: genDays, count: genCount }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data && data.codes) {
          setGeneratedCodes(data.codes);
          setMessage(`Successfully generated ${data.codes.length} redeem codes!`);
          loadDashboardData();
        }
      }
    } catch (err: any) {
      setMessage(`Failed: ${err.message}`);
    }
  };

  const handleToggleUserStatus = async (userId: string, currentStatus: string) => {
    const newStatus = currentStatus === 'suspended' ? 'active' : 'suspended';
    try {
      await apiFetch(`/api/admin/users/${userId}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      loadDashboardData();
    } catch (err: any) {
      alert(`Error updating user: ${err.message}`);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 font-sans text-slate-200 select-none">
      <div className="w-full max-w-5xl h-[85vh] bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 text-lg">🛡️</span>
            <div>
              <h3 className="text-base font-bold text-yellow-400 uppercase tracking-wider">Houmi Studio Admin Console</h3>
              <p className="text-xs text-slate-400">Manage users, license keys, system quotas, and security audit logs</p>
              {loading && <span className="text-[10px] text-slate-500">Loading…</span>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-xs font-semibold hover:bg-zinc-800 transition-colors"
          >
            Close (✕)
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-zinc-800 bg-zinc-950 px-6 gap-2 pt-2">
          {[
            { id: 'overview', icon: '📊', label: 'Overview & Status' },
            { id: 'users', icon: '👥', label: 'User Management' },
            { id: 'codes', icon: '🔑', label: 'Redeem Codes' },
            { id: 'audit', icon: '📜', label: 'Audit Logs' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? 'bg-zinc-900 text-yellow-400 border-t border-x border-zinc-800'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-zinc-950/40 text-xs">
          {activeTab === 'overview' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                  <span className="text-slate-400 font-semibold">Total Registered Users</span>
                  <div className="text-2xl font-bold text-white">{users.length}</div>
                </div>
                <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                  <span className="text-slate-400 font-semibold">Active Subscriptions</span>
                  <div className="text-2xl font-bold text-green-400">
                    {users.filter((u) => u.status === 'active').length}
                  </div>
                </div>
                <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                  <span className="text-slate-400 font-semibold">Server Runtime</span>
                  <div className="text-2xl font-bold text-yellow-400">Host (PostgreSQL/Redis)</div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'users' && (
            <div className="space-y-4">
              <h4 className="font-bold text-slate-200 text-sm">User Directory ({users.length})</h4>
              <div className="border border-zinc-800 rounded-lg overflow-hidden">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-zinc-900 text-slate-400 uppercase text-[10px] font-bold">
                    <tr>
                      <th className="p-3">Username</th>
                      <th className="p-3">Email</th>
                      <th className="p-3">Role</th>
                      <th className="p-3">Status</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-slate-300">
                    {users.map((u) => (
                      <tr key={u.id} className="hover:bg-zinc-900/40">
                        <td className="p-3 font-semibold text-white">{u.username}</td>
                        <td className="p-3 font-mono">{u.email || '-'}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${u.role === 'admin' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-slate-800 text-slate-300'}`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${u.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                            {u.status}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            onClick={() => handleToggleUserStatus(u.id, u.status)}
                            className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-slate-200 rounded font-semibold transition-colors"
                          >
                            {u.status === 'suspended' ? 'Approve' : 'Suspend'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'codes' && (
            <div className="space-y-6">
              {message && (
                <div className="p-3 rounded-lg border border-yellow-500/20 bg-yellow-500/5 text-yellow-300">
                  {message}
                </div>
              )}
              <form onSubmit={handleGenerateCodes} className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-4">
                <h4 className="font-bold text-yellow-400 uppercase tracking-wider text-xs">🔑 Generate New Redeem Keys</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Code Prefix</label>
                    <input
                      type="text"
                      value={genPrefix}
                      onChange={(e) => setGenPrefix(e.target.value)}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Duration (Days)</label>
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      value={genDays}
                      onChange={(e) => setGenDays(Number(e.target.value))}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Count</label>
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={genCount}
                      onChange={(e) => setGenCount(Number(e.target.value))}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-white font-mono"
                    />
                  </div>
                </div>
                <button type="submit" className="px-4 py-2 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded text-xs transition-colors">
                  Generate License Keys
                </button>
              </form>

              {generatedCodes.length > 0 && (
                <div className="p-4 bg-zinc-900/80 rounded-xl border border-yellow-500/30 space-y-2">
                  <span className="text-yellow-400 font-bold uppercase tracking-wider text-[10px]">Generated Keys (Copy & Share):</span>
                  <div className="space-y-1 font-mono text-xs text-white">
                    {generatedCodes.map((code, idx) => (
                      <div key={idx} className="p-2 bg-zinc-950 rounded border border-zinc-800 select-all">
                        {code}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'audit' && (
            <div className="space-y-4">
              <h4 className="font-bold text-slate-200 text-sm">Security & Administrative Audit Trail</h4>
              <div className="space-y-2 font-mono">
                {auditLogs.length === 0 ? (
                  <div className="text-slate-500 italic p-4 text-center">No audit log records found.</div>
                ) : (
                  auditLogs.map((log) => (
                    <div key={log.id} className="p-3 bg-zinc-900/40 rounded border border-zinc-900 flex justify-between items-center">
                      <div>
                        <span className="text-yellow-400 font-bold">{log.action}</span>
                        <span className="text-slate-400 ml-2">by Admin ({log.admin_id})</span>
                      </div>
                      <span className="text-slate-500 text-[10px]">{log.created_at}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
