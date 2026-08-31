import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const packageJsonPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'package.json')
const packageMetadata = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8')) as { version: string }
const releaseChannel = process.env.HOUMI_RELEASE_CHANNEL || 'stable'
const updatesEnabled = process.env.HOUMI_UPDATES_ENABLED === '1'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  define: {
    __HOUMI_VERSION__: JSON.stringify(packageMetadata.version),
    __HOUMI_RELEASE_CHANNEL__: JSON.stringify(releaseChannel),
    __HOUMI_UPDATES_ENABLED__: JSON.stringify(updatesEnabled),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/index.[ext]',
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: '127.0.0.1',
    watch: {
      ignored: ['**/src-tauri/**', '**/target/**', '**/backend/**'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:4000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:4000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:4000',
        ws: true,
      },
    },
  },
})
