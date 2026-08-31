import { describe, expect, it } from 'vitest';
import {
  clientProfileToProjectSettings,
  createClientProjectProfile,
  loadClientProjectProfiles,
  serializeClientProjectProfiles,
  setProfileTemplateFont,
} from '../utils/clientProfiles';

describe('client project presets', () => {
  it('provides safe standard presets on a fresh installation', () => {
    const profiles = loadClientProjectProfiles(null);

    expect(profiles.length).toBeGreaterThanOrEqual(1);
    expect(profiles[0].name).toBe('มาตรฐาน');
    expect(profiles[0].text_templates.bubble.font_stack).toHaveLength(1);
  });

  it('keeps template changes in the profile snapshot sent to a new project', () => {
    const base = createClientProjectProfile('ลูกค้า A');
    const profile = setProfileTemplateFont(base, 'bubble', 'TH SarabunPSK');
    const settings = clientProfileToProjectSettings(profile);

    expect(settings.client_profile_name).toBe('ลูกค้า A');
    expect((settings.text_templates as typeof profile.text_templates).bubble.font_stack[0]).toBe('TH SarabunPSK');

    (settings.text_templates as typeof profile.text_templates).bubble.font_stack[0] = 'Changed only in project';
    expect(profile.text_templates.bubble.font_stack[0]).toBe('TH SarabunPSK');
  });

  it('round-trips valid profiles and replaces corrupted storage with the standard preset', () => {
    const created = createClientProjectProfile('ฝ่าย B');
    const restored = loadClientProjectProfiles(serializeClientProjectProfiles([created]));

    expect(restored[0].name).toBe('ฝ่าย B');
    expect(loadClientProjectProfiles('{not json}')[0].name).toBe('มาตรฐาน');
  });
});
