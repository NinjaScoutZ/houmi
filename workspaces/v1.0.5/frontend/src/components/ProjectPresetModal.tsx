import React, { useState, useEffect, useRef } from 'react';
import { Globe, UserCheck, Check, FolderCog, Upload, Download, Cpu, X } from 'lucide-react';
import {
  loadClientProjectProfiles,
  serializeClientProjectProfiles,
  createClientProjectProfile,
  exportClientProfilesToJson,
  importClientProfilesFromJson,
  CLIENT_PROFILES_STORAGE_KEY,
  type ClientProjectProfile,
} from '../utils/clientProfiles';

interface ProjectPresetModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentSourceLang?: string;
  currentClientId?: string;
  currentOcrEngine?: string;
  currentBalloonModel?: string;
  projectName?: string;
  onSavePreset: (
    sourceLang: string,
    clientProfile: ClientProjectProfile,
    ocrEngine?: string,
    balloonModel?: string
  ) => void;
}

export const ProjectPresetModal: React.FC<ProjectPresetModalProps> = ({
  isOpen,
  onClose,
  currentSourceLang = 'zh',
  currentClientId = '',
  currentOcrEngine = 'ppocrv5',
  currentBalloonModel = 'sao',
  projectName = '',
  onSavePreset,
}) => {
  const [sourceLang, setSourceLang] = useState<string>(currentSourceLang);
  const [ocrEngine, setOcrEngine] = useState<string>(currentOcrEngine);
  const [balloonModel, setBalloonModel] = useState<string>(currentBalloonModel);
  const [clientProfiles, setClientProfiles] = useState<ClientProjectProfile[]>([]);
  const [selectedClientId, setSelectedClientId] = useState<string>('');
  const [isCreatingNewClient, setIsCreatingNewClient] = useState<boolean>(false);
  const [newClientName, setNewClientName] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importStatus, setImportStatus] = useState<string>('');

  const handleExport = () => {
    exportClientProfilesToJson(clientProfiles, `houmi_font_templates_${Date.now()}.json`);
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = evt.target?.result as string;
      try {
        const { profiles: updated, importedCount } = importClientProfilesFromJson(content, clientProfiles);
        setClientProfiles(updated);
        localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
        if (updated.length) setSelectedClientId(updated[updated.length - 1].id);
        setImportStatus(`✅ นำเข้าสำเร็จ ${importedCount} โปรไฟล์`);
        setTimeout(() => setImportStatus(''), 4000);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'นำเข้าไม่สำเร็จ';
        setImportStatus(`❌ ${msg}`);
      }
    };
    reader.readAsText(file);
  };

  useEffect(() => {
    if (isOpen) {
      const loaded = loadClientProjectProfiles(localStorage.getItem(CLIENT_PROFILES_STORAGE_KEY));
      setClientProfiles(loaded);
      setSourceLang(currentSourceLang || 'zh');
      
      const matched = loaded.find(p => p.id === currentClientId) || loaded[0];
      if (matched) {
        setSelectedClientId(matched.id);
      }
      setOcrEngine(currentOcrEngine || 'ppocrv5');
      setBalloonModel(currentBalloonModel || 'sao');
      setIsCreatingNewClient(false);
      setNewClientName('');
    }
  }, [isOpen, currentSourceLang, currentClientId, currentOcrEngine, currentBalloonModel]);

  if (!isOpen) return null;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    let chosenProfile: ClientProjectProfile;

    if (isCreatingNewClient && newClientName.trim()) {
      const created = createClientProjectProfile(newClientName.trim());
      const updated = [...clientProfiles, created];
      setClientProfiles(updated);
      localStorage.setItem(CLIENT_PROFILES_STORAGE_KEY, serializeClientProjectProfiles(updated));
      chosenProfile = created;
    } else {
      chosenProfile = clientProfiles.find(p => p.id === selectedClientId) || clientProfiles[0];
    }

    onSavePreset(sourceLang, chosenProfile, ocrEngine, balloonModel);
    onClose();
  };

  const activeProfile = clientProfiles.find(p => p.id === selectedClientId) || clientProfiles[0];

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 animate-fade-in p-4 font-sans select-none">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl relative overflow-hidden text-slate-100 p-6 animate-slide-up max-h-[90vh] overflow-y-auto">
        {/* Background Subtle Lighting */}
        <div className="absolute top-[-25%] left-[-25%] w-[50%] h-[50%] bg-amber-500/10 rounded-full filter blur-[50px] pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4 mb-4 z-10 relative">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-yellow-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <FolderCog size={20} className="text-black" />
            </div>
            <div>
              <h3 className="text-sm font-extrabold text-white uppercase tracking-wider font-pixel">
                ตั้งค่าด่วนโปรเจกต์ & โปรไฟล์ลูกค้า
              </h3>
              <p className="text-[10px] text-amber-400/90 font-medium">
                {projectName ? `สำหรับ: ${projectName}` : 'กำหนดภาษาและชุดฟอนต์ประจำตัวลูกค้า'}
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

        <form onSubmit={handleSave} className="space-y-4 z-10 relative text-xs">
          {/* 1. Language Preset */}
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5 font-pixel">
              <Globe size={13} className="text-amber-400" />
              1. ภาษาภาพมังงะต้นฉบับ (SOURCE LANGUAGE)
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'zh', label: '🇨🇳 ภาษาจีน', desc: 'Chinese (zh)' },
                { id: 'ko', label: '🇰🇷 ภาษาเกาหลี', desc: 'Korean (ko)' },
                { id: 'ja', label: '🇯🇵 ภาษาญี่ปุ่น', desc: 'Japanese (ja)' },
                { id: 'en', label: '🇬🇧 ภาษาอังกฤษ', desc: 'English (en)' },
              ].map(lang => (
                <button
                  type="button"
                  key={lang.id}
                  onClick={() => setSourceLang(lang.id)}
                  className={`flex flex-col items-start p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                    sourceLang === lang.id
                      ? 'border-amber-500 bg-amber-500/15 text-white shadow-md shadow-amber-500/10'
                      : 'border-zinc-800 bg-zinc-950/70 text-slate-400 hover:border-zinc-700 hover:text-slate-200'
                  }`}
                >
                  <span className="font-bold text-[11px] flex items-center justify-between w-full">
                    {lang.label}
                    {sourceLang === lang.id && <Check size={12} className="text-amber-400" />}
                  </span>
                  <span className="text-[9px] text-slate-500 mt-0.5">{lang.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 2. Client Preset / Customer Name */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 font-pixel">
                <UserCheck size={13} className="text-amber-400" />
                2. โปรไฟล์งานลูกค้า / ชุดฟอนต์ (CLIENT PRESET)
              </label>

              {/* Import / Export JSON Buttons */}
              <div className="flex gap-1.5">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleImportFile}
                  accept=".json"
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  title="นำเข้าโปรไฟล์ฟอนต์จากไฟล์ JSON (Import Font Templates)"
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-[9px] font-bold text-amber-300 hover:bg-amber-500/20 cursor-pointer"
                >
                  <Upload size={10} /> นำเข้า (.json)
                </button>
                <button
                  type="button"
                  onClick={handleExport}
                  title="ส่งออกโปรไฟล์ฟอนต์ทั้งหมดเป็นไฟล์ JSON (Export Font Templates)"
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-zinc-700 bg-zinc-900 text-[9px] font-bold text-slate-300 hover:border-zinc-600 hover:text-white cursor-pointer"
                >
                  <Download size={10} /> ส่งออก (.json)
                </button>
              </div>
            </div>

            {importStatus && (
              <p className="text-[9px] font-bold mb-2 text-amber-400 animate-fade-in">
                {importStatus}
              </p>
            )}

            {!isCreatingNewClient ? (
              <div className="space-y-2">
                <select
                  value={selectedClientId}
                  onChange={(e) => {
                    if (e.target.value === '__NEW__') {
                      setIsCreatingNewClient(true);
                    } else {
                      setSelectedClientId(e.target.value);
                    }
                  }}
                  className="w-full p-2.5 rounded-lg bg-zinc-950 border border-zinc-800 text-white font-semibold focus:outline-none focus:border-amber-500 cursor-pointer"
                >
                  {clientProfiles.map(p => (
                    <option key={p.id} value={p.id}>
                      👤 {p.name} {p.default_font_family ? `(ฟอนต์หลัก: ${p.default_font_family})` : ''}
                    </option>
                  ))}
                  <option value="__NEW__">➕ เพิ่มชื่อลูกค้าคนใหม่...</option>
                </select>

                {activeProfile && (
                  <div className="p-3 rounded-lg bg-zinc-900/80 border border-zinc-800/80 space-y-1.5 text-[10px] text-slate-300">
                    <div className="flex justify-between items-center text-slate-400 font-pixel">
                      <span>ฟอนต์หลักประจำตัวลูกค้า:</span>
                      <span className="text-amber-400 font-bold">{activeProfile.default_font_family}</span>
                    </div>
                    {activeProfile.text_templates?.bubble && (
                      <div className="flex justify-between items-center text-slate-400 font-pixel">
                        <span>ขนาดฟอนต์บอลลูน:</span>
                        <span className="text-slate-200">{activeProfile.text_templates.bubble.font_size}px</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <label className="block text-[9px] font-bold text-amber-300 uppercase tracking-wider">
                  กรอกชื่อลูกค้าใหม่ (Create New Client Profile)
                </label>
                <input
                  type="text"
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  placeholder="เช่น สำนักพิมพ์ A / ลูกค้าเว็บตูน B"
                  className="w-full p-2 rounded bg-zinc-950 border border-amber-500/50 text-white focus:outline-none font-bold"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setIsCreatingNewClient(false)}
                  className="text-[9px] text-slate-400 hover:text-white underline cursor-pointer"
                >
                  ← ยกเลิก แล้วเลือกจากรายชื่อลูกค้าเดิม
                </button>
              </div>
            )}
          </div>

          {/* 3. AI Engines & Detection Settings */}
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5 font-pixel">
              <Cpu size={13} className="text-amber-400" />
              3. โมเดลประมวลผลเริ่มต้น (DEFAULT AI ENGINES)
            </label>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-[9px] font-bold text-slate-400 block mb-1">OCR Engine:</span>
                <select
                  value={ocrEngine}
                  onChange={(e) => setOcrEngine(e.target.value)}
                  className="w-full p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-yellow-400 font-bold focus:outline-none focus:border-amber-500 cursor-pointer text-xs"
                >
                  <option value="ppocrv5">⚡ RapidOCR (PP-OCRv5)</option>
                  <option value="rapidocr">⚡ RapidOCR (PP-OCRv6 Multilingual)</option>
                  <option value="gemini">✨ DOBKLE OCR (Gemini)</option>
                  <option value="glm">🧠 GLM-OCR (VLM)</option>
                  <option value="rapidocr">🐋 RapidOCR-OCR (VLM)</option>
                </select>
              </div>
              <div>
                <span className="text-[9px] font-bold text-slate-400 block mb-1">Balloon Detector:</span>
                <select
                  value={balloonModel}
                  onChange={(e) => setBalloonModel(e.target.value)}
                  className="w-full p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-slate-200 font-bold focus:outline-none focus:border-amber-500 cursor-pointer text-xs"
                >
                  <option value="sao">🎈 SAO Manga/Webtoon (SOTA)</option>
                  <option value="yolo">⚡ Fast YOLO Detector</option>
                </select>
              </div>
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-2 justify-end pt-3 border-t border-zinc-800 font-pixel">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md border border-zinc-800 bg-zinc-900 text-slate-400 hover:text-white font-bold cursor-pointer"
            >
              ยกเลิก (Cancel)
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-md bg-amber-500 text-black hover:bg-amber-400 font-extrabold cursor-pointer shadow-lg shadow-amber-500/20 active:scale-[0.98] transition-all"
            >
              บันทึกการตั้งค่า (Apply Preset)
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
