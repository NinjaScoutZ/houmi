import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
  define: {
    __HOUMI_VERSION__: JSON.stringify('1.0.1'),
    __HOUMI_RELEASE_CHANNEL__: JSON.stringify('stable'),
    __HOUMI_UPDATES_ENABLED__: JSON.stringify(false),
  },
});
