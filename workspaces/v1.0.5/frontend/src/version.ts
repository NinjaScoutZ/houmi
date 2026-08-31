/**
 * Build metadata exposed in both browser and Tauri runtimes.
 * The value is injected from frontend/package.json by Vite so the UI has a
 * single version source instead of carrying a second hand-edited constant.
 */
export const HOUMI_VERSION = __HOUMI_VERSION__;
export const HOUMI_RELEASE_CHANNEL = __HOUMI_RELEASE_CHANNEL__;
export const HOUMI_VERSION_LABEL = `v${HOUMI_VERSION}`;
