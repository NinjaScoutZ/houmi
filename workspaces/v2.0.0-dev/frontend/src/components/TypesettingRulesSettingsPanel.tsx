import React, { useState, useEffect } from 'react';
import { BookOpen, Plus, Trash2, RotateCcw, Save, Play, CheckCircle2, AlertCircle, Sparkles, Tag, Layers, FileText } from 'lucide-react';
import { apiFetch } from '../api/runtime';

export interface TypesettingRulesData {
  version: string;
  description: string;
  last_updated?: string;
  forward_glue_particles: string[];
  backward_glue_particles: string[];
  never_start_line: string[];
  never_end_line: string[];
  custom_compound_words: string[];
  unbreakable_phrases: string[];
}

export interface TypesettingRulesSettingsPanelProps {
  showToast?: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export const TypesettingRulesSettingsPanel: React.FC<TypesettingRulesSettingsPanelProps> = ({ showToast: parentShowToast }) => {
  const showToast = (msg: string, type?: 'info' | 'success' | 'warning' | 'error') => {
    const mappedType = type === 'warning' ? 'info' : type;
    parentShowToast?.(msg, mappedType);
  };
  const [activeTab, setActiveTab] = useState<'forward' | 'backward' | 'boundaries' | 'compounds' | 'phrases' | 'tester'>('forward');
  const [rules, setRules] = useState<TypesettingRulesData>({
    version: '2.0.0',
    description: 'Typesetting Rules',
    forward_glue_particles: [],
    backward_glue_particles: [],
    never_start_line: [],
    never_end_line: [],
    custom_compound_words: [],
    unbreakable_phrases: [],
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // New tag inputs
  const [inputForward, setInputForward] = useState('');
  const [inputBackward, setInputBackward] = useState('');
  const [inputNeverStart, setInputNeverStart] = useState('');
  const [inputNeverEnd, setInputNeverEnd] = useState('');
  const [inputCompound, setInputCompound] = useState('');
  const [inputPhrase, setInputPhrase] = useState('');

  // Live Tester Playground State
  const [testText, setTestText] = useState('อะไรนะ!? สูงกว่ามหาบุรุษก็มีชื่อบนทำเนียบได้แล้วรึ?');
  const [targetLines, setTargetLines] = useState(3);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{
    tokens: string[];
    split_lines: string[];
    applied_forward_glues: string[];
    applied_backward_glues: string[];
    triggered_rules: string[];
  } | null>(null);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const res = await apiFetch('/api/typesetting/rules');
      if (res.ok) {
        const data = await res.json();
        setRules(data);
        setDirty(false);
      }
    } catch (err: any) {
      console.error('Failed to fetch typesetting rules:', err);
      showToast?.('ไม่สามารถโหลดกฎ Typesetting ได้', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchRules();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      const updatedRules = {
        ...rules,
        last_updated: new Date().toISOString(),
      };
      const res = await apiFetch('/api/typesetting/rules', {
        method: 'POST',
        body: JSON.stringify(updatedRules),
      });
      if (res.ok) {
        setRules(updatedRules);
        setDirty(false);
        showToast?.('บันทึกกฎ Typesetting เรียบร้อยแล้ว', 'success');
      } else {
        showToast?.('เกิดข้อผิดพลาดในการบันทึก', 'error');
      }
    } catch (err: any) {
      showToast?.(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm('คุณต้องการคืนค่ากฎการจัดตัวอักษรทั้งหมดกลับเป็นค่าเริ่มต้นตามหลักภาษาศาสตร์หรือไม่?')) {
      return;
    }
    try {
      setLoading(true);
      const res = await apiFetch('/api/typesetting/rules/reset', {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setRules(data);
        setDirty(false);
        showToast?.('คืนค่ากฎเริ่มต้นเรียบร้อยแล้ว', 'success');
      }
    } catch (err: any) {
      showToast?.(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRunTest = async () => {
    if (!testText.trim()) return;
    try {
      setTestLoading(true);
      const res = await apiFetch('/api/typesetting/rules/test', {
        method: 'POST',
        body: JSON.stringify({
          sample_text: testText,
          target_lines: targetLines,
          custom_rules: rules,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      }
    } catch (err: any) {
      showToast?.(`ทดสอบไม่สำเร็จ: ${err.message}`, 'error');
    } finally {
      setTestLoading(false);
    }
  };

  // Tag helper functions
  const addTag = (field: keyof TypesettingRulesData, value: string, clearInput: () => void) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const currentList = (rules[field] as string[]) || [];
    if (currentList.includes(trimmed)) {
      showToast?.(`คำว่า "${trimmed}" มีอยู่ในรายการแล้ว`, 'warning');
      return;
    }
    setRules({
      ...rules,
      [field]: [...currentList, trimmed],
    });
    setDirty(true);
    clearInput();
  };

  const removeTag = (field: keyof TypesettingRulesData, itemToRemove: string) => {
    const currentList = (rules[field] as string[]) || [];
    setRules({
      ...rules,
      [field]: currentList.filter((item) => item !== itemToRemove),
    });
    setDirty(true);
  };

  return (
    <div className="flex flex-col gap-5 text-slate-200">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-zinc-900/80 border border-zinc-800 shadow-md">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📜</span>
            <h2 className="text-base font-bold text-yellow-400 font-pixel tracking-wide">
              Typesetting & Thai Linguistic Rules
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400 border border-yellow-500/30">
              v{rules.version}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            กำหนดกฎการตัดคำและเชื่อมคำอนุภาคภาษาไทย (เช่น "ก็", "จะ", "นะ") ห้ามตัดบรรทัดแยกจากกัน พร้อมระบบเรียนรู้คำเฉพาะเรื่อง
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={handleReset}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-slate-300 text-xs transition border border-zinc-700 cursor-pointer"
            title="คืนค่าเริ่มต้น"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !dirty}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition shadow cursor-pointer ${
              dirty
                ? 'bg-yellow-500 hover:bg-yellow-400 text-zinc-950 shadow-yellow-500/20'
                : 'bg-zinc-800 text-slate-500 border border-zinc-700/50 cursor-not-allowed'
            }`}
          >
            <Save className="w-3.5 h-3.5" />
            <span>{saving ? 'Saving...' : dirty ? 'Save Changes *' : 'Saved'}</span>
          </button>
        </div>
      </div>

      {/* Navigation Subtabs */}
      <div className="flex flex-wrap items-center gap-1.5 p-1 rounded-xl bg-zinc-950 border border-zinc-850 select-none">
        <button
          type="button"
          onClick={() => setActiveTab('forward')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
            activeTab === 'forward'
              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900/50'
          }`}
        >
          <span>🧲</span>
          <span>คำเชื่อมหน้า (Forward Glue)</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-zinc-800 text-slate-400">
            {rules.forward_glue_particles?.length || 0}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('backward')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
            activeTab === 'backward'
              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900/50'
          }`}
        >
          <span>📎</span>
          <span>คำลงท้าย (Backward Glue)</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-zinc-800 text-slate-400">
            {rules.backward_glue_particles?.length || 0}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('boundaries')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
            activeTab === 'boundaries'
              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900/50'
          }`}
        >
          <span>🚫</span>
          <span>กฎขอบบรรทัด (Never Start/End)</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('compounds')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
            activeTab === 'compounds'
              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900/50'
          }`}
        >
          <span>📚</span>
          <span>คำเฉพาะเรื่อง (Dictionary)</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-zinc-800 text-slate-400">
            {rules.custom_compound_words?.length || 0}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('phrases')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
            activeTab === 'phrases'
              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-zinc-900/50'
          }`}
        >
          <span>🔗</span>
          <span>วลีห้ามตัดแยก</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('tester');
            void handleRunTest();
          }}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ml-auto ${
            activeTab === 'tester'
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold'
              : 'text-emerald-400 hover:bg-emerald-500/10'
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Live Tester (ทดสอบประโยคจริง)</span>
        </button>
      </div>

      {/* Tab 1: Forward Clitics */}
      {activeTab === 'forward' && (
        <div className="flex flex-col gap-4 p-5 rounded-xl bg-zinc-900/40 border border-zinc-800">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🧲 คำเชื่อมหน้าและคำช่วย (Forward Glue Particles)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              คำเหล่านี้เมื่อพบในประโยค ระบบจะ<strong>ผูกติดกับคำถัดไปทันที</strong> (เช่น <code className="text-yellow-400">"ก็" + "มี" ➔ "ก็มี"</code>, <code className="text-yellow-400">"จะ" + "ไป" ➔ "จะไป"</code>) ทำให้ไม่สามารถหลุดไปขึ้นต้นบรรทัดใหม่โดดๆ หรือค้างท้ายบรรทัดคนเดียวได้
            </p>
          </div>

          {/* Add input */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="พิมพ์คำเชื่อมใหม่ เช่น 'ก็', 'จะ', 'จึ่ง'..."
              value={inputForward}
              onChange={(e) => setInputForward(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addTag('forward_glue_particles', inputForward, () => setInputForward(''));
              }}
              className="flex-1 max-w-sm px-3 py-2 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-yellow-500"
            />
            <button
              type="button"
              onClick={() => addTag('forward_glue_particles', inputForward, () => setInputForward(''))}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-yellow-500 hover:bg-yellow-400 text-zinc-950 text-xs font-bold cursor-pointer transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>เพิ่มคำ</span>
            </button>
          </div>

          {/* Tag Pills */}
          <div className="flex flex-wrap gap-2 pt-2">
            {rules.forward_glue_particles?.map((item) => (
              <span
                key={item}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-yellow-500/10 text-yellow-300 border border-yellow-500/25 text-xs group transition hover:border-yellow-500/50"
              >
                <span className="font-semibold">{item}</span>
                <button
                  type="button"
                  onClick={() => removeTag('forward_glue_particles', item)}
                  className="text-yellow-500/60 hover:text-red-400 text-xs font-bold leading-none p-0.5 rounded cursor-pointer"
                  title="ลบ"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Backward Clitics */}
      {activeTab === 'backward' && (
        <div className="flex flex-col gap-4 p-5 rounded-xl bg-zinc-900/40 border border-zinc-800">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>📎 คำลงท้ายบอกอารมณ์ (Backward Glue Particles)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              คำเหล่านี้เมื่อพบในประโยค ระบบจะ<strong>ผูกติดกับคำข้างหน้าเสมอ</strong> (เช่น <code className="text-yellow-400">"อะไร" + "นะ!?" ➔ "อะไรนะ!?"</code>, <code className="text-yellow-400">"ได้แล้ว" + "รึ?" ➔ "ได้แล้วรึ?"</code>) ป้องกันไม่ให้ตกไปขึ้นต้นบรรทัดใหม่ตามลำพัง
            </p>
          </div>

          {/* Add input */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="พิมพ์คำลงท้าย เช่น 'นะ', 'ล่ะ', 'รึ', 'สิ'..."
              value={inputBackward}
              onChange={(e) => setInputBackward(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addTag('backward_glue_particles', inputBackward, () => setInputBackward(''));
              }}
              className="flex-1 max-w-sm px-3 py-2 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-yellow-500"
            />
            <button
              type="button"
              onClick={() => addTag('backward_glue_particles', inputBackward, () => setInputBackward(''))}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-yellow-500 hover:bg-yellow-400 text-zinc-950 text-xs font-bold cursor-pointer transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>เพิ่มคำ</span>
            </button>
          </div>

          {/* Tag Pills */}
          <div className="flex flex-wrap gap-2 pt-2">
            {rules.backward_glue_particles?.map((item) => (
              <span
                key={item}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-sky-500/10 text-sky-300 border border-sky-500/25 text-xs group transition hover:border-sky-500/50"
              >
                <span className="font-semibold">{item}</span>
                <button
                  type="button"
                  onClick={() => removeTag('backward_glue_particles', item)}
                  className="text-sky-500/60 hover:text-red-400 text-xs font-bold leading-none p-0.5 rounded cursor-pointer"
                  title="ลบ"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Boundaries */}
      {activeTab === 'boundaries' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Never Start Line */}
          <div className="flex flex-col gap-3 p-4 rounded-xl bg-zinc-900/40 border border-zinc-800">
            <h4 className="text-xs font-bold text-red-400 flex items-center gap-1.5">
              <span>🚫 ห้ามขึ้นต้นบรรทัด (Never Start Line)</span>
            </h4>
            <p className="text-[11px] text-slate-400">
              ตัวอักษรหรือสัญลักษณ์เหล่านี้จะถูกปฏิเสธไม่ให้เป็นคำแรกของบรรทัดเด็ดขาด
            </p>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="เพิ่มคำ/สัญลักษณ์ เช่น '!'..."
                value={inputNeverStart}
                onChange={(e) => setInputNeverStart(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addTag('never_start_line', inputNeverStart, () => setInputNeverStart(''));
                }}
                className="flex-1 px-2.5 py-1.5 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-red-500"
              />
              <button
                type="button"
                onClick={() => addTag('never_start_line', inputNeverStart, () => setInputNeverStart(''))}
                className="px-2.5 py-1.5 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 text-xs font-bold border border-red-500/30 cursor-pointer"
              >
                เพิ่ม
              </button>
            </div>

            <div className="flex flex-wrap gap-1.5 pt-1">
              {rules.never_start_line?.map((item) => (
                <span
                  key={item}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20 text-[11px]"
                >
                  <span>{item}</span>
                  <button
                    type="button"
                    onClick={() => removeTag('never_start_line', item)}
                    className="hover:text-white cursor-pointer ml-0.5"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Never End Line */}
          <div className="flex flex-col gap-3 p-4 rounded-xl bg-zinc-900/40 border border-zinc-800">
            <h4 className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
              <span>⚠️ ห้ามลงท้ายบรรทัด (Never End Line)</span>
            </h4>
            <p className="text-[11px] text-slate-400">
              คำเชื่อมหรือเครื่องหมายเปิดที่จะไม่ให้ค้างอยู่ท้ายบรรทัดโดยไม่มีคำตาม
            </p>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="เพิ่มคำ เช่น 'ที่', 'เพราะ'..."
                value={inputNeverEnd}
                onChange={(e) => setInputNeverEnd(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addTag('never_end_line', inputNeverEnd, () => setInputNeverEnd(''));
                }}
                className="flex-1 px-2.5 py-1.5 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-amber-500"
              />
              <button
                type="button"
                onClick={() => addTag('never_end_line', inputNeverEnd, () => setInputNeverEnd(''))}
                className="px-2.5 py-1.5 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-xs font-bold border border-amber-500/30 cursor-pointer"
              >
                เพิ่ม
              </button>
            </div>

            <div className="flex flex-wrap gap-1.5 pt-1">
              {rules.never_end_line?.map((item) => (
                <span
                  key={item}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[11px]"
                >
                  <span>{item}</span>
                  <button
                    type="button"
                    onClick={() => removeTag('never_end_line', item)}
                    className="hover:text-white cursor-pointer ml-0.5"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Custom Compound Words */}
      {activeTab === 'compounds' && (
        <div className="flex flex-col gap-4 p-5 rounded-xl bg-zinc-900/40 border border-zinc-800">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>📚 คำเฉพาะเรื่องและชื่อตัวละคร (Custom Proper Names & Dictionary)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              คำศัพท์เฉพาะ, ตำแหน่ง, หรือชื่อตัวละครที่จะถูกบรรจุเข้าสู่พจนานุกรมประมวลผลภาษาไทยโดยตรง <strong>ห้ามระบบตัดแบ่งครึ่งคำโดยเด็ดขาด</strong>
            </p>
          </div>

          {/* Add input */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="พิมพ์ชื่อเฉพาะ เช่น 'นายน้อยฉางเกอ', 'ราชวงศ์เซียนอู๋ซวง'..."
              value={inputCompound}
              onChange={(e) => setInputCompound(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addTag('custom_compound_words', inputCompound, () => setInputCompound(''));
              }}
              className="flex-1 max-w-sm px-3 py-2 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-yellow-500"
            />
            <button
              type="button"
              onClick={() => addTag('custom_compound_words', inputCompound, () => setInputCompound(''))}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-yellow-500 hover:bg-yellow-400 text-zinc-950 text-xs font-bold cursor-pointer transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>เพิ่มชื่อเฉพาะ</span>
            </button>
          </div>

          {/* Tag Pills */}
          <div className="flex flex-wrap gap-2 pt-2">
            {rules.custom_compound_words?.map((item) => (
              <span
                key={item}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-300 border border-purple-500/25 text-xs group transition hover:border-purple-500/50"
              >
                <span className="font-semibold">{item}</span>
                <button
                  type="button"
                  onClick={() => removeTag('custom_compound_words', item)}
                  className="text-purple-500/60 hover:text-red-400 text-xs font-bold leading-none p-0.5 rounded cursor-pointer"
                  title="ลบ"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tab 5: Unbreakable Phrases */}
      {activeTab === 'phrases' && (
        <div className="flex flex-col gap-4 p-5 rounded-xl bg-zinc-900/40 border border-zinc-800">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🔗 วลีและประโยคห้ามตัดแยก (Unbreakable Phrases)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              กลุ่มคำหรือวลียอดนิยมที่ต้องการให้คงอยู่บนบรรทัดเดียวกันเสมอ
            </p>
          </div>

          {/* Add input */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="พิมพ์วลี เช่น 'อะไรนะ!?', 'เป็นความจริงหรือ'..."
              value={inputPhrase}
              onChange={(e) => setInputPhrase(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addTag('unbreakable_phrases', inputPhrase, () => setInputPhrase(''));
              }}
              className="flex-1 max-w-sm px-3 py-2 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-yellow-500"
            />
            <button
              type="button"
              onClick={() => addTag('unbreakable_phrases', inputPhrase, () => setInputPhrase(''))}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-yellow-500 hover:bg-yellow-400 text-zinc-950 text-xs font-bold cursor-pointer transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>เพิ่มวลี</span>
            </button>
          </div>

          {/* Tag Pills */}
          <div className="flex flex-wrap gap-2 pt-2">
            {rules.unbreakable_phrases?.map((item) => (
              <span
                key={item}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/25 text-xs group transition hover:border-indigo-500/50"
              >
                <span className="font-semibold">{item}</span>
                <button
                  type="button"
                  onClick={() => removeTag('unbreakable_phrases', item)}
                  className="text-indigo-500/60 hover:text-red-400 text-xs font-bold leading-none p-0.5 rounded cursor-pointer"
                  title="ลบ"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tab 6: Interactive Live Tester */}
      {activeTab === 'tester' && (
        <div className="flex flex-col gap-4 p-5 rounded-xl bg-zinc-900/60 border border-emerald-500/30">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                <span>Live Interactive Typesetting Tester (สนามทดสอบตัดคำจริง)</span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                พิมพ์ประโยคเพื่อทดสอบการตัดคำและการผูกอนุภาค (เช่น "ก็", "นะ", "รึ") แบบ Real-time
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">จำนวนบรรทัดเป้าหมาย:</span>
              <select
                value={targetLines}
                onChange={(e) => setTargetLines(Number(e.target.value))}
                className="bg-zinc-950 border border-zinc-800 text-white rounded px-2 py-1 text-xs"
              >
                <option value={2}>2 บรรทัด</option>
                <option value={3}>3 บรรทัด (เพชร)</option>
                <option value={4}>4 บรรทัด</option>
                <option value={5}>5 บรรทัด</option>
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                placeholder="พิมพ์ข้อความภาษาไทยที่ต้องการทดสอบ..."
                className="flex-1 px-3 py-2 text-xs rounded-lg bg-zinc-950 border border-zinc-800 text-white focus:outline-none focus:border-emerald-500"
              />
              <button
                type="button"
                onClick={handleRunTest}
                disabled={testLoading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs cursor-pointer transition"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{testLoading ? 'Processing...' : 'Run Test'}</span>
              </button>
            </div>

            {/* Presets */}
            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              <span>ตัวอย่างประโยคจริง:</span>
              <button
                type="button"
                onClick={() => setTestText('อะไรนะ!? สูงกว่ามหาบุรุษก็มีชื่อบนทำเนียบได้แล้วรึ?')}
                className="text-slate-400 hover:text-yellow-400 underline cursor-pointer"
              >
                [1] สูงกว่ามหาบุรุษก็มี...
              </button>
              <button
                type="button"
                onClick={() => setTestText('เจ้าโง่ ตอนนี้ต้องเรียกว่าองค์เทพประมุข!')}
                className="text-slate-400 hover:text-yellow-400 underline cursor-pointer"
              >
                [2] เจ้าโง่... องค์เทพประมุข
              </button>
              <button
                type="button"
                onClick={() => setTestText('เป็นความจริงหรือ นายน้อยฉางเกอ?')}
                className="text-slate-400 hover:text-yellow-400 underline cursor-pointer"
              >
                [3] นายน้อยฉางเกอ
              </button>
            </div>
          </div>

          {/* Test Results Output */}
          {testResult && (
            <div className="flex flex-col gap-3.5 pt-3 border-t border-zinc-800">
              {/* Token breakdown */}
              <div>
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  1. ก้อนคำหลังผ่านกฎไวยากรณ์ (Cohesive Tokens):
                </span>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {testResult.tokens.map((tok, idx) => {
                    const isGlued = tok.includes('ก็') || tok.includes('นะ') || tok.includes('รึ') || tok.includes('ได้');
                    return (
                      <span
                        key={idx}
                        className={`px-2 py-1 rounded text-xs border font-mono ${
                          isGlued
                            ? 'bg-yellow-500/15 border-yellow-500/40 text-yellow-300 font-bold'
                            : 'bg-zinc-950 border-zinc-800 text-slate-300'
                        }`}
                      >
                        {tok}
                      </span>
                    );
                  })}
                </div>
              </div>

              {/* Line splits preview */}
              <div>
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  2. ผลการจัดแบ่งบรรทัด (Simulated Line Breaks):
                </span>
                <div className="flex flex-col gap-1 mt-1.5 p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-center font-medium text-xs text-emerald-300">
                  {testResult.split_lines.map((line, idx) => (
                    <div key={idx} className="py-0.5">
                      <span className="text-[10px] text-slate-600 mr-2 font-mono">L{idx + 1}:</span>
                      {line}
                    </div>
                  ))}
                </div>
              </div>

              {/* Triggered rules summary */}
              {testResult.triggered_rules.length > 0 && (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300">
                  <div className="font-bold mb-1 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>กฎที่ถูกนำมาใช้งานในประโยคนี้:</span>
                  </div>
                  <ul className="list-disc list-inside space-y-0.5 text-[11px] text-emerald-200">
                    {testResult.triggered_rules.map((rule, idx) => (
                      <li key={idx}>{rule}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
