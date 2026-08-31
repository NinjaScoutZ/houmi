import {
  DEFAULT_TEXT_TEMPLATES,
  normalizeTextTemplates,
  type TextTemplate,
} from './textTemplates';

export const CLIENT_PROFILES_STORAGE_KEY = 'houmi_client_project_profiles_v1';
export const ACTIVE_CLIENT_PROFILE_STORAGE_KEY = 'houmi_active_client_project_profile_v1';

export interface ClientProjectProfile {
  id: string;
  name: string;
  description: string;
  default_font_family: string;
  default_text_template_id: string;
  text_templates: Record<string, TextTemplate>;
  created_at: string;
  updated_at: string;
}

const cloneTemplates = (templates: Record<string, TextTemplate>) => (
  normalizeTextTemplates(JSON.parse(JSON.stringify(templates)))
);

const createId = () => (
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `client-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
);

export const createClientProjectProfile = (
  name = 'มาตรฐาน',
  templates: Record<string, TextTemplate> = DEFAULT_TEXT_TEMPLATES,
  overrides: Partial<Pick<ClientProjectProfile, 'description' | 'default_font_family' | 'default_text_template_id'>> = {},
): ClientProjectProfile => {
  const normalizedTemplates = cloneTemplates(templates);
  const preferredTemplate = normalizedTemplates[overrides.default_text_template_id || 'bubble']
    || normalizedTemplates.bubble
    || Object.values(normalizedTemplates)[0];
  const now = new Date().toISOString();
  return {
    id: createId(),
    name: name.trim() || 'โปรไฟล์ใหม่',
    description: overrides.description?.trim() || '',
    default_font_family: overrides.default_font_family || preferredTemplate?.font_stack?.[0] || 'NotoSansThai',
    default_text_template_id: preferredTemplate?.id || 'bubble',
    text_templates: normalizedTemplates,
    created_at: now,
    updated_at: now,
  };
};

const normalizeProfile = (raw: unknown): ClientProjectProfile | null => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const value = raw as Partial<ClientProjectProfile>;
  if (typeof value.id !== 'string' || !value.id.trim() || typeof value.name !== 'string' || !value.name.trim()) {
    return null;
  }
  const templates = normalizeTextTemplates(value.text_templates);
  const templateId = typeof value.default_text_template_id === 'string' && templates[value.default_text_template_id]
    ? value.default_text_template_id
    : (templates.bubble?.id || Object.keys(templates)[0] || 'bubble');
  const now = new Date().toISOString();
  return {
    id: value.id,
    name: value.name.trim(),
    description: typeof value.description === 'string' ? value.description.trim() : '',
    default_font_family: typeof value.default_font_family === 'string' && value.default_font_family.trim()
      ? value.default_font_family.trim()
      : templates[templateId]?.font_stack?.[0] || 'NotoSansThai',
    default_text_template_id: templateId,
    text_templates: cloneTemplates(templates),
    created_at: typeof value.created_at === 'string' ? value.created_at : now,
    updated_at: typeof value.updated_at === 'string' ? value.updated_at : now,
  };
};

export const createPathompongClientProfile = (): ClientProjectProfile => {
  const baseTemplates = cloneTemplates(DEFAULT_TEXT_TEMPLATES);
  const now = new Date().toISOString();

  const templates: Record<string, TextTemplate> = {
    ...baseTemplates,
    bubble: {
      ...baseTemplates.bubble,
      id: 'bubble',
      name: 'คำปกติ',
      semantic_tag: 'คำปกติ',
      font_stack: ['TH Sarabun New', 'THSarabunNew', 'TH Sarabun PSK'],
      bold: true,
    },
    shout: {
      ...baseTemplates.emphasis,
      id: 'shout',
      name: 'ตะโกน',
      semantic_tag: 'ตะโกน',
      font_stack: ['Layiji_TarMineTine1', 'Layiji TarMineTine1'],
      bold: true,
    },
    thought: {
      ...baseTemplates.thought,
      id: 'thought',
      name: 'ความคิด',
      semantic_tag: 'ความคิด',
      font_stack: ['TF PHETAI', 'TF Phetai'],
      bold: false,
    },
    jagged_moan: {
      ...baseTemplates.emphasis,
      id: 'jagged_moan',
      name: 'คำครางตะโกน (แฉกแหลม)',
      semantic_tag: 'คำครางตะโกน',
      font_stack: ['Layiji JaRaKeFadHang v1.0 Regular', 'Layiji JaRaKeFadHang v1.0'],
      bold: false,
    },
    moan: {
      ...baseTemplates.whisper,
      id: 'moan',
      name: 'คำคราง',
      semantic_tag: 'คำคราง',
      font_stack: ['Fc muffin', 'FC Muffin'],
      bold: false,
    },
    floating: {
      ...baseTemplates.bubble,
      id: 'floating',
      name: 'คำลอยนอกกรอบ',
      semantic_tag: 'คำลอยนอกกรอบ',
      font_stack: ['itim', 'Itim'],
      bold: false,
    },
    system: {
      ...baseTemplates.narration,
      id: 'system',
      name: 'ระบบ',
      semantic_tag: 'ระบบ',
      font_stack: ['IrisUPC BOLD', 'IrisUPC'],
      bold: true,
    },
    sfx: {
      ...baseTemplates.sfx,
      id: 'sfx',
      name: 'เอฟเฟกต์เสียง',
      semantic_tag: 'เอฟเฟกต์เสียง',
      font_stack: ['iannnnn TIGER Black', 'iannnnn TIGER'],
      bold: true,
    },
    chat_header_other: {
      ...baseTemplates.title,
      id: 'chat_header_other',
      name: 'แชท / พาดหัวข่าว / ใบประกาศ / อื่นๆ',
      semantic_tag: 'แชท,พาดหัวข่าว,ใบประกาศ,อื่นๆ',
      font_stack: ['Baijam Bold', 'Baijam'],
      bold: true,
    },
  };

  return {
    id: 'client-pathompong',
    name: 'ลูกค้าปฐมพงศ์',
    description: 'ชุดฟอนต์เฉพาะทางสำหรับลูกค้าปฐมพงศ์ (TH Sarabun New, Layiji, FC Muffin, ฯลฯ)',
    default_font_family: 'TH Sarabun New',
    default_text_template_id: 'bubble',
    text_templates: templates,
    created_at: now,
    updated_at: now,
  };
};

/** Read the reusable client presets. A fresh installation receives safe standard presets including Pathompong Preset. */
export const loadClientProjectProfiles = (stored: string | null): ClientProjectProfile[] => {
  const pathompong = createPathompongClientProfile();
  const defaultStd = createClientProjectProfile();

  if (!stored) return [defaultStd, pathompong];
  try {
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [defaultStd, pathompong];
    const profiles = parsed.map(normalizeProfile).filter((profile): profile is ClientProjectProfile => Boolean(profile));
    
    // Ensure Pathompong preset is always present in list if not added yet
    if (!profiles.some(p => p.id === pathompong.id || p.name === pathompong.name)) {
      profiles.push(pathompong);
    }
    return profiles.length ? profiles : [defaultStd, pathompong];
  } catch {
    return [defaultStd, pathompong];
  }
};

export const serializeClientProjectProfiles = (profiles: ClientProjectProfile[]) => (
  JSON.stringify(profiles.map(profile => ({ ...profile, text_templates: cloneTemplates(profile.text_templates) })))
);

/** Each document receives its own immutable starting snapshot of the chosen client preset. */
export const clientProfileToProjectSettings = (profile: ClientProjectProfile): Record<string, unknown> => ({
  client_profile_id: profile.id,
  client_profile_name: profile.name,
  client_profile_version: profile.updated_at,
  default_font_family: profile.default_font_family,
  default_text_template_id: profile.default_text_template_id,
  text_templates: cloneTemplates(profile.text_templates),
});

export const setProfileTemplateFont = (
  profile: ClientProjectProfile,
  templateId: string,
  fontFamily: string,
): ClientProjectProfile => {
  const templates = cloneTemplates(profile.text_templates);
  const key = templates[templateId]
    ? templateId
    : Object.keys(templates).find(keyName => templates[keyName].id === templateId);
  if (!key || !fontFamily.trim()) return profile;
  templates[key] = { ...templates[key], font_stack: [fontFamily.trim()] };
  return {
    ...profile,
    default_font_family: profile.default_text_template_id === templates[key].id
      ? fontFamily.trim()
      : profile.default_font_family,
    text_templates: templates,
    updated_at: new Date().toISOString(),
  };
};

/** Export a single Client Profile to JSON file download */
export const exportSingleClientProfileToJson = (profile: ClientProjectProfile, filename?: string) => {
  const safeName = profile.name.replace(/[/\\?%*:|"<>]/g, '_').trim() || 'client_profile';
  const outName = filename || `houmi_profile_${safeName}_${Date.now()}.json`;
  const jsonString = JSON.stringify({ ...profile, text_templates: cloneTemplates(profile.text_templates) }, null, 2);
  const blob = new Blob([jsonString], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = outName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

/** Export Client Font Templates / Profiles to JSON file download */
export const exportClientProfilesToJson = (profiles: ClientProjectProfile[], filename = 'houmi_all_client_profiles.json') => {
  const jsonString = serializeClientProjectProfiles(profiles);
  const blob = new Blob([jsonString], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

/** Import Client Font Templates / Profiles from JSON string and merge with existing list */
export const importClientProfilesFromJson = (jsonString: string, currentProfiles: ClientProjectProfile[]): { profiles: ClientProjectProfile[]; importedCount: number } => {
  try {
    const parsed: unknown = JSON.parse(jsonString);
    const rawArray = Array.isArray(parsed) ? parsed : [parsed];
    const importedProfiles = rawArray.map(normalizeProfile).filter((profile): profile is ClientProjectProfile => Boolean(profile));
    
    if (!importedProfiles.length) {
      throw new Error('ไม่พบข้อมูล Font Template ที่ถูกต้องในไฟล์ JSON');
    }

    const existingMap = new Map(currentProfiles.map(p => [p.id, p]));
    let count = 0;

    for (const imp of importedProfiles) {
      // If ID conflict or same name, generate fresh ID for unique import
      if (existingMap.has(imp.id)) {
        imp.id = createId();
      }
      existingMap.set(imp.id, imp);
      count++;
    }

    const merged = Array.from(existingMap.values());
    return { profiles: merged, importedCount: count };
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'ไฟล์ JSON ไม่ถูกต้อง';
    throw new Error(`นำเข้า Font Template ไม่สำเร็จ: ${msg}`);
  }
};

